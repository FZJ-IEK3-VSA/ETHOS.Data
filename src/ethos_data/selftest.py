"""Whether this machine can obtain data at all: settings, catalogue, a small download.

A package's own collections may be large, restricted or not installed, so the
check uses a collections file that ships with ETHOS.Data,
:data:`EXAMPLE_COLLECTIONS`: public test data of under 200 KB that both the
public and the internal catalogue describe -- the same file the documentation's
examples use. :func:`run_selftest` takes three steps and stops at the first
that fails:

1. the settings, read the way every handle reads them;
2. the catalogue those settings choose, with its version;
3. every file of every collection in the file: downloaded, already present or
   read in place, and then checked against the catalogue's checksums.

``ethos-data selftest`` prints the result; it passes ``--catalog`` and
``--root`` through, so an empty ``--root`` forces a real download.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings, read_settings
from .errors import EthosDataError

__all__ = ["EXAMPLE_COLLECTIONS", "FileOutcome", "SelfTest", "run_selftest"]

#: The collections file the self-test fetches and the documentation's examples
#: work with. A package's collections file, in the shape any package writes.
EXAMPLE_COLLECTIONS = Path(__file__).with_name("examples") / "collections.yaml"

#: The steps, in the order they run, as a report names them.
STEPS = ("settings", "catalogue", "files")

DOWNLOADED = "downloaded"
PRESENT = "already present"
IN_PLACE = "read in place"


@dataclass(frozen=True)
class FileOutcome:
    """One file of the self-test: how it came to be here, and whether it checks out."""

    key: str
    how: str
    path: Path
    #: The verification status: ``ok``, or what is wrong with the file.
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class SelfTest:
    """What the self-test found, step by step; ``failed`` names the step that stopped it."""

    settings: Settings | None = None
    catalog: str = ""
    catalog_source: str = ""
    version: str | None = None
    files: list[FileOutcome] = field(default_factory=list)
    failed: str | None = None
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.failed is None


def run_selftest(
    *, catalog: str | None = None, root: str | Path | None = None
) -> SelfTest:
    """Check settings, catalogue, store and cache with a download of under 200 KB.

    Never raises for what it is checking: a step that fails is recorded with
    its error, and the steps after it are not run.
    """
    from . import retrieval
    from .selection import load_collections
    from .verify import verify

    result = SelfTest()
    try:
        result.settings = read_settings(root=root, catalog=catalog)
    except EthosDataError as error:
        return _failed(result, "settings", error)

    try:
        handle = load_collections(
            EXAMPLE_COLLECTIONS,
            settings=result.settings,
            roots=result.settings.roots,
            tool="ethos-data",
        )
    except EthosDataError as error:
        return _failed(result, "catalogue", error)
    snapshot = handle.settings
    result.catalog = snapshot.catalog or ""
    result.catalog_source = snapshot.catalog_source
    result.version = snapshot.catalog_version

    try:
        roots = result.settings.roots
        for name in handle.names():
            resources = handle.select(name)
            plan = retrieval.plan(handle.catalog, resources, roots)
            how = {r.key: IN_PLACE for r in plan["in_place"]}
            how.update({r.key: PRESENT for r in plan["present"]})
            files = handle.fetch(name, progressbar=False)
            for finding in verify(handle.catalog, resources, roots, deep=True):
                key = finding.resource.key
                result.files.append(
                    FileOutcome(
                        key,
                        how.get(key, DOWNLOADED),
                        Path(files[key]),
                        finding.status,
                        finding.detail,
                    )
                )
    except (EthosDataError, OSError, ValueError) as error:
        # pooch reports a download whose bytes do not match the catalogue as a
        # ValueError, and an unreachable store as an OSError.
        return _failed(result, "files", error)
    if not all(outcome.ok for outcome in result.files):
        broken = [o.key for o in result.files if not o.ok]
        result.failed = "files"
        result.error = (
            f"{len(broken)} file(s) do not match the catalogue: {', '.join(broken)}"
        )
    return result


def _failed(result: SelfTest, step: str, error: Exception) -> SelfTest:
    result.failed = step
    result.error = getattr(error, "message", None) or str(error)
    return result
