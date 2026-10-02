"""``catalog record``: freeze a dataset, naming the copy that is authoritative from now on.

    ethos-data catalog record era5 --dry-run
    ethos-data catalog record era5
    ethos-data catalog record gadm-3.6 --copy /shared/restricted/gadm-3.6

Once its bytes are uploaded and verified, or copied into a cache that owns
them, a dataset's build input is no longer needed, and should no longer be
read: a rebuild hashes whatever it is pointed at, so a corrupted original
would be recorded as correct. Freezing the dataset keeps the inventory as it
was built and retires ``source_dir``, so the recorded hashes stay an
independent witness to the copy.

Two stages:

``check``   choose the copy and check it, file by file: an upload anonymously
            over HTTP, a cache entry on this machine
``freeze``  record it as the authoritative copy and retire ``source_dir``

Which copy, when there are several: the upload, else the copy a cache owns,
else, for restricted data, the registered installation. A link to public or
internal data borrows the build input and is the authoritative copy only when
named with ``--copy``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
from ..formats import keys as k
from ..formats.status_file import Copy, StatusFile
from ..model import lifecycle
from . import is_namespace, read_descriptor, resources_of
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "Freeze", "choose", "run"]


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
            "borrows its source_dir, which a rebuild still reads: upload it or "
            "materialize it first, or name a copy with --copy. Its copies:\n"
            f"{_listing(status.copies)}"
        )
    if len(candidates) > 1:
        raise MaintenanceError(
            f"{dataset} has {len(candidates)} copies that could be its authoritative "
            f"one; name one with --copy:\n{_listing(candidates)}"
        )
    return candidates[0]


@dataclass
class Freeze:
    """The dataset ``record`` freezes, and the copy it is frozen with."""

    catalog_root: Path
    dataset: str
    named: str | None = None
    name: str = ""
    directory: Path | None = None
    status: StatusFile | None = None
    chosen: Copy | None = None


class Check:
    name = "check"

    def plan(self, freeze: Freeze) -> list[Action]:
        from .upload import resolve_name

        name = resolve_name(freeze.catalog_root, freeze.dataset)
        directory = dataset_status.dataset_dir_in(freeze.catalog_root, name)
        if is_namespace(directory):
            raise MaintenanceError(
                f"{name} is a family and has no bytes of its own; record each member."
            )
        status = dataset_status.read(directory)
        if status is None:
            raise MaintenanceError(
                f"{name} has no {dataset_status.STATUS} yet, so there is nothing to "
                f"record the freeze in. Write one from its dataset.yaml with\n"
                f"    ethos-data catalog migrate {name}"
            )
        lifecycle.step("record", status.state, name)
        access = read_descriptor(directory).get(k.ACCESS, k.PUBLIC)
        chosen = choose(name, status, access, freeze.named)
        package = json.loads((directory / "datapackage.json").read_text("utf-8"))
        finding = dataset_status.check_copy(chosen, resources_of(package, directory))
        report.info(f"  {self.name:<12} {finding}")
        if not finding.ok:
            raise MaintenanceError(
                f"{name}: the copy does not hold the inventory as built, so it "
                "cannot be the authoritative one. Find out why before freezing it."
            )
        freeze.name, freeze.directory = name, directory
        freeze.status, freeze.chosen = status, chosen
        return []


class Retire:
    name = "freeze"

    def plan(self, freeze: Freeze) -> list[Action]:
        status, chosen = freeze.status, freeze.chosen
        if status.state == lifecycle.FROZEN and status.authority == chosen.location:
            report.info(
                f"  {freeze.name} is frozen already, with this copy as its "
                "authoritative one."
            )
            return []
        retired = status.source_dir
        text = f"freeze {freeze.name}: {chosen.location} becomes its authoritative copy"
        if retired:
            text += f", and its source_dir {retired} is retired"

        def perform() -> None:
            dataset_status.take(
                freeze.directory,
                status,
                "record",
                dataset=freeze.name,
                copy=chosen.model_copy(update={"verified": dataset_status.now()}),
                source_dir=retired,
                changes={"source_dir": None, "authority": chosen.location},
            )

        return [Action(text, perform)]


PIPELINE: Pipeline[Freeze] = Pipeline("record", [Check(), Retire()])


@report.reported
def run(
    catalog_root: Path, dataset: str, *, copy: str | None = None, dry_run: bool = False
) -> int:
    """Freeze ``dataset`` with its authoritative copy checked; returns 0, or raises."""
    freeze = Freeze(catalog_root, dataset, copy)
    if PIPELINE.run(freeze, dry_run=dry_run) and not dry_run:
        report.info(
            f"\nrecorded     {freeze.name} is frozen; a rebuild keeps its inventory "
            "as it is"
        )
    return 0
