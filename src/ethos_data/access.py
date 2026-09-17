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

import os
import warnings
from dataclasses import dataclass
from pathlib import Path

from .catalogs import Catalog, Dataset, Resource
from .config import Roots, resolve_skip_unavailable

__all__ = [
    "AccessError",
    "borrowed_parent",
    "cache_entries",
    "entry_ancestry",
    "entry_for",
    "Location",
    "locate",
    "requires_local_root",
    "unavailable",
    "which_cache",
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
#: a package's ``verify`` command can say something more useful than "not found".
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


def entry_for(catalog: Catalog, roots: Roots, name: str) -> Path:
    """Where this dataset's cache entry belongs, whatever is or is not there.

    The access class picks the root, exactly as :func:`locate` does -- so the
    commands that *make* an entry cannot put one somewhere retrieval would never
    look for it. Raises UnknownDataset for a name the catalogue does not
    describe, and ValueError when a restricted dataset has no restricted cache:
    there is nowhere to put it, and the public cache is the one place it may
    never go.
    """
    root = roots.for_access(access_class(catalog.dataset(name)))
    if root is None:
        raise ValueError(
            f"dataset {name!r} is restricted and no restricted cache is configured; "
            "there is no entry for it. Set one with:\n"
            "    ethos-data config set-restricted-cache /path/to/ethos_data_restricted"
        )
    return root / name


def entry_ancestry(entry: Path, name: str) -> tuple[Path, list[Path]]:
    """The cache root this entry sits in, and the directories between them.

    No cache root is passed, deliberately. An entry is ``<root>/<name>`` and
    nothing else -- :func:`entry_for` has no other rule, and the namespace
    planner builds the same path -- so the number of parts in the name is the
    number of components below the root, and this cannot disagree with
    ``entry_for`` about where the root is. A root passed in could disagree, and
    then every caller below would be reasoning about a different directory from
    the one the entry was built from.

    Outermost first, because both callers work down from the root: one looks for
    the first borrowed component, and the other creates each component in turn
    and has to meet a link before it has written anything underneath it.

    The root itself is not in the list. Pointing a whole cache at a symbolic
    link is a configuration somebody made on purpose, not a borrowed tree.
    """
    above = list(entry.parents)
    depth = min(len(Path(name).parts) - 1, len(above) - 1)
    return above[depth], list(reversed(above[:depth]))


def borrowed_parent(entry: Path, name: str) -> Path | None:
    """The outermost component between the cache root and ``entry`` that is a link.

    ``Path.mkdir(parents=True, exist_ok=True)`` succeeds when a parent is
    already a symbolic link to a directory -- the ``FileExistsError`` is
    swallowed and ``is_dir()`` follows the link -- so an entry written below one
    lands *inside* the borrowed tree, silently, and is reported as made. That is
    the one thing a borrowed entry promises can never happen: a symbolic-link
    entry is routed to "in-place" by :func:`locate`, a download into one is
    refused, and the reason those reads are safe is that the cache never writes
    there either. The entry also disappears the day its owner removes that one
    link, having been printed as linked and counted in a summary.

    The shape that produces it is the reorganisation the namespace planner
    exists for: a dataset that was flat becomes a family, so ``family`` stops
    being an entry and becomes a prefix, while the machine still holds
    yesterday's ``<cache>/family -> /project/storage/family``.

    This reads the cache at one moment, so what it establishes is that nothing
    was borrowed *when it was asked* -- which is advice to a planner and not a
    guarantee to a writer. The guarantee belongs to whatever does the writing,
    which is why :func:`ethos_data.maintain.namespace._create` creates the
    components one at a time instead of trusting an answer from before the run.

    Only a *symbolic* link is found. A Windows junction (``mklink /J``) is
    reported as an ordinary directory here exactly as it is by
    :func:`cache_entries` and :func:`locate`, so the guarantee this supports is
    "no symbolic link above the entry", not "no borrowed tree at all".
    """
    _, parents = entry_ancestry(entry, name)
    return next((parent for parent in parents if parent.is_symlink()), None)


def _same_directory(left: Path, right: Path) -> bool:
    """Whether two paths name one directory on this machine, however spelled.

    The cheap comparison first, and the filesystem only when the two spellings
    actually differ. That is not only speed: these caches can sit on an SMB
    share, ``os.path.realpath`` has no timeout, and a command with no need to
    ask must not be able to hang on a dead mount.

    Every spelling that turns up in this codebase is equated by that pair --
    case, the two separators, a trailing separator, Windows' 8.3 short name, a
    symlinked spelling of the same directory, and a path that does not exist
    yet, which a configured-but-never-created restricted cache is.
    """
    if os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right)
    ):
        return True
    try:
        return os.path.normcase(os.path.realpath(left)) == os.path.normcase(
            os.path.realpath(right)
        )
    except OSError:
        return False


def which_cache(roots: Roots, path: Path) -> str | None:
    """Which of this machine's caches ``path`` is: restricted, public, or neither.

    The inverse of :meth:`ethos_data.config.Roots.for_access`, which routes a
    dataset to a root. The two answer one question from opposite ends and have
    to agree, because a command told it is building the public cache while
    pointed at the restricted one will delete entries on the strength of a
    policy that does not apply there.

    ``None`` is a legitimate and common answer rather than a failure: building a
    cache for another machine is the documented cluster workflow, and most
    machines have no restricted cache configured at all. What may be done to an
    unidentified directory is the caller's decision, and the only safe reading
    is that it may be anything -- including another machine's restricted cache.

    Restricted is tested first and wins. On a machine whose public and
    restricted caches are configured to the same directory, answering "public"
    is what would build a shared namespace on top of licensed bytes; answering
    "restricted" makes every caller that refuses the restricted cache refuse
    that configuration too, which is the alarm it deserves.

    Compared as directories rather than as text, because the spellings genuinely
    differ: ``resolve_catalog_root`` returns a resolved path while ``--root`` is
    only expanded, which on Windows is the difference between the 8.3 short name
    of a user directory and its long one, for one directory. Deliberately not
    the comparison :func:`ethos_data.maintain.namespace._same_target` makes:
    that one asks whether a link still spells the curated ``source_dir``, where
    resolving would call two different curated paths the same thing. This one
    asks whether two paths are the same directory, where resolving is the whole
    question.
    """
    for kind, root in ((RESTRICTED, roots.restricted), (PUBLIC, roots.public)):
        if root is not None and _same_directory(root, path):
            return kind
    return None


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
        return Location(
            resource,
            roots.restricted / dataset.name / resource.path,
            "in-place",
            ORIGIN_RESTRICTED,
        )

    if skip_unavailable:
        return Location(resource, None, UNAVAILABLE, ORIGIN_RESTRICTED)

    note = dataset.descriptor.get("ethos:restriction", "")
    lines = [f"dataset {dataset.name!r} is restricted and is never downloaded."]
    if note:
        lines.append(f"  {note}")
    lines.append("No restricted cache is configured on this machine.")
    lines.append("")
    lines.append("If you have a copy, say where it is:")
    lines.append(
        "    ethos-data config set-restricted-cache /path/to/ethos_data_restricted"
    )
    lines.append(
        f"    ethos-data config set-root {dataset.name} /path/to/{dataset.name}"
        "    # just this one"
    )
    lines.append("")
    lines.append("If you do not, carry on without it:")
    lines.append("    ethos-data ... --skip-unavailable")
    lines.append(
        "    ethos-data config set-skip-unavailable true    # once, for this machine"
    )
    lines.append(
        "Datasets you cannot reach are then left out of the result and listed, "
        "rather than silently missing."
    )
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
    configured = {
        name: Path(path).expanduser() for name, path in (dataset_roots or {}).items()
    }
    located: list[Location] = []
    warned: set[str] = set()

    for resource in resources:
        dataset = catalog.dataset(resource.dataset)
        access = access_class(dataset)

        # 1. The per-dataset escape hatch wins over everything, including
        #    staging: it is the most specific thing anybody can have said.
        root = configured.get(dataset.name)
        if root is not None:
            located.append(
                Location(resource, root / resource.path, "in-place", ORIGIN_CONFIGURED)
            )
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
                located.append(
                    Location(
                        resource, staged / resource.path, "in-place", ORIGIN_STAGING
                    )
                )
                continue

        # 3. Restricted data lives in its own root and is only ever read.
        if access == RESTRICTED:
            located.append(
                _restricted_location(roots, dataset, resource, skip_unavailable)
            )
            continue

        # 4. Everything else comes from the public cache. A symbolic link means
        #    the data is already on this machine and must not be written to.
        entry = roots.public / dataset.name
        if entry.is_symlink():
            located.append(
                Location(resource, entry / resource.path, "in-place", ORIGIN_LINK)
            )
            continue

        if not catalog.publication_url:
            raise AccessError(
                f"dataset {dataset.name!r} is not in the public cache as a link, and the "
                f"catalogue declares no publication URL, so there is nowhere to fetch it "
                f"from.\n"
                f"Either set ethos:publication_url in catalog.yaml, or, while the data is "
                f"not yet uploaded, point at the copy on this machine:\n"
                f"    ethos-data link {dataset.name} /path/to/{dataset.name}\n"
                f"or, for this one dataset only:\n"
                f"    ethos-data config set-root {dataset.name} /path/to/{dataset.name} "
                f"--scope environment"
            )

        located.append(
            Location(resource, entry / resource.path, "download", ORIGIN_DOWNLOAD)
        )

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

    A directory that cannot be listed is reported as an entry rather than
    descended into. Every caller of this either leaves an entry alone or offers
    to remove it, and "I could not look" and "there is nothing there" are the
    same answer only to a command that deletes on the strength of it. It is also
    what lets :func:`ethos_data.maintain.namespace.plan` promise that no state
    the cache is in makes it raise, which is what makes ``--dry-run`` safe to
    point at a cache in any condition.
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
                try:
                    holds_files = any(item.is_file() for item in child.iterdir())
                except OSError:
                    found.append((name, child))
                    continue
                if holds_files:
                    found.append((name, child))
                else:
                    walk(child, name)

    walk(root, "")
    return found
