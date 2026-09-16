"""Downloading catalogue resources into the shared, hash-verified cache.

(Module named ``retrieval`` rather than ``fetch`` so it can never shadow the
public ``ethos_data.fetch`` function -- the same reason ``selection`` is not
called ``collections``. At runtime the function won anyway, because ``def
fetch`` in ``__init__`` runs after the ``from .fetch import ...`` line, but
static tooling saw only the module: griffe could not document the package's
main entry point, and editors and type checkers offered the module's members
for ``ethos_data.fetch``. ``download`` and ``plan`` are exported from here under
their own names for the same reason -- do not rename this module to either.)

The cache layout is the whole trick behind cross-tool deduplication:

    <public cache>/<dataset>/<resource path>

Every tool derives that path from the same catalogue, so two tools asking for
the same file land on the same file. There is nothing to synchronise: the second
tool simply finds the file already there.

A dataset's entry in that root may be a **symbolic link** to data that is
already on this machine, in which case nothing is downloaded and nothing is
copied -- see :mod:`ethos_data.access` for the resolution rules. Downloads only
ever create real directories, and never write through a link.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pooch

from .access import (
    AccessError,
    Location,
    check_missing,
    locate,
    unavailable,
)
from .catalogs import Catalog, Resource
from .config import ENV_VAR, Roots, dataset_roots, resolve_public_cache

__all__ = [
    "AccessError",
    "DataFiles",
    "ENV_VAR",
    "NamedPaths",
    "cache_dir",
    "download",
    "local_path",
    "plan",
]


class NamedPaths(dict):
    """A collection's ``paths``, resolved: ``{handle: absolute Path}``.

    An ordinary dict whose missing-key error lists the handles the collection
    does define. The handles are the maintainer's vocabulary for a workflow's
    inputs -- ``era5``, ``gwa_100m`` -- and a typo in one should say so, not
    fail three frames later inside a raster reader.
    """

    def __init__(self, *args, collection: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.collection = collection
        #: Handles the collection defines but this machine cannot reach, left
        #: out under ``skip_unavailable``. Kept so a missing-key error can say
        #: "unavailable here" rather than "never defined".
        self.omitted: list[str] = []

    def __missing__(self, handle):
        offered = ", ".join(sorted(self)) or "none"
        where = f" in collection {self.collection!r}" if self.collection else ""
        if handle in self.omitted:
            raise KeyError(
                f"named path {handle!r}{where} is not available on this machine "
                f"(left out under skip_unavailable); available: {offered}"
            )
        raise KeyError(f"no named path {handle!r}{where}; it defines: {offered}")


class DataFiles(dict):
    """The files a collection resolved to: ``{"<dataset>/<path>": Path}``.

    Behaves as an ordinary dict, with two conveniences for the common cases --
    handing the whole set to a workflow, and pulling out one known file -- and,
    for a collection that declares ``paths``, the handles it named as
    :attr:`named`.
    """

    def __init__(self, *args, named: NamedPaths | dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        #: ``{handle: Path}`` for the collection's ``paths`` -- what
        #: :func:`ethos_data.paths` returns. Empty for a collection that
        #: declares none, and for the plain ``download()`` of a resource list.
        self.named: NamedPaths = (
            named if isinstance(named, NamedPaths) else NamedPaths(named or {})
        )

    @property
    def paths(self) -> list[Path]:
        """Every file, in catalogue order."""
        return list(self.values())

    @property
    def directories(self) -> list[Path]:
        """The distinct directories the files live in, for path-based readers."""
        seen: dict[Path, None] = {}
        for path in self.values():
            seen.setdefault(path.parent, None)
        return list(seen)

    def one(self, suffix: str) -> Path:
        """The single file whose key ends with ``suffix``.

        Raises if it is ambiguous or absent, so a typo fails loudly instead of
        silently handing back the wrong raster.
        """
        matches = [key for key in self if key.endswith(suffix)]
        if not matches:
            raise KeyError(f"no file ending in {suffix!r}; have: {', '.join(sorted(self))}")
        if len(matches) > 1:
            raise KeyError(f"{suffix!r} is ambiguous, matches: {', '.join(sorted(matches))}")
        return self[matches[0]]


def cache_dir(explicit: str | Path | None = None) -> Path:
    """Root of the shared public cache.

    Resolved from an explicit argument, then $ETHOS_DATA_DIR, then the user /
    environment / site config files, then the per-user OS cache directory.
    See :mod:`ethos_data.config` for the full precedence and the reasoning.
    """
    return resolve_public_cache(explicit).value


def local_path(resource: Resource, root: Path | None = None) -> Path:
    return (root or cache_dir()) / resource.dataset / resource.path


def plan(
    catalog: Catalog,
    resources: list[Resource],
    roots: "Roots | str | Path | None" = None,
    skip_unavailable: bool | None = None,
) -> dict:
    """Report what a fetch would do, without touching the network."""
    roots = Roots.coerce(roots)
    locations = locate(catalog, resources, roots, dataset_roots(), skip_unavailable)

    present, missing, in_place = [], [], []
    by_origin: dict[str, list[Resource]] = {}
    for location in locations:
        if not location.available:
            continue
        if location.in_place:
            in_place.append(location)
            by_origin.setdefault(location.origin, []).append(location.resource)
            continue
        # Size is a cheap presence check; download() verifies the hash and
        # re-fetches anything that fails, so this is an estimate, not a promise.
        target = location.path
        if target.is_file() and target.stat().st_size == location.resource.bytes:
            present.append(location)
        else:
            missing.append(location)

    return {
        "root": roots.public,
        "roots": roots,
        "locations": locations,
        "present": [l.resource for l in present],
        "missing": [l.resource for l in missing],
        "in_place": [l.resource for l in in_place],
        "in_place_by_origin": by_origin,
        "unreadable": check_missing(locations),
        "unavailable": [l.resource for l in unavailable(locations)],
        "bytes_total": sum(r.bytes for r in resources),
        "bytes_to_download": sum(l.resource.bytes for l in missing),
    }


def download(
    catalog: Catalog,
    resources: list[Resource],
    root: "Roots | str | Path | None" = None,
    progressbar: bool = True,
    skip_unavailable: bool | None = None,
) -> DataFiles:
    """Make every resource available locally and return where each one is.

    Resources resolved in place -- a link in the public cache, the restricted
    cache, a staging entry, or a configured root -- are used where they lie and
    never copied; the rest are downloaded into the public cache, skipping
    anything already present and hash-verified.
    """
    roots = Roots.coerce(root)
    _warn_about_licensing(catalog, resources)

    locations = locate(catalog, resources, roots, dataset_roots(), skip_unavailable)

    absent = unavailable(locations)
    if absent:
        names = sorted({loc.resource.dataset for loc in absent})
        warnings.warn(
            f"{len(absent)} file(s) from {', '.join(names)} are not available on this "
            f"machine and have been left out of the result. The returned mapping has no "
            f"entry for them -- check for the keys you need rather than assuming they "
            f"are there.",
            UserWarning,
            stacklevel=3,
        )

    unreadable = check_missing(locations)
    if unreadable:
        listing = "\n".join(f"    {loc.path}   [{loc.origin}]" for loc in unreadable[:8])
        more = "" if len(unreadable) <= 8 else f"\n    ... and {len(unreadable) - 8} more"
        raise AccessError(
            f"{len(unreadable)} file(s) are missing from where they were expected:\n"
            f"{listing}{more}\n"
            "Run `ethos-data verify` for a per-file account, or check the roots with "
            "`ethos-data config show`."
        )

    files = DataFiles()
    to_download: dict[str, list[Location]] = {}
    for location in locations:
        if not location.available:
            continue
        if location.in_place:
            files[location.resource.key] = location.path
        else:
            to_download.setdefault(location.resource.dataset, []).append(location)

    for dataset_name, items in sorted(to_download.items()):
        dataset = catalog.dataset(dataset_name)
        destination = roots.public / dataset_name
        _refuse_to_write_through_a_link(destination)
        base_url = catalog.base_url_for(dataset)
        puller = pooch.create(
            path=destination,
            base_url=base_url,
            # Frictionless writes "sha256:..."; pooch reads the same "alg:hash"
            # convention, so the manifest value passes straight through.
            registry={loc.resource.path: loc.resource.hash for loc in items},
            retry_if_failed=3,
        )
        for location in items:
            fetched = puller.fetch(location.resource.path, progressbar=progressbar)
            files[location.resource.key] = Path(fetched)

    # Return in catalogue order, not download order. Unavailable resources are
    # simply absent -- a missing key is something a caller can notice, whereas a
    # path to a file that is not there is not.
    return DataFiles(
        (loc.resource.key, files[loc.resource.key])
        for loc in locations
        if loc.available
    )


def _refuse_to_write_through_a_link(destination: Path) -> None:
    """Never let a download land in somebody else's directory.

    ``locate`` already routes a symbolic-link entry to "in-place", so reaching
    here with one means a bug or a race -- a link created between planning and
    fetching. Either way the consequence would be writing into shared project
    storage that this cache only borrows, so it is worth a second check.
    """
    if destination.is_symlink():
        raise AccessError(
            f"{destination} is a symbolic link to {destination.resolve()}, so it is data "
            f"this machine already has and does not own. Refusing to download into it.\n"
            f"If the link is stale, remove it and fetch again; if you want a real, "
            f"independent copy in the cache, use `ethos-data materialize`."
        )


def _warn_about_licensing(catalog: Catalog, resources: list[Resource]) -> None:
    """Refuse to let unresolved licensing pass silently.

    An absent licence is a question, not a default. Datasets are published with
    ethos:license_status until somebody has actually read the upstream terms.
    """
    unresolved = sorted(
        {r.dataset for r in resources if catalog.dataset(r.dataset).license_status != "resolved"}
    )
    for name in unresolved:
        note = catalog.dataset(name).descriptor.get("ethos:license_note", "")
        warnings.warn(
            f"dataset {name!r} has unresolved licensing; redistribution terms "
            f"have not been confirmed. {note}".strip(),
            UserWarning,
            stacklevel=3,
        )
