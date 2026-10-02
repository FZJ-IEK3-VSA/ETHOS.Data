"""Checking that the data on disk is still the data the catalogue describes.

Existence is not integrity. A cache entry that is a symbolic link into shared
project storage is only as stable as that storage: the target can be moved,
re-generated, truncated or replaced by a well-meaning colleague, and nothing
about the path changes when it happens. ``download`` verifies checksums for the
files it fetches, but data read *in place* has never been checked at all -- so
this is the one place where the promise "these bytes are the ones in the
manifest" is actually tested.

    <tool>-data verify onshore_wind            # sizes: cheap, run it often
    <tool>-data verify onshore_wind --deep     # checksums: slow, run it before you publish
    <tool>-data verify --all --deep --repair   # and re-fetch whatever drifted

It is deliberately link-agnostic. A symbolic link, a hard link, a staged entry
and an ordinary downloaded directory are all just paths by the time they get
here. What it reports about the caches themselves -- a broken link, an entry in
a restricted cache the lookup passed over -- names the cache.

Repair downloads a damaged copy again into the public cache. It never removes or
replaces a link, and never touches restricted or staged data: those are reported
for whoever owns them, on the cluster the maintainers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .access import (
    ORIGIN_LINK,
    ORIGIN_STAGING,
    RESTRICTED,
    Location,
    linked_entry,
    locate,
    restricted_entry,
)
from .catalogs import Catalog
from .config import Roots
from .model import digest
from .model.resource import Resource

__all__ = ["Finding", "verify", "repair", "summarise", "STATUSES", "OK", "UNAVAILABLE"]

OK = "ok"
UNAVAILABLE = "unavailable here"
MISSING = "missing"
DANGLING = "dangling"
SIZE = "wrong size"
HASH = "wrong checksum"
UNREADABLE = "unreadable"
UNVERIFIABLE = "unverifiable"
#: About a cache rather than a file, for whoever maintains that cache; never a
#: failure of the check.
NOTE = "note"

#: Ordered worst-first, which is the order a report should print them in.
STATUSES = (
    DANGLING,
    HASH,
    SIZE,
    MISSING,
    UNREADABLE,
    UNAVAILABLE,
    UNVERIFIABLE,
    NOTE,
    OK,
)


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
        UNVERIFIABLE counts so only for staged data, which carries no checksum
        by design; a catalogue record without a SHA-256 is a fault of the
        catalogue's. A NOTE is about a cache, not about the file that was read.
        """
        if self.status == UNVERIFIABLE:
            return self.location.origin == ORIGIN_STAGING
        return self.status in (OK, UNAVAILABLE, NOTE)

    def __str__(self) -> str:
        line = f"{self.status:<14} {self.resource.key}"
        return f"{line}\n                 {self.detail}" if self.detail else line


def _broken_link(roots: Roots, dataset: str, origin: str) -> str | None:
    """Why the dataset's entry is a symbolic link pointing nowhere, naming the cache.

    Checked once per dataset rather than once per file: a dataset with 170,000
    resources behind a dangling link should cost one ``stat``, not 170,000. A
    restricted dataset is read only from an entry that is readable, so its
    broken entries are notes; see :func:`_notes`.
    """
    if origin == ORIGIN_STAGING and roots.staging is not None:
        entry = roots.staging / dataset
        where = f"the staging root {roots.staging}"
    elif origin == ORIGIN_LINK:
        entry = linked_entry(roots.public, dataset)
        where = f"the public cache {roots.public}"
    else:
        return None
    if entry is not None and entry.is_symlink() and not entry.exists():
        return f"{entry} in {where} points at {entry.readlink()}, which does not exist"
    return None


def _notes(catalog: Catalog, roots: Roots, dataset: str) -> list[str]:
    """What the restricted caches say about one dataset that its read does not.

    For restricted data, an entry the lookup passed over because it is
    dangling or cannot be read, in a cache listed before the one it read. For
    public data, an entry in a restricted cache, which the lookup never reads
    and its maintainer removes.
    """
    if catalog.dataset(dataset).access == RESTRICTED:
        entry, reasons = restricted_entry(roots.restricted, dataset)
        return reasons if entry is not None else []
    return [
        f"{cache / dataset} is an entry in a restricted cache, but the dataset is "
        f"public; its maintainer removes it: "
        f"ethos-data --root {cache} unlink {dataset}"
        for cache in roots.restricted
        if (cache / dataset).exists() or (cache / dataset).is_symlink()
    ]


def verify(
    catalog: Catalog,
    resources: list[Resource],
    roots: Roots | None = None,
    deep: bool = False,
) -> list[Finding]:
    """Check every resource against the manifest. Never writes anything.

    Without ``deep`` this compares sizes, which catches truncation, replacement
    by a different file, and an empty placeholder -- the common failures -- for
    the cost of one ``stat`` per file. With ``deep`` it compares checksums,
    which catches everything and reads every byte. Restricted data this
    account cannot read is reported as ``unavailable here``, with the reason.
    Like a fetch, it warns about a dataset whose licensing is unsettled.
    """
    from .retrieval import warn_about_licensing

    roots = roots if roots is not None else catalog.settings.roots
    warn_about_licensing(catalog, resources)
    locations = locate(catalog, resources, roots, describe=True)

    findings: list[Finding] = []
    link_state: dict[str, str | None] = {}
    noted: set[str] = set()

    for location in locations:
        name = location.resource.dataset
        if name not in noted:
            noted.add(name)
            findings.extend(
                Finding(location, NOTE, note) for note in _notes(catalog, roots, name)
            )
        if not location.available:
            findings.append(
                Finding(
                    location, UNAVAILABLE, f"{location.reason}; nothing was checked"
                )
            )
            continue
        if name not in link_state:
            link_state[name] = _broken_link(
                roots, name, location.origin, catalog.dataset(name).entry_name
            )
        broken = link_state[name]
        if broken is not None:
            findings.append(Finding(location, DANGLING, broken))
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
        return Finding(
            location, SIZE, f"{path}: expected {expected:,} bytes, found {actual:,}"
        )

    wanted = digest.expected(location.resource.hash)
    if wanted is None:
        if not deep:
            return Finding(location, OK)
        if location.origin == ORIGIN_STAGING:
            return Finding(location, UNVERIFIABLE, "staged: no checksum")
        return Finding(
            location, UNVERIFIABLE, "the catalogue records no SHA-256 for this file"
        )
    if not deep:
        return Finding(location, OK)

    try:
        found = digest.of_file(path)
    except OSError as error:
        return Finding(location, UNREADABLE, f"{path}: {error}")
    if found != wanted:
        return Finding(
            location, HASH, f"{path}: expected {wanted[:16]}..., found {found[:16]}..."
        )
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
    roots: Roots | None = None,
    dry_run: bool = False,
    progressbar: bool = True,
) -> dict:
    """Download again, into the public cache, the copies that no longer match.

    Only copies the public cache owns are repaired. A link is never removed or
    replaced: a broken link, and a file behind a link that does not match, are
    reported for whoever owns the link -- on the cluster, the maintainers, since
    every user reads the cluster's public cache. Restricted data is never
    repaired -- there is nothing to fetch it from, by definition -- and staged
    data is never repaired either, because the whole point of a staging entry is
    that it is *not* the catalogue's version.
    """
    from .retrieval import (
        download,
    )  # local: retrieval imports access, which imports config

    roots = roots if roots is not None else catalog.settings.roots
    broken = [f for f in findings if not f.ok]

    skipped: dict[str, str] = {
        f.resource.key: "not available on this machine"
        for f in findings
        if f.status == UNAVAILABLE
    }
    fetchable: list[Finding] = []
    for finding in broken:
        dataset = catalog.dataset(finding.resource.dataset)
        if dataset.access == RESTRICTED:
            skipped[finding.resource.key] = "restricted: never downloaded"
        elif finding.location.origin == ORIGIN_STAGING:
            skipped[finding.resource.key] = "staged: fix the staging entry yourself"
        elif finding.status == DANGLING:
            skipped[finding.resource.key] = (
                "a broken link: repair never changes a link; report it to whoever "
                "maintains the cache"
            )
        elif finding.location.origin == ORIGIN_LINK:
            skipped[finding.resource.key] = (
                "read through a link: repair never changes a link; report it to "
                "whoever maintains the linked data"
            )
        elif finding.status == UNVERIFIABLE:
            skipped[finding.resource.key] = (
                "the catalogue records no SHA-256, so no download can be checked"
            )
        else:
            fetchable.append(finding)

    report = {
        "broken": broken,
        "skipped": skipped,
        "resources": [f.resource for f in fetchable],
        "dry_run": dry_run,
        "downloaded": 0,
    }
    if dry_run or not fetchable:
        return report

    files = download(
        catalog, [f.resource for f in fetchable], root=roots, progressbar=progressbar
    )
    report["downloaded"] = len(files)
    return report
