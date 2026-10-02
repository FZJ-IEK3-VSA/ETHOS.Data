"""Building the public cache as a namespace of links, from the catalogue.

    ethos-data link --all --root /shared/ethos/public --dry-run
    ethos-data link --all --root /shared/ethos/public

The result is one entry per dataset, named for the dataset, pointing at wherever
that data already sits on this machine:

    <public cache>/
    |-- global-wind-atlas  -> /legacy/shared/Global_Wind_Atlas/GWA_4.0
    |-- corine-land-cover  -> /legacy/shared/landcover/clc2018
    |-- test-data/era5     -> /legacy/shared/era5-subset   (a nested dataset,
    |                                                       entry where its name says)
    `-- submarine-cables/     (a real directory, downloaded from dCache)

Nothing is copied and nothing is moved: the entries cost a few hundred bytes in
total. What they buy is a stable name for each dataset, so that when the storage
behind one is reorganised, exactly one link changes and every user follows.

The command that drives this planner sits with the user-facing ``link`` rather
than under ``catalog``, because filling a whole cache from a checkout and
pointing one dataset at a directory are the same job at two scales. The planner
itself still reads a source checkout, and that has not changed: ``source_dir``
is never published -- it is a statement about one machine -- so the namespace is
built once by somebody who knows where things are, and everybody else just
points ``public_cache`` at the result. That is what keeps the user-facing
configuration down to two settings.

**Real directories are never touched.** An entry that has been downloaded from
dCache, or materialised with ``ethos-data materialize``, is data the cache owns;
replacing it with a link would silently discard it.

Given ``--catalog-root``, the command also takes the ``link`` step of each
dataset it links (see :mod:`.status`): a dataset whose state does not allow it,
a draft not built yet, is skipped, and every link is recorded as a copy in the
dataset's ``status.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
from ..formats import keys as k
from ..formats.derived import license_settled
from ..formats.status_file import Copy
from ..model import lifecycle
from . import (
    dataset_name_for,
    datasets_dir,
    is_namespace,
    iter_dataset_dirs,
    read_descriptor,
)
from . import status as dataset_status

__all__ = ["Action", "plan", "apply", "run"]

RESTRICTED = k.RESTRICTED


@dataclass
class Action:
    """What should happen to one entry, and why."""

    dataset: str
    verb: str
    entry: Path | None = None
    target: Path | None = None
    detail: str = ""

    @property
    def changes_anything(self) -> bool:
        return self.verb in ("link", "repoint", "prune")

    def __str__(self) -> str:
        line = f"{self.verb:<12} {self.dataset:<32}"
        if self.target is not None and self.verb in ("link", "repoint"):
            line += f" -> {self.target}"
        return f"{line}  {self.detail}".rstrip()


def _declared(catalog_root: Path) -> list[tuple[str, dict]]:
    """Every dataset with a dataset.yaml, at any depth, by catalogue name.

    Not a listing of the top level, because a nested family is described as a
    dataset.yaml naming the family with the datasets that actually hold files
    *below* it. Reading only the top level found the family node, reported it as
    having no ``source_dir`` -- true, and not its job to have one -- and left
    every member unlinked, which is the whole family missing from the cache.

    The name is the path below ``datasets/``, so a member is ``family/member``
    and its entry is ``<root>/family/member``: the same name the manifest
    builder writes, the collections file uses, and the reader looks up.

    Namespace nodes are dropped rather than reported: a namespace owns no files,
    so "no source_dir" is not a finding about it.
    """
    root = datasets_dir(catalog_root)
    found = []
    for directory in iter_dataset_dirs(root):
        if is_namespace(directory):
            continue
        found.append((dataset_name_for(root, directory), read_descriptor(directory)))
    return found


def _same_target(current: Path, source: Path) -> bool:
    """Whether a link already points where the catalogue says it should.

    Compared as text, because a link *is* text -- resolving both would call two
    different curated paths the same thing the moment either went through
    another link, which is exactly what source_dir is allowed to do. The one
    spelling difference that is not a real difference is Windows's ``\\\\?\\``
    extended-length prefix, added when the link is stored: without stripping it,
    every run would repoint an entry that is already correct.
    """
    return str(current).removeprefix("\\\\?\\") == str(source).removeprefix("\\\\?\\")


def plan(
    catalog_root: Path, root: Path, prune: bool = False, *, record: bool = False
) -> list[Action]:
    """Decide what the namespace needs, without touching the filesystem.

    ``record`` skips a dataset whose state does not allow the ``link`` step.
    """
    actions: list[Action] = []
    declared = _declared(catalog_root)
    names = {name for name, _ in declared}

    for name, meta in declared:
        entry = root / name
        access = meta.get(k.ACCESS, k.PUBLIC)

        if access == RESTRICTED:
            actions.append(
                Action(
                    name,
                    "skip",
                    entry,
                    detail="restricted: belongs in the restricted cache as a real, owned copy, "
                    "not as a link",
                )
            )
            continue

        if not license_settled(meta):
            # Building this namespace is how a dataset reaches everybody on the
            # machine. An absent licence is a question, not a permission, and
            # answering it is one line in dataset.yaml.
            actions.append(
                Action(
                    name,
                    "skip",
                    entry,
                    detail="unresolved licensing: record the terms in dataset.yaml before "
                    "linking it into a shared cache",
                )
            )
            continue

        try:
            built_from = dataset_status.build_input(
                datasets_dir(catalog_root) / name, meta, name
            )
            state = built_from.status.state if built_from.status else None
            if state in (lifecycle.WITHDRAWN, lifecycle.PURGED):
                actions.append(
                    Action(
                        name, "skip", entry, detail="withdrawn: out of the catalogue"
                    )
                )
                continue
            if record and state is not None:
                lifecycle.step("link", state, name)
        except MaintenanceError as error:
            first = error.message.splitlines()[0]
            actions.append(Action(name, "skip", entry, detail=first))
            continue
        source = built_from.source_dir
        if source is None:
            detail = "no source_dir"
            if built_from.frozen:
                detail += ": its inventory is final"
            actions.append(Action(name, "skip", entry, detail=detail))
            continue

        if not source.is_dir():
            actions.append(
                Action(
                    name,
                    "missing",
                    entry,
                    source,
                    detail=f"source_dir does not exist: {source}",
                )
            )
            continue

        if entry.is_symlink():
            current = entry.readlink()
            if _same_target(current, source):
                actions.append(Action(name, "unchanged", entry, source))
            else:
                actions.append(
                    Action(name, "repoint", entry, source, detail=f"was {current}")
                )
        elif entry.exists():
            actions.append(
                Action(
                    name,
                    "keep",
                    entry,
                    source,
                    detail="a real directory the cache owns; not replaced with a link",
                )
            )
        else:
            actions.append(Action(name, "link", entry, source))

    if prune and root.is_dir():
        # The reader's own walk, so that a nested entry is found where its name
        # says it is (``family/member``) rather than not at all: listing the top
        # level would see ``family``, never look inside it, and prune nothing.
        from ..access import cache_entries

        for name, existing in cache_entries(root):
            if name in names or not existing.is_symlink():
                continue
            actions.append(
                Action(name, "prune", existing, detail="not in the catalogue any more")
            )

    return actions


def _record(catalog_root: Path, actions: list[Action]) -> tuple[int, list[str]]:
    """Record every link the namespace has now; (recorded, without a status file)."""
    recorded, unrecorded = 0, []
    for action in actions:
        if action.verb not in ("link", "repoint", "unchanged"):
            continue
        copy = Copy(
            kind=k.COPY_LINKED, location=str(action.entry), target=str(action.target)
        )
        state = dataset_status.record_copy(
            catalog_root, action.dataset, "link", copy, repeat=False
        )
        if state is None:
            unrecorded.append(action.dataset)
        else:
            recorded += 1
    return recorded, unrecorded


def apply(actions: list[Action]) -> list[Action]:
    """Carry out the planned actions. Only links are ever created or removed."""
    for action in actions:
        if action.verb == "link":
            action.entry.parent.mkdir(parents=True, exist_ok=True)
            action.entry.symlink_to(action.target)
        elif action.verb == "repoint":
            action.entry.unlink()
            action.entry.symlink_to(action.target)
        elif action.verb == "prune":
            action.entry.unlink()
    return actions


@report.reported
def run(
    catalog_root: Path,
    root: Path,
    *,
    dry_run: bool = False,
    prune: bool = False,
    record: bool = False,
) -> int:
    """Plan the namespace, report it, and -- unless ``dry_run`` -- build it.

    ``record`` takes the ``link`` step of every dataset linked, and records
    each link in its ``status.yaml``.

    ``root`` arrives already decided, and deliberately has no default. The
    earlier signature took the argparse namespace and looked the public cache up
    itself when ``--root`` was absent, which put a second cache lookup inside a
    command that had already done one. The two could answer differently -- a
    top-level ``--root`` the second lookup never saw, or ``$ETHOS_DATA_DIR`` read
    at a different moment -- and the result was a full link tree built in a
    directory the rest of the command had never mentioned, printed as a success.
    Deciding once, in the caller, is what makes that impossible rather than
    merely unlikely.
    """
    actions = plan(catalog_root, root, prune=prune, record=record)

    changes = [a for a in actions if a.changes_anything]
    problems = [a for a in actions if a.verb == "missing"]

    report.info(f"namespace root: {root}")
    report.info(f"catalogue:      {catalog_root}\n")
    for action in actions:
        report.info(f"  {action}")

    if dry_run:
        report.info(f"\n{len(changes)} change(s) would be made. Nothing was written.")
        return 1 if problems else 0

    if changes:
        apply(changes)
    if record:
        recorded, unrecorded = _record(catalog_root, actions)
        if recorded:
            report.info(f"\nrecorded {recorded} link(s) in the datasets' status files.")
        if unrecorded:
            report.warning(dataset_status.unrecorded(unrecorded))
    if not changes:
        report.info("\nnothing to do.")
        return 1 if problems else 0

    report.info(f"\n{len(changes)} change(s) applied.")
    if problems:
        report.info(
            f"{len(problems)} dataset(s) have a source_dir that does not exist -- "
            f"fix dataset.yaml or the storage, then run this again."
        )
        return 1
    return 0
