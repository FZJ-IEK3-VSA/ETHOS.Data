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

import os
import shutil
import warnings
from pathlib import Path

from .access import (
    ORIGIN_CACHED,
    AccessError,
    Location,
    check_missing,
    linked_entry,
    locate,
    unavailable,
)
from .adapters import Downloader
from .adapters.downloads import PoochDownloader
from .catalogs import Catalog, Resource
from .config import ENV_VAR, Roots, resolve_public_cache
from .errors import NotFetched
from .formats import keys as k
from .model import digest, names

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

    def __missing__(self, handle):
        offered = ", ".join(sorted(self)) or "none"
        where = f" in collection {self.collection!r}" if self.collection else ""
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
            raise KeyError(
                f"no file ending in {suffix!r}; have: {', '.join(sorted(self))}"
            )
        if len(matches) > 1:
            raise KeyError(
                f"{suffix!r} is ambiguous, matches: {', '.join(sorted(matches))}"
            )
        return self[matches[0]]


def cache_dir(explicit: str | Path | None = None) -> Path:
    """Root of the shared public cache.

    Resolved from an explicit argument, then $ETHOS_DATA_DIR, then the settings
    file, then the per-user cache directory.
    See :mod:`ethos_data.config` for the full precedence and the reasoning.
    """
    return resolve_public_cache(explicit).value


def _seeded(
    public: Path, dataset, items: list[Location], files: DataFiles
) -> list[Location]:
    """The files still to download once those an earlier revision holds are copied.

    A later revision keeps most files of the one before, and its cache entry
    is a directory of its own, so a file unchanged since an earlier revision
    is taken from that revision's entry, hard-linked where the filesystem
    allows and copied where not, rather than downloaded again. Only a file of
    the recorded size and hash is taken.
    """
    if dataset.revision <= 1:
        return items
    earlier = [
        public / names.entry(dataset.name, revision)
        for revision in range(dataset.revision - 1, 0, -1)
    ]
    remaining = []
    for location in items:
        target, resource = location.path, location.resource
        source = next(
            (
                entry / resource.path
                for entry in earlier
                if _holds(entry / resource.path, resource)
            ),
            None,
        )
        if source is None or target.exists():
            remaining.append(location)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
        files[resource.key] = target
    return remaining


def _holds(path: Path, resource: Resource) -> bool:
    """Whether ``path`` is the file ``resource`` describes, by size and hash."""
    try:
        if path.is_symlink() or path.stat().st_size != resource.bytes:
            return False
    except OSError:
        return False
    return digest.matches(resource.hash, digest.of_file(path))


def local_path(resource: Resource, root: Path | None = None) -> Path:
    return (root or cache_dir()) / resource.dataset / resource.path


def plan(
    catalog: Catalog,
    resources: list[Resource],
    roots: "Roots | str | Path | None" = None,
) -> dict:
    """Report what a fetch would do, without touching the network.

    Licensed data this machine cannot read is listed under ``unavailable``,
    with the reason on each location, rather than refused: the report only
    describes. The fetch itself refuses it.
    """
    roots = Roots.coerce(roots)
    locations = locate(catalog, resources, roots, describe=True)

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
    *,
    fetch: bool = True,
    downloader: Downloader | None = None,
) -> DataFiles:
    """Make every resource available locally and return where each one is.

    Resources resolved in place -- a link in the public cache, the restricted
    cache, a staging entry, or a configured root -- are used where they lie and
    never copied; the rest are downloaded into the public cache, skipping
    anything already present and hash-verified. Every resource is required:
    licensed data this machine cannot read raises AccessError, describing the
    dataset, before anything is downloaded.

    With ``fetch=False`` nothing is downloaded and no store is contacted: a
    copy already in the public cache is returned as it is, and a file that
    would have to be downloaded raises :class:`~ethos_data.errors.NotFetched`,
    naming the path it belongs at.
    """
    roots = Roots.coerce(root)
    downloader = downloader if downloader is not None else PoochDownloader()
    _warn_about_licensing(catalog, resources)

    locations = locate(catalog, resources, roots)

    unreadable = check_missing(locations)
    if unreadable:
        listing = "\n".join(
            f"    {loc.path}   [{loc.origin}]" for loc in unreadable[:8]
        )
        more = (
            "" if len(unreadable) <= 8 else f"\n    ... and {len(unreadable) - 8} more"
        )
        raise AccessError(
            f"{len(unreadable)} file(s) are missing from where they were expected:\n"
            f"{listing}{more}\n"
            "Run your package's data command with `verify` for a per-file account, "
            "or check the roots with "
            "`ethos-data config show`."
        )

    files = DataFiles()
    to_download: dict[str, list[Location]] = {}
    for location in locations:
        if location.in_place or (not fetch and location.origin == ORIGIN_CACHED):
            files[location.resource.key] = location.path
        else:
            to_download.setdefault(location.resource.dataset, []).append(location)

    if not fetch and to_download:
        raise NotFetched(
            _not_fetched([loc for items in to_download.values() for loc in items])
        )

    for dataset_name, items in sorted(to_download.items()):
        dataset = catalog.dataset(dataset_name)
        destination = roots.public / dataset.entry_name
        _refuse_to_write_through_a_link(roots.public, dataset.entry_name)
        items = _seeded(roots.public, dataset, items, files)
        # Each file from the folder of the revision its bytes were published in.
        by_revision: dict[int, list[Location]] = {}
        for location in items:
            by_revision.setdefault(location.resource.revision, []).append(location)
        for revision, group in sorted(by_revision.items()):
            fetched = downloader.fetch(
                catalog.base_url_for(dataset, revision),
                destination,
                {loc.resource.path: loc.resource.hash for loc in group},
                progressbar=progressbar,
            )
            for location in group:
                files[location.resource.key] = fetched[location.resource.path]

    # In catalogue order, not download order.
    return DataFiles((loc.resource.key, files[loc.resource.key]) for loc in locations)


def _not_fetched(locations: list[Location]) -> str:
    """Which files ``fetch=False`` found missing, and where each belongs."""
    shown = locations[:8]
    width = max(len(loc.resource.key) for loc in shown)
    listing = "\n".join(
        f"    {loc.resource.key:<{width}}  belongs at {loc.path}" for loc in shown
    )
    more = "" if len(locations) <= 8 else f"\n    ... and {len(locations) - 8} more"
    return (
        f"{len(locations)} file(s) are not on this machine, and fetch=False "
        f"downloads nothing:\n{listing}{more}\n"
        "The same call with fetch=True downloads them to those paths."
    )


def _refuse_to_write_through_a_link(root: Path, name: str) -> None:
    """Never let a download land in somebody else's directory.

    ``locate`` already routes a linked entry, the dataset's own or its
    family's, to "in-place", so reaching here with one means a bug or a race --
    a link created between planning and fetching. Either way the consequence
    would be writing into shared project storage that this cache only borrows,
    so it is worth a second check.
    """
    destination = linked_entry(root, name)
    if destination is not None:
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
        {
            r.dataset
            for r in resources
            if catalog.dataset(r.dataset).license_status != "resolved"
        }
    )
    for name in unresolved:
        note = catalog.dataset(name).descriptor.get(k.LICENSE_NOTE, "")
        warnings.warn(
            f"dataset {name!r} has unresolved licensing; redistribution terms "
            f"have not been confirmed. {note}".strip(),
            UserWarning,
            stacklevel=3,
        )
