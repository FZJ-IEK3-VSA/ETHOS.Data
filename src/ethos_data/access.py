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
  2. the bundles a package ships, for what they hold: in place, hash-checked
     once per process, never passed by
  3. the restricted caches, for restricted datasets: in place from the first
     listed cache whose entry is readable; never downloaded, never written to
  4. the public cache: in place where the dataset's entry, or its family's, is
     a link; otherwise a copy of the size the catalogue records
  5. a download from the publication root into the public cache, for public
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
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from . import report
from .catalogs import Catalog, Dataset
from .config import Roots
from .errors import AccessError, BundleError
from .formats import keys as k
from .model import names
from .model.resource import Resource

__all__ = [
    "Chain",
    "Locator",
    "cache_entries",
    "chain_for",
    "entry_for",
    "entry_states",
    "Location",
    "locate",
    "restricted_entry",
    "restricted_refusal",
    "restricted_states",
    "unavailable",
    "ORIGIN_STAGING",
    "ORIGIN_RESTRICTED",
    "ORIGIN_LINK",
    "ORIGIN_CACHED",
    "ORIGIN_DOWNLOAD",
    "ORIGIN_BUNDLE",
    "Reroute",
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
ORIGIN_BUNDLE = "bundle"
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
    dataset = catalog.dataset(name)
    restricted = access_class(dataset) == RESTRICTED
    entry = dataset.entry_name
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
        return named / entry
    if not restricted:
        return roots.public / entry
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
    return roots.restricted[0] / entry


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
            report.warning(
                f"dataset {dataset.name!r} is being read from the staging root "
                f"({staged}), not from the catalogue. Staged data is not "
                f"checksummed and is not reproducible -- do not publish results "
                f"based on it.",
                UserWarning,
                stacklevel=5,
            )
        return Location(resource, staged / resource.path, "in-place", ORIGIN_STAGING)


#: The state of one dataset's entry in one restricted cache.
READABLE = "readable"
NO_ENTRY = "no entry"
UNREACHABLE = "cannot be reached"
UNREADABLE = "entry cannot be read"


def _entry_state(cache: Path, name: str) -> str:
    """The state of ``name``'s entry in ``cache``: one of the states above, or dangling."""
    try:
        reachable = cache.is_dir()
    except OSError:
        reachable = False
    if not reachable:
        return UNREACHABLE
    link = linked_entry(cache, name)
    if link is not None and not link.exists():
        return f"entry dangling: {link} points at {link.readlink()}"
    entry = cache / name
    if not entry.exists():
        return NO_ENTRY
    if not os.access(entry, os.R_OK | os.X_OK):
        return UNREADABLE
    return READABLE


def _reason(cache: Path, state: str) -> str:
    """A state other than a missing copy, as the sentence a refusal prints."""
    if state == UNREACHABLE:
        return f"The restricted cache {cache} cannot be reached."
    if state == UNREADABLE:
        return f"The entry in {cache} cannot be read."
    return f"The entry in {cache} is dangling: {state.split(': ', 1)[1]}."


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
        state = _entry_state(cache, name)
        if state == READABLE:
            return cache / name, reasons
        if state != NO_ENTRY:
            reasons.append(_reason(cache, state))
    return None, reasons


def entry_states(caches: tuple[Path, ...], name: str) -> list[tuple[Path, str]]:
    """The state of ``name``'s entry in every listed restricted cache, in reading order."""
    return [(cache, _entry_state(cache, name)) for cache in caches]


def restricted_states(caches: tuple[Path, ...], name: str) -> str:
    """The state of ``name`` in every listed restricted cache, for what only describes."""
    if not caches:
        return "restricted; this account lists no restricted cache"
    states = "; ".join(
        f"{cache}: {state}" for cache, state in entry_states(caches, name)
    )
    return f"restricted; no listed restricted cache has a readable entry ({states})"


@dataclass(frozen=True)
class Reroute:
    """What a locator answers to send a file on through the chain as another resource.

    The bundle locator answers it under the download switch: a bundled file
    whose bytes the catalogue holds under the same key is read through the
    catalogue route, as the catalogue's dataset and resource.
    """

    dataset: Dataset
    resource: Resource


@dataclass
class Bundled(Locator):
    """2. The bundles a package ships: in place, hash-checked, never passed by.

    A bundled file that is missing, or changed without ``bundle update``
    recording it, is refused, never downloaded: a bundle is authoritative for
    its package. Under the download switch, a bundled file whose SHA-256 the
    catalogue holds for the same key goes on through the catalogue route; a
    bundle's own bytes never enter a cache. With ``describe_only`` a refusal
    is reported as not available here instead.
    """

    describe_only: bool = False

    def describe(self) -> str:
        return "bundles the package ships, hash-checked, for what they hold"

    def locate(self, catalog, dataset, resource):
        bundle = catalog.bundle_of(dataset.name) if catalog.bundles else None
        if bundle is None:
            return None
        from .bundles import checked_file, warn_once

        if catalog.routes is not None:
            routed = _routed(catalog.routes, resource)
            if routed is not None:
                return routed
        why = checked_file(bundle, resource)
        if not why:
            warn_once(bundle)
            return Location(
                resource, bundle.file(resource.key), "in-place", ORIGIN_BUNDLE
            )
        if self.describe_only:
            return Location(resource, None, UNAVAILABLE, ORIGIN_BUNDLE, why)
        raise BundleError(
            f"{resource.key} is in the bundle {bundle.path}, but {why}. A bundled "
            "file is never a reason to download: restore it from the repository, "
            "or record the change with `bundle update`."
        )


def _routed(catalog: Catalog, resource: Resource) -> Reroute | None:
    """The catalogue's copy of a bundled file, when it holds the same bytes under its key."""
    from .errors import EthosDataError
    from .model import digest

    try:
        dataset = catalog.dataset(resource.dataset)
        held = dataset.inventory.at(resource.path)
    except EthosDataError:
        return None
    if held is None or digest.expected(held.hash) != digest.expected(resource.hash):
        return None
    return Reroute(dataset, held)


@dataclass
class RestrictedCache(Locator):
    """3. Restricted data: read in place from a listed restricted cache, or refused.

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
            self._entries[dataset.name] = restricted_entry(
                self.caches, dataset.entry_name
            )
        entry, reasons = self._entries[dataset.name]
        if entry is not None:
            return Location(
                resource, entry / resource.path, "in-place", ORIGIN_RESTRICTED
            )
        if self.describe_only:
            why = restricted_states(self.caches, dataset.entry_name)
            return Location(resource, None, UNAVAILABLE, ORIGIN_RESTRICTED, why)
        raise AccessError(restricted_refusal(dataset, reasons))


def restricted_refusal(dataset: Dataset, reasons: list[str]) -> str:
    """The refusal for a restricted dataset this account cannot read.

    Short, for the person who meets it: that the dataset is restricted; how to
    obtain it, its homepage and whom to ask, each where the catalogue records
    it; why it cannot be read, when that is more than a missing copy; and the
    two commands that register a copy. ``--meta`` prints the full description.
    """
    descriptor = dataset.descriptor
    lines = [f"the dataset {dataset.name!r} is restricted."]
    for label, key in (
        ("Obtain it", k.RESTRICTION),
        ("Homepage", k.HOMEPAGE),
        ("Contact", k.CONTACT),
    ):
        value = " ".join(str(descriptor.get(key) or "").split())
        if value:
            lines.append(f"  {label}: {value}")
    lines.extend(f"  {reason}" for reason in reasons)
    lines.append("  Once you have a copy you may use, register it:")
    lines.append("    ethos-data config add-restricted-cache DIR")
    lines.append(f"    ethos-data link {dataset.name} DIR")
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
    """4. The public cache: data already on this machine, or a copy it holds.

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
                linked_entry(self.root, dataset.entry_name) is not None
            )
        target = self.root / dataset.entry_name / resource.path
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
    """5. A download from the publication root into the public cache.

    For public data only: restricted data never gets here, because its locator
    never passes. Refuses rather than passes, since nothing comes after it;
    with ``describe_only`` the file is reported as not available here instead.
    """

    root: Path
    describe_only: bool = False

    def describe(self) -> str:
        return f"a download into {self.root}, for public data only"

    def locate(self, catalog, dataset, resource):
        if not catalog.publication_url:
            if self.describe_only:
                why = "the catalogue declares no publication URL to download it from"
                return Location(resource, None, UNAVAILABLE, ORIGIN_DOWNLOAD, why)
            raise AccessError(
                f"dataset {dataset.name!r} is not in the public cache as a link, and the "
                f"catalogue declares no publication URL, so there is nowhere to fetch it "
                f"from.\n"
                f"Either set ethos:publication_url in catalog.yaml, or, while the data is "
                f"not yet uploaded, point at the copy on this machine:\n"
                f"    ethos-data link {dataset.name} /path/to/{dataset.name}"
            )
        target = self.root / dataset.entry_name / resource.path
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
            current = resource
            for locator in self.locators:
                found = locator.locate(catalog, dataset, current)
                if isinstance(found, Reroute):
                    dataset, current = found.dataset, found.resource
                    continue
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
    available here instead of refused. The bundles a catalogue view holds, a
    package's handle given ``bundles=``, are read by the second locator.
    """
    return Chain(
        (
            Staging(roots.staging),
            Bundled(describe),
            RestrictedCache(roots.restricted, describe),
            PublicCache(roots.public),
            Download(roots.public, describe),
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
