"""A place for data that is not in the catalogue yet.

Preparing a dataset takes weeks: the files change shape, get regenerated, get
renamed, and none of it belongs in a catalogue that other people's reproducible
runs resolve against. But the code being written against that data wants the
ordinary API -- ``fetch("my_collection")`` -- from the first day, not a pile of
hard-coded paths that have to be unpicked later.

The staging root is that middle ground. It is an ordinary directory whose
entries are dataset names, exactly like the public cache:

    ethos-data staging add my-new-dataset /scratch/me/new-data
    ethos-data staging list
    ethos-data staging remove my-new-dataset

An entry here shadows the catalogue completely, and is **described by what is on
disk** rather than by any manifest -- which is the point: the file list is still
changing. Sizes come from ``stat``; there are no checksums, so nothing about
staged data can be verified, and :mod:`ethos_data.access` warns every time a job
reads it.

Two guarantees, because a development convenience must not become a way to
launder data into a result:

  * **Restricted datasets are never shadowed.** Licence terms are not a
    development concern.
  * **Staged data is never uploaded.** These datasets exist only on this
    machine; ``ethos-data catalog`` never sees them, because the staging root is a
    consumer-side idea the maintainer tooling knows nothing about.

When the data is ready, describe it properly in the catalogue, publish it, and
remove the staging entry. Nothing in the calling code changes.
"""

from __future__ import annotations

import json
import os
import time
import warnings
from dataclasses import dataclass, replace
from pathlib import Path

from .access import AccessError
from .catalog import Catalog, Dataset, Resource
from .config import Roots, resolve_staging_cache

__all__ = [
    "NEW",
    "SHADOWING",
    "StagedDataset",
    "INDEX_FILE",
    "add",
    "apply_staging",
    "with_staging",
    "classify_staged",
    "list_staged",
    "remove",
    "staged_only",
    "staging_root",
]

#: Provenance for the entries, so ``staging list`` can say who added what and why.
INDEX_FILE = ".ice2-staging.json"

#: Never part of a dataset's inventory.
EXCLUDE_NAMES = {".git", ".datalad", "__pycache__", ".ipynb_checkpoints", INDEX_FILE}
EXCLUDE_SUFFIXES = {".pyc", ".part", ".tmp"}

STAGING_ACCESS = "staging"


#: A staged dataset the official caches know nothing about -- it exists only
#: here, and nothing outside this machine can resolve it.
NEW = "new"
#: A staged dataset that also has an entry in the public or restricted cache,
#: so there is an official version of it and staging is hiding that version.
SHADOWING = "shadowing"


@dataclass(frozen=True)
class StagedDataset:
    """One entry in the staging root."""

    name: str
    entry: Path
    target: Path
    files: int
    bytes: int
    note: str = ""
    added: str = ""
    added_by: str = ""
    #: NEW or SHADOWING -- see :func:`classify`. Empty when nothing was
    #: classified against, which is what plain ``list_staged`` does.
    status: str = ""
    #: Where the official version lives, when this entry is SHADOWING one.
    official: Path | None = None

    @property
    def is_link(self) -> bool:
        return self.entry.is_symlink()

    @property
    def broken(self) -> bool:
        return not self.target.is_dir()

    @property
    def is_new(self) -> bool:
        """Nothing outside this machine can resolve this dataset."""
        return self.status == NEW


def staging_root(explicit: str | Path | None = None) -> Path | None:
    """The configured staging directory, or None if staging is not in use."""
    resolved = resolve_staging_cache(explicit)
    return resolved.value if resolved else None


def _require_root(explicit: str | Path | None = None) -> Path:
    root = staging_root(explicit)
    if root is None:
        raise SystemExit(
            "no staging root is configured.\n"
            "Pick a directory for work in progress and set it once:\n"
            "    ethos-data config set-staging-cache /path/to/ethos_data_staging"
        )
    return root


def _index_path(root: Path) -> Path:
    return root / INDEX_FILE


def _read_index(root: Path) -> dict:
    path = _index_path(root)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError:
        # A corrupt index costs provenance, not data -- the entries on disk are
        # the truth. Say so rather than refusing to work.
        warnings.warn(f"{path} is not valid JSON; staging provenance is unavailable",
                      UserWarning, stacklevel=2)
        return {}


def _write_index(root: Path, index: dict) -> None:
    _index_path(root).write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")


def iter_files(directory: Path):
    """Every file that counts as part of a staged dataset."""
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        if any(part in EXCLUDE_NAMES for part in relative.parts):
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        yield path, relative.as_posix()


def add(
    name: str,
    path: str | Path,
    note: str = "",
    root: str | Path | None = None,
    copy: bool = False,
) -> StagedDataset:
    """Register a directory as a staged dataset.

    By default this links rather than copies: work in progress usually lives in
    a scratch or project directory that is still being written to, and a copy
    would go stale the moment it was made.
    """
    staging = _require_root(root)
    staging.mkdir(parents=True, exist_ok=True)
    source = Path(path).expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"not a directory: {source}")

    entry = staging / name
    if entry.exists() or entry.is_symlink():
        raise SystemExit(
            f"{name!r} is already staged at {entry}.\n"
            f"Remove it first:  ethos-data staging remove {name}"
        )

    if copy:
        import shutil

        shutil.copytree(source, entry, symlinks=False)
    else:
        entry.symlink_to(source)

    index = _read_index(staging)
    index[name] = {
        "target": str(source),
        "note": note,
        "added": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "added_by": os.environ.get("USER", ""),
        "copied": bool(copy),
    }
    _write_index(staging, index)
    return _describe(staging, name, index)


def remove(name: str, root: str | Path | None = None, force: bool = False) -> Path:
    """Unregister a staged dataset.

    A link is removed; the data it points at is never touched. A staging entry
    that is a real directory holds the only copy of somebody's work, so removing
    it needs ``force`` said out loud.
    """
    staging = _require_root(root)
    entry = staging / name
    if not (entry.exists() or entry.is_symlink()):
        raise SystemExit(f"{name!r} is not staged in {staging}")

    if entry.is_symlink():
        entry.unlink()
    elif entry.is_dir():
        if not force:
            raise SystemExit(
                f"{entry} is a real directory, not a link -- removing it deletes the data.\n"
                f"If that is what you mean:  ethos-data staging remove {name} --force"
            )
        import shutil

        shutil.rmtree(entry)

    index = _read_index(staging)
    index.pop(name, None)
    _write_index(staging, index)
    return entry


def _describe(staging: Path, name: str, index: dict) -> StagedDataset:
    entry = staging / name
    target = entry.resolve()
    record = index.get(name, {})
    files = total = 0
    if target.is_dir():
        for path, _ in iter_files(target):
            files += 1
            total += path.stat().st_size
    return StagedDataset(
        name=name,
        entry=entry,
        target=target,
        files=files,
        bytes=total,
        note=record.get("note", ""),
        added=record.get("added", ""),
        added_by=record.get("added_by", ""),
    )


def list_staged(root: str | Path | None = None) -> list[StagedDataset]:
    """Everything in the staging root, described from what is on disk."""
    staging = staging_root(root)
    if staging is None or not staging.is_dir():
        return []
    index = _read_index(staging)
    return [_describe(staging, name, index) for name in staged_names(staging)]


def _official_entry(roots: Roots, name: str) -> Path | None:
    """Where the official version of a dataset sits, if there is one.

    Membership of the catalogue is decided from the two official roots rather
    than from datacatalog.json, deliberately: this has to answer for a machine
    that may have no catalogue loaded, and the caches are the thing that
    actually determines what a job can resolve. A dataset described in the
    catalogue but not yet linked into the public cache is, on this machine,
    exactly as unavailable as one nobody has described at all.
    """
    for root in (roots.public, roots.restricted):
        if root is None:
            continue
        entry = root / name
        if entry.exists() or entry.is_symlink():
            return entry
    return None


def classify_staged(
    roots: "Roots | None" = None,
    root: str | Path | None = None,
) -> list[StagedDataset]:
    """Every staged dataset, each marked NEW or SHADOWING.

    NEW means the name has no entry in the public or restricted cache, so this
    machine holds the only copy and nothing else can resolve it. Those are the
    datasets that still need describing, uploading, or deleting before anybody
    can rely on the catalogue being complete.
    """
    roots = roots if roots is not None else Roots.coerce(None)
    staging = Path(root).expanduser() if root is not None else roots.staging
    if staging is None or not staging.is_dir():
        return []

    index = _read_index(staging)
    described = []
    for name in staged_names(staging):
        official = _official_entry(roots, name)
        base = _describe(staging, name, index)
        described.append(replace(
            base,
            status=SHADOWING if official is not None else NEW,
            official=official,
        ))
    return described


def staged_only(
    roots: "Roots | None" = None,
    root: str | Path | None = None,
) -> list[StagedDataset]:
    """Staged datasets that exist *only* here -- not in either official cache.

    The answer to "what have we still not described?", which is the question
    that gates deleting anything from shared storage.
    """
    return [staged for staged in classify_staged(roots, root) if staged.is_new]


def staged_names(root: str | Path | None = None) -> list[str]:
    staging = staging_root(root)
    if staging is None or not staging.is_dir():
        return []
    return sorted(
        p.name for p in staging.iterdir()
        if p.name != INDEX_FILE and (p.is_dir() or p.is_symlink())
    )


def synthesize(name: str, directory: Path, access: str = STAGING_ACCESS) -> Dataset:
    """Build a Dataset from a directory, with no manifest behind it.

    Sizes come from ``stat`` and there are no checksums -- ``hash`` is left
    empty, which ``verify`` reports as unverifiable rather than as correct.
    """
    if not directory.is_dir():
        raise AccessError(
            f"staging entry {name!r} is not a readable directory: {directory}. "
            "Restore its target or remove the staging entry; refusing an empty "
            "selection or a fallback to official data."
        )
    resources: dict[str, Resource] = {}
    total = 0
    for path, relative in iter_files(directory):
        size = path.stat().st_size
        total += size
        resources[relative] = Resource(
            dataset=name,
            name=relative.replace("/", "-").lower(),
            path=relative,
            bytes=size,
            hash="",
            mediatype="application/octet-stream",
        )

    entry = {
        "name": name,
        "ethos:access": access,
        "ethos:visibility": "hidden",
        "ethos:file_count": len(resources),
        "ethos:total_bytes": total,
    }
    dataset = Dataset(name=name, title=f"{name} (staged, not in the catalogue)", entry=entry)
    # Setting the descriptor is what makes load() a no-op: there is no
    # datapackage.json to fetch, and asking for one must not reach the network.
    dataset._descriptor = {
        "name": name,
        "ethos:staged": True,
        "ethos:access": access,
        "resources": [],
    }
    dataset._resources = resources
    return dataset


def apply_staging(
    catalog: Catalog,
    roots: "Roots | None" = None,
    warn: bool = True,
) -> list[str]:
    """Shadow the catalogue with whatever is in the staging root.

    A staged entry replaces the catalogue's description of that dataset
    entirely, because during development the file list is exactly the thing that
    keeps changing. Restricted datasets are never shadowed.

    Returns the names that were shadowed or added.
    """
    roots = roots if roots is not None else Roots.coerce(None)
    if roots.staging is None or not roots.staging.is_dir():
        return []

    shadowed = []
    for name in staged_names(roots.staging):
        directory = roots.staging / name
        known = catalog.datasets.get(name)
        if known is not None and known.access == "restricted":
            # Always warned about, whatever ``warn`` says. Somebody has put a
            # directory named after a licensed dataset into a development
            # overlay; that it was ignored is exactly the thing they must be
            # told, and it is not the routine "staging is on" noise that
            # ``warn`` exists to quieten.
            warnings.warn(
                f"{name!r} is staged at {directory} but is a restricted dataset; "
                f"the staging entry is IGNORED. Licensed data is only ever read from "
                f"the restricted cache.",
                UserWarning,
                stacklevel=2,
            )
            continue
        access = known.access if known is not None else STAGING_ACCESS
        catalog.datasets[name] = synthesize(name, directory, access)
        shadowed.append(name)

    if shadowed and warn:
        warnings.warn(
            f"staging is active: {', '.join(shadowed)} "
            f"{'is' if len(shadowed) == 1 else 'are'} read from {roots.staging} instead of "
            f"the catalogue. Results from staged data are not reproducible.",
            UserWarning,
            stacklevel=2,
        )
    return shadowed


def with_staging(catalog: Catalog, roots: Roots | None = None, warn: bool = True) -> Catalog:
    """Return a staging view without replacing datasets in the caller's catalogue.

    The catalogue can be reused for an official-data check after development;
    applying a temporary overlay must not leave hashless datasets in that object.
    """
    view = replace(catalog, datasets=dict(catalog.datasets))
    apply_staging(view, roots, warn=warn)
    return view
