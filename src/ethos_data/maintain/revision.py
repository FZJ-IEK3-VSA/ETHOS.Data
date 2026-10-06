"""``catalog build --revision``: a new revision of a dataset whose bytes are published.

    ethos-data catalog build era5 --revision --from /corrected/era5 --dry-run
    ethos-data catalog build era5 --revision --from /corrected/era5

Published objects never change, so other bytes for a dataset that was
uploaded or materialized are a new revision: the same dataset under the same
keys, its changed and new files published under ``<remote_prefix>@<revision>/``
and its unchanged ones left where they are. Two stages:

``compare``  build the inventory of the corrected files and compare it with
             the one recorded: the files that changed, the new ones, the gone
``revise``   write it as the next revision and record that; the dataset is
             built again, its new bytes still to be made available, and its
             authoritative copy is none until a copy of them is recorded

Both inventories are read by the one inventory reader. Run again after an
interruption between writing the revision and recording it, the command
records what it wrote.

A file that goes takes its key with it, and every collection that names the
key breaks. That is refused unless ``--remove-missing`` says it is meant: a
layout that changed so much is usually a successor, a new dataset whose
``dataset.yaml`` says ``ethos:supersedes``. A dataset that is only linked has
no revisions; it changes in place with its source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
from ..formats import keys as k
from ..formats.status_file import StatusFile
from . import datasets_dir
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "Revision", "RevisionResult", "run"]


@dataclass
class Revision:
    """One new revision: the dataset, its corrected files, and what changed."""

    catalog_root: Path
    dataset: str
    source: Path | None = None
    remove_missing: bool = False
    directory: Path | None = None
    status: StatusFile | None = None
    number: int = 0
    files: dict[str, str] = field(default_factory=dict)
    changed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    #: Written by an earlier run that stopped before recording it.
    written: bool = False

    @property
    def summary(self) -> str:
        if self.written:
            return "written before an interruption"
        return (
            f"{len(self.changed)} changed, {len(self.added)} new, "
            f"{len(self.removed)} gone"
        )


class Compare:
    name = "compare"

    def plan(self, revision: Revision) -> list[Action]:
        from . import manifest

        name = revision.dataset
        directory = dataset_status.dataset_dir_in(revision.catalog_root, name)
        status = dataset_status.checked_status(directory, name, "revise")
        if not any(
            copy.kind in (k.COPY_UPLOADED, k.COPY_MATERIALIZED)
            for copy in status.copies
        ):
            raise MaintenanceError(
                f"{name} has no bytes the catalogue published or owns, only links to "
                "its source, so it has no revisions: it changes in place with its "
                f"source. Rebuild it with\n    ethos-data catalog build {name}"
            )
        source = revision.source or (
            Path(status.source_dir) if status.source_dir else None
        )
        if source is None:
            raise MaintenanceError(
                f"{name} has no source_dir left; name the corrected files with --from"
            )
        if not source.is_absolute():
            source = (directory / source).resolve()
        if not source.is_dir():
            raise MaintenanceError(f"{source} is not a directory")
        number = status.revision + 1
        revision.directory, revision.status = directory, status
        revision.number, revision.source = number, source
        package = json.loads((directory / k.PACKAGE_FILE).read_text("utf-8"))
        if int(package.get(k.REVISION, 1)) == number:
            # Written by a run that stopped before it recorded the revision.
            revision.written = True
            report.info(f"  {self.name:<12} revision {number} of {name} is written")
            return []
        root = datasets_dir(revision.catalog_root)
        files = manifest.render_dataset(
            directory,
            check=True,
            name=name,
            inherited=manifest.inherited_for(root, directory),
            superseded_by=manifest.superseded_by_map(revision.catalog_root).get(name),
            source=source,
            revision=number,
        )
        before = manifest.records_on_disk(name, directory)
        after = manifest.rendered_records(name, directory, files)
        revision.changed = sorted(
            path
            for path in after
            if path in before and after[path][k.HASH] != before[path][k.HASH]
        )
        revision.added = sorted(set(after) - set(before))
        revision.removed = sorted(set(before) - set(after))
        if not (revision.changed or revision.added or revision.removed):
            raise MaintenanceError(
                f"the files under {source} are the ones revision {status.revision} "
                f"of {name} holds; there is nothing to make a revision of"
            )
        if revision.removed and not revision.remove_missing:
            listed = ", ".join(revision.removed[:5])
            more = (
                f" and {len(revision.removed) - 5} more"
                if len(revision.removed) > 5
                else ""
            )
            raise MaintenanceError(
                f"the new files of {name} leave out {listed}{more}. Each takes its key "
                "with it, and every collection that names one breaks. If the layout "
                "changed, make a successor: a new dataset whose dataset.yaml says\n"
                f"    {k.SUPERSEDES}: {name}\n"
                "If the files are meant to go, pass --remove-missing."
            )
        for path in revision.changed:
            report.info(f"  changed      {path}")
        for path in revision.added:
            report.info(f"  new          {path}")
        for path in revision.removed:
            report.info(f"  gone         {path}")
        revision.files = files
        return []


class Revise:
    name = "revise"

    def plan(self, revision: Revision) -> list[Action]:
        def revise() -> None:
            from . import manifest

            if revision.files:
                manifest.write_dataset(revision.directory, revision.files)
            package = json.loads(
                (revision.directory / k.PACKAGE_FILE).read_text(encoding="utf-8")
            )
            dataset_status.take(
                revision.directory,
                revision.status,
                "revise",
                dataset=revision.dataset,
                # The authoritative copy holds the bytes of the revision before.
                changes={
                    "revision": revision.number,
                    "source_dir": str(revision.source),
                    "authority": None,
                },
                note=f"revision {revision.number}: {revision.summary}",
                files=package[k.FILE_COUNT],
                bytes=package[k.TOTAL_BYTES],
            )
            manifest.write_index(revision.catalog_root)

        verb = "record" if revision.written else "write and record"
        return [
            Action(
                f"{verb} revision {revision.number} of {revision.dataset}: "
                f"{revision.summary}",
                revise,
            )
        ]


PIPELINE: Pipeline[Revision] = Pipeline("revision", [Compare(), Revise()])


@dataclass(frozen=True)
class RevisionResult:
    """The revision ``catalog build --revision`` made, or would make."""

    dataset: str
    number: int
    #: Whether it was written and recorded: not for a dry run.
    made: bool

    @property
    def ok(self) -> bool:
        return True


@report.reported
def run(
    catalog_root: Path,
    dataset: str,
    *,
    source: str | Path | None = None,
    remove_missing: bool = False,
    dry_run: bool = False,
) -> RevisionResult:
    """Make the next revision of ``dataset`` from ``source``, or its ``source_dir``."""
    revision = Revision(
        catalog_root,
        dataset,
        Path(source).expanduser() if source is not None else None,
        remove_missing,
    )
    PIPELINE.run(revision, dry_run=dry_run)
    if not dry_run:
        report.info(
            f"\n{dataset} is built as revision {revision.number}. Make its new bytes "
            "available, as for the first: `ethos-data catalog status` says how."
        )
    return RevisionResult(dataset, revision.number, not dry_run)
