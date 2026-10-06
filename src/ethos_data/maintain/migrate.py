"""``catalog migrate``: convert a catalogue's datasets to status files and ``shards/``.

    ethos-data catalog migrate --dry-run
    ethos-data catalog migrate
    ethos-data catalog migrate era5 global-wind-atlas-v4

The one converter of the clean break. It takes a catalogue whose
``dataset.yaml`` files state where each dataset stands -- ``source_dir`` what
it is built from, ``ethos:uploaded`` that dCache holds the copy its inventory
describes, ``ethos:frozen`` that the inventory is final -- writes each
dataset's ``status.yaml`` from them and from the files beside them, and
removes them from ``dataset.yaml``:

=================================  ===================================================
``dataset.yaml`` says              ``status.yaml`` says
=================================  ===================================================
``source_dir``, never built        draft, with ``source_dir`` as an absolute path
``source_dir``, built              built, with ``source_dir`` as an absolute path
``ethos:uploaded: true``           frozen, its copy on dCache the authoritative one
``ethos:frozen: true``             frozen, where its authoritative copy is unrecorded
=================================  ===================================================

A dataset whose shards are in ``manifests/`` gets them in ``shards/``, where
the build and every reader look, and its ``datapackage.json`` names them there.

The keys are removed line by line, so every other line, comments included,
stays as it was; a file that does not come out the same is left alone and
reported. A dataset whose keys contradict each other is left alone too.

Nothing is checked against the bytes: a migrated record says what
``dataset.yaml`` said, and ``ethos-data catalog status --check`` compares it
with the evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..formats import keys as k
from ..formats.derived import remote_prefix_of, resource_url
from ..formats.edit import without_keys
from ..formats.status_file import Copy, StatusFile
from ..model import lifecycle
from ..model.inventory import SHARD_DIR
from . import DESCRIPTOR, read_catalog_meta, read_descriptor, source_dir_of
from . import status as dataset_status

__all__ = ["MigrateResult", "Outcome", "run"]

#: The keys of ``dataset.yaml`` this converts into a status file.
CONVERTED = dataset_status.CONVERTED
_, UPLOADED, FROZEN = CONVERTED
#: The directory of shards this moves to ``shards/``.
MANIFESTS = "manifests"


@dataclass(frozen=True)
class Outcome:
    """What migrating one dataset did, or would do."""

    dataset: str
    verb: str
    state: str = ""
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.verb:<14} {self.dataset:<32} {self.state:<10} {self.detail}".rstrip()


@dataclass
class MigrateResult:
    """Each dataset ``catalog migrate`` looked at, and what it did."""

    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(outcome.verb == "refused" for outcome in self.outcomes)


def _contradiction(meta: dict) -> str:
    """Why the keys cannot describe one state; empty when they can."""
    uploaded = bool(meta.get(UPLOADED, False))
    final = bool(meta.get(FROZEN, False)) or uploaded
    if meta.get(k.ACCESS, k.PUBLIC) == k.RESTRICTED and uploaded:
        return (
            f"restricted data is never uploaded, so {UPLOADED}: true cannot be "
            f"right; if its inventory is final, say {FROZEN}: true instead"
        )
    if final and meta.get(k.SOURCE_DIR) is not None:
        declared = UPLOADED if uploaded else FROZEN
        return (
            f"declares {declared}: true and still has source_dir: "
            f"{meta[k.SOURCE_DIR]!r}; remove the one that is wrong"
        )
    # Empty counts as absent: resolved against the dataset directory, an empty
    # source_dir would build the dataset from its own descriptor files.
    if not final and not meta.get(k.SOURCE_DIR):
        return f"has no source_dir, and neither {UPLOADED} nor {FROZEN}"
    return ""


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
    dataset_dir: Path, meta: dict, present: list[str], publication_url
) -> tuple[StatusFile | None, str]:
    """The status ``dataset.yaml``'s keys describe, or None and why there is none."""
    problem = _contradiction(meta)
    if problem:
        return None, problem
    built = (dataset_dir / "datapackage.json").is_file()
    uploaded = bool(meta.get(UPLOADED))
    note = f"from {', '.join(present)} in {DESCRIPTOR}"
    if not (uploaded or meta.get(FROZEN)):
        state = lifecycle.BUILT if built else lifecycle.DRAFT
        return StatusFile(
            state=state,
            source_dir=str(source_dir_of(dataset_dir, meta)),
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
    final = bool(meta.get(UPLOADED)) or bool(meta.get(FROZEN))
    if final and status.state != lifecycle.FROZEN:
        return (
            f"{DESCRIPTOR} says its inventory is final and status.yaml that it is "
            f"{status.state}; freeze it with `ethos-data catalog record {name}`, "
            f"then delete the key from {DESCRIPTOR}"
        )
    return ""


def _move_shards(dataset_dir: Path) -> None:
    """Move ``manifests/`` to ``shards/`` and name it so in ``datapackage.json``."""
    (dataset_dir / MANIFESTS).rename(dataset_dir / SHARD_DIR)
    package_file = dataset_dir / "datapackage.json"
    if not package_file.is_file():
        return
    package = json.loads(package_file.read_text(encoding="utf-8"))
    for shard in package.get(k.SHARDS, []):
        if shard[k.PATH].startswith(f"{MANIFESTS}/"):
            shard[k.PATH] = SHARD_DIR + shard[k.PATH][len(MANIFESTS) :]
    package_file.write_text(
        json.dumps(package, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _migrate(name: str, dataset_dir: Path, publication_url, dry_run: bool) -> Outcome:
    meta = read_descriptor(dataset_dir)
    present = [key for key in CONVERTED if key in meta]
    shards = (dataset_dir / MANIFESTS).is_dir()
    status = dataset_status.read(dataset_dir)
    if status is not None and not present and not shards:
        return Outcome(name, "unchanged", status.state, "has a status.yaml already")
    if shards and (dataset_dir / SHARD_DIR).exists():
        return Outcome(
            name,
            "refused",
            status.state if status else "",
            f"has both {MANIFESTS}/ and {SHARD_DIR}/; keep the one its index names",
        )
    written = None
    if status is None:
        written, problem = _status_from(dataset_dir, meta, present, publication_url)
        if written is None:
            return Outcome(name, "refused", "", problem)
        state = written.state
    else:
        problem = _conflict(name, meta, status)
        if problem:
            return Outcome(name, "refused", status.state, problem)
        state = status.state
    edited = None
    if present:
        text = (dataset_dir / DESCRIPTOR).read_bytes().decode("utf-8")
        try:
            edited = without_keys(text, present)
        except ValueError:
            return Outcome(
                name,
                "refused",
                state,
                f"{', '.join(present)} could not be removed from {DESCRIPTOR} line "
                "by line; delete them by hand, then run this again",
            )
    done = [f"{', '.join(present)} moved out of {DESCRIPTOR}"] if present else []
    if shards:
        done.append(f"{MANIFESTS}/ moved to {SHARD_DIR}/")
    if dry_run:
        return Outcome(name, "would migrate", state, "; ".join(done))
    if written is not None:
        dataset_status.write(dataset_dir, written)
    if edited is not None:
        (dataset_dir / DESCRIPTOR).write_bytes(edited.encode("utf-8"))
    if shards:
        _move_shards(dataset_dir)
    return Outcome(name, "migrated", state, "; ".join(done))


@report.reported
def run(
    catalog_root: Path, names: list[str], *, dry_run: bool = False
) -> MigrateResult:
    """Convert ``names``, or every dataset; the result says which were refused."""
    publication_url = read_catalog_meta(catalog_root).get(k.PUBLICATION_URL)
    result = MigrateResult(
        [
            _migrate(name, dataset_dir, publication_url, dry_run)
            for name, dataset_dir in dataset_status.datasets(catalog_root, names)
        ]
    )
    for outcome in result.outcomes:
        report.info(f"  {outcome}")
    refused = [outcome for outcome in result.outcomes if outcome.verb == "refused"]
    changed = [o for o in result.outcomes if o.verb in ("migrated", "would migrate")]
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
    return result
