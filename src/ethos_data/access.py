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

Where a file is read is decided by one chain of locators, built from the
settings snapshot of a handle or a command, each looking in one place, in this
order:

  1. the staging root -- work in progress, shadowing the catalogue during
     development.  Never applies to restricted data.
  2. the restricted cache, for restricted datasets: always in place, never
     downloaded, never written to
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

The rule that matters: restricted data is never written into a shared cache and
never silently downloaded. If there is nowhere to read it from, asking
for it fails with an explanation instead of doing something surprising.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .catalogs import Catalog, Dataset
from .config import Roots, resolve_skip_unavailable
from .errors import AccessError
from .formats import keys as k
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
    "unavailable",
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


@dataclass
class RestrictedCache(Locator):
    """2. Licensed data: found in the restricted cache, or refused. Never passes.

    Having no restricted cache is a legitimate, permanent state -- most people,
    most of the time, are not on the institute cluster and have no right to the
    licensed bytes. It is reported, not guessed around.
    """

    root: Path | None
    skip_unavailable: bool = False

    def describe(self) -> str:
        where = self.root if self.root else "(not set)"
        return f"restricted cache {where}, for restricted data only"

    def locate(self, catalog, dataset, resource):
        if access_class(dataset) != RESTRICTED:
            return None
        if self.root is not None:
            return Location(
                resource,
                self.root / dataset.name / resource.path,
                "in-place",
                ORIGIN_RESTRICTED,
            )
        if self.skip_unavailable:
            return Location(resource, None, UNAVAILABLE, ORIGIN_RESTRICTED)
        raise AccessError(_no_restricted_cache(dataset))


def _no_restricted_cache(dataset: Dataset) -> str:
    note = dataset.descriptor.get(k.RESTRICTION, "")
    lines = [f"dataset {dataset.name!r} is restricted and is never downloaded."]
    if note:
        lines.append(f"  {note}")
    lines.append("No restricted cache is configured on this machine.")
    lines.append("")
    lines.append("If you have a copy, register it:")
    lines.append(
        "    ethos-data config set-restricted-cache /path/to/ethos_data_restricted"
    )
    lines.append(f"    ethos-data link {dataset.name} /path/to/{dataset.name}")
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


def chain_for(roots: Roots, *, skip_unavailable: bool = False) -> Chain:
    """The lookup chain, built from ``roots``; building it touches nothing.

    Bundles are not in the chain: they are read through
    :func:`ethos_data.load_bundle`.
    """
    return Chain(
        (
            Staging(roots.staging),
            RestrictedCache(roots.restricted, skip_unavailable),
            PublicCache(roots.public),
            Download(roots.public),
        )
    )


def locate(
    catalog: Catalog,
    resources: list[Resource],
    roots: Roots | None = None,
    skip_unavailable: bool | None = None,
) -> list[Location]:
    """Work out where every resource should be read from.

    ``roots`` are the cache roots to read; without them, those of the
    catalogue's settings snapshot.

    ``skip_unavailable`` decides what happens to licensed data this machine has
    no access to: ``False`` raises, ``True`` marks it "unavailable" and carries
    on with everything else. ``None`` takes the configured answer, which
    defaults to raising.

    Raises AccessError -- naming the dataset and what to configure -- rather than
    falling back to the cache or to a download when neither is permitted. The
    chain it runs is :func:`chain_for`.
    """
    roots = roots if roots is not None else catalog.settings.roots
    if skip_unavailable is None:
        skip_unavailable = resolve_skip_unavailable()[0]
    return chain_for(roots, skip_unavailable=skip_unavailable).locate(
        catalog, resources
    )


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
