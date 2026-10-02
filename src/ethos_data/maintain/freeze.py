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

The copy is checked, file by file, before the dataset is frozen: an upload
anonymously over HTTP, a cache entry on this machine. Which copy, when there
are several: the upload, else the copy a cache owns, else, for restricted
data, the registered installation. A link to public or internal data borrows
the build input and is the authoritative copy only when named with ``--copy``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
from ..formats import keys as k
from ..formats.status_file import Copy, StatusFile
from ..model import lifecycle
from . import is_namespace, read_descriptor, resources_of
from . import status as dataset_status

__all__ = ["choose", "run"]


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


@report.reported
def run(
    catalog_root: Path, dataset: str, *, copy: str | None = None, dry_run: bool = False
) -> int:
    """Freeze ``dataset`` with its authoritative copy checked; returns 0, or raises."""
    from .upload import resolve_name

    name = resolve_name(catalog_root, dataset)
    directory = dataset_status.dataset_dir_in(catalog_root, name)
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
    chosen = choose(name, status, access, copy)

    package = json.loads((directory / "datapackage.json").read_text(encoding="utf-8"))
    finding = dataset_status.check_copy(chosen, resources_of(package, directory))
    report.info(f"  {finding}")
    if not finding.ok:
        raise MaintenanceError(
            f"{name}: the copy does not hold the inventory as built, so it cannot "
            "be the authoritative one. Find out why before freezing the dataset."
        )
    if status.state == lifecycle.FROZEN and status.authority == chosen.location:
        report.info(
            f"\n{name} is frozen already, with this copy as its authoritative one."
        )
        return 0
    retired = status.source_dir
    if dry_run:
        report.info(
            f"\nwould freeze {name}: {chosen.location} becomes its authoritative copy"
            + (f" and its source_dir {retired} is retired." if retired else ".")
            + " Nothing was written."
        )
        return 0
    dataset_status.take(
        directory,
        status,
        "record",
        dataset=name,
        copy=chosen.model_copy(update={"verified": dataset_status.now()}),
        source_dir=retired,
        changes={"source_dir": None, "authority": chosen.location},
    )
    report.info(
        f"\nrecorded     {name} is frozen; its authoritative copy is {chosen.location}"
    )
    if retired:
        report.info(
            f"             its source_dir {retired} is not read again; a rebuild "
            "keeps the inventory as it is"
        )
    return 0
