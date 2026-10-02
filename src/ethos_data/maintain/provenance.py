"""``catalog check-source``: compare a fresh download with what the catalogue recorded.

    ethos-data catalog check-source global-wind-atlas-v4 /validation/gwa-v4 --dry-run
    ethos-data catalog check-source global-wind-atlas-v4 /validation/gwa-v4 \\
        --note "against the 2026-09 release on the provider's site"

Provenance is checked by downloading a dataset from its source again, into a
folder apart from every cache, and comparing the bytes with the inventory.
This is the comparison and its record, in two stages:

``compare``  hash every file under the folder whose path the inventory lists,
             and compare its size and SHA-256 with the recorded ones
``record``   add the result to the dataset's ``status.yaml``

A sample is enough: the files under the folder are the ones compared, and the
record says how many of the inventory's that is. A file the inventory does not
list is reported and not compared. Only downloaded data has a source to check
against; created and derived data is reviewed by its author, inputs and
derivation instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
from ..formats import keys as k
from ..model import digest, lifecycle
from . import read_descriptor, resources_of
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "Check", "run"]


@dataclass
class Check:
    """One comparison: the dataset, the folder holding the fresh download, and the outcome."""

    catalog_root: Path
    dataset: str
    folder: Path
    note: str = ""
    matched: list[str] = field(default_factory=list)
    differ: list[str] = field(default_factory=list)
    unlisted: list[str] = field(default_factory=list)
    inventory: int = 0

    @property
    def summary(self) -> str:
        compared = len(self.matched) + len(self.differ)
        text = (
            f"{compared} of {self.inventory} files compared with {self.folder}: "
            f"{len(self.matched)} match, {len(self.differ)} differ"
        )
        return f"{text}; {self.note}" if self.note else text


class Compare:
    name = "compare"

    def plan(self, check: Check) -> list[Action]:
        directory = dataset_status.dataset_dir_in(check.catalog_root, check.dataset)
        status = dataset_status.read(directory)
        if status is None:
            raise MaintenanceError(
                f"{check.dataset} has no {dataset_status.STATUS} yet to record the "
                f"check in. Write one with\n    ethos-data catalog migrate {check.dataset}"
            )
        lifecycle.step("check-source", status.state, check.dataset)
        origin = read_descriptor(directory).get(k.ORIGIN, k.DOWNLOADED)
        if origin != k.DOWNLOADED:
            raise MaintenanceError(
                f"{check.dataset} is {origin}, so it has no source to download it "
                "from again. Its review checks the authors, the inputs and the "
                "derivation instead."
            )
        if not check.folder.is_dir():
            raise MaintenanceError(f"{check.folder} is not a directory")
        package = json.loads((directory / "datapackage.json").read_text("utf-8"))
        recorded = {
            resource[k.PATH]: resource for resource in resources_of(package, directory)
        }
        check.inventory = len(recorded)
        for path in sorted(p for p in check.folder.rglob("*") if p.is_file()):
            relative = path.relative_to(check.folder).as_posix()
            resource = recorded.get(relative)
            if resource is None:
                check.unlisted.append(relative)
                continue
            same = path.stat().st_size == resource[k.BYTES] and digest.matches(
                resource[k.HASH], digest.of_file(path)
            )
            (check.matched if same else check.differ).append(relative)
        for relative in check.differ:
            report.info(f"  differs      {relative}")
        for relative in check.unlisted:
            report.info(f"  not listed   {relative}")
        if not check.matched and not check.differ:
            raise MaintenanceError(
                f"no file under {check.folder} is one the inventory of "
                f"{check.dataset} lists; download them with the paths the "
                "catalogue records"
            )
        return []


class Record:
    name = "record"

    def plan(self, check: Check) -> list[Action]:
        def record() -> None:
            directory = dataset_status.dataset_dir_in(check.catalog_root, check.dataset)
            dataset_status.take(
                directory,
                dataset_status.read(directory),
                "check-source",
                dataset=check.dataset,
                note=check.summary,
                files=len(check.matched) + len(check.differ),
            )

        return [Action(f"record: {check.summary}", record)]


PIPELINE: Pipeline[Check] = Pipeline("check-source", [Compare(), Record()])


@report.reported
def run(
    catalog_root: Path,
    dataset: str,
    folder: str | Path,
    *,
    note: str = "",
    dry_run: bool = False,
) -> int:
    """Compare ``folder`` with the inventory of ``dataset`` and record the result.

    Returns 1 when a file differs, else 0.
    """
    check = Check(catalog_root, dataset, Path(folder).expanduser(), note)
    PIPELINE.run(check, dry_run=dry_run)
    return 1 if check.differ else 0
