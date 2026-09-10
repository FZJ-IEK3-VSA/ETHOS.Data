"""Turning a borrowed dataset into one the cache actually owns.

A dataset that appears in the cache as a symbolic link costs no disk space, but
it is only as durable as whatever it points at. Sooner or later you want a real
copy instead:

  * the storage behind the link is about to be reorganised or deleted, and the
    data is not on dCache yet
  * a long run must be insulated from anybody editing the shared original
    halfway through
  * the link crosses to a filesystem that is slow, full, or about to be
    unmounted

``materialize`` replaces the link with a real directory holding real files:

    ethos-data materialize global-wind-atlas          # one dataset
    ethos-data materialize --all --dry-run            # what it would cost

Only files the catalogue describes are copied. A cache is not a backup of
somebody's project directory -- it holds the inventory the manifest lists, and
copying the strays as well would quietly make the cache a second, divergent
source of truth.

Every copy is checksummed against the manifest before it is put in place, and
the old link target is recorded in ``.ethos-data-materialized.json`` so that a copy
can always be traced back to where it came from.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .access import RESTRICTED, access_class
from .catalog import Catalog, Resource, UnknownDataset
from .config import Roots
from .verify import sha256_of, _expected_digest

__all__ = ["MaterializeReport", "materialize", "plan_materialize", "PROVENANCE_FILE"]

#: Written into a materialised directory so the copy can be traced back.
PROVENANCE_FILE = ".ethos-data-materialized.json"

#: Refuse if the copy would leave less than this fraction of the filesystem
#: free. A cache that fills the disk it lives on takes everyone else down too.
HEADROOM = 0.02


@dataclass
class MaterializeReport:
    """What happened, or would happen, to one dataset."""

    dataset: str
    action: str
    detail: str = ""
    entry: Path | None = None
    target: Path | None = None
    files: int = 0
    bytes: int = 0
    failures: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        head = f"{self.action:<14} {self.dataset}"
        return f"{head}  {self.detail}" if self.detail else head


def _entry_for(catalog: Catalog, roots: Roots, name: str) -> Path:
    """The cache entry for a dataset, in whichever root its class belongs to."""
    root = roots.for_access(access_class(catalog.dataset(name)))
    if root is None:
        raise ValueError(
            f"dataset {name!r} is restricted and no restricted cache is configured; "
            "there is no entry to materialise."
        )
    return root / name


def plan_materialize(
    catalog: Catalog,
    names: list[str],
    roots: "Roots | str | Path | None" = None,
    force: bool = False,
) -> list[MaterializeReport]:
    """Classify each dataset without copying anything.

    Note that this pulls the full inventory of every dataset named, including
    every shard of a sharded one -- that is what "how many bytes is this" costs.
    """
    roots = Roots.coerce(roots)
    reports = []
    for name in sorted(set(names)):
        try:
            entry = _entry_for(catalog, roots, name)
        except UnknownDataset:
            # A cache directory accumulates links nobody remembers making, and
            # ``--all`` walks the directory rather than the catalogue. One
            # stray name must not abort the run for every real dataset behind
            # it -- but it is worth saying out loud, because a link the
            # catalogue cannot explain is usually rubbish worth removing.
            reports.append(MaterializeReport(
                name, "unknown",
                "there is an entry with this name in the cache, but the catalogue does "
                "not describe it; `ethos-data catalog link-cache --prune` removes stale links"))
            continue
        except ValueError as error:
            reports.append(MaterializeReport(name, "cannot", str(error)))
            continue

        if not entry.is_symlink():
            if not entry.exists():
                reports.append(MaterializeReport(
                    name, "absent", f"no entry at {entry}; nothing to materialise", entry=entry))
            elif force:
                reports.append(MaterializeReport(
                    name, "already real", f"{entry} is a real directory; --force re-copies "
                    "nothing, it is already owned", entry=entry))
            else:
                reports.append(MaterializeReport(
                    name, "already real", f"{entry} is already a real directory", entry=entry))
            continue

        target = entry.resolve()
        if not target.is_dir():
            reports.append(MaterializeReport(
                name, "dangling", f"{entry} points at {entry.readlink()}, which does not exist",
                entry=entry, target=target))
            continue

        resources = list(catalog.dataset(name).resources.values())
        total = sum(r.bytes for r in resources)
        reports.append(MaterializeReport(
            name, "would copy", f"{len(resources):,} files, {total:,} bytes from {target}",
            entry=entry, target=target, files=len(resources), bytes=total))
    return reports


def _check_space(root: Path, needed: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    reserve = int(usage.total * HEADROOM)
    if needed > usage.free - reserve:
        raise OSError(
            f"not enough room in {root}: need {needed:,} bytes, "
            f"{usage.free:,} free, keeping {reserve:,} in reserve."
        )


def materialize(
    catalog: Catalog,
    names: list[str],
    roots: "Roots | str | Path | None" = None,
    force: bool = False,
    verify_hashes: bool = True,
    dry_run: bool = False,
    on_file=None,
) -> list[MaterializeReport]:
    """Replace symbolic-link cache entries with real, verified copies.

    Copies into a temporary directory beside the entry, verifies it, and only
    then puts it in place. A failure part-way through leaves the original link
    untouched, so an interrupted run costs time and nothing else.
    """
    roots = Roots.coerce(roots)
    planned = plan_materialize(catalog, names, roots, force=force)
    if dry_run:
        return planned

    done: list[MaterializeReport] = []
    for report in planned:
        if report.action != "would copy":
            done.append(report)
            continue
        done.append(_materialize_one(catalog, report, roots, verify_hashes, on_file))
    return done


def _materialize_one(
    catalog: Catalog,
    report: MaterializeReport,
    roots: Roots,
    verify_hashes: bool,
    on_file,
) -> MaterializeReport:
    entry, target = report.entry, report.target
    resources = list(catalog.dataset(report.dataset).resources.values())

    try:
        _check_space(entry.parent, report.bytes)
    except OSError as error:
        return MaterializeReport(report.dataset, "failed", str(error), entry=entry, target=target)

    staging = entry.parent / f"{report.dataset}.materializing.{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    failures: list[str] = []
    copied = 0
    copied_bytes = 0
    try:
        for resource in resources:
            source = target / resource.path
            destination = staging / resource.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source, destination)
            except OSError as error:
                failures.append(f"{resource.path}: {error}")
                continue
            if verify_hashes:
                message = _verify_copy(destination, resource)
                if message:
                    failures.append(f"{resource.path}: {message}")
                    continue
            copied += 1
            copied_bytes += resource.bytes
            if on_file is not None:
                on_file(resource, copied, len(resources))

        if failures:
            shutil.rmtree(staging, ignore_errors=True)
            return MaterializeReport(
                report.dataset, "failed",
                f"{len(failures)} of {len(resources)} files did not copy or did not verify; "
                f"the link is untouched",
                entry=entry, target=target, failures=failures)

        (staging / PROVENANCE_FILE).write_text(json.dumps({
            "dataset": report.dataset,
            "materialized_from": str(target),
            "was_a_link_at": str(entry),
            "catalog": catalog.location,
            "files": copied,
            "bytes": copied_bytes,
            "verified": verify_hashes,
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "by": os.environ.get("USER", ""),
        }, indent=2) + "\n")

        # A directory cannot be renamed onto a symbolic link, so the link has to
        # go first. The window between the two is the only moment the dataset is
        # absent; everything is already copied and verified by this point, so it
        # is as short as the filesystem can make it.
        link_target = entry.readlink()
        entry.unlink()
        try:
            staging.rename(entry)
        except OSError as error:
            entry.symlink_to(link_target)
            shutil.rmtree(staging, ignore_errors=True)
            return MaterializeReport(
                report.dataset, "failed",
                f"could not put the copy in place ({error}); the link was restored",
                entry=entry, target=target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return MaterializeReport(
        report.dataset, "materialized",
        f"{copied:,} files, {copied_bytes:,} bytes copied from {target}",
        entry=entry, target=target, files=copied, bytes=copied_bytes)


def _verify_copy(path: Path, resource: Resource) -> str:
    """Empty string if the copy is sound, else why it is not."""
    size = path.stat().st_size
    if resource.bytes and size != resource.bytes:
        return f"expected {resource.bytes:,} bytes, copied {size:,}"
    digest = _expected_digest(resource.hash or "")
    if not digest:
        return ""
    found = sha256_of(path)
    if found != digest:
        return f"checksum {found[:16]}... does not match the manifest's {digest[:16]}..."
    return ""
