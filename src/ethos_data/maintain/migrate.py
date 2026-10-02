"""``catalog migrate``: move each dataset's state from ``dataset.yaml`` into ``status.yaml``.

    ethos-data catalog migrate --dry-run
    ethos-data catalog migrate
    ethos-data catalog migrate era5 global-wind-atlas-v4

Before status files, three keys of ``dataset.yaml`` said where a dataset
stood: ``source_dir`` what it is built from, ``ethos:uploaded`` that dCache
holds the copy its inventory describes, ``ethos:frozen`` that the inventory is
final. This writes each dataset's ``status.yaml`` from them and from the files
beside them, and removes them from ``dataset.yaml``:

=================================  ===================================================
``dataset.yaml`` says              ``status.yaml`` says
=================================  ===================================================
``source_dir``, never built        draft, with the ``source_dir``
``source_dir``, built              built, with the ``source_dir``
``ethos:uploaded: true``           frozen, its copy on dCache the authoritative one
``ethos:frozen: true``             frozen, where its authoritative copy is unrecorded
=================================  ===================================================

The keys are removed line by line, so every other line, comments included,
stays as it was. The result is read back and compared with the original less
those keys, and a file that does not come out the same is left alone and
reported. A dataset whose keys the build would refuse is left alone too.

Nothing is checked against the bytes: a migrated record says what
``dataset.yaml`` said, and ``ethos-data catalog status --check`` compares it
with the evidence.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import report
from ..errors import DescriptorError
from ..formats import dataset as dataset_format
from ..formats import keys as k
from ..formats.derived import remote_prefix_of, resource_url
from ..formats.status_file import Copy, StatusFile
from ..model import lifecycle
from . import DESCRIPTOR, read_catalog_meta, read_descriptor
from . import status as dataset_status

__all__ = ["Outcome", "run", "without_keys"]


@dataclass(frozen=True)
class Outcome:
    """What migrating one dataset did, or would do."""

    dataset: str
    verb: str
    state: str = ""
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.verb:<14} {self.dataset:<32} {self.state:<10} {self.detail}".rstrip()


def without_keys(text: str, keys: Iterable[str]) -> str:
    """``text`` without the top-level ``keys``, and the indented lines that continue them."""
    patterns = [
        re.compile(rf"(?:{re.escape(key)}|\"{re.escape(key)}\"|'{re.escape(key)}')\s*:")
        for key in keys
    ]
    kept: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if not line.strip():
            skipping = False
        elif line[:1] not in (" ", "\t"):
            skipping = any(pattern.match(line) for pattern in patterns)
        if not skipping:
            kept.append(line)
    return "".join(kept)


def _edited(path: Path, keys: list[str]) -> tuple[bytes | None, str]:
    """The file without ``keys``, or None and why it cannot be edited safely."""
    raw = path.read_bytes().decode("utf-8")
    edited = without_keys(raw, keys)
    expected = {
        key: value
        for key, value in (yaml.safe_load(raw) or {}).items()
        if key not in keys
    }
    if (yaml.safe_load(edited) or {}) != expected:
        return None, (
            f"{', '.join(keys)} could not be removed from {DESCRIPTOR} line by line; "
            "delete them by hand once its status.yaml is written"
        )
    return edited.encode("utf-8"), ""


def _uploaded_copy(dataset_dir: Path, publication_url: str | None) -> Copy | None:
    """The copy ``ethos:uploaded`` claims, at the URL a reader downloads it from."""
    if not publication_url:
        return None
    package = json.loads((dataset_dir / "datapackage.json").read_text(encoding="utf-8"))
    return Copy(
        kind=k.COPY_UPLOADED,
        location=resource_url(publication_url.rstrip("/"), remote_prefix_of(package)),
    )


def _status_from(
    name: str, dataset_dir: Path, meta: dict, present: list[str], publication_url
) -> tuple[StatusFile | None, str]:
    """The status ``dataset.yaml``'s keys describe, or None and why there is none."""
    try:
        dataset_format.check_legacy_state(meta)
    except DescriptorError as error:
        return None, error.message
    built = (dataset_dir / "datapackage.json").is_file()
    uploaded = bool(meta.get(k.UPLOADED))
    note = f"from {', '.join(present)} in {DESCRIPTOR}"
    if not (uploaded or meta.get(k.FROZEN)):
        state = lifecycle.BUILT if built else lifecycle.DRAFT
        return StatusFile(
            state=state,
            source_dir=str(meta[k.SOURCE_DIR]),
            history=[dataset_status.event("migrate", state, note=note)],
        ), ""
    if not built:
        return None, "its inventory is declared final, but there is no datapackage.json"
    copies, authority = [], None
    if uploaded:
        copy = _uploaded_copy(dataset_dir, publication_url)
        if copy is None:
            return None, (
                f"catalog.yaml names no {k.PUBLICATION_URL}, so where its copy on "
                "dCache is cannot be recorded"
            )
        copies, authority = [copy], copy.location
    return StatusFile(
        state=lifecycle.FROZEN,
        authority=authority,
        copies=copies,
        history=[dataset_status.event("migrate", lifecycle.FROZEN, note=note)],
    ), ""


def _conflict(name: str, meta: dict, status: StatusFile) -> str:
    """Why keys left in ``dataset.yaml`` disagree with the status file; empty if they agree."""
    if k.SOURCE_DIR in meta and meta[k.SOURCE_DIR] != status.source_dir:
        return (
            f"{DESCRIPTOR} says source_dir: {meta[k.SOURCE_DIR]!r} and status.yaml "
            f"{status.source_dir!r}; delete the one that is wrong from {DESCRIPTOR}"
        )
    final = bool(meta.get(k.UPLOADED)) or bool(meta.get(k.FROZEN))
    if final and status.state != lifecycle.FROZEN:
        return (
            f"{DESCRIPTOR} says its inventory is final and status.yaml that it is "
            f"{status.state}; freeze it with `ethos-data catalog record {name}`, "
            f"then delete the key from {DESCRIPTOR}"
        )
    return ""


def _migrate(name: str, dataset_dir: Path, publication_url, dry_run: bool) -> Outcome:
    meta = read_descriptor(dataset_dir)
    present = [key for key in dataset_status.LEGACY_KEYS if key in meta]
    status = dataset_status.read(dataset_dir)
    if status is not None and not present:
        return Outcome(name, "unchanged", status.state, "has a status.yaml already")
    written = None
    if status is None:
        written, problem = _status_from(
            name, dataset_dir, meta, present, publication_url
        )
        if written is None:
            return Outcome(name, "refused", "", problem)
        state = written.state
    else:
        problem = _conflict(name, meta, status)
        if problem:
            return Outcome(name, "refused", status.state, problem)
        state = status.state
    edited, problem = _edited(dataset_dir / DESCRIPTOR, present)
    if edited is None:
        return Outcome(name, "refused", state, problem)
    moved = f"{', '.join(present)} moved out of {DESCRIPTOR}"
    if dry_run:
        return Outcome(name, "would migrate", state, moved)
    if written is not None:
        dataset_status.write(dataset_dir, written)
    (dataset_dir / DESCRIPTOR).write_bytes(edited)
    return Outcome(name, "migrated", state, moved)


@report.reported
def run(catalog_root: Path, names: list[str], *, dry_run: bool = False) -> int:
    """Write the status files of ``names``, or of every dataset; 1 if one was refused."""
    publication_url = read_catalog_meta(catalog_root).get(k.PUBLICATION_URL)
    outcomes = [
        _migrate(name, dataset_dir, publication_url, dry_run)
        for name, dataset_dir in dataset_status.datasets(catalog_root, names)
    ]
    for outcome in outcomes:
        report.info(f"  {outcome}")
    refused = [outcome for outcome in outcomes if outcome.verb == "refused"]
    changed = [o for o in outcomes if o.verb in ("migrated", "would migrate")]
    if dry_run:
        report.info(
            f"\n{len(changed)} dataset(s) would be migrated. Nothing was written."
        )
    elif changed:
        report.info(
            f"\n{len(changed)} dataset(s) migrated. Review the change with `git diff`, "
            "then compare the records with the evidence:\n"
            "    ethos-data catalog status --check"
        )
    if refused:
        report.warning(
            f"{len(refused)} dataset(s) left as they were; fix what is named above "
            "and run this again."
        )
        return 1
    return 0
