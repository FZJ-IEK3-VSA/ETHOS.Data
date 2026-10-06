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
and so do its cache entries and its bytes on dCache, until a major release is
recorded after the removal: the releases of the current major made before it
still describe the dataset.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
from ..model import lifecycle
from . import dataset_name_for, datasets_dir, is_namespace, read_descriptor
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "Removal", "RemoveResult", "run"]


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
            meta = read_descriptor(directory)
            status = dataset_status.build_input(directory, meta, name).status
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

            if families:
                manifest.run(removal.catalog_root, families)
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


@dataclass(frozen=True)
class RemoveResult:
    """The datasets ``catalog remove`` withdrew, or would withdraw."""

    datasets: list[str]
    #: Whether the status files and the index were written: not for a dry run.
    written: bool

    @property
    def ok(self) -> bool:
        return True


@report.reported
def run(
    catalog_root: Path,
    names: list[str],
    *,
    reason: str = "",
    dry_run: bool = False,
) -> RemoveResult:
    """Withdraw ``names`` -- datasets or families -- and rebuild the index without them."""
    removal = Removal(catalog_root, list(names), reason)
    PIPELINE.run(removal, dry_run=dry_run)
    if not dry_run:
        report.info(
            "\nCommit the withdrawal, merge it and release the catalogue: a "
            "withdrawal needs a minor release. Their cache entries and their bytes "
            "on dCache stay until a major release is recorded after the removal."
        )
    return RemoveResult([name for name, _ in removal.datasets], not dry_run)
