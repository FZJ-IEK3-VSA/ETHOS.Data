"""Access classes, and where a dataset's bytes actually come from.

Three classes, declared per dataset in the catalogue:

    public      on dCache with o+rx -- anyone downloads it
    internal    held by ICE-2, not published (yet) -- VO credentials or a local root
    restricted  licensed; may never be copied -- resolved in place, never downloaded

The class picks the root; the filesystem picks the mode. A dataset's entry in
the public cache is read **in place** when it is a symbolic link, and is an
ordinary download target when it is a real directory. That one rule replaces a
per-dataset configuration table, which matters because this cache is shared by
a whole institute: the information is already on disk, so nobody has to write it
down, and re-pointing a link migrates every user at once.

Resolution order for one dataset:

  1. ``dataset_roots`` -- the per-dataset escape hatch, for a private copy
  2. the staging root -- work in progress, shadowing the catalogue during
     development.  Never applies to restricted data.
  3. the restricted root, for restricted datasets: always in place, never
     downloaded, never written to
  4. the public root, for everything else: in place if the entry is a symbolic
     link, downloaded otherwise

The rule that matters, unchanged: restricted data is never written into a shared
cache and never silently downloaded. If there is nowhere to read it from, asking
for it fails with an explanation instead of doing something surprising.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from .catalog import Catalog, Dataset, Resource
from .config import Roots, resolve_skip_unavailable

__all__ = [
    "AccessError",
    "cache_entries",
    "Location",
    "locate",
    "requires_local_root",
    "unavailable",
    "ORIGIN_CONFIGURED",
    "ORIGIN_STAGING",
    "ORIGIN_RESTRICTED",
    "ORIGIN_LINK",
    "ORIGIN_DOWNLOAD",
    "UNAVAILABLE",
]

PUBLIC = "public"
INTERNAL = "internal"
RESTRICTED = "restricted"
#: Synthesised for a dataset that exists only in the staging root. Never
#: appears in a real catalogue, so it can never be uploaded or published.
STAGING = "staging"

#: Why a location resolved the way it did -- carried so that error messages and
#: ``ethos-data verify`` can say something more useful than "not found".
ORIGIN_CONFIGURED = "configured root"
ORIGIN_STAGING = "staging"
ORIGIN_RESTRICTED = "restricted cache"
ORIGIN_LINK = "namespace link"
ORIGIN_DOWNLOAD = "download"


class AccessError(RuntimeError):
    """Raised when a dataset cannot be reached under the current configuration."""


#: This machine cannot reach these bytes at all, and saying so is the whole
#: answer -- there is no path to report, because there is no copy to point at.
UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Location:
    """Where one resource lives on this machine, and how it got there."""

    resource: Resource
    #: None exactly when ``mode`` is "unavailable": there is nowhere to look.
    path: Path | None
    #: "download" -- fetch into the shared cache; "in-place" -- already on disk,
    #: never copied; "unavailable" -- not reachable from this machine at all
    mode: str
    #: Which of the resolution rules produced this, for diagnostics.
    origin: str = ""

    @property
    def in_place(self) -> bool:
        return self.mode == "in-place"

    @property
    def available(self) -> bool:
        return self.mode != UNAVAILABLE


def access_class(dataset: Dataset) -> str:
    # From the catalogue index, not the descriptor: deciding *where* a dataset
    # comes from must never be the thing that pulls its file inventory in.
    return dataset.access


def requires_local_root(dataset: Dataset) -> bool:
    """Restricted data can only ever be used from a configured local root."""
    return access_class(dataset) == RESTRICTED


def _staged(roots: Roots, name: str) -> Path | None:
    """This dataset's staging entry, if there is one.

    A *dangling* staging link counts as staged. Falling back to the catalogue
    when somebody's work-in-progress link is broken would silently swap the data
    under a job that asked for the new version; being told the link is broken is
    the more useful outcome.
    """
    if roots.staging is None:
        return None
    entry = roots.staging / name
    if entry.exists() or entry.is_symlink():
        return entry
    return None


def _restricted_location(
    roots: Roots, dataset: Dataset, resource: Resource, skip_unavailable: bool
) -> Location:
    """Where a restricted resource is read from, or why it cannot be.

    Having no restricted cache is a legitimate, permanent state -- most people,
    most of the time, are not on the institute cluster and have no right to the
    licensed bytes. That is not a misconfiguration to be corrected, so it is
    offered as a choice rather than reported as an error only.
    """
    if roots.restricted is not None:
        return Location(resource, roots.restricted / dataset.name / resource.path,
                        "in-place", ORIGIN_RESTRICTED)

    if skip_unavailable:
        return Location(resource, None, UNAVAILABLE, ORIGIN_RESTRICTED)

    note = dataset.descriptor.get("ethos:restriction", "")
    lines = [f"dataset {dataset.name!r} is restricted and is never downloaded."]
    if note:
        lines.append(f"  {note}")
    lines.append("No restricted cache is configured on this machine.")
    lines.append("")
    lines.append("If you have a copy, say where it is:")
    lines.append("    ethos-data config set-restricted-cache /path/to/ethos_data_restricted")
    lines.append(f"    ethos-data config set-root {dataset.name} /path/to/{dataset.name}"
                 "    # just this one")
    lines.append("")
    lines.append("If you do not, carry on without it:")
    lines.append("    ethos-data ... --skip-unavailable")
    lines.append("    ethos-data config set-skip-unavailable true    # once, for this machine")
    lines.append("Datasets you cannot reach are then left out of the result and listed, "
                 "rather than silently missing.")
    raise AccessError("\n".join(lines))


def locate(
    catalog: Catalog,
    resources: list[Resource],
    roots: "Roots | str | Path | None" = None,
    dataset_roots: dict[str, str | Path] | None = None,
    skip_unavailable: bool | None = None,
) -> list[Location]:
    """Work out where every resource should be read from.

    ``roots`` accepts a :class:`~ethos_data.config.Roots`, or a bare path meaning
    the public cache -- which is what a lone cache directory always meant.

    ``skip_unavailable`` decides what happens to licensed data this machine has
    no access to: ``False`` raises, ``True`` marks it "unavailable" and carries
    on with everything else. ``None`` takes the configured answer, which
    defaults to raising.

    Raises AccessError -- naming the dataset and what to configure -- rather than
    falling back to the cache or to a download when neither is permitted.
    """
    roots = Roots.coerce(roots)
    if skip_unavailable is None:
        skip_unavailable = resolve_skip_unavailable()[0]
    configured = {name: Path(path).expanduser() for name, path in (dataset_roots or {}).items()}
    located: list[Location] = []
    warned: set[str] = set()

    for resource in resources:
        dataset = catalog.dataset(resource.dataset)
        access = access_class(dataset)

        # 1. The per-dataset escape hatch wins over everything, including
        #    staging: it is the most specific thing anybody can have said.
        root = configured.get(dataset.name)
        if root is not None:
            located.append(Location(resource, root / resource.path, "in-place", ORIGIN_CONFIGURED))
            continue

        # 2. Staging shadows the catalogue -- but never for restricted data,
        #    whose licence terms are not a development concern.
        if access != RESTRICTED:
            staged = _staged(roots, dataset.name)
            if staged is not None:
                if dataset.name not in warned:
                    warned.add(dataset.name)
                    warnings.warn(
                        f"dataset {dataset.name!r} is being read from the staging root "
                        f"({staged}), not from the catalogue. Staged data is not "
                        f"checksummed and is not reproducible -- do not publish results "
                        f"based on it.",
                        UserWarning,
                        stacklevel=3,
                    )
                located.append(Location(resource, staged / resource.path, "in-place", ORIGIN_STAGING))
                continue

        # 3. Restricted data lives in its own root and is only ever read.
        if access == RESTRICTED:
            located.append(_restricted_location(roots, dataset, resource, skip_unavailable))
            continue

        # 4. Everything else comes from the public cache. A symbolic link means
        #    the data is already on this machine and must not be written to.
        entry = roots.public / dataset.name
        if entry.is_symlink():
            located.append(Location(resource, entry / resource.path, "in-place", ORIGIN_LINK))
            continue

        if not catalog.publication_url:
            raise AccessError(
                f"dataset {dataset.name!r} is not in the public cache as a link, and the "
                f"catalogue declares no publication URL, so there is nowhere to fetch it "
                f"from.\n"
                f"Either set ethos:publication_url in catalog.yaml, or, while the data is "
                f"not yet uploaded, point at the copy on this machine:\n"
                f"    ln -s /path/to/{dataset.name} {entry}\n"
                f"or, for this one dataset only:\n"
                f"    ethos-data config set-root {dataset.name} /path/to/{dataset.name} "
                f"--scope environment"
            )

        located.append(Location(resource, entry / resource.path, "download", ORIGIN_DOWNLOAD))

    return located


def check_missing(locations: list[Location]) -> list[Location]:
    """In-place files that are not actually there.

    A misconfigured root, a dangling link, or a dataset that was never copied
    into the restricted cache are all common and confusing failures, so they are
    reported as a list of concrete missing paths rather than one generic error.
    """
    return [loc for loc in locations if loc.in_place and not loc.path.is_file()]


def unavailable(locations: list[Location]) -> list[Location]:
    """Resources this machine cannot reach at all, whatever it does."""
    return [loc for loc in locations if not loc.available]


def cache_entries(root: Path) -> list[tuple[str, Path]]:
    """Dataset entries in a cache root, at any depth, as ``(name, path)``.

    A nested dataset's entry sits where its name says: ``family/alpha`` is
    ``<root>/family/alpha``. So finding what a cache holds means walking down
    until an entry is reached, rather than listing the top level -- which would
    see ``family`` and never look inside it.

    An entry is a symbolic link (data read in place) or a directory holding
    files (data downloaded). Descent stops at either, so a link is never
    followed and a downloaded dataset's own subdirectories are not mistaken for
    more datasets.
    """
    found: list[tuple[str, Path]] = []
    if not root.is_dir():
        return found

    def walk(directory: Path, prefix: str) -> None:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            name = f"{prefix}/{child.name}" if prefix else child.name
            if child.is_symlink():
                found.append((name, child))
            elif child.is_dir():
                if any(item.is_file() for item in child.iterdir()):
                    found.append((name, child))
                else:
                    walk(child, name)

    walk(root, "")
    return found
