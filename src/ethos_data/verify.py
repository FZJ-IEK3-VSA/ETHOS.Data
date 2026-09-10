"""Checking that the data on disk is still the data the catalogue describes.

Existence is not integrity. A cache entry that is a symbolic link into shared
project storage is only as stable as that storage: the target can be moved,
re-generated, truncated or replaced by a well-meaning colleague, and nothing
about the path changes when it happens. ``download`` verifies checksums for the
files it fetches, but data read *in place* has never been checked at all -- so
this is the one place where the promise "these bytes are the ones in the
manifest" is actually tested.

    ethos-data verify onshore_wind            # sizes: cheap, run it often
    ethos-data verify onshore_wind --deep     # checksums: slow, run it before you publish
    ethos-data verify --all --deep --repair   # and re-fetch whatever drifted

It is deliberately link-agnostic. A symbolic link, a hard link, a configured
root and an ordinary downloaded directory are all just paths by the time they
get here, which is what makes this useful during a migration where a dataset may
be any of those on any given day.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .access import ORIGIN_STAGING, RESTRICTED, Location, locate
from .catalog import Catalog, Resource
from .config import Roots, dataset_roots

__all__ = ["Finding", "verify", "repair", "summarise", "STATUSES", "OK", "UNAVAILABLE"]

OK = "ok"
UNAVAILABLE = "unavailable here"
MISSING = "missing"
DANGLING = "dangling"
SIZE = "wrong size"
HASH = "wrong checksum"
UNREADABLE = "unreadable"
UNVERIFIABLE = "unverifiable"

#: Ordered worst-first, which is the order a report should print them in.
STATUSES = (DANGLING, HASH, SIZE, MISSING, UNREADABLE, UNAVAILABLE, UNVERIFIABLE, OK)

CHUNK = 8 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    """One resource, and what is wrong with it -- or that nothing is."""

    location: Location
    status: str
    detail: str = ""

    @property
    def resource(self) -> Resource:
        return self.location.resource

    @property
    def ok(self) -> bool:
        """Nothing to act on. Not the same as "verified" -- see the report.

        UNAVAILABLE counts as nothing-to-act-on because there is genuinely no
        action: the machine has no access to those bytes and never will. It is
        still reported, so it can never be mistaken for a clean check.
        """
        return self.status in (OK, UNVERIFIABLE, UNAVAILABLE)

    def __str__(self) -> str:
        line = f"{self.status:<14} {self.resource.key}"
        return f"{line}\n                 {self.detail}" if self.detail else line


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _expected_digest(recorded: str) -> str:
    """The bare hex digest from a Frictionless ``hash`` field.

    Written as "sha256:<hex>" by our manifest builder, but the spec permits a
    bare digest, and a catalogue built by another tool may use one.
    """
    if ":" in recorded:
        algorithm, _, digest = recorded.partition(":")
        return digest if algorithm.lower() == "sha256" else ""
    return recorded


def _broken_link(roots: Roots, dataset: str, origin: str) -> tuple[Path, Path] | None:
    """The dataset's entry if it is a symbolic link pointing nowhere.

    Checked once per dataset rather than once per file: a dataset with 170,000
    resources behind a dangling link should cost one ``stat``, not 170,000.
    """
    candidates = []
    if origin == ORIGIN_STAGING and roots.staging is not None:
        candidates.append(roots.staging / dataset)
    else:
        candidates.append(roots.public / dataset)
        if roots.restricted is not None:
            candidates.append(roots.restricted / dataset)
    for entry in candidates:
        if entry.is_symlink() and not entry.exists():
            return entry, entry.readlink()
    return None


def verify(
    catalog: Catalog,
    resources: list[Resource],
    roots: "Roots | str | Path | None" = None,
    deep: bool = False,
    skip_unavailable: bool | None = None,
) -> list[Finding]:
    """Check every resource against the manifest. Never writes anything.

    Without ``deep`` this compares sizes, which catches truncation, replacement
    by a different file, and an empty placeholder -- the common failures -- for
    the cost of one ``stat`` per file. With ``deep`` it compares checksums,
    which catches everything and reads every byte.
    """
    roots = Roots.coerce(roots)
    locations = locate(catalog, resources, roots, dataset_roots(), skip_unavailable)

    findings: list[Finding] = []
    link_state: dict[str, tuple[Path, Path] | None] = {}

    for location in locations:
        if not location.available:
            findings.append(Finding(
                location, UNAVAILABLE,
                "no access to this dataset from this machine; nothing was checked",
            ))
            continue
        name = location.resource.dataset
        if name not in link_state:
            link_state[name] = _broken_link(roots, name, location.origin)
        broken = link_state[name]
        if broken is not None:
            findings.append(Finding(
                location, DANGLING,
                f"{broken[0]} points at {broken[1]}, which does not exist",
            ))
            continue
        findings.append(_check_one(location, deep))
    return findings


def _check_one(location: Location, deep: bool) -> Finding:
    path = location.path
    expected = location.resource.bytes
    try:
        if not path.is_file():
            return Finding(location, MISSING, f"no file at {path}")
        actual = path.stat().st_size
    except PermissionError as error:
        return Finding(location, UNREADABLE, f"{path}: {error.strerror}")
    except OSError as error:
        return Finding(location, UNREADABLE, f"{path}: {error}")

    if expected and actual != expected:
        return Finding(location, SIZE, f"{path}: expected {expected:,} bytes, found {actual:,}")

    digest = _expected_digest(location.resource.hash or "")
    if not digest:
        # Staged data, or a catalogue that records a digest we cannot check.
        return Finding(location, UNVERIFIABLE if deep else OK,
                       "no sha256 in the manifest" if deep else "")
    if not deep:
        return Finding(location, OK)

    try:
        found = sha256_of(path)
    except OSError as error:
        return Finding(location, UNREADABLE, f"{path}: {error}")
    if found != digest:
        return Finding(location, HASH, f"{path}: expected {digest[:16]}..., found {found[:16]}...")
    return Finding(location, OK)


def summarise(findings: list[Finding]) -> dict[str, list[Finding]]:
    """Group findings by status, worst first, omitting empty groups."""
    grouped: dict[str, list[Finding]] = {}
    for status in STATUSES:
        matching = [f for f in findings if f.status == status]
        if matching:
            grouped[status] = matching
    return grouped


def repair(
    catalog: Catalog,
    findings: list[Finding],
    roots: "Roots | str | Path | None" = None,
    dry_run: bool = False,
    progressbar: bool = True,
) -> dict:
    """Re-fetch from dCache whatever no longer matches the manifest.

    Restricted data is never repaired -- there is nothing to fetch it from, by
    definition -- and staged data is never repaired either, because the whole
    point of a staging entry is that it is *not* the catalogue's version.

    A dangling link in a shared cache is removed so that the download has
    somewhere to land. That is a change other people see, which is why it is
    listed explicitly before it happens and why ``dry_run`` exists.
    """
    from .retrieval import download  # local: retrieval imports access, which imports config

    roots = Roots.coerce(roots)
    broken = [f for f in findings if not f.ok]

    skipped: dict[str, str] = {
        f.resource.key: "not available on this machine"
        for f in findings if f.status == UNAVAILABLE
    }
    fetchable: list[Finding] = []
    for finding in broken:
        dataset = catalog.dataset(finding.resource.dataset)
        if dataset.access == RESTRICTED:
            skipped[finding.resource.key] = "restricted: never downloaded"
        elif finding.location.origin == ORIGIN_STAGING:
            skipped[finding.resource.key] = "staged: fix the staging entry yourself"
        else:
            fetchable.append(finding)

    links_to_remove = sorted({
        roots.public / f.resource.dataset
        for f in fetchable
        if (roots.public / f.resource.dataset).is_symlink()
    })

    report = {
        "broken": broken,
        "skipped": skipped,
        "links_to_remove": links_to_remove,
        "resources": [f.resource for f in fetchable],
        "dry_run": dry_run,
        "downloaded": 0,
    }
    if dry_run or not fetchable:
        return report

    for link in links_to_remove:
        link.unlink()

    files = download(catalog, [f.resource for f in fetchable], root=roots,
                     progressbar=progressbar)
    report["downloaded"] = len(files)
    return report
