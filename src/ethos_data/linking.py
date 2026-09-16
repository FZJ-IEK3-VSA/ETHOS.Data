"""Pointing one cache entry at data that is already on this machine.

    ethos-data link global-wind-atlas /data/GWA_4.0   # this directory
    ethos-data link global-wind-atlas                 # its source_dir
    ethos-data link --all                             # every source_dir there is
    ethos-data unlink global-wind-atlas

This is the single-dataset counterpart to ``ethos-data catalog link-cache``.
That command builds a *shared* namespace: it takes the root to build explicitly,
reviews the whole catalogue with ``--dry-run``, and prunes stale entries. This
one fills the cache this machine is configured to read, and reaches three things
link-cache does not:

  * one dataset by name, rather than every one in the catalogue
  * a dataset that has been uploaded, so its descriptor has no ``source_dir``
    left, but whose bytes are sitting right here and need no downloading
  * a restricted dataset, which ``link-cache`` skips on purpose -- a shared
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
this module nor ``link-cache`` will ever replace one with a link.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .access import entry_for
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
        # Windows stores a symbolic link with a \\?\ extended-length prefix, so
        # reading one back shows a path nobody typed. It is the same directory;
        # printing the spelling the person used is what makes the line checkable.
        target = str(self.target).removeprefix("\\\\?\\")
        return f"{self.verb:<11} {self.dataset}  {self.entry} -> {target}"


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
    one thing this does and ``catalog link-cache`` does not: it skips restricted
    datasets, because building a shared public namespace must never touch them,
    while linking one deliberately by name is how an authorised installation gets
    registered.

    Raises :class:`LinkError` if the directory is not there, if the entry is
    already a link and ``force`` is not set, or if the entry is a real directory
    -- which is never replaced, because it is data the cache owns.
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
