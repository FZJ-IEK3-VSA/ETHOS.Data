"""Each dataset's ``status.yaml``: where it stands, and the steps that brought it there.

    ethos-data catalog status                  # every dataset, its state and next step
    ethos-data catalog status era5 --check     # and whether the record still holds

A status file sits beside every ``dataset.yaml`` that describes files. The
commands write it, and nobody else: ``catalog build`` records a first build and
a changed inventory, ``catalog upload`` a verified upload, ``catalog record``
the freeze, and ``ethos-data link`` and ``materialize`` a copy they made when
they are given ``--catalog-root``. Each of them asks :mod:`~ethos_data.model.lifecycle`
first whether the dataset's state allows the step, so a draft is never
uploaded and a frozen dataset never rebuilt from local files.

``dataset.yaml`` describes the data and nothing else. A dataset without a
status file, or whose ``dataset.yaml`` says where its bytes are as well, is
refused by every step; ``catalog migrate`` writes the status file.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import ValidationError

from .. import report
from ..adapters import Git, Store
from ..config import current_user
from ..errors import DescriptorError, MaintenanceError
from ..formats import keys as k
from ..formats import status_file
from ..formats.dataset import describe
from ..formats.derived import license_settled
from ..formats.status_file import Copy, Event, StatusFile
from ..model import lifecycle
from ..model.versions import Version
from . import (
    _read_mapping,
    dataset_name_for,
    datasets_dir,
    inventory_of,
    is_namespace,
    iter_dataset_dirs,
    read_descriptor,
    source_dir_of,
)

__all__ = [
    "CONVERTED",
    "STATUS",
    "BuildInput",
    "Finding",
    "StatusResult",
    "build_input",
    "check_copy",
    "datasets",
    "evidence",
    "read",
    "run",
    "take",
    "withdrawn",
    "write",
]

STATUS = status_file.FILENAME

#: The keys of ``dataset.yaml`` that ``catalog migrate`` moves into a status
#: file. A dataset that states one is refused; `catalog migrate` converts it.
CONVERTED = (k.SOURCE_DIR, "ethos:uploaded", "ethos:frozen")

HEADER = (
    "# Written by the ethos-data catalog commands; do not edit it by hand.\n"
    "# `ethos-data catalog status` shows where each dataset stands.\n"
)


def now() -> str:
    """The time a step is recorded at: UTC, to the second."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def path_of(dataset_dir: Path) -> Path:
    return dataset_dir / STATUS


def read(dataset_dir: Path) -> StatusFile | None:
    """A dataset's status file, checked against its rules; None when it has none."""
    path = path_of(dataset_dir)
    if not path.is_file():
        return None
    try:
        status = StatusFile.model_validate(_read_mapping(path))
        status_file.check(status)
    except ValidationError as error:
        raise DescriptorError(f"{path}: {'; '.join(describe(error))}") from None
    except DescriptorError as error:
        raise DescriptorError(f"{path}: {error.message}") from None
    return status


def _document(status: StatusFile) -> dict:
    """The file's keys, in the specification's order, without empty ones."""
    document = status.model_dump(by_alias=True, exclude_none=True)
    if not document.get(k.COPIES):
        document.pop(k.COPIES, None)
    if document.get("revision") == 1:
        document.pop("revision")
    return document


def write(dataset_dir: Path, status: StatusFile) -> Path:
    """Write ``status`` beside the dataset's ``dataset.yaml``, with LF line ends."""
    status_file.check(status)
    path = path_of(dataset_dir)
    path.write_text(
        HEADER
        + yaml.safe_dump(
            _document(status), sort_keys=False, allow_unicode=True, width=100
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


def event(step: str, state: str, *, previous: str | None = None, **details) -> Event:
    """One history entry for ``step``, taken now by whoever runs this."""
    return Event(
        at=now(),
        by=current_user(),
        step=step,
        previous=previous if previous != state else None,
        state=state,
        **details,
    )


def _with_copy(copies: list[Copy], copy: Copy) -> list[Copy]:
    """``copies`` with ``copy`` in place of the one at the same location, or added."""
    kept = [each for each in copies if each.location != copy.location]
    return [*kept, copy]


def take(
    dataset_dir: Path,
    status: StatusFile,
    step: str,
    *,
    dataset: str,
    copy: Copy | None = None,
    changes: Mapping | None = None,
    **details,
) -> StatusFile:
    """Take ``step``: check the state allows it, record it, and write the file.

    ``copy`` is a copy the step made or checked, recorded in place of an
    earlier one at the same location; ``changes`` sets other keys of the status
    file, and ``details`` are the history entry's. Returns the new status.
    """
    after = lifecycle.step(step, status.state, dataset)
    update: dict = {
        "state": after,
        "history": [
            *status.history,
            event(step, after, previous=status.state, copy_=copy, **details),
        ],
    }
    if copy is not None:
        update["copies"] = _with_copy(status.copies, copy)
    update.update(changes or {})
    taken = status.model_copy(update=update)
    write(dataset_dir, taken)
    return taken


# -- where the build reads the bytes ---------------------------------------------


@dataclass(frozen=True)
class BuildInput:
    """Where a dataset's bytes are read from, and whether its inventory is final."""

    source_dir: Path | None
    frozen: bool
    status: StatusFile


def build_input(dataset_dir: Path, meta: Mapping, dataset: str) -> BuildInput:
    """The build input of the dataset in ``dataset_dir``, ``meta`` its ``dataset.yaml``.

    From its status file, the one record of where the bytes are: a dataset
    without one, or whose ``dataset.yaml`` states any of :data:`CONVERTED` as
    well, is refused, naming ``catalog migrate``.
    """
    status = read(dataset_dir)
    stated = [key for key in CONVERTED if key in meta]
    if status is None or stated:
        what = (
            f"its dataset.yaml states {', '.join(stated)}"
            if stated
            else f"it has no {STATUS}"
        )
        raise DescriptorError(
            f"{dataset}: {what}; its {STATUS} says where its bytes are. Write it "
            f"with\n    ethos-data catalog migrate {dataset}"
        )
    return BuildInput(
        source_dir_of(dataset_dir, {k.SOURCE_DIR: status.source_dir}),
        status.state == lifecycle.FROZEN,
        status,
    )


def withdrawn(dataset_dir: Path) -> bool:
    """Whether the dataset was taken out of the catalogue: withdrawn or purged."""
    status = read(dataset_dir)
    return status is not None and status.state in (
        lifecycle.WITHDRAWN,
        lifecycle.PURGED,
    )


def checked_status(dataset_dir: Path, dataset: str, step: str) -> StatusFile:
    """The dataset's status, after checking it allows ``step``."""
    status = build_input(dataset_dir, read_descriptor(dataset_dir), dataset).status
    lifecycle.step(step, status.state, dataset)
    return status


def dataset_dir_in(catalog_root: Path, dataset: str) -> Path:
    """The directory of ``dataset`` in the checkout, or MaintenanceError."""
    directory = datasets_dir(catalog_root) / dataset
    if not (directory / "dataset.yaml").is_file():
        raise MaintenanceError(
            f"no dataset called {dataset!r} in {datasets_dir(catalog_root)}"
        )
    return directory


def allow(catalog_root: Path, dataset: str, step: str) -> None:
    """Refuse, before it acts, a step the dataset's state in the checkout does not allow."""
    checked_status(dataset_dir_in(catalog_root, dataset), dataset, step)


def record_copy(
    catalog_root: Path,
    dataset: str,
    step: str,
    copy: Copy,
    *,
    repeat: bool = True,
    **details,
) -> str:
    """Take ``step`` for ``dataset`` in the checkout, recording ``copy``.

    Returns the dataset's state afterwards. ``repeat=False`` records nothing
    when the step would change nothing: the same copy, already recorded, in a
    state it keeps.
    """
    directory = dataset_dir_in(catalog_root, dataset)
    status = build_input(directory, read_descriptor(directory), dataset).status
    after = lifecycle.step(step, status.state, dataset)
    if not repeat and after == status.state and copy in status.copies:
        return after
    return take(directory, status, step, dataset=dataset, copy=copy, **details).state


def releases(status: StatusFile) -> tuple[str | None, int]:
    """The last release that holds the dataset's steps, and how many came after it."""
    last, after = None, 0
    for entry in status.history:
        if entry.step == "release":
            last, after = entry.release, 0
        else:
            after += 1
    return last, after


def since_release(status: StatusFile) -> list[Event]:
    """The steps the dataset took after its last release step: every one, without one."""
    last = max(
        (
            index
            for index, entry in enumerate(status.history)
            if entry.step == "release"
        ),
        default=-1,
    )
    return status.history[last + 1 :]


def major_release_after(status: StatusFile, step: str) -> str | None:
    """The first major release recorded after the last ``step``, or None."""
    seen, found = False, None
    for entry in status.history:
        if entry.step == step:
            seen, found = True, None
        elif (
            seen
            and found is None
            and entry.step == "release"
            and entry.release
            and Version.parse(entry.release).is_major
        ):
            found = entry.release
    return found


# -- whether the record still holds ----------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One thing ``catalog status --check`` compared, and whether it held."""

    ok: bool
    text: str

    def __str__(self) -> str:
        return f"{'ok' if self.ok else 'FAIL':<5} {self.text}"


def _same_target(current: str | Path, recorded: str | Path) -> bool:
    """Link targets compared as text, without Windows's ``\\\\?\\`` prefix."""
    return str(current).removeprefix("\\\\?\\") == str(recorded).removeprefix("\\\\?\\")


def _files_under(entry: Path, resources: list[dict]) -> list[str]:
    """The inventory's files that are missing under ``entry`` or have another size."""
    wrong = []
    for resource in resources:
        path = entry / resource[k.PATH]
        try:
            size = path.stat().st_size
        except OSError:
            wrong.append(f"{resource[k.PATH]} is missing")
            continue
        if size != resource[k.BYTES]:
            wrong.append(
                f"{resource[k.PATH]} has {size:,} bytes, not {resource[k.BYTES]:,}"
            )
    return wrong


def check_copy(copy: Copy, resources: list[dict], store: Store) -> Finding:
    """Whether ``copy`` still holds every file of the inventory, at its recorded size.

    An upload is read back through ``store`` anonymously, as any public reader
    would ask for it; a cache entry is looked at on this machine.
    """
    where = f"{copy.kind} {copy.location}"
    if copy.kind == k.COPY_UPLOADED:
        from .upload import read_back

        _ok, missing, wrong = read_back(store, resources, copy.location)
        if missing or wrong:
            return Finding(
                False,
                f"{where}: {len(missing)} of {len(resources)} files not readable, "
                f"{len(wrong)} of another size",
            )
        return Finding(
            True, f"{where}: {len(resources)} of {len(resources)} files readable"
        )
    entry = Path(copy.location)
    if copy.kind == k.COPY_LINKED:
        if not entry.is_symlink():
            state = "is a real directory now" if entry.exists() else "is missing"
            return Finding(False, f"{where}: the entry {state}")
        if copy.target is not None and not _same_target(entry.readlink(), copy.target):
            return Finding(
                False, f"{where}: points at {entry.readlink()}, recorded {copy.target}"
            )
    elif entry.is_symlink() or not entry.is_dir():
        state = "is a link now" if entry.is_symlink() else "is missing"
        return Finding(False, f"{where}: the entry {state}")
    wrong = _files_under(entry, resources)
    if wrong:
        return Finding(False, f"{where}: {len(wrong)} files differ, first {wrong[0]}")
    return Finding(True, f"{where}: all {len(resources)} files there")


def _inventory(
    catalog_root: Path, dataset_dir: Path, dataset: str, superseded: Mapping
) -> Finding:
    from . import manifest

    try:
        files = manifest.render_dataset(
            dataset_dir,
            check=True,
            name=dataset,
            inherited=manifest.inherited_for(datasets_dir(catalog_root), dataset_dir),
            superseded_by=superseded.get(dataset),
        )
    except MaintenanceError as error:
        return Finding(False, f"the build refuses it: {error.message}")
    if manifest.stale_files(dataset_dir, files):
        return Finding(
            False,
            f"datapackage.json is out of date: ethos-data catalog build {dataset}",
        )
    return Finding(True, "datapackage.json is current")


def evidence(
    catalog_root: Path,
    dataset_dir: Path,
    dataset: str,
    status: StatusFile,
    store: Store,
    superseded: Mapping | None = None,
) -> list[Finding]:
    """What a dataset's record claims, compared with what is there.

    The descriptor a build would write, the build input a draft needs, and
    every recorded copy, file by file. ``superseded`` is the catalogue's
    successors by dataset, read for each call that does not pass it.
    """
    if superseded is None:
        from . import manifest

        superseded = manifest.superseded_by_map(catalog_root)
    meta = read_descriptor(dataset_dir)
    if status.state == lifecycle.DRAFT:
        try:
            source = build_input(dataset_dir, meta, dataset).source_dir
        except MaintenanceError as error:
            return [Finding(False, error.message.splitlines()[0])]
        if source is None or not source.is_dir():
            return [Finding(False, f"source_dir does not exist: {source}")]
        return [Finding(True, f"source_dir is there: {source}")]
    if status.state in (lifecycle.WITHDRAWN, lifecycle.PURGED):
        return []

    findings = [_inventory(catalog_root, dataset_dir, dataset, superseded)]
    if not (dataset_dir / "datapackage.json").is_file():
        return findings
    resources = inventory_of(dataset, dataset_dir).records()
    access = meta.get(k.ACCESS, k.PUBLIC)
    for copy in status.copies:
        if copy.kind == k.COPY_UPLOADED and access == k.RESTRICTED:
            findings.append(
                Finding(
                    False,
                    f"{copy.kind} {copy.location}: the dataset is restricted now, "
                    "and a copy of it is on dCache",
                )
            )
            continue
        findings.append(check_copy(copy, resources, store))
    if status.state == lifecycle.AVAILABLE and not status.copies:
        findings.append(Finding(False, "available, but no copy is recorded"))
    if status.state == lifecycle.FROZEN and status.authority is None:
        findings.append(
            Finding(
                False,
                "frozen, but where its authoritative copy is was never recorded: "
                f"record the copy, then ethos-data catalog record {dataset}",
            )
        )
    return findings


# -- the command ---------------------------------------------------------------


def datasets(
    catalog_root: Path, names: list[str], *, tombstones: bool = False
) -> list[tuple[str, Path]]:
    """The named datasets, or every one with files, as (name, directory).

    ``tombstones`` adds, to every dataset, those purged: a directory holding
    only its ``status.yaml``.
    """
    root = datasets_dir(catalog_root)
    if names:
        found = []
        for name in names:
            directory = root / name
            if not (directory / "dataset.yaml").is_file():
                raise MaintenanceError(f"no dataset called {name!r} in {root}")
            if is_namespace(directory):
                found += [
                    (dataset_name_for(root, member), member)
                    for member in iter_dataset_dirs(directory)
                    if member != directory and not is_namespace(member)
                ]
            else:
                found.append((name, directory))
        return found
    found = [
        (dataset_name_for(root, directory), directory)
        for directory in iter_dataset_dirs(root)
        if not is_namespace(directory)
    ]
    if tombstones and root.is_dir():
        found += [
            (dataset_name_for(root, path.parent), path.parent)
            for path in sorted(root.rglob(STATUS))
            if not (path.parent / "dataset.yaml").is_file()
        ]
    return sorted(found)


@dataclass
class StatusResult:
    """Each dataset's state, and the findings ``--check`` made, by dataset."""

    states: dict[str, str] = field(default_factory=dict)
    findings: dict[str, list[Finding]] = field(default_factory=dict)
    #: The datasets whose status file is missing or cannot be read.
    unreadable: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unreadable and all(
            finding.ok for found in self.findings.values() for finding in found
        )


@report.reported
def run(
    catalog_root: Path,
    names: list[str],
    *,
    check: bool = False,
    store: Store | None = None,
    git: Git | None = None,
) -> StatusResult:
    """List each dataset's state and next step; with ``check``, test the record.

    ``store`` reads uploads back, dCache's public door by default. ``git``
    reaches the clone, for the smallest admissible next release; without a git
    checkout, that line is left out. The result is not ``ok`` when a status
    file is missing or cannot be read, or a record does not hold.
    """
    if store is None:
        from ..adapters.dcache import DcacheStore

        store = DcacheStore()
    result = StatusResult()
    rows = datasets(catalog_root, names, tombstones=not names)
    superseded: Mapping = {}
    if check:
        from . import manifest

        superseded = manifest.superseded_by_map(catalog_root)
    width = max([len(name) for name, _ in rows] + [7])
    report.info(
        f"  {'dataset':<{width}}  {'state':<10} {'access':<11} {'release':<16} next"
    )
    for name, dataset_dir in rows:
        described = (dataset_dir / "dataset.yaml").is_file()
        meta = read_descriptor(dataset_dir) if described else {}
        access = meta.get(k.ACCESS, k.PUBLIC) if described else "-"
        try:
            status = read(dataset_dir)
        except DescriptorError as error:
            result.unreadable.append(name)
            report.info(
                f"  {name:<{width}}  {'?':<10} {access:<11} {'':<16} {error.message}"
            )
            continue
        if status is None:
            result.unreadable.append(name)
            hint = f"ethos-data catalog migrate {name}"
            report.info(f"  {name:<{width}}  {'-':<10} {access:<11} {'-':<16} {hint}")
            continue
        result.states[name] = status.state
        last, after = releases(status)
        release = (last or "-") + (f" +{after}" if after and last else "")
        hint = lifecycle.next_step(
            name,
            status.state,
            access=access,
            kinds={copy.kind for copy in status.copies},
            authority=status.authority,
            licensed=license_settled(meta),
            checkout=str(catalog_root),
        )
        report.info(
            f"  {name:<{width}}  {status.state:<10} {access:<11} {release:<16} "
            f"{hint or '-'}"
        )
        if check and described:
            found = evidence(
                catalog_root, dataset_dir, name, status, store, superseded
            )
            result.findings[name] = found
            for finding in found:
                report.info(f"  {'':<{width}}    {finding}")
    if not names:
        _next_release(catalog_root, git)
    if check:
        failed = sum(
            not finding.ok for found in result.findings.values() for finding in found
        )
        report.info(
            f"\n{failed} finding(s) do not hold." if failed else "\nEvery record holds."
        )
    return result


def _next_release(catalog_root: Path, git: Git | None) -> None:
    """Report the smallest admissible next release, and why; nothing outside git."""
    from .release import next_release

    if git is None:
        from ..adapters.git import GitRepository

        git = GitRepository(catalog_root)
    try:
        version, changes = next_release(catalog_root, git)
    except MaintenanceError:
        return
    if version is None:
        report.info("\nnext release: none, nothing changed since the last one")
        return
    report.info(f"\nnext release: {version} at least, a {changes.level} release")
    for reason in changes.reasons[:10]:
        report.info(f"  {reason}")
