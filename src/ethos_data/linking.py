"""Pointing one cache entry at data that is already on this machine.

    ethos-data link global-wind-atlas /data/GWA_4.0
    ethos-data unlink global-wind-atlas

This is the single-dataset counterpart to ``ethos-data catalog link-cache``,
which builds the whole namespace from the catalogue's ``source_dir`` values. That
command is the right one when there is a catalogue checkout and a maintainer
building a shared cache for everybody. This one is for the cases it cannot
reach:

  * a dataset that has been uploaded, so its descriptor no longer has a
    ``source_dir`` to link from, but whose bytes are sitting right here and do
    not need downloading again
  * a restricted dataset, which ``link-cache`` skips on purpose: its entry is
    made by an administrator, in the restricted root
  * anybody who has the files and no catalogue checkout at all

Until now the answer was "type ``ln -s`` yourself", which is advice that quietly
does the wrong thing on Windows -- ``ln -s`` in Git Bash copies the whole tree
instead of linking -- and which puts the entry at whatever path the person
guessed rather than the one retrieval will look in.

**The entry is a link, and that is the point.** A symbolic link is how the cache
records "these bytes are borrowed": retrieval reads them in place, refuses to
write through them, and ``ethos-data materialize`` knows there is something to
copy. A real directory means the opposite -- data the cache owns -- so neither
this module nor ``link-cache`` will ever replace one with a link.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .access import entry_for
from .catalog import Catalog
from .config import Roots

__all__ = ["LinkError", "LinkReport", "link", "unlink"]


class LinkError(RuntimeError):
    """Raised when an entry cannot be created or removed, and why."""


@dataclass
class LinkReport:
    """What happened to one cache entry."""

    dataset: str
    verb: str
    entry: Path
    target: Path | None = None
    #: One file the manifest lists that is not under the target -- the symptom of
    #: a link made one directory too high or too low. Empty when nothing is
    #: wrong, or when the inventory could not be read to check.
    missing: str = ""

    def __str__(self) -> str:
        if self.target is None:
            return f"{self.verb:<11} {self.dataset}  {self.entry}"
        # Windows stores a symbolic link with a \\?\ extended-length prefix, so
        # reading one back shows a path nobody typed. It is the same directory;
        # printing the spelling the person used is what makes the line checkable.
        target = str(self.target).removeprefix("\\\\?\\")
        return f"{self.verb:<11} {self.dataset}  {self.entry} -> {target}"


def _absolute(directory: str | Path) -> Path:
    """The directory as an absolute path, with symbolic links left alone.

    Absolute because a link records the string it is given, and a relative one
    would be read against the cache directory rather than the caller's. Not
    ``resolve()``d, for the reason the manifest builder does not resolve
    ``source_dir`` either: a curated path that itself goes through a link is the
    one that stays correct when the storage behind it moves, and it is what the
    next person reading ``ls -l`` needs to recognise.
    """
    path = Path(directory).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _sample_missing(catalog: Catalog, name: str, target: Path) -> str:
    """One file from the manifest that is not under ``target``, if there is one.

    Linking one directory too high or too low is the ordinary mistake, and it is
    silent: the entry exists, and every read fails later with a missing file. One
    stat catches it while the person is still looking at the command they typed.
    Any failure to answer is not the operation's problem -- a diagnostic must
    never be the thing that breaks the thing it is diagnosing.
    """
    try:
        resources = catalog.dataset(name).resources
        first = next(iter(resources.values()), None)
        if first is None or (target / first.path).exists():
            return ""
        return first.path
    except Exception:
        return ""


def _refusal(name: str, target: Path, error: OSError) -> str:
    """Why the link could not be made, and what to do instead."""
    if os.name != "nt":
        return f"could not create the link: {error}"
    return (
        f"Windows would not create the link ({error}).\n"
        "Symbolic links need Developer Mode (Settings > System > For developers), "
        "or an elevated shell.\n"
        "Without either, point this one dataset at the directory instead:\n"
        f"    ethos-data config set-root {name} {target}\n"
        "Do not substitute a junction (mklink /J): it is reported as an ordinary "
        "directory, so the cache would treat borrowed data as a copy it owns and "
        "could write downloads into it."
    )


def link(
    catalog: Catalog,
    name: str,
    directory: str | Path,
    roots: "Roots | str | Path | None" = None,
    force: bool = False,
) -> LinkReport:
    """Make this dataset's cache entry a symbolic link to ``directory``.

    The entry goes in whichever root the dataset's access class belongs to, so a
    restricted dataset lands in the restricted cache or nowhere at all.

    Raises :class:`LinkError` if the directory is not there, if the entry is
    already a link and ``force`` is not set, or if the entry is a real directory
    -- which is never replaced, because it is data the cache owns.
    """
    roots = Roots.coerce(roots)
    try:
        entry = entry_for(catalog, roots, name)
    except ValueError as error:
        raise LinkError(str(error)) from None

    target = _absolute(directory)
    if not target.is_dir():
        raise LinkError(f"not a directory: {target}")

    verb = "linked"
    if entry.is_symlink():
        if not force:
            raise LinkError(
                f"{entry} already points at {entry.readlink()}.\n"
                f"Repoint it with --force, or remove it with `ethos-data unlink {name}`."
            )
        entry.unlink()
        verb = "repointed"
    elif entry.exists():
        raise LinkError(
            f"{entry} is a real directory, not a link -- data the cache owns. Replacing "
            "it with a link would discard it. Move or delete it deliberately first."
        )

    entry.parent.mkdir(parents=True, exist_ok=True)
    try:
        entry.symlink_to(target, target_is_directory=True)
    except OSError as error:
        raise LinkError(_refusal(name, target, error)) from None

    return LinkReport(name, verb, entry, target, missing=_sample_missing(catalog, name, target))


def unlink(
    catalog: Catalog,
    name: str,
    roots: "Roots | str | Path | None" = None,
) -> LinkReport:
    """Remove this dataset's cache entry, if it is a link.

    The data it points at is never touched. A real directory is refused: it is
    the cache's own copy, and deleting somebody's downloaded or materialised
    dataset is not something a command called ``unlink`` should do.
    """
    roots = Roots.coerce(roots)
    try:
        entry = entry_for(catalog, roots, name)
    except ValueError as error:
        raise LinkError(str(error)) from None

    if entry.is_symlink():
        target = entry.readlink()
        entry.unlink()
        return LinkReport(name, "removed", entry, target)
    if entry.exists():
        raise LinkError(
            f"{entry} is a real directory, not a link -- it holds the cache's own copy of "
            f"{name!r}. Remove it yourself if that is really what you mean."
        )
    raise LinkError(f"no cache entry at {entry}")
