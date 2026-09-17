"""Pointing one cache entry at data that is already on this machine.

    ethos-data link global-wind-atlas /data/GWA_4.0   # this directory
    ethos-data link global-wind-atlas                 # its source_dir
    ethos-data link --all                             # every source_dir there is
    ethos-data unlink global-wind-atlas

This is the single-dataset mode of ``ethos-data link``; the other is ``--all``,
which is a different job wearing the same name. ``--all`` builds a *shared*
namespace from a source checkout: it takes the root to build explicitly, reviews
the whole catalogue with ``--dry-run``, and prunes stale entries. Naming a
dataset instead fills the cache this machine is configured to read, and reaches
three things ``--all`` does not:

  * one dataset by name, rather than every one in the catalogue
  * a dataset that has been uploaded, so its descriptor has no ``source_dir``
    left, but whose bytes are sitting right here and need no downloading
  * a restricted dataset, which ``--all`` skips on purpose -- a shared
    public namespace must never touch licensed data, but registering one
    authorised installation by name is exactly how it is meant to be done

Until now the answer was "type ``ln -s`` yourself", which is advice that quietly
does the wrong thing on Windows -- ``ln -s`` in Git Bash copies the whole tree
instead of linking -- and which puts the entry at whatever path the person
guessed rather than the one retrieval will look in.

**The entry is a link, and that is the point.** A symbolic link is how the cache
records "these bytes are borrowed": retrieval reads them in place, refuses to
write through them, and ``ethos-data materialize`` knows there is something to
copy. A real directory means the opposite -- data the cache owns -- so neither
mode of ``ethos-data link`` will ever replace one with a link.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .access import borrowed_parent, entry_for
from .catalogs import LICENSE_RESOLVED, Catalog
from .config import Roots

__all__ = ["LinkError", "LinkReport", "link", "source_dir_for", "unlink"]


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
        return (
            f"{self.verb:<11} {self.dataset}  {self.entry} -> {_as_typed(self.target)}"
        )


def _as_typed(path: Path | str) -> Path:
    """A path as somebody would have typed it, without Windows's ``\\\\?\\`` prefix.

    Windows stores a symbolic link with an extended-length prefix, so reading one
    back and printing it shows a path nobody wrote, which cannot be compared with
    the ``source_dir`` or the directory the person is being asked to look at.
    Every place that compares a stored link with a configured directory, or shows
    one to be checked against the other, has to take the prefix off first -- so it
    is taken off here, once, rather than in each of them.
    """
    return Path(str(path).removeprefix("\\\\?\\"))


def _link_target(entry: Path) -> Path | None:
    """Where a link points, as it was typed, or ``None`` when that cannot be read.

    Reading a link is never the operation here, it is the diagnosis: this is
    called to say what an entry points at *now*, inside a message or a plan. So a
    link removed between the ``is_symlink()`` test and the ``readlink()`` call, or
    a reparse point the system will not describe, has to cost the sentence its
    detail rather than cost the run -- which is what lets
    :func:`ethos_data.maintain.namespace.plan` promise that no state the cache is
    in makes it raise.
    """
    try:
        return _as_typed(entry.readlink())
    except OSError:
        return None


def source_dir_for(name: str, catalog_root: str | Path | None = None) -> Path:
    """The ``source_dir`` a source catalogue records for this dataset.

    ``source_dir`` is popped out of the descriptor when it is built, so it lives
    in the hand-written ``datasets/<name>/dataset.yaml`` and nowhere else -- not
    in ``datapackage.json``, not in any ``datacatalog.json``. Reading it means
    reading the checkout, exactly as ``catalog build`` and ``catalog upload`` do;
    ``catalog_root`` names it, or it is searched for upward from the current
    directory.

    The maintainer half of the package is imported here rather than at module
    scope so that ``import ethos_data`` stays the read-only library it promises
    to be: nothing is pulled in until somebody asks for a path only a checkout
    can answer.
    """
    from .maintain import datasets_dir, resolve_catalog_root

    try:
        root = resolve_catalog_root(
            str(catalog_root) if catalog_root is not None else None
        )
    except SystemExit as error:
        # `resolve_catalog_root` is written for the maintainer commands, which
        # exit on a missing checkout. Here it is one way of answering a question,
        # so it becomes the same error every other failure in this module raises.
        raise LinkError(str(error)) from None
    descriptor = datasets_dir(root) / name / "dataset.yaml"
    if not descriptor.is_file():
        raise LinkError(f"no dataset called {name!r} in {datasets_dir(root)}")

    import yaml

    meta = yaml.safe_load(descriptor.read_text(encoding="utf-8")) or {}
    raw = meta.get("source_dir")
    if not raw:
        raise LinkError(
            f"{descriptor} has no source_dir, so there is nothing to link from.\n"
            "An uploaded dataset has none by design -- dCache holds it. Name the "
            f"directory instead:\n    ethos-data link {name} /path/to/{name}"
        )
    source = Path(str(raw)).expanduser()
    if not source.is_absolute():
        source = (datasets_dir(root) / name / source).resolve()
    return source


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


def _require_settled_licence(catalog: Catalog, name: str) -> None:
    """Refuse to put a dataset with unread terms into a cache other people read.

    A cache entry is how a dataset reaches everybody sharing that cache, and an
    absent licence is a question, not a permission. The reader has always warned
    about this; a warning is the right answer when somebody already has the data
    in front of them and the wrong one at the moment it is being handed out.

    Staging is deliberately exempt, and named here because it is the answer to
    "but I need to work with it now": a staging entry is one person's, shadows
    nothing for anybody else, and is unverifiable by construction.
    """
    if catalog.dataset(name).license_status == LICENSE_RESOLVED:
        return
    try:
        note = catalog.dataset(name).descriptor.get("ethos:license_note", "")
    except Exception:
        # The status is promoted into the index precisely so that asking this
        # costs no fetch. The note is a nicety on top -- and it is stripped from
        # published catalogues anyway -- so not having the descriptor to hand
        # must not turn a clear refusal into a crash.
        note = ""
    raise LinkError(
        f"{name!r} has unresolved licensing, so it is not linked into a cache other "
        f"people read. {note}\n".rstrip()
        + "\n"
        "Record the terms in its dataset.yaml -- a `licenses:` entry, or "
        "`ethos:license_status: resolved` once somebody has read them -- and rebuild.\n"
        "To work with it meanwhile, stage it instead:\n"
        f"    staging add {name} <directory>  (with your package's data command)"
    )


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


def _borrowed_refusal(entry: Path, borrowed: Path) -> str:
    """Why an entry below a borrowed link is refused -- in both modes at once.

    The walk that finds ``borrowed`` is already shared
    (:func:`ethos_data.access.borrowed_parent`); this is the sentence that goes
    with it. Both modes refuse the same write, for the same reason, with the same
    remedy, and differ only in *when* they refuse -- which is a property of the
    mode and not of the sentence. A second copy of it in the other mode is the
    copy that goes stale.
    """
    return (
        f"{borrowed} is a symbolic link, not a directory the cache owns -- the bytes "
        f"under it are borrowed. Creating {entry} would write this cache's own entry "
        f"into somebody else's tree, where removing that one link takes the entry with "
        f"it. Remove {borrowed} and run this again: it discards nothing, because "
        "nothing under it belongs to the cache."
    )


def _lost(name: str, entry: Path, replaced: Path | None) -> str:
    """What ``--force`` has already destroyed, when the new link cannot be made.

    There is no atomic repoint to fall back on. Renaming a freshly made symbolic
    link over an existing one is refused by Windows whichever call is used --
    a directory symbolic link carries the directory attribute, and the replace
    flag will not take it -- so the old entry has to go before the new one can be
    attempted. When the attempt then fails, the person asked for a repoint and got
    a deletion, and the one thing that deletion destroyed is the record of where
    the entry pointed, which is also the only thing needed to put it back. Saying
    so is the whole of what is left to do about it.
    """
    if replaced is None:
        return ""
    quoted = f'"{replaced}"' if " " in str(replaced) else str(replaced)
    return (
        f"\n--force had already removed the link this was to replace, so there is no "
        f"entry at {entry} at all now. It pointed at {replaced}. Once links can be "
        f"made, put it back with:\n    ethos-data link {name} {quoted}"
    )


def link(
    catalog: Catalog,
    name: str,
    directory: str | Path | None = None,
    roots: "Roots | str | Path | None" = None,
    force: bool = False,
    catalog_root: str | Path | None = None,
) -> LinkReport:
    """Make this dataset's cache entry a symbolic link to ``directory``.

    Without a ``directory``, the source catalogue's ``source_dir`` for this
    dataset is used -- see :func:`source_dir_for`, which is also what decides
    where ``catalog_root`` is looked for.

    The entry goes in whichever root the dataset's access class belongs to, so a
    restricted dataset lands in the restricted cache or nowhere at all. That is
    one thing naming a dataset does and ``ethos-data link --all`` does not:
    ``--all`` skips restricted datasets, because building a shared public
    namespace must never touch them, while linking one deliberately by name is
    how an authorised installation gets registered.

    Raises :class:`LinkError` if the directory is not there, if the entry is
    already a link and ``force`` is not set, if the entry is a real directory --
    which is never replaced, because it is data the cache owns -- or if a
    component of the path above it is itself a link, because the entry would
    then be created inside data the cache has only borrowed.
    """
    roots = Roots.coerce(roots)
    try:
        entry = entry_for(catalog, roots, name)
    except ValueError as error:
        raise LinkError(str(error)) from None

    _require_settled_licence(catalog, name)

    if directory is None:
        directory = source_dir_for(name, catalog_root)
    target = _absolute(directory)
    if not target.is_dir():
        raise LinkError(f"not a directory: {target}")

    # Checked above the whole cascade below, not merely above the ``mkdir``
    # that would do the damage. ``entry.parent.mkdir(parents=True,
    # exist_ok=True)`` succeeds on a parent that is already a link to a
    # directory, so the entry would be written into somebody else's tree and
    # reported as made -- but a ``--force`` repoint gets there only after
    # ``entry.unlink()`` has run, which would destroy the existing entry on the
    # way to refusing. Refusing first is also the right answer on its own
    # terms: repointing an entry that lives inside a borrowed tree is another
    # write through the link.
    borrowed = borrowed_parent(entry, name)
    if borrowed is not None:
        raise LinkError(_borrowed_refusal(entry, borrowed))

    verb = "linked"
    #: Read before the removal, because the removal is what destroys it.
    replaced: Path | None = None
    if entry.is_symlink():
        if not force:
            raise LinkError(
                f"{entry} already points at {_link_target(entry)}.\n"
                f"Repoint it with --force, or remove it with `ethos-data unlink {name}`."
            )
        replaced = _link_target(entry)
        try:
            entry.unlink()
        except OSError as error:
            raise LinkError(
                f"could not remove {entry}, the link this was to replace: {error}. "
                "It is still there and still points where it did."
            ) from None
        verb = "repointed"
    elif entry.exists():
        raise LinkError(
            f"{entry} is a real directory, not a link -- data the cache owns. Replacing "
            "it with a link would discard it. Move or delete it deliberately first."
        )

    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise LinkError(
            f"could not create {entry.parent}, the directory this entry goes in: "
            f"{error}" + _lost(name, entry, replaced)
        ) from None
    try:
        entry.symlink_to(target, target_is_directory=True)
    except OSError as error:
        raise LinkError(
            _refusal(name, target, error) + _lost(name, entry, replaced)
        ) from None

    return LinkReport(
        name, verb, entry, target, missing=_sample_missing(catalog, name, target)
    )


def unlink(
    catalog: Catalog,
    name: str,
    roots: "Roots | str | Path | None" = None,
) -> LinkReport:
    """Remove this dataset's cache entry, if it is a link.

    The data it points at is never touched. A real directory is refused: it is
    the cache's own copy, and deleting somebody's downloaded or materialised
    dataset is not something a command called ``unlink`` should do.

    Deliberately not guarded against a borrowed parent, unlike :func:`link`. An
    entry an earlier version of this command wrote *through* such a link can
    only be cleaned up by removing it, and removing a link discards nothing; a
    guard here would leave that damage unreachable by the tool that made it.
    """
    roots = Roots.coerce(roots)
    try:
        entry = entry_for(catalog, roots, name)
    except ValueError as error:
        raise LinkError(str(error)) from None

    if entry.is_symlink():
        target = _link_target(entry)
        try:
            entry.unlink()
        except OSError as error:
            raise LinkError(
                f"could not remove {entry}: {error}. The entry is still there and "
                "still points where it did."
            ) from None
        return LinkReport(name, "removed", entry, target)
    if entry.exists():
        raise LinkError(
            f"{entry} is a real directory, not a link -- it holds the cache's own copy of "
            f"{name!r}. Remove it yourself if that is really what you mean."
        )
    raise LinkError(f"no cache entry at {entry}")
