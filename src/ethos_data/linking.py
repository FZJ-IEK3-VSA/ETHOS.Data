"""Pointing one cache entry at data that is already on this machine.

    ethos-data link global-wind-atlas /data/GWA_4.0      # this directory
    ethos-data link global-wind-atlas                    # its source_dir
    ethos-data --root /shared/ethos/restricted/g link gadm-3.6 /data/gadm
    ethos-data link --all --root /shared/ethos/cache     # every source_dir there is
    ethos-data unlink global-wind-atlas

This is the single-dataset mode of ``ethos-data link``; the other is ``--all``,
which is a different job wearing the same name. ``--all`` builds a *shared*
namespace from a source checkout: it takes the root to build explicitly, reviews
the whole catalogue with ``--dry-run``, and prunes stale entries. Naming a
dataset instead fills one cache entry, and reaches three things ``--all`` does
not:

  * one dataset by name, rather than every one in the catalogue
  * a dataset that has been uploaded, so its descriptor has no ``source_dir``
    left, but whose bytes are sitting right here and need no downloading
  * a restricted dataset, which ``--all`` skips on purpose -- a shared
    public namespace must never touch restricted data, but registering one
    authorised installation by name, in the restricted cache of its access
    combination, is exactly how it is meant to be done

The entry goes where retrieval reads it: a public dataset's into the public
cache, a restricted dataset's into a listed restricted cache, and into the
cache the global ``--root`` names when one is named; see
:func:`ethos_data.access.entry_for`. ``ln -s`` by hand puts it wherever the
person guessed, and in Git Bash on Windows copies the whole tree instead.

**The entry is a link, and that is the point.** A symbolic link is how the cache
records "these bytes are borrowed": retrieval reads them in place, refuses to
write through them, and ``ethos-data materialize`` knows there is something to
copy. A real directory means the opposite -- data the cache owns -- so neither
mode of ``ethos-data link`` will ever replace one with a link.

A catalogue maintainer who links a dataset into a shared cache, or registers
an installation, passes ``--catalog-root``: the command line then takes the
link as a step of the dataset in that checkout, through
:mod:`ethos_data.maintain.namespace`. This module records nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .access import entry_for
from .catalogs import Catalog
from .config import Roots
from .errors import AccessError, CatalogUnavailable, IncompleteCatalog, LinkError
from .formats import keys as k
from .model import lifecycle

__all__ = ["LinkReport", "link", "unlink"]


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


def _require_settled_licence(catalog: Catalog, name: str) -> None:
    """Refuse to put a dataset with unread terms into a cache other people read.

    The guard of the ``link`` step (see :func:`ethos_data.model.lifecycle.refusal`),
    which a link made by name takes whether or not it is recorded. Staging is
    the answer to "but I need to work with it now": a staging entry is one
    person's, and shadows nothing for anybody else.
    """
    raise_if_refused(catalog, name, "link", LinkError)


def raise_if_refused(catalog: Catalog, name: str, step: str, error: type) -> None:
    """Raise ``error`` when the guards of ``step`` refuse it for this dataset."""
    dataset = catalog.dataset(name)
    if dataset.license_status == k.RESOLVED:
        return
    try:
        note = dataset.descriptor.get(k.LICENSE_NOTE, "")
    except (IncompleteCatalog, CatalogUnavailable):
        # The status is promoted into the index so that asking costs no read.
        # The note is a nicety on top, and must not turn the refusal into a crash.
        note = ""
    reason = lifecycle.refusal(step, repr(name), settled=False, note=note)
    if reason:
        raise error(reason)


def _on_windows() -> bool:
    """Whether this is Windows, where a symbolic link needs a privilege."""
    return os.name == "nt"


def _refusal(name: str, target: Path, error: OSError) -> str:
    """Why the link could not be made, and what to do instead."""
    if not _on_windows():
        return f"could not create the link: {error}"
    return (
        f"Windows would not create the link ({error}).\n"
        "Symbolic links need Developer Mode (Settings > System > For developers), "
        "or an elevated shell.\n"
        "Without either, make a verified copy in the cache instead:\n"
        f"    ethos-data materialize {name} --from {target}\n"
        "Do not substitute a junction (mklink /J): it is reported as an ordinary "
        "directory, so the cache would treat borrowed data as a copy it owns and "
        "could write downloads into it."
    )


def link(
    catalog: Catalog,
    name: str,
    directory: str | Path,
    roots: Roots | None = None,
    force: bool = False,
    cache: str | Path | None = None,
) -> LinkReport:
    """Make this dataset's cache entry a symbolic link to ``directory``.

    ``ethos-data link NAME`` without a directory reads the dataset's build
    input from a source checkout, with
    :func:`ethos_data.maintain.source_dir_for`, and passes it here.

    ``cache`` is the cache that holds the entry, as the global ``--root`` names
    it. Without it, a public dataset's entry goes into the public cache and a
    restricted dataset's into the only listed restricted cache; a restricted
    dataset lands in a listed restricted cache or nowhere at all. That is one
    thing naming a dataset does and ``ethos-data link --all`` does not:
    ``--all`` skips restricted datasets, because building a shared public
    namespace must never touch them, while linking one deliberately by name is
    how an authorised installation gets registered.

    Raises :class:`LinkError` if the directory is not there, if the entry is
    already a link and ``force`` is not set, or if the entry is a real directory
    -- which is never replaced, because it is data the cache owns.
    """
    roots = roots if roots is not None else catalog.settings.roots
    try:
        entry = entry_for(catalog, roots, name, cache)
    except AccessError as error:
        raise LinkError(error.message) from None

    _require_settled_licence(catalog, name)

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
    roots: Roots | None = None,
    cache: str | Path | None = None,
) -> LinkReport:
    """Remove this dataset's cache entry, if it is a link.

    The data it points at is never touched. A real directory is refused: it is
    the cache's own copy, and deleting somebody's downloaded or materialised
    dataset is not something a command called ``unlink`` should do. ``cache``
    names the cache as :func:`link` takes it.
    """
    roots = roots if roots is not None else catalog.settings.roots
    try:
        entry = entry_for(catalog, roots, name, cache, removing=True)
    except AccessError as error:
        raise LinkError(error.message) from None

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
