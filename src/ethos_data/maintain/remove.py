"""``catalog remove``: take datasets out of the catalogue, metadata first.

    ethos-data catalog remove old-dataset --reason "accepted by mistake" --dry-run
    ethos-data catalog remove old-dataset --reason "accepted by mistake"

Removing is the reverse of publishing: metadata first, bytes second, because
a catalogue that points at deleted bytes breaks every reader half-way. This is
the first half, in two stages:

``withdraw``  record every dataset named -- a family stands for its members --
              as withdrawn, with the reason
``index``     rebuild the index, and the families above them, without them

A withdrawn dataset is left out of every later build and of the public
catalogue. Its description, inventory and status file stay where they are,
and so do its cache entries and its bytes on dCache: they go once a release
without it is out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
from ..model import lifecycle
from . import dataset_name_for, datasets_dir, is_namespace
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "Removal", "run"]


@dataclass
class Removal:
    """The datasets ``remove`` was asked to take out, and why."""

    catalog_root: Path
    names: list[str]
    reason: str = ""
    #: Each dataset to withdraw, by name, with its directory: set by ``withdraw``.
    datasets: list[tuple[str, Path]] = field(default_factory=list)


class Withdraw:
    name = "withdraw"

    def plan(self, removal: Removal) -> list[Action]:
        removal.datasets = dataset_status.datasets(removal.catalog_root, removal.names)
        if not removal.datasets:
            raise MaintenanceError(
                f"{', '.join(removal.names)} has no dataset with files to remove"
            )
        actions = []
        for name, directory in removal.datasets:
            status = dataset_status.read(directory)
            if status is None:
                raise MaintenanceError(
                    f"{name} has no {dataset_status.STATUS} yet to record the removal "
                    f"in. Write one from its dataset.yaml with\n"
                    f"    ethos-data catalog migrate {name}"
                )
            if status.state == lifecycle.WITHDRAWN:
                continue
            lifecycle.step("remove", status.state, name)
            actions.append(
                Action(
                    f"withdraw {name}, {status.state}", self._withdraw(removal, name)
                )
            )
        return actions

    @staticmethod
    def _withdraw(removal: Removal, name: str):
        def withdraw() -> None:
            directory = dataset_status.dataset_dir_in(removal.catalog_root, name)
            dataset_status.take(
                directory,
                dataset_status.read(directory),
                "remove",
                dataset=name,
                note=removal.reason or None,
            )

        return withdraw


class Index:
    name = "index"

    def plan(self, removal: Removal) -> list[Action]:
        families = sorted(
            {
                dataset_name_for(datasets_dir(removal.catalog_root), parent)
                for _, directory in removal.datasets
                for parent in directory.parents
                if parent.is_relative_to(datasets_dir(removal.catalog_root))
                and parent != datasets_dir(removal.catalog_root)
                and (parent / "dataset.yaml").is_file()
                and is_namespace(parent)
            }
        )
        text = "rebuild the index" + (f" and {', '.join(families)}" if families else "")

        def rebuild() -> None:
            from . import manifest

            if families and manifest.run(removal.catalog_root, families):
                raise MaintenanceError(f"rebuilding {', '.join(families)} failed")
            manifest.write_index(removal.catalog_root)

        def gone() -> str:
            index = json.loads(
                (removal.catalog_root / "datacatalog.json").read_text(encoding="utf-8")
            )
            listed = {row.get("name") for row in index.get("datasets", [])}
            still = [name for name, _ in removal.datasets if name in listed]
            return f"the index still lists {', '.join(still)}" if still else ""

        return [Action(text, rebuild, gone)]


PIPELINE: Pipeline[Removal] = Pipeline("remove", [Withdraw(), Index()])


@report.reported
def run(
    catalog_root: Path,
    names: list[str],
    *,
    reason: str = "",
    dry_run: bool = False,
) -> int:
    """Withdraw ``names`` -- datasets or families -- and rebuild the index without them."""
    removal = Removal(catalog_root, list(names), reason)
    PIPELINE.run(removal, dry_run=dry_run)
    if not dry_run:
        report.info(
            "\nPublish and release the catalogue without them. Their cache entries "
            "and their bytes on dCache stay until that release is out."
        )
    return 0
