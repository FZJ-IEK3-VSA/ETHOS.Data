"""``catalog record``: freeze datasets, naming the copy that is authoritative from now on.

    ethos-data catalog record era5 --dry-run
    ethos-data catalog record era5
    ethos-data catalog record reskit-test-data
    ethos-data catalog record gadm-3.6 --copy /shared/restricted/gadm-3.6

Once its bytes are uploaded and verified, or copied into a cache that owns
them, a dataset needs its build input no more, and should not read it again:
a rebuild hashes whatever it is pointed at, so a corrupted original would be
recorded as correct. Freezing the dataset keeps the inventory as it
was built and retires ``source_dir``, so the recorded hashes stay an
independent witness to the copy.

Two stages:

``check``   choose the copy and check it, file by file: an upload read back
            anonymously through the store, a cache entry on this machine
``freeze``  record it as the authoritative copy and retire ``source_dir``;
            one in the clone's ``build-inputs/``, where ``catalog add-bundle``
            copies a bundle's files, is deleted

Every dataset named is checked before any is frozen. A family stands for
its members, and a member frozen or withdrawn already is passed over; a
dataset named itself is checked all the same.

Which copy, when there are several: the upload, else the copy a cache owns,
else, for restricted data, the registered installation, a link in a
restricted cache. A link to public data borrows the build input and is the
authoritative copy only when named with ``--copy``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..adapters import Store
from ..errors import MaintenanceError
from ..formats import keys as k
from ..formats.status_file import Copy, StatusFile
from ..model import lifecycle
from . import (
    build_inputs_dir,
    in_build_inputs,
    inventory_of,
    read_descriptor,
)
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "Freeze", "RecordResult", "Target", "choose", "run"]


def _same(location: str, other: str) -> bool:
    return location.rstrip("/\\") == other.rstrip("/\\")


def _listing(copies: list[Copy]) -> str:
    return (
        "\n".join(f"    {copy.kind:<13} {copy.location}" for copy in copies)
        or "    (none)"
    )


def choose(dataset: str, status: StatusFile, access: str, named: str | None) -> Copy:
    """The copy to make authoritative: the one ``named``, or the one the rule picks."""
    if named is not None:
        for copy in status.copies:
            if _same(copy.location, named):
                return copy
        raise MaintenanceError(
            f"{dataset} has no recorded copy at {named}. Its copies:\n"
            f"{_listing(status.copies)}"
        )
    by_kind = [
        [copy for copy in status.copies if copy.kind == kind]
        for kind in (k.COPY_UPLOADED, k.COPY_MATERIALIZED)
    ]
    if access == k.RESTRICTED:
        by_kind.append([copy for copy in status.copies if copy.kind == k.COPY_LINKED])
    candidates = next((copies for copies in by_kind if copies), [])
    if not candidates:
        raise MaintenanceError(
            f"{dataset} has no copy that can be its authoritative one. A link "
            "borrows its source_dir, which every rebuild reads: upload it or "
            "materialize it first, or name a copy with --copy. Its copies:\n"
            f"{_listing(status.copies)}"
        )
    if len(candidates) > 1:
        raise MaintenanceError(
            f"{dataset} has {len(candidates)} copies that could be its authoritative "
            f"one; name one with --copy:\n{_listing(candidates)}"
        )
    return candidates[0]


@dataclass(frozen=True)
class Target:
    """One dataset ``record`` freezes, and the copy it is frozen with."""

    name: str
    directory: Path
    status: StatusFile
    chosen: Copy


@dataclass
class Freeze:
    """The datasets ``record`` freezes, and the copy each is frozen with."""

    catalog_root: Path
    datasets: list[str]
    named: str | None = None
    #: Reads an upload back.
    store: Store | None = None
    #: Each dataset checked and cleared, in the order asked for: set by ``check``.
    targets: list[Target] = field(default_factory=list)


class Check:
    name = "check"

    def plan(self, freeze: Freeze) -> list[Action]:
        from .upload import expand_families, passed_over, resolve_name

        names = expand_families(
            freeze.catalog_root,
            [resolve_name(freeze.catalog_root, each) for each in freeze.datasets],
            "record",
        )
        if freeze.named is not None and len(names) != 1:
            raise MaintenanceError(
                "--copy names the copy of one dataset; name that one dataset with it."
            )
        for name, family in names.items():
            directory = dataset_status.dataset_dir_in(freeze.catalog_root, name)
            meta = read_descriptor(directory)
            status = dataset_status.build_input(directory, meta, name).status
            if passed_over(family, status.state):
                report.info(
                    f"  {self.name:<12} {name}: {status.state}, nothing to record"
                )
                continue
            lifecycle.step("record", status.state, name)
            access = meta.get(k.ACCESS, k.PUBLIC)
            chosen = choose(name, status, access, freeze.named)
            records = inventory_of(name, directory).records()
            finding = dataset_status.check_copy(chosen, records, freeze.store)
            report.info(f"  {self.name:<12} {finding}")
            if not finding.ok:
                raise MaintenanceError(
                    f"{name}: the copy does not hold the inventory as built, so it "
                    "cannot be the authoritative one. Find out why before freezing it."
                )
            freeze.targets.append(Target(name, directory, status, chosen))
        return []


class Retire:
    name = "freeze"

    def plan(self, freeze: Freeze) -> list[Action]:
        actions = []
        for target in freeze.targets:
            status, chosen = target.status, target.chosen
            if status.state == lifecycle.FROZEN and status.authority == chosen.location:
                report.info(
                    f"  {target.name} is frozen already, with this copy as its "
                    "authoritative one."
                )
                continue
            actions.append(self._freeze(freeze.catalog_root, target))
        return actions

    @staticmethod
    def _freeze(catalog_root: Path, target: Target) -> Action:
        status, chosen = target.status, target.chosen
        retired = status.source_dir
        text = f"freeze {target.name}: {chosen.location} becomes its authoritative copy"
        if retired:
            text += f", and its source_dir {retired} is retired"
        doomed = _deletable(catalog_root, retired, status)
        if doomed:
            text += " and deleted"

        def perform() -> None:
            dataset_status.take(
                target.directory,
                status,
                "record",
                dataset=target.name,
                copy=chosen.model_copy(update={"verified": dataset_status.now()}),
                source_dir=retired,
                changes={"source_dir": None, "authority": chosen.location},
            )
            if doomed:
                _delete(catalog_root, doomed)

        return Action(text, perform, subject=target.name)


def _deletable(
    catalog_root: Path, retired: str | None, status: StatusFile
) -> Path | None:
    """The retired build input ``record`` deletes: one in the clone's build inputs.

    Not while a link in a cache still points into it.
    """
    if not retired or not in_build_inputs(catalog_root, retired):
        return None
    path = Path(retired)
    for copy in status.copies:
        if copy.kind == k.COPY_LINKED and copy.target:
            if Path(copy.target).absolute().is_relative_to(path.absolute()):
                return None
    return path if path.is_dir() else None


def _delete(catalog_root: Path, path: Path) -> None:
    """Delete ``path``, and the folders above it it leaves empty, up to the build inputs."""
    shutil.rmtree(path)
    top = build_inputs_dir(catalog_root)
    parent = path.absolute().parent
    while parent != top and parent.is_relative_to(top) and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


PIPELINE: Pipeline[Freeze] = Pipeline("record", [Check(), Retire()])


@dataclass(frozen=True)
class RecordResult:
    """The datasets ``catalog record`` froze, or would freeze, and their authoritative copies."""

    #: Each dataset checked, by name: its authoritative copy.
    authorities: dict[str, str]
    #: The datasets whose status file was written: none for a dry run, nor
    #: one frozen with this copy already.
    written: list[str]
    #: Why each dataset that failed to freeze did.
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed


@report.reported
def run(
    catalog_root: Path,
    datasets: str | list[str],
    *,
    copy: str | None = None,
    dry_run: bool = False,
    store: Store | None = None,
) -> RecordResult:
    """Freeze ``datasets`` -- names, paths or families -- each copy checked first.

    Every dataset is checked before any is frozen, or the reason is raised. A
    family stands for its members, those frozen or withdrawn already passed
    over. ``copy`` names the copy of a single dataset. ``store`` reads an
    upload back, dCache's public door by default.
    """
    if store is None:
        from ..adapters.dcache import DcacheStore

        store = DcacheStore()
    names = [datasets] if isinstance(datasets, str) else list(datasets)
    freeze = Freeze(catalog_root, names, copy, store)
    outcome = PIPELINE.run(freeze, dry_run=dry_run)
    written = [
        target.name
        for target in freeze.targets
        if not dry_run
        and target.name not in outcome.failed
        and not (
            target.status.state == lifecycle.FROZEN
            and target.status.authority == target.chosen.location
        )
    ]
    for name in written:
        report.info(
            f"\nrecorded     {name} is frozen; a rebuild keeps its inventory as it is"
        )
    authorities = {target.name: target.chosen.location for target in freeze.targets}
    return RecordResult(authorities, written, outcome.failed)
