"""Building the public cache as a namespace of links, from the catalogue.

    ethos-data catalog link-cache --root /shared/ethos/public --dry-run
    ethos-data catalog link-cache --root /shared/ethos/public

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

This is maintainer-side on purpose. ``source_dir`` is never published -- it is a
statement about one machine -- so the namespace is built once by somebody who
knows where things are, and everybody else just points ``public_cache`` at the
result. That is what keeps the user-facing configuration down to two settings.

**Real directories are never touched.** An entry that has been downloaded from
dCache, or materialised with ``ethos-data materialize``, is data the cache owns;
replacing it with a link would silently discard it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..catalogs import license_settled
from . import dataset_name_for, datasets_dir, is_namespace, iter_dataset_dirs

__all__ = ["Action", "plan", "apply", "run"]

RESTRICTED = "restricted"


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
        meta = yaml.safe_load((directory / "dataset.yaml").read_text(encoding="utf-8")) or {}
        found.append((dataset_name_for(root, directory), meta))
    return found


def _source_of(catalog_root: Path, name: str, meta: dict) -> Path | None:
    raw = meta.get("source_dir")
    if not raw:
        return None
    source = Path(str(raw)).expanduser()
    if not source.is_absolute():
        source = (datasets_dir(catalog_root) / name / source).resolve()
    return source


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
        access = meta.get("ethos:access", "public")

        if access == RESTRICTED:
            actions.append(Action(
                name, "skip", entry,
                detail="restricted: belongs in the restricted cache as a real, owned copy, "
                       "not as a link"))
            continue

        if not license_settled(meta):
            # Building this namespace is how a dataset reaches everybody on the
            # machine. An absent licence is a question, not a permission, and
            # answering it is one line in dataset.yaml.
            actions.append(Action(
                name, "skip", entry,
                detail="unresolved licensing: record the terms in dataset.yaml before "
                       "linking it into a shared cache"))
            continue

        source = _source_of(catalog_root, name, meta)
        if source is None:
            actions.append(Action(name, "skip", entry, detail="no source_dir in dataset.yaml"))
            continue

        if not source.is_dir():
            actions.append(Action(
                name, "missing", entry, source,
                detail=f"source_dir does not exist: {source}"))
            continue

        if entry.is_symlink():
            current = entry.readlink()
            if _same_target(current, source):
                actions.append(Action(name, "unchanged", entry, source))
            else:
                actions.append(Action(
                    name, "repoint", entry, source, detail=f"was {current}"))
        elif entry.exists():
            actions.append(Action(
                name, "keep", entry, source,
                detail="a real directory the cache owns; not replaced with a link"))
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
            actions.append(Action(
                name, "prune", existing,
                detail="not in the catalogue any more"))

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


def run(catalog_root: Path, args) -> int:
    if args.root is None:
        from ..config import resolve_public_cache

        resolved = resolve_public_cache()
        root = resolved.value
        print(f"no --root given; using the public cache from {resolved.source}")
    else:
        root = Path(args.root).expanduser()
    actions = plan(catalog_root, root, prune=args.prune)

    changes = [a for a in actions if a.changes_anything]
    problems = [a for a in actions if a.verb == "missing"]

    print(f"namespace root: {root}")
    print(f"catalogue:      {catalog_root}\n")
    for action in actions:
        print(f"  {action}")

    if args.dry_run:
        print(f"\n{len(changes)} change(s) would be made. Nothing was written.")
        return 1 if problems else 0

    if not changes:
        print("\nnothing to do.")
        return 1 if problems else 0

    apply(changes)
    print(f"\n{len(changes)} change(s) applied.")
    if problems:
        print(f"{len(problems)} dataset(s) have a source_dir that does not exist -- "
              f"fix dataset.yaml or the storage, then run this again.")
        return 1
    return 0
