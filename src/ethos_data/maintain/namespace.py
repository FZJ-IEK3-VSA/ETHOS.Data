"""Building the public cache as a namespace of links, from the catalogue.

    ethos-data link --all --root /shared/ethos/cache --dry-run
    ethos-data link --all --root /shared/ethos/cache

The result is one entry per dataset, named for the dataset, pointing at wherever
that data already sits on this machine:

    <public cache>/
    |-- global-wind-atlas  -> /projects/shared/Global_Wind_Atlas/GWA_4.0
    |-- corine-land-cover  -> /projects/shared/landcover/clc2018
    |-- test-data/era5     -> /projects/shared/era5-subset   (a nested dataset,
    |                                                       entry where its name says)
    `-- submarine-cables/     (a real directory, downloaded from dCache)

Nothing is copied and nothing is moved: the entries cost a few hundred bytes in
total. What they buy is a stable name for each dataset, so that when the storage
behind one is reorganised, exactly one link changes and every user follows.

The command sits with the user-facing ``link`` rather than under ``catalog``,
because filling a whole cache from a checkout and pointing one dataset at a
directory are the same job at two scales. It reads a source checkout:
``source_dir`` is never published -- it is a statement about one machine -- so
the namespace is built by somebody who knows where things are, in practice in
the cluster's public cache, which every cluster user's ``public_cache`` names.
It holds public data only: a restricted dataset is linked by name into the
restricted cache of its access combination.

**Real directories are never touched.** An entry that has been downloaded from
dCache, or materialised with ``ethos-data materialize``, is data the cache owns;
replacing it with a link would silently discard it.

It runs as a pipeline (see :mod:`.pipeline`), and ``--dry-run`` prints its plan:

``plan``    what each dataset's entry needs, and why a dataset is left out
``apply``   make, repoint and, with ``--prune``, remove the links
``record``  with ``--catalog-root``, take the ``link`` step of each dataset
            linked and record the link as a copy in its ``status.yaml``; a
            dataset whose state does not allow the step, a draft not built
            yet, is left out

The links and copies ``ethos-data link`` and ``materialize`` make by name,
given ``--catalog-root``, are recorded here as well, by two more pipelines:

``link``         ``check`` that the dataset's state and its licensing allow the
                 step, ``link`` the entry, ``record`` the link as a copy
``materialize``  ``check``, ``copy`` the files into the entry, ``verify`` the
                 copy in place against the inventory, ``record`` it as a copy

Their entries are made through :mod:`ethos_data.linking` and
:mod:`ethos_data.materialize`, in the cache the global ``--root`` names: the
public cache, or a listed restricted cache. Reading data never writes a
catalogue, so the record is made here, in the dataset's ``status.yaml``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..access import entry_for
from ..catalogs import Catalog
from ..config import Roots
from ..errors import LinkError, MaintenanceError
from ..formats import keys as k
from ..formats.derived import license_settled
from ..formats.status_file import Copy
from ..linking import LinkReport, raise_if_refused
from ..linking import link as make_link
from ..materialize import MaterializeReport, materialize, plan_materialize
from ..model import lifecycle, names
from . import (
    dataset_name_for,
    datasets_dir,
    is_namespace,
    iter_dataset_dirs,
    read_descriptor,
    source_dir_for,
)
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = [
    "LINK",
    "LINK_ALL",
    "MATERIALIZE",
    "CopyResult",
    "Copying",
    "Linking",
    "Namespace",
    "NamespaceResult",
    "link",
    "materialize_and_record",
    "run",
]


@dataclass
class Namespace:
    """The public cache ``link --all`` builds, from which checkout, and what it found."""

    catalog_root: Path
    root: Path
    prune: bool = False
    #: Take the ``link`` step of each dataset linked, and record the link.
    record: bool = False
    #: What each dataset's entry needs, by verb: ``link``, ``repoint``,
    #: ``prune``; or why it is left as it is: ``unchanged``, ``keep``,
    #: ``skip``, ``missing``. Set by ``plan``, as ``(verb, dataset, detail)``.
    findings: list[tuple[str, str, str]] = field(default_factory=list)
    #: The entries the cache holds as links once the plan is applied, as
    #: ``(dataset, entry, target)``; and the changes to make, as
    #: ``(verb, dataset, entry, target)``.
    links: list[tuple[str, Path, Path]] = field(default_factory=list)
    changes: list[tuple[str, str, Path, Path | None]] = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        """The datasets whose ``source_dir`` does not exist."""
        return [dataset for verb, dataset, _ in self.findings if verb == "missing"]


def _declared(catalog_root: Path) -> list[tuple[str, dict]]:
    """Every dataset with a dataset.yaml, at any depth, by catalogue name.

    Not a listing of the top level, because a nested family is described as a
    dataset.yaml naming the family with the datasets that hold files *below*
    it: the family node has no ``source_dir``, and is not meant to.

    The name is the path below ``datasets/``, so a member is ``family/member``
    and its entry is ``<root>/family/member``: the same name the manifest
    builder writes, the collections file uses, and the reader looks up.

    Namespace nodes are dropped rather than reported: a namespace owns no files,
    so "no source_dir" is not a finding about it.
    """
    root = datasets_dir(catalog_root)
    found = []
    for directory in iter_dataset_dirs(root):
        if is_namespace(directory):
            continue
        found.append((dataset_name_for(root, directory), read_descriptor(directory)))
    return found


def _same_target(current: Path, source: Path) -> bool:
    """Whether a link already points where the catalogue says it should.

    Compared as text, because a link *is* text -- resolving both would call two
    different curated paths the same thing the moment either went through
    another link, which is exactly what source_dir is allowed to do. The one
    spelling difference that is not a real difference is Windows's ``\\\\?\\``
    extended-length prefix, added when the link is stored: without stripping it,
    every run would repoint an entry that is already correct.
    """
    return str(current).removeprefix("\\\\?\\") == str(source).removeprefix("\\\\?\\")


class Plan:
    """Decide what each dataset's entry needs, reading the checkout and the cache."""

    name = "plan"

    def plan(self, namespace: Namespace) -> list[Action]:
        declared = _declared(namespace.catalog_root)
        for name, meta in declared:
            self._entry(namespace, name, meta)
        if namespace.prune and namespace.root.is_dir():
            # The reader's own walk, so that a nested entry is found where its
            # name says it is (``family/member``) rather than not at all.
            from ..access import cache_entries

            # An entry of any revision of a dataset the catalogue describes
            # stays: an earlier release may name that revision.
            declared_names = {name for name, _ in declared}
            for name, existing in cache_entries(namespace.root):
                if (
                    names.of_entry(name)[0] in declared_names
                    or not existing.is_symlink()
                ):
                    continue
                namespace.findings.append(
                    ("prune", name, "not in the catalogue any more")
                )
                namespace.changes.append(("prune", name, existing, None))
        for verb, dataset, detail in namespace.findings:
            if verb not in ("link", "repoint", "prune"):
                report.info(f"  {verb:<12} {dataset:<32}  {detail}".rstrip())
        return []

    @staticmethod
    def _entry(namespace: Namespace, name: str, meta: dict) -> None:
        def leave(verb: str, detail: str) -> None:
            namespace.findings.append((verb, name, detail))

        if meta.get(k.ACCESS, k.PUBLIC) == k.RESTRICTED:
            leave(
                "skip",
                "restricted: link it by name into the restricted cache of its "
                "access combination",
            )
            return
        # Building this namespace is how a dataset reaches everybody on the
        # machine: the guard of the link step applies to every dataset in it.
        reason = lifecycle.refusal("link", name, settled=license_settled(meta))
        if reason:
            leave("skip", reason.splitlines()[0])
            return
        try:
            built_from = dataset_status.build_input(
                datasets_dir(namespace.catalog_root) / name, meta, name
            )
            state = built_from.status.state
            if state in (lifecycle.WITHDRAWN, lifecycle.PURGED):
                leave("skip", "withdrawn: out of the catalogue")
                return
            if namespace.record:
                lifecycle.step("link", state, name)
        except MaintenanceError as error:
            leave("skip", error.message.splitlines()[0])
            return
        source = built_from.source_dir
        if source is None:
            detail = "no source_dir"
            if built_from.frozen:
                detail += ": its inventory is final"
            leave("skip", detail)
            return
        if not source.is_dir():
            leave("missing", f"source_dir does not exist: {source}")
            return

        # The entry of the revision the checkout describes.
        entry = namespace.root / names.entry(name, built_from.status.revision)
        if entry.is_symlink():
            current = entry.readlink()
            if _same_target(current, source):
                leave("unchanged", f"-> {source}")
            else:
                namespace.findings.append(("repoint", name, f"was {current}"))
                namespace.changes.append(("repoint", name, entry, source))
        elif entry.exists():
            leave("keep", "a real directory the cache owns; not replaced with a link")
            return
        else:
            namespace.findings.append(("link", name, ""))
            namespace.changes.append(("link", name, entry, source))
        namespace.links.append((name, entry, source))


class Apply:
    """Make, repoint and remove links; a real directory is never touched."""

    name = "apply"

    def plan(self, namespace: Namespace) -> list[Action]:
        actions = []
        for verb, dataset, entry, target in namespace.changes:
            if verb == "prune":
                text = f"prune {entry}: not in the catalogue any more"
            else:
                text = f"{verb} {entry} -> {target}"
            actions.append(
                Action(text, self._change(verb, entry, target), subject=dataset)
            )
        return actions

    @staticmethod
    def _change(verb: str, entry: Path, target: Path | None):
        def change() -> None:
            if verb in ("repoint", "prune"):
                entry.unlink()
            if verb in ("link", "repoint"):
                entry.parent.mkdir(parents=True, exist_ok=True)
                entry.symlink_to(target)

        return change


class RecordLinks:
    """Record each link as a copy of its dataset, unless it is recorded already."""

    name = "record"

    def plan(self, namespace: Namespace) -> list[Action]:
        if not namespace.record:
            return []
        actions = []
        for dataset, entry, target in namespace.links:
            directory = datasets_dir(namespace.catalog_root) / dataset
            status = dataset_status.read(directory)
            after = lifecycle.step("link", status.state, dataset)
            copy = Copy(kind=k.COPY_LINKED, location=str(entry), target=str(target))
            if after == status.state and copy in status.copies:
                continue
            actions.append(
                Action(
                    f"{dataset} becomes {after}, the link recorded in its status.yaml",
                    self._record(namespace.catalog_root, dataset, copy),
                    subject=dataset,
                )
            )
        return actions

    @staticmethod
    def _record(catalog_root: Path, dataset: str, copy: Copy):
        def record() -> None:
            dataset_status.record_copy(
                catalog_root, dataset, "link", copy, repeat=False
            )

        return record


LINK_ALL: Pipeline[Namespace] = Pipeline("link --all", [Plan(), Apply(), RecordLinks()])


@dataclass
class NamespaceResult:
    """What ``link --all`` found, and whether it carried the plan out."""

    #: The datasets whose ``source_dir`` does not exist.
    missing: list[str]
    #: Why each change or record that failed did, by dataset.
    failed: dict[str, str] = field(default_factory=dict)
    applied: bool = False

    @property
    def ok(self) -> bool:
        return not (self.missing or self.failed)


@report.reported
def run(
    catalog_root: Path,
    root: Path,
    *,
    dry_run: bool = False,
    prune: bool = False,
    record: bool = False,
) -> NamespaceResult:
    """Plan the namespace, report it, and -- unless ``dry_run`` -- build it.

    ``record`` takes the ``link`` step of every dataset linked, and records
    each link in its ``status.yaml``. ``root`` is the public cache the caller
    names, and has no default: a link tree built in a directory nobody named
    would print as a success.
    """
    namespace = Namespace(catalog_root, root, prune=prune, record=record)
    report.info(f"namespace root: {root}")
    report.info(f"catalogue:      {catalog_root}\n")
    outcome = LINK_ALL.run(namespace, dry_run=dry_run)
    if namespace.missing and not dry_run:
        report.info(
            f"{len(namespace.missing)} dataset(s) have a source_dir that does not "
            "exist; restore the directory, then run this again."
        )
    return NamespaceResult(
        namespace.missing, outcome.failed, applied=bool(outcome.planned) and not dry_run
    )


# -- links and copies made by name, recorded in a clone ------------------------------


def _state_after(catalog_root: Path, dataset: str, step: str) -> str:
    """The state ``step`` leads the dataset to; refuses a step its state does not allow."""
    directory = dataset_status.dataset_dir_in(catalog_root, dataset)
    status = dataset_status.checked_status(directory, dataset, step)
    return lifecycle.step(step, status.state, dataset)


# -- link NAME --catalog-root --------------------------------------------------------


@dataclass
class Linking:
    """One dataset to link by name, and the clone that records it."""

    catalog_root: Path
    catalog: Catalog
    dataset: str
    #: The directory to link to; the dataset's build input when None.
    directory: Path | None
    roots: Roots
    force: bool = False
    cache: str | Path | None = None
    #: The state the step leads to: set by ``check``.
    after: str = ""
    #: The entry linked: set by ``link``.
    made: LinkReport | None = None


class CheckLink:
    name = "check"

    def plan(self, linking: Linking) -> list[Action]:
        linking.after = _state_after(linking.catalog_root, linking.dataset, "link")
        raise_if_refused(linking.catalog, linking.dataset, "link", LinkError)
        if linking.directory is None:
            linking.directory = source_dir_for(linking.dataset, linking.catalog_root)
        return []


class MakeLink:
    name = "link"

    def plan(self, linking: Linking) -> list[Action]:
        entry = entry_for(
            linking.catalog, linking.roots, linking.dataset, linking.cache
        )

        def perform() -> None:
            linking.made = make_link(
                linking.catalog,
                linking.dataset,
                linking.directory,
                linking.roots,
                force=linking.force,
                cache=linking.cache,
            )

        return [Action(f"link {entry} -> {linking.directory}", perform)]


class RecordLink:
    name = "record"

    def plan(self, linking: Linking) -> list[Action]:
        def perform() -> None:
            made = linking.made
            dataset_status.record_copy(
                linking.catalog_root,
                made.dataset,
                "link",
                Copy(
                    kind=k.COPY_LINKED,
                    location=str(made.entry),
                    target=str(made.target),
                ),
            )

        return [
            Action(
                f"{linking.dataset} becomes {linking.after}, the link recorded in its "
                "status.yaml",
                perform,
            )
        ]


LINK: Pipeline[Linking] = Pipeline("link", [CheckLink(), MakeLink(), RecordLink()])


def link(linking: Linking, *, dry_run: bool = False) -> LinkReport | None:
    """Link the dataset and record the link; the entry made, or None for a dry run."""
    LINK.run(linking, dry_run=dry_run)
    return linking.made


# -- materialize NAMES --catalog-root ------------------------------------------------


@dataclass
class Copying:
    """The datasets to copy into their cache entries, and the clone that records them."""

    catalog_root: Path
    catalog: Catalog
    names: list[str]
    roots: Roots
    verify_hashes: bool = True
    source: str | Path | None = None
    cache: str | Path | None = None
    #: What ``check`` found for each dataset it will not copy, and the copies
    #: it plans, by dataset, with the state each step leads to.
    passed_over: list[MaterializeReport] = field(default_factory=list)
    planned: dict[str, MaterializeReport] = field(default_factory=dict)
    after: dict[str, str] = field(default_factory=dict)
    #: The copies made: set by ``copy``.
    made: dict[str, MaterializeReport] = field(default_factory=dict)

    def source_dir(self) -> Callable[[str], Path]:
        return lambda name: source_dir_for(name, self.catalog_root)


class CheckCopies:
    name = "check"

    def plan(self, copying: Copying) -> list[Action]:
        allowed = []
        for name in copying.names:
            try:
                copying.after[name] = _state_after(
                    copying.catalog_root, name, "materialize"
                )
            except MaintenanceError as error:
                copying.passed_over.append(
                    MaterializeReport(name, "cannot", error.message.splitlines()[0])
                )
                continue
            allowed.append(name)
        for found in plan_materialize(
            copying.catalog,
            allowed,
            copying.roots,
            source=copying.source,
            source_dir=copying.source_dir(),
            cache=copying.cache,
        ):
            if found.action == "would copy":
                copying.planned[found.dataset] = found
            else:
                copying.passed_over.append(found)
        return []


class CopyFiles:
    name = "copy"

    def plan(self, copying: Copying) -> list[Action]:
        return [
            Action(
                f"copy {planned.files:,} files, {planned.bytes:,} bytes of {name} from "
                f"{planned.target} into {planned.entry}",
                self._copy(copying, name),
                subject=name,
            )
            for name, planned in copying.planned.items()
        ]

    @staticmethod
    def _copy(copying: Copying, name: str):
        def copy() -> None:
            (made,) = materialize(
                copying.catalog,
                [name],
                copying.roots,
                verify_hashes=copying.verify_hashes,
                source=copying.source,
                source_dir=copying.source_dir(),
                cache=copying.cache,
            )
            copying.made[name] = made
            if made.action != "materialized":
                failures = "".join(f"\n    {failure}" for failure in made.failures[:10])
                raise MaintenanceError(f"{made.detail}{failures}")

        return copy


class VerifyCopies:
    name = "verify"

    def plan(self, copying: Copying) -> list[Action]:
        return [
            Action(
                f"check that {planned.entry} holds the {planned.files:,} files of "
                f"{name} at their recorded sizes",
                self._verify(copying, name, planned.entry),
                subject=name,
            )
            for name, planned in copying.planned.items()
        ]

    @staticmethod
    def _verify(copying: Copying, name: str, entry: Path):
        def verify() -> None:
            if entry.is_symlink() or not entry.is_dir():
                raise MaintenanceError(f"{entry} is not a real directory")
            wrong = [
                resource.path
                for resource in copying.catalog.dataset(name).resources.values()
                if not (entry / resource.path).is_file()
                or (entry / resource.path).stat().st_size != resource.bytes
            ]
            if wrong:
                raise MaintenanceError(
                    f"{len(wrong)} files of {name} are missing from {entry} or have "
                    f"the wrong size, the first {wrong[0]}"
                )

        return verify


class RecordCopies:
    name = "record"

    def plan(self, copying: Copying) -> list[Action]:
        return [
            Action(
                f"{name} becomes {copying.after[name]}, the copy recorded in its "
                "status.yaml",
                self._record(copying, name),
                subject=name,
            )
            for name in copying.planned
        ]

    @staticmethod
    def _record(copying: Copying, name: str):
        def record() -> None:
            made = copying.made[name]
            dataset_status.record_copy(
                copying.catalog_root,
                name,
                "materialize",
                Copy(
                    kind=k.COPY_MATERIALIZED,
                    location=str(made.entry),
                    verified=dataset_status.now() if copying.verify_hashes else None,
                ),
                files=made.files,
                bytes=made.bytes,
            )

        return record


MATERIALIZE: Pipeline[Copying] = Pipeline(
    "materialize", [CheckCopies(), CopyFiles(), VerifyCopies(), RecordCopies()]
)


@dataclass
class CopyResult:
    """What ``materialize --catalog-root`` found and did, dataset by dataset."""

    reports: list[MaterializeReport]
    #: Why each copy that was planned failed, by dataset.
    failed: dict[str, str]

    @property
    def ok(self) -> bool:
        return not self.failed and not any(
            report.action in ("unknown", "cannot", "dangling")
            for report in self.reports
        )


def materialize_and_record(copying: Copying, *, dry_run: bool = False) -> CopyResult:
    """Copy the datasets into their entries and record each copy in the clone."""
    outcome = MATERIALIZE.run(copying, dry_run=dry_run)
    done = [
        copying.made.get(name, planned) for name, planned in copying.planned.items()
    ]
    return CopyResult(copying.passed_over + done, outcome.failed)
