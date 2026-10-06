"""``catalog add``: take a reviewed draft into the catalogue.

    ethos-data catalog add /projects/shared/candidates/my-dataset --dry-run
    ethos-data catalog add /projects/shared/candidates/my-dataset
    ethos-data catalog add drafts/dataset.yaml --name my-dataset

A proposal brings a draft ``dataset.yaml``, beside the data or anywhere else,
that names the bytes with ``source_dir``. Accepting it is three stages:

``intake``  read the draft and check it as the build would: a name, a
            ``source_dir`` that is a directory, licence documents that exist
``place``   write ``datasets/<name>/dataset.yaml`` without ``source_dir``,
            copy its licence documents beside it, and write its
            ``status.yaml``: a draft built from that ``source_dir``
``build``   build it, which makes it built

A relative ``source_dir`` is relative to the draft, and is recorded as the
absolute path it names, symbolic links left as they are. The draft is copied
line by line, comments and all; only ``source_dir`` is left out. Run again
after an interruption, ``add`` places what is missing and builds the dataset:
the status file is written last, so a dataset without one is placed again.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
from ..formats import dataset as dataset_format
from ..formats import keys as k
from ..formats.edit import without_keys
from ..formats.status_file import StatusFile
from ..model import lifecycle
from ..model.names import relative
from . import DESCRIPTOR, _read_mapping, datasets_dir
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "AddResult", "Draft", "run"]


@dataclass
class Draft:
    """What ``add`` was given, and what its intake makes of it."""

    catalog_root: Path
    source: Path
    name: str | None = None
    #: The draft ``dataset.yaml``, its text and its keys.
    path: Path | None = None
    text: str = ""
    meta: dict = field(default_factory=dict)
    source_dir: Path | None = None
    documents: list[str] = field(default_factory=list)
    #: The text the catalogue's ``dataset.yaml`` gets.
    description: str = ""
    #: Placed by an earlier run, so only the build is left.
    placed: bool = False

    @property
    def directory(self) -> Path:
        return datasets_dir(self.catalog_root) / str(self.name)


class Intake:
    name = "intake"

    def plan(self, draft: Draft) -> list[Action]:
        source = draft.source.expanduser()
        path = source / DESCRIPTOR if source.is_dir() else source
        if not path.is_file():
            raise MaintenanceError(
                f"no draft at {path}: name its dataset.yaml, or the directory holding it"
            )
        draft.path = path = Path(os.path.abspath(path))
        draft.text = path.read_bytes().decode("utf-8")
        draft.meta = _read_mapping(path)
        self._name(draft)
        self._source_dir(draft)
        name = draft.name
        meta = {**draft.meta, k.NAME: name}
        for warning in dataset_format.check_draft(meta):
            report.warning(f"warning: {warning}")
        for entry in meta.get(k.LICENSES) or []:
            document = entry.get(k.DOCUMENT) if isinstance(entry, dict) else None
            if document and not (path.parent / document).is_file():
                raise MaintenanceError(
                    f"{name}: its licences name {k.DOCUMENT} {document}, which is "
                    f"not a file beside the draft, at {path.parent / document}"
                )
            if document:
                draft.documents.append(str(document))
        try:
            draft.description = without_keys(draft.text, [k.SOURCE_DIR])
        except ValueError:
            raise MaintenanceError(
                f"{name}: source_dir could not be left out of the draft line by "
                "line; write the draft as one key per line"
            ) from None
        self._target(draft)
        return []

    def _name(self, draft: Draft) -> None:
        stated = draft.meta.get(k.NAME)
        if draft.name and stated and draft.name != stated:
            raise MaintenanceError(
                f"the draft names the dataset {stated!r} and --name {draft.name!r}; "
                "the directory in the catalogue decides, so drop --name or fix the draft"
            )
        name = draft.name or stated
        if not name:
            raise MaintenanceError(
                f"{draft.path} names no dataset: add `name:` to it, or pass --name"
            )
        try:
            relative(str(name), "dataset name")
        except ValueError as error:
            raise MaintenanceError(str(error)) from None
        draft.name = str(name)

    def _source_dir(self, draft: Draft) -> None:
        raw = draft.meta.get(k.SOURCE_DIR)
        if not raw:
            raise MaintenanceError(
                f"{draft.name}: the draft names no source_dir, so there is nothing to "
                "build the dataset from"
            )
        source = Path(str(raw)).expanduser()
        if not source.is_absolute():
            source = Path(os.path.abspath(draft.path.parent / source))
        if not source.is_dir():
            raise MaintenanceError(
                f"{draft.name}: its source_dir {source} is not a directory"
            )
        draft.source_dir = source

    def _target(self, draft: Draft) -> None:
        target = draft.directory
        if not (target / DESCRIPTOR).is_file():
            return
        status = dataset_status.read(target)
        described = (target / DESCRIPTOR).read_bytes().decode(
            "utf-8"
        ) == draft.description
        if described and status is None:
            # An earlier run stopped inside ``place``, before the status file,
            # which it writes last: place the draft again.
            return
        same = (
            described
            and status is not None
            and status.state == lifecycle.DRAFT
            and status.source_dir == str(draft.source_dir)
        )
        if not same:
            state = status.state if status is not None else "described"
            raise MaintenanceError(
                f"{draft.name} is in the catalogue already ({state}), at {target}. "
                "Change it there and rebuild it with\n"
                f"    ethos-data catalog build {draft.name}"
            )
        draft.placed = True


class Place:
    name = "place"

    def plan(self, draft: Draft) -> list[Action]:
        if draft.placed:
            return []
        where = f"datasets/{draft.name}"
        actions = [
            Action(
                f"write {where}/{DESCRIPTOR}, without source_dir", self._describe(draft)
            )
        ]
        for document in draft.documents:
            actions.append(Action(f"copy {document}", self._copy(draft, document)))
        actions.append(
            Action(
                f"write {where}/{dataset_status.STATUS}: draft, built from "
                f"{draft.source_dir}",
                self._status(draft),
            )
        )
        return actions

    @staticmethod
    def _describe(draft: Draft):
        def write() -> None:
            draft.directory.mkdir(parents=True, exist_ok=True)
            (draft.directory / DESCRIPTOR).write_bytes(
                draft.description.encode("utf-8")
            )

        return write

    @staticmethod
    def _copy(draft: Draft, document: str):
        def copy() -> None:
            target = draft.directory / document
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(draft.path.parent / document, target)

        return copy

    @staticmethod
    def _status(draft: Draft):
        def write() -> None:
            dataset_status.write(
                draft.directory,
                StatusFile(
                    state=lifecycle.DRAFT,
                    source_dir=str(draft.source_dir),
                    history=[
                        dataset_status.event(
                            "add", lifecycle.DRAFT, note=f"from {draft.path}"
                        )
                    ],
                ),
            )

        return write


class Build:
    name = "build"

    def plan(self, draft: Draft) -> list[Action]:
        def build() -> None:
            from . import manifest

            manifest.run(draft.catalog_root, [str(draft.name)])

        def built() -> str:
            status = dataset_status.read(draft.directory)
            state = status.state if status is not None else None
            return "" if state == lifecycle.BUILT else f"it is {state}, not built"

        return [Action(f"build {draft.name}", build, built)]


PIPELINE: Pipeline[Draft] = Pipeline("add", [Intake(), Place(), Build()])


@dataclass(frozen=True)
class AddResult:
    """The dataset ``catalog add`` took in, or would take in."""

    dataset: str
    #: Whether it was placed and built: not for a dry run.
    built: bool

    @property
    def ok(self) -> bool:
        return True


@report.reported
def run(
    catalog_root: Path,
    source: str | Path,
    *,
    name: str | None = None,
    dry_run: bool = False,
) -> AddResult:
    """Take the draft at ``source`` into the catalogue and build it, or raise why not."""
    draft = Draft(catalog_root, Path(source), name)
    PIPELINE.run(draft, dry_run=dry_run)
    if not dry_run:
        report.info(
            f"\n{draft.name} is built. Check its inventory against the proposal, then "
            "make its bytes available; `ethos-data catalog status` says how."
        )
    return AddResult(str(draft.name), not dry_run)
