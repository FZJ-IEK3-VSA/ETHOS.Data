"""Access classes, and where a dataset's bytes actually come from.

Two classes, declared per dataset in the catalogue:

    public      published on dCache, world-readable -- anyone downloads it
    restricted  not published: licensed data, and data the institute holds
                without publishing it -- read in place from a restricted cache
                whose file permissions admit the reader, never downloaded

The class picks the root; the filesystem picks the mode. A dataset's entry in
the public cache is read **in place** when it is a symbolic link, and is an
ordinary download target when it is a real directory. That one rule replaces a
per-dataset configuration table, which matters because this cache is shared by
a whole institute: the information is already on disk, so nobody has to write it
down, and re-pointing a link migrates every user at once.

Where a file is read is decided by one chain of locators, built from the
settings snapshot of a handle or a command, each looking in one place, in this
order:

  1. the staging root -- work in progress, shadowing the catalogue during
     development.  Never applies to restricted data.
  2. the restricted caches, for restricted datasets: in place from the first
     listed cache whose entry is readable; never downloaded, never written to
  3. the public cache: in place where the dataset's entry, or its family's, is
     a link; otherwise a copy of the size the catalogue records
  4. a download from the publication root into the public cache, for public
     data only

Each locator answers *found* with a :class:`Location`, *pass* with None, or
*refuse* by raising :class:`AccessError`. A refusal ends the chain, which is what
keeps a restricted file without an installation from ever falling through to a
download. Building the chain touches nothing; locating touches only the file
system. Whether a file that has to be downloaded is downloaded is the caller's
choice, see ``fetch=`` in :mod:`ethos_data.retrieval`.

The rule that matters: restricted data is never written into the public cache
and never silently downloaded. If there is nowhere to read it from, asking
for it fails with an explanation instead of doing something surprising.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .catalogs import Catalog, Dataset
from .config import Roots
from .errors import AccessError
from .formats import keys as k
from .formats.derived import reader_description
from .model import names
from .model.resource import Resource

__all__ = [
    "Chain",
    "Locator",
    "cache_entries",
    "chain_for",
    "entry_for",
    "Location",
    "locate",
    "restricted_entry",
    "unavailable",
    "ORIGIN_STAGING",
    "ORIGIN_RESTRICTED",
    "ORIGIN_LINK",
    "ORIGIN_CACHED",
    "ORIGIN_DOWNLOAD",
    "UNAVAILABLE",
]

PUBLIC = k.PUBLIC
RESTRICTED = k.RESTRICTED
#: Synthesised for a dataset that exists only in the staging root. Never
#: appears in a real catalogue, so it can never be uploaded or published.
STAGING = "staging"

#: Why a location resolved the way it did -- carried so that error messages and
#: a package's ``verify`` command can say something more useful than "not found".
ORIGIN_STAGING = "staging"
ORIGIN_RESTRICTED = "restricted cache"
ORIGIN_LINK = "namespace link"
ORIGIN_CACHED = "public cache copy"
ORIGIN_DOWNLOAD = "download"


#: This machine cannot reach these bytes at all, and saying so is the whole
#: answer -- there is no path to report, because there is no copy to point at.
UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Location:
    """Where one resource lives on this machine, and how it got there."""

    resource: Resource
    #: None exactly when ``mode`` is "unavailable": there is nowhere to look.
    path: Path | None
    #: "download" -- fetch into the public cache; "in-place" -- already on disk,
    #: never copied; "unavailable" -- not reachable from this machine at all
    mode: str
    #: Which of the resolution rules produced this, for diagnostics.
    origin: str = ""
    #: Why this machine cannot reach the file, when ``mode`` is "unavailable".
    reason: str = ""

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


def entry_for(
    catalog: Catalog,
    roots: Roots,
    name: str,
    cache: str | Path | None = None,
    *,
    removing: bool = False,
) -> Path:
    """Where this dataset's cache entry belongs, whatever is or is not there.

    ``cache`` is the cache a command names with ``--root``. Without it, a public
    dataset's entry goes into the public cache, and a restricted dataset's into
    the only listed restricted cache. A restricted dataset's entry goes only
    into a listed restricted cache, and a public dataset's never into one, so
    the commands that *make* an entry cannot put one where retrieval would
    never read it, or where it would reach the wrong readers.

    ``removing`` lets ``unlink`` reach a public dataset's entry in a restricted
    cache, which ``verify`` reports for its maintainer to remove.

    Raises UnknownDataset for a name the catalogue does not describe, and
    AccessError when no cache may hold the entry, naming the listed caches or
    how to list one.
    """
    restricted = access_class(catalog.dataset(name)) == RESTRICTED
    if cache is not None:
        named = Path(cache).expanduser()
        listed = roots.restricted_cache(named)
        if restricted and listed is None:
            raise AccessError(
                f"dataset {name!r} is restricted, and {named} is not one of the "
                f"restricted caches this account lists ({_listing(roots)}). Its entry "
                "goes only into a listed restricted cache."
            )
        if not restricted and listed is not None and not removing:
            raise AccessError(
                f"dataset {name!r} is public, and {named} is a restricted cache. A "
                "public dataset's entry never goes into one."
            )
        return named / name
    if not restricted:
        return roots.public / name
    if not roots.restricted:
        raise AccessError(
            f"dataset {name!r} is restricted, and this account lists no restricted "
            "cache to hold its entry. List the one for its access combination:\n"
            "    ethos-data config add-restricted-cache DIR"
        )
    if len(roots.restricted) > 1:
        raise AccessError(
            f"dataset {name!r} is restricted, and this account lists several "
            f"restricted caches ({_listing(roots)}). Name the one for its access "
            "combination with the global --root, for example:\n"
            f"    ethos-data --root {roots.restricted[0]} link {name} DIR"
        )
    return roots.restricted[0] / name


def _listing(roots: Roots) -> str:
    return ", ".join(str(cache) for cache in roots.restricted) or "none"


def _staged(staging: Path | None, name: str) -> Path | None:
    """This dataset's staging entry, if there is one.

    A *dangling* staging link counts as staged. Falling back to the catalogue
    when somebody's work-in-progress link is broken would silently swap the data
    under a job that asked for the new version; being told the link is broken is
    the more useful outcome.
    """
    if staging is None:
        return None
    entry = staging / name
    if entry.exists() or entry.is_symlink():
        return entry
    return None


class Locator:
    """One place a file may be read from: a link in the lookup chain.

    :meth:`locate` answers *found* with a :class:`Location`, *pass* with None,
    or *refuse* by raising :class:`AccessError`, which ends the chain.
    """

    #: How :class:`Chain` names this place, for ``config show``.
    def describe(self) -> str:
        raise NotImplementedError

    def locate(
        self, catalog: Catalog, dataset: Dataset, resource: Resource
    ) -> Location | None:
        raise NotImplementedError

    def reset(self) -> None:
        """Forget what one :meth:`Chain.locate` call learnt; called before each."""


@dataclass
class Staging(Locator):
    """1. The staging root, shadowing the catalogue -- never for restricted data."""

    root: Path | None
    _warned: set[str] = field(default_factory=set, repr=False)

    def describe(self) -> str:
        return f"staging root {self.root}" if self.root else "staging root (not set)"

    def reset(self) -> None:
        self._warned.clear()

    def locate(self, catalog, dataset, resource):
        # Licence terms are not a development concern.
        if access_class(dataset) == RESTRICTED:
            return None
        staged = _staged(self.root, dataset.name)
        if staged is None:
            return None
        if dataset.name not in self._warned:
            self._warned.add(dataset.name)
            warnings.warn(
                f"dataset {dataset.name!r} is being read from the staging root "
                f"({staged}), not from the catalogue. Staged data is not "
                f"checksummed and is not reproducible -- do not publish results "
                f"based on it.",
                UserWarning,
                stacklevel=5,
            )
        return Location(resource, staged / resource.path, "in-place", ORIGIN_STAGING)


def restricted_entry(
    caches: tuple[Path, ...], name: str
) -> tuple[Path | None, list[str]]:
    """The first readable entry of ``name`` in ``caches``, and what was wrong before it.

    A cache that holds no entry for the dataset is no reason: most caches hold
    most datasets not. A reason names the cache: a listed cache that cannot be
    reached, or an entry that is dangling or cannot be read. With no cache
    listed, that is the reason, worded as the normal state it is.
    """
    if not caches:
        return None, ["This account lists no restricted cache."]
    reasons: list[str] = []
    for cache in caches:
        try:
            reachable = cache.is_dir()
        except OSError:
            reachable = False
        if not reachable:
            reasons.append(f"The restricted cache {cache} cannot be reached.")
            continue
        link = linked_entry(cache, name)
        if link is not None and not link.exists():
            reasons.append(
                f"The entry in {cache} is dangling: {link} points at {link.readlink()}."
            )
            continue
        entry = cache / name
        if not entry.exists():
            continue
        if not os.access(entry, os.R_OK | os.X_OK):
            reasons.append(f"The entry in {cache} cannot be read.")
            continue
        return entry, reasons
    return None, reasons


@dataclass
class RestrictedCache(Locator):
    """2. Restricted data: read in place from a listed restricted cache, or refused.

    The first listed cache whose entry is readable wins. Never passes. Listing
    no restricted cache is a legitimate, permanent state -- an account that
    reads public data only lists none, on the cluster too. Without a readable
    entry the file is refused before anything is downloaded, with the
    dataset's description and how to register a copy: a workflow cannot run
    without one of its inputs. With ``describe_only`` it is reported as not
    available here instead, for commands that only say what a fetch would do.
    """

    caches: tuple[Path, ...]
    describe_only: bool = False
    _entries: dict[str, tuple[Path | None, list[str]]] = field(
        default_factory=dict, repr=False
    )

    def describe(self) -> str:
        if not self.caches:
            return "restricted caches: none listed"
        listed = ", ".join(str(cache) for cache in self.caches)
        return f"restricted caches {listed}, in order, for restricted data only"

    def reset(self) -> None:
        self._entries.clear()

    def locate(self, catalog, dataset, resource):
        if access_class(dataset) != RESTRICTED:
            return None
        # Once per dataset, not per file.
        if dataset.name not in self._entries:
            self._entries[dataset.name] = restricted_entry(self.caches, dataset.name)
        entry, reasons = self._entries[dataset.name]
        if entry is not None:
            return Location(
                resource, entry / resource.path, "in-place", ORIGIN_RESTRICTED
            )
        why = "; ".join(reasons) or "no listed restricted cache has an entry for it"
        if self.describe_only:
            return Location(resource, None, UNAVAILABLE, ORIGIN_RESTRICTED, why)
        raise AccessError(restricted_refusal(dataset, why))


def restricted_refusal(dataset: Dataset, why: str) -> str:
    """The refusal for a restricted dataset this machine cannot read.

    What the person who meets it needs: what the dataset is and how to obtain
    it, from its catalogue entry, and the two commands that register a copy
    once they have one.
    """
    lines = [
        (
            f"dataset {dataset.name!r} is restricted, and this machine cannot read "
            f"it: {why}."
        ),
        "",
    ]
    lines.extend(f"  {line}" for line in reader_description(dataset.descriptor))
    lines.extend(
        [
            "",
            (
                "Every input a workflow names is required. If you have a copy you "
                "may use, register it:"
            ),
            "    ethos-data config add-restricted-cache DIR",
            f"    ethos-data link {dataset.name} DIR",
        ]
    )
    return "\n".join(lines)


def linked_entry(root: Path, name: str) -> Path | None:
    """The link in ``root`` this dataset is read through: its own, or its family's.

    A family linked as a whole holds its members inside the link target, so a
    member with no link of its own is still data this machine borrows, and must
    never be written into.
    """
    for candidate in (
        *(root / family for family in names.ancestors(name)),
        root / name,
    ):
        if candidate.is_symlink():
            return candidate
    return None


@dataclass
class PublicCache(Locator):
    """3. The public cache: data already on this machine, or a copy it holds.

    In place where the dataset's entry, or a family entry above it, is a link.
    Otherwise a file of the size the catalogue records, which is still a
    download location: fetching it checks the hash, and replaces the copy if
    it differs.
    """

    root: Path
    _linked: dict[str, bool] = field(default_factory=dict, repr=False)

    def describe(self) -> str:
        return (
            f"public cache {self.root}: in place where an entry is a link, "
            "else a copy of the recorded size"
        )

    def reset(self) -> None:
        self._linked.clear()

    def locate(self, catalog, dataset, resource):
        # Once per dataset, not per file: 170,000 files behind one link cost
        # one look at the link.
        linked = self._linked.get(dataset.name)
        if linked is None:
            linked = self._linked[dataset.name] = (
                linked_entry(self.root, dataset.name) is not None
            )
        target = self.root / dataset.name / resource.path
        if linked:
            return Location(resource, target, "in-place", ORIGIN_LINK)
        try:
            present = target.stat().st_size == resource.bytes
        except OSError:
            present = False
        if not present:
            return None
        return Location(resource, target, "download", ORIGIN_CACHED)


@dataclass
class Download(Locator):
    """4. A download from the publication root into the public cache.

    For public data only: restricted data never gets here, because its locator
    never passes. Refuses rather than passes, since nothing comes after it.
    """

    root: Path

    def describe(self) -> str:
        return f"a download into {self.root}, for public data only"

    def locate(self, catalog, dataset, resource):
        if not catalog.publication_url:
            raise AccessError(
                f"dataset {dataset.name!r} is not in the public cache as a link, and the "
                f"catalogue declares no publication URL, so there is nowhere to fetch it "
                f"from.\n"
                f"Either set ethos:publication_url in catalog.yaml, or, while the data is "
                f"not yet uploaded, point at the copy on this machine:\n"
                f"    ethos-data link {dataset.name} /path/to/{dataset.name}"
            )
        target = self.root / dataset.name / resource.path
        return Location(resource, target, "download", ORIGIN_DOWNLOAD)


@dataclass
class Chain:
    """The locators, in order: the first that finds a file decides where it is read."""

    locators: tuple[Locator, ...]

    def locate(self, catalog: Catalog, resources: Iterable[Resource]) -> list[Location]:
        """Where every resource is read from, in the order given.

        Raises the first refusal, naming the dataset and what to configure,
        rather than falling through to a place that is not permitted.
        """
        for locator in self.locators:
            locator.reset()
        located = []
        for resource in resources:
            dataset = catalog.dataset(resource.dataset)
            for locator in self.locators:
                found = locator.locate(catalog, dataset, resource)
                if found is not None:
                    located.append(found)
                    break
            else:  # pragma: no cover - Download never passes
                raise AccessError(f"no locator can place {resource.key}")
        return located

    def __str__(self) -> str:
        return "\n".join(
            f"  {number}. {locator.describe()}"
            for number, locator in enumerate(self.locators, start=1)
        )


def chain_for(roots: Roots, *, describe: bool = False) -> Chain:
    """The lookup chain, built from ``roots``; building it touches nothing.

    ``describe`` builds the chain for a command that only says what a fetch
    would do: restricted data this machine cannot read is reported as not
    available here instead of refused. Bundles are not in the chain: they are
    read through :func:`ethos_data.load_bundle`.
    """
    return Chain(
        (
            Staging(roots.staging),
            RestrictedCache(roots.restricted, describe),
            PublicCache(roots.public),
            Download(roots.public),
        )
    )


def locate(
    catalog: Catalog,
    resources: list[Resource],
    roots: Roots | None = None,
    *,
    describe: bool = False,
) -> list[Location]:
    """Work out where every resource should be read from.

    ``roots`` are the cache roots to read; without them, those of the
    catalogue's settings snapshot.

    Every input is required: licensed data this machine cannot read raises
    AccessError, describing the dataset and how to register a copy, before
    anything is downloaded. ``describe=True`` reports it as "unavailable"
    instead, for commands that only say what a fetch would do. The chain it
    runs is :func:`chain_for`.
    """
    roots = roots if roots is not None else catalog.settings.roots
    return chain_for(roots, describe=describe).locate(catalog, resources)


def check_missing(locations: list[Location]) -> list[Location]:
    """In-place files that are not actually there.

    A misconfigured root, a dangling link, or a dataset that was never copied
    into a restricted cache are all common and confusing failures, so they are
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
