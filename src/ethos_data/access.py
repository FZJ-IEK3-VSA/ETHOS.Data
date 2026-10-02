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

Where a file is read is decided by one chain of locators, each looking in
one place, in this order:

  1. ``dataset_roots`` -- the per-dataset escape hatch, for a private copy
  2. the staging root -- work in progress, shadowing the catalogue during
     development.  Never applies to restricted data.
  3. the package's bundles (planned: the repository is the source of truth for
     its test data)
  4. the restricted cache, for restricted datasets: always in place, never
     downloaded, never written to
  5. a link in the public cache, the dataset's own or its family's: in place
  6. a copy already in the public cache
  7. a download from the publication root, for public data only

Each locator answers *found* with a :class:`Location`, *pass* with None, or
*refuse* by raising :class:`AccessError`. A refusal ends the chain, which is what
keeps a restricted file without an installation from ever falling through to a
download. Building the chain touches nothing; locating touches only the file
system. Whether a file that has to be downloaded is downloaded is the caller's
choice, see ``fetch=`` in :mod:`ethos_data.retrieval`.

The rule that matters, unchanged: restricted data is never written into a shared
cache and never silently downloaded. If there is nowhere to read it from, asking
for it fails with an explanation instead of doing something surprising.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .catalogs import Catalog, Dataset, Resource
from .config import Roots
from .errors import AccessError
from .formats import keys as k
from .formats.derived import reader_description
from .model import names

__all__ = [
    "AccessError",
    "Chain",
    "Locator",
    "cache_entries",
    "chain_for",
    "entry_for",
    "Location",
    "locate",
    "requires_local_root",
    "unavailable",
    "ORIGIN_CONFIGURED",
    "ORIGIN_STAGING",
    "ORIGIN_RESTRICTED",
    "ORIGIN_LINK",
    "ORIGIN_CACHED",
    "ORIGIN_DOWNLOAD",
    "UNAVAILABLE",
]

PUBLIC = k.PUBLIC
INTERNAL = k.INTERNAL
RESTRICTED = k.RESTRICTED
#: Synthesised for a dataset that exists only in the staging root. Never
#: appears in a real catalogue, so it can never be uploaded or published.
STAGING = "staging"

#: Why a location resolved the way it did -- carried so that error messages and
#: a package's ``verify`` command can say something more useful than "not found".
ORIGIN_CONFIGURED = "configured root"
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
    #: "download" -- fetch into the shared cache; "in-place" -- already on disk,
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


def requires_local_root(dataset: Dataset) -> bool:
    """Restricted data can only ever be used from a configured local root."""
    return access_class(dataset) == RESTRICTED


def entry_for(catalog: Catalog, roots: Roots, name: str) -> Path:
    """Where this dataset's cache entry belongs, whatever is or is not there.

    The access class picks the root, exactly as :func:`locate` does -- so the
    commands that *make* an entry cannot put one somewhere retrieval would never
    look for it. Raises UnknownDataset for a name the catalogue does not
    describe, and AccessError when a restricted dataset has no restricted cache:
    there is nowhere to put it, and the public cache is the one place it may
    never go.
    """
    root = roots.for_access(access_class(catalog.dataset(name)))
    if root is None:
        raise AccessError(
            f"dataset {name!r} is restricted and no restricted cache is configured; "
            "there is no entry for it. Set one with:\n"
            "    ethos-data config set-restricted-cache /path/to/ethos_data_restricted"
        )
    return root / name


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
class DatasetRoots(Locator):
    """1. A per-dataset root: the most specific thing anybody can have said."""

    roots: Mapping[str, Path]

    def describe(self) -> str:
        listed = ", ".join(sorted(self.roots)) or "none set"
        return f"per-dataset roots ({listed})"

    def locate(self, catalog, dataset, resource):
        root = self.roots.get(dataset.name)
        if root is None:
            return None
        return Location(resource, root / resource.path, "in-place", ORIGIN_CONFIGURED)


@dataclass
class Staging(Locator):
    """2. The staging root, shadowing the catalogue -- never for restricted data."""

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


@dataclass
class RestrictedCache(Locator):
    """4. Licensed data: found in the restricted cache, or refused. Never passes.

    Refused when this machine has no restricted cache, when the cache has no
    entry for the dataset, or when the entry cannot be read -- before anything
    is downloaded, with the dataset's description and how to register a copy.
    A workflow cannot run without one of its inputs. With ``describe`` the
    file is reported as not available here instead, for commands that only
    say what a fetch would do.
    """

    root: Path | None
    describe_only: bool = False
    _why: dict[str, str] = field(default_factory=dict, repr=False)

    def describe(self) -> str:
        where = self.root if self.root else "(not set)"
        return f"restricted cache {where}, for restricted data only"

    def reset(self) -> None:
        self._why.clear()

    def _unreadable(self, name: str) -> str:
        """Why this dataset cannot be read from the restricted cache; "" if it can."""
        if self.root is None:
            return "no restricted cache is configured on this machine"
        entry = self.root / name
        if entry.is_symlink() and not entry.exists():
            return (
                f"its entry {entry} is a link to {entry.readlink()}, which is not there"
            )
        if not entry.exists():
            return f"the restricted cache {self.root} has no entry for it"
        if not os.access(entry, os.R_OK | os.X_OK):
            return f"you may not read its entry {entry}"
        return ""

    def locate(self, catalog, dataset, resource):
        if access_class(dataset) != RESTRICTED:
            return None
        # Once per dataset: 170,000 files behind one entry cost one look at it.
        why = self._why.get(dataset.name)
        if why is None:
            why = self._why[dataset.name] = self._unreadable(dataset.name)
        if not why:
            return Location(
                resource,
                self.root / dataset.name / resource.path,
                "in-place",
                ORIGIN_RESTRICTED,
            )
        if self.describe_only:
            return Location(resource, None, UNAVAILABLE, ORIGIN_RESTRICTED, why)
        raise AccessError(restricted_refusal(dataset, why))


def restricted_refusal(dataset: Dataset, why: str) -> str:
    """The refusal for a licensed dataset this machine cannot read.

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
            "    ethos-data config set-restricted-cache /path/to/ethos_data_restricted",
            f"    ethos-data link {dataset.name} /path/to/{dataset.name}",
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
class PublicLinks(Locator):
    """5. A link in the public cache: data already on this machine, read in place."""

    root: Path
    _linked: dict[str, bool] = field(default_factory=dict, repr=False)

    def describe(self) -> str:
        return f"links in the public cache {self.root}"

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
        if not linked:
            return None
        entry = self.root / dataset.name
        return Location(resource, entry / resource.path, "in-place", ORIGIN_LINK)


@dataclass
class PublicCopies(Locator):
    """6. A copy already in the public cache, of the size the catalogue records.

    Still a download location: fetching it checks the hash, and replaces the
    copy if it differs.
    """

    root: Path

    def describe(self) -> str:
        return f"copies in the public cache {self.root}"

    def locate(self, catalog, dataset, resource):
        target = self.root / dataset.name / resource.path
        try:
            present = target.stat().st_size == resource.bytes
        except OSError:
            present = False
        if not present:
            return None
        return Location(resource, target, "download", ORIGIN_CACHED)


@dataclass
class Download(Locator):
    """7. A download from the publication root into the public cache.

    For public data only. Internal data is not published, so it is not
    downloaded: it is read where the shared cache holds it. Refuses rather than
    passes, since nothing comes after it.
    """

    root: Path

    def describe(self) -> str:
        return f"a download into {self.root}, for public data only"

    def locate(self, catalog, dataset, resource):
        if access_class(dataset) == INTERNAL:
            raise AccessError(
                f"dataset {dataset.name!r} is internal: it is not published, so it is "
                "never downloaded, and this machine has no copy of it.\n"
                "On the cluster computer it is read from the shared public cache; "
                "check the cache with `ethos-data config show`. Elsewhere, point at a "
                "copy you hold:\n"
                f"    ethos-data link {dataset.name} /path/to/{dataset.name}"
            )
        if not catalog.publication_url:
            raise AccessError(
                f"dataset {dataset.name!r} is not in the public cache as a link, and the "
                f"catalogue declares no publication URL, so there is nowhere to fetch it "
                f"from.\n"
                f"Either set ethos:publication_url in catalog.yaml, or, while the data is "
                f"not yet uploaded, point at the copy on this machine:\n"
                f"    ethos-data link {dataset.name} /path/to/{dataset.name}\n"
                f"or, for this one dataset only:\n"
                f"    ethos-data config set-root {dataset.name} /path/to/{dataset.name}"
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
    """The lookup chain the decision record names, built from ``roots``.

    ``describe`` builds the chain for a command that only says what a fetch
    would do: licensed data this machine cannot read is reported as not
    available here instead of refused. The package's bundles join it as the
    third locator when bundles are part of the chain; until then they are read
    through :func:`ethos_data.load_bundle`.
    """
    return Chain(
        (
            DatasetRoots(
                {name: Path(path).expanduser() for name, path in roots.datasets.items()}
            ),
            Staging(roots.staging),
            RestrictedCache(roots.restricted, describe),
            PublicLinks(roots.public),
            PublicCopies(roots.public),
            Download(roots.public),
        )
    )


def locate(
    catalog: Catalog,
    resources: list[Resource],
    roots: "Roots | str | Path | None" = None,
    dataset_roots: dict[str, str | Path] | None = None,
    *,
    describe: bool = False,
) -> list[Location]:
    """Work out where every resource should be read from.

    ``roots`` accepts a :class:`~ethos_data.config.Roots`, or a bare path meaning
    the public cache -- which is what a lone cache directory always meant.
    ``dataset_roots`` replaces the roots' own per-dataset roots.

    Every input is required: licensed data this machine cannot read raises
    AccessError, describing the dataset and how to register a copy, before
    anything is downloaded. ``describe=True`` reports it as "unavailable"
    instead, for commands that only say what a fetch would do. The chain it
    runs is :func:`chain_for`.
    """
    roots = Roots.coerce(roots)
    if dataset_roots is not None:
        from dataclasses import replace

        roots = replace(roots, datasets=dict(dataset_roots))
    return chain_for(roots, describe=describe).locate(catalog, resources)


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
