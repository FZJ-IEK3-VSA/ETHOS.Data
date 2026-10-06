"""Building the public cache as a namespace of links, from the catalogue.

    ethos-data link --all --root /shared/ethos/cache --dry-run
    ethos-data link --all --root /shared/ethos/cache

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
itself reads a source checkout: ``source_dir`` is never published -- it is a
statement about one machine -- so the namespace is built by somebody who knows
where things are, in practice in the cluster's public cache, which every
cluster user's ``public_cache`` names. It holds public data only: a restricted
dataset is linked by name into the restricted cache of its access combination.

**Real directories are never touched.** An entry that has been downloaded from
dCache, or materialised with ``ethos-data materialize``, is data the cache owns;
replacing it with a link would silently discard it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import report
from ..formats import keys as k
from ..formats.derived import license_settled
from . import (
    dataset_name_for,
    datasets_dir,
    is_namespace,
    iter_dataset_dirs,
    read_descriptor,
    source_dir_of,
)

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


def plan(catalog_root: Path, root: Path, prune: bool = False) -> list[Action]:
    """Decide what the namespace needs, without touching the filesystem."""
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
                    detail="restricted: link it by name into the restricted cache of "
                    "its access combination",
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
                    "linking it into a cache other people read",
                )
            )
            continue

        source = source_dir_of(datasets_dir(catalog_root) / name, meta)
        if source is None:
            actions.append(
                Action(name, "skip", entry, detail="no source_dir in dataset.yaml")
            )
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


@dataclass
class NamespaceResult:
    """The actions ``link --all`` planned, and whether it carried them out."""

    actions: list[Action]
    applied: bool = False

    @property
    def problems(self) -> list[Action]:
        """The datasets whose ``source_dir`` does not exist."""
        return [action for action in self.actions if action.verb == "missing"]

    @property
    def ok(self) -> bool:
        return not self.problems


@report.reported
def run(
    catalog_root: Path,
    root: Path,
    *,
    dry_run: bool = False,
    prune: bool = False,
) -> NamespaceResult:
    """Plan the namespace, report it, and -- unless ``dry_run`` -- build it.

    ``root`` is the public cache the caller names, and deliberately has no
    default: a link tree built in a directory nobody named would still print as
    a success.
    """
    actions = plan(catalog_root, root, prune=prune)

    changes = [a for a in actions if a.changes_anything]
    problems = [a for a in actions if a.verb == "missing"]

    report.info(f"namespace root: {root}")
    report.info(f"catalogue:      {catalog_root}\n")
    for action in actions:
        report.info(f"  {action}")

    if dry_run:
        report.info(f"\n{len(changes)} change(s) would be made. Nothing was written.")
        return NamespaceResult(actions)

    if not changes:
        report.info("\nnothing to do.")
        return NamespaceResult(actions)

    apply(changes)
    report.info(f"\n{len(changes)} change(s) applied.")
    if problems:
        report.info(
            f"{len(problems)} dataset(s) have a source_dir that does not exist -- "
            f"fix dataset.yaml or the storage, then run this again."
        )
    return NamespaceResult(actions, applied=True)
