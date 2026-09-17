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
replacing it with a link would silently discard it. The one exception is a
directory holding no file of its own, which is not data and never was -- see
:func:`_owns_data`.

**This command is told which namespace it is building.** Whether an entry that
must not be in a shared namespace may be *removed* depends on what the directory
is, and the planner is handed that answer rather than inferring one: see
:func:`authority_for`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..access import (
    PUBLIC,
    RESTRICTED,
    borrowed_parent,
    cache_entries,
    entry_ancestry,
    which_cache,
)
from ..catalogs import license_settled
from ..config import Roots

# Not deferred, and deliberately the private names. There is one answer to "this
# machine will not make symbolic links" -- Developer Mode or an elevated shell,
# ``config set-root`` for a single dataset, and never a junction -- one sentence
# for an entry below borrowed data, and one way to read a stored link back as it
# was typed. A second copy of any of them is the one that goes stale, so both
# modes say the same thing by saying it in the same place. Importing this module
# runs ``ethos_data/__init__`` first, which has already imported ``linking``, so
# the direction that needs deferring is linking -> maintain (see
# ``linking.source_dir_for``) and never this one.
from ..linking import _as_typed, _borrowed_refusal, _link_target, _refusal
from . import dataset_name_for, datasets_dir, iter_dataset_dirs

__all__ = [
    "Action",
    "PUBLIC_CACHE",
    "RESTRICTED_CACHE",
    "UNIDENTIFIED",
    "apply",
    "authority_for",
    "plan",
    "restricted_root_message",
    "run",
]

#: What the directory being built is, as far as this installation can tell. The
#: planner is told, rather than comparing paths itself, because the answer comes
#: from the configuration the caller has already resolved -- and because a
#: default here is how a deletion gets justified by an assumption nobody made
#: out loud.
PUBLIC_CACHE = "public cache"
RESTRICTED_CACHE = "restricted cache"
UNIDENTIFIED = "unidentified directory"

#: Why an exposure was left in place, so that the summary can offer the right
#: remedy without working it out a second time. The empty string means nothing
#: withheld it: either it was retracted, or only ``--prune`` was missing.
WITHHELD_AUTHORITY = "authority"
WITHHELD_BORROWED = "borrowed"

#: The verbs :func:`apply` acts on, split the way it acts on them. Written once
#: and read everywhere: :attr:`Action.changes_anything` is their union, ``apply``
#: loops over these two tuples, and nothing else decides what this command
#: writes or deletes. A verb added to either is a change to that, and a verb
#: added to neither cannot be carried out at all.
_REMOVALS = ("prune", "retract")
_CREATIONS = ("link", "repoint", "replace")
_WRITES = _REMOVALS + _CREATIONS

#: The verbs that are findings: nothing was written for them, the reason is in
#: the action's detail, and any one of them makes the run return 1. One tuple, so
#: that a new finding cannot be added to the vocabulary and left out of the exit
#: code -- which would let a nightly rebuild read success off a run that refused
#: to do its work.
FINDINGS = ("missing", "exposed", "blocked", "conflict", "obstructed", "collides")


@dataclass
class Action:
    """What should happen to one entry, and why.

    The verb is this planner's whole vocabulary, so it is written down once:

    ``link`` / ``repoint``
        create the entry, or point an existing link at where the catalogue now
        says the data is.
    ``replace``
        remove an empty directory standing where an entry belongs, and link the
        dataset there. The only real directory this command ever removes, and
        only because nothing in it is the cache's -- see :func:`_owns_data`.
        Planned only under ``--prune``.
    ``prune``
        remove a link for a name the catalogue no longer describes. Planned
        only under ``--prune``.
    ``retract``
        remove a link for a name the catalogue still describes but this
        namespace must not hold: a dataset reclassified as restricted, or whose
        licensing was withdrawn, after the namespace was built. Planned only
        under ``--prune``, and for a restricted dataset only where this
        installation can say what the namespace is.
    ``exposed``
        that same finding with nothing to act on it -- no ``--prune``, an entry
        reached through borrowed data that is not this cache's to remove, or a
        directory this installation cannot identify. Nothing is written.
    ``blocked``
        the entry would be created inside a borrowed tree, because a link stands
        where a namespace prefix belongs. Nothing is written.
    ``conflict``
        the checkout declares this name as owning files *and* declares a dataset
        below it. The two cannot both have a cache entry, so neither is made
        from this name; the member below it is linked as usual.
    ``obstructed``
        something stands where the entry belongs that is neither this dataset's
        data nor this command's to remove without being asked: an empty
        directory left by a withdrawn family, or a file.
    ``collides``
        the cache spells this entry differently from the catalogue name. This
        filesystem calls the two spellings one path; the machines that read the
        cache over a share do not.
    ``missing``
        the dataset's ``source_dir`` is not on this machine.
    ``skip``
        nothing to do and nothing wrong: no ``source_dir``, or a dataset this
        namespace must not hold and does not hold as a link.
    ``unchanged`` / ``keep``
        the entry is already correct, or is a real directory the cache owns --
        which is never replaced with a link, because it is the only copy.
    ``failed``
        set by :func:`apply` and never by :func:`plan`: this one entry could not
        be written or removed, and the rest of the namespace was built anyway.

    Every verb in :data:`FINDINGS` makes the run return 1; every verb in
    ``_REMOVALS`` or ``_CREATIONS`` is work :func:`apply` carries out.
    """

    dataset: str
    verb: str
    entry: Path | None = None
    #: Where the entry should point, for the verbs that write one. For
    #: ``exposed`` and ``retract`` it is where the entry points *now*, so that a
    #: caller can read the exposed path without parsing a sentence;
    #: :meth:`__str__` prints the ``->`` arrow only for the verbs that create,
    #: where it still means "will point here".
    target: Path | None = None
    detail: str = ""
    #: For ``exposed`` only: what stood between this finding and its removal,
    #: one of the ``WITHHELD_`` values or "". The summary needs it to name a
    #: remedy that is true of this entry -- ``--prune`` removes a public cache's
    #: exposure, removes nothing that is reached through a borrowed link, and
    #: must not be recommended at all for a directory nobody has identified.
    withheld: str = ""

    @property
    def changes_anything(self) -> bool:
        """Whether this action still has work to do, or did any.

        The union of the two tuples :func:`apply` loops over, so choosing the
        work and counting what happened are the same question asked twice of one
        vocabulary. ``failed`` is not among them, for the reason :func:`_failed`
        gives.
        """
        return self.verb in _WRITES

    def __str__(self) -> str:
        line = f"{self.verb:<12} {self.dataset:<32}"
        if self.target is not None and self.verb in _CREATIONS:
            line += f" -> {self.target}"
        return f"{line}  {self.detail}".rstrip()


def authority_for(roots: Roots, root: Path) -> str:
    """What this installation can say about the directory a namespace goes in.

    The planner needs this because one of its decisions turns on it and no
    other: whether a *restricted* dataset linked in the namespace may be
    removed. In this installation's own public cache such a link is an exposure
    and ``--prune`` retracts it. In an unidentified directory the same link may
    be another machine's authorised installation, registered deliberately by
    somebody entitled to hold the bytes, and removing it would destroy exactly
    what ``ethos-data link <dataset> <directory>`` exists to create. The planner
    cannot tell those apart, and a planner that guesses will be wrong in the
    direction that deletes.

    So it is computed here, from the roots the caller has already resolved, and
    passed in as a required argument. An unresolved *licence* needs none of
    this: there is no namespace in which "nobody has read the terms" is
    acceptable, so that removal is justified without knowing which namespace
    this is.
    """
    kind = which_cache(roots, root)
    if kind == RESTRICTED:
        return RESTRICTED_CACHE
    if kind == PUBLIC:
        return PUBLIC_CACHE
    return UNIDENTIFIED


def restricted_root_message(roots: Roots, root: Path) -> str:
    """Why ``link --all`` will not build the restricted cache, and what does.

    Refused before the checkout is read, so that no plan exists to print and no
    remedy line exists to copy. ``link --all`` builds a shared namespace *from a
    catalogue*; the restricted cache is not built that way and never has been.
    Every entry in it is one authorised installation of licensed data, and there
    is no work this mode could legitimately do there: it may not create
    restricted entries in bulk from a checkout -- ``source_dir`` is a statement
    about the maintainer's own machine, and each installation has to be a
    deliberate, named act by somebody with the right to hold the data -- and a
    public entry written there would sit where ``locate`` never looks. A mode
    whose every action is forbidden should say so rather than run and skip
    everything.

    When the two caches are configured to the same directory the message leads
    with that instead, because it is the more serious fact and it is why this
    refusal fired.
    """
    if which_cache(Roots(public=roots.public), root) == PUBLIC:
        opening = (
            f"the public cache and the restricted cache are the same directory "
            f"({root}), so building a namespace here would serve licensed bytes to "
            "everybody who reads it. Fix the configuration first:\n"
            "    ethos-data config show"
        )
    else:
        opening = (
            f"--root {root} is the restricted cache on this machine "
            f"(from {roots.restricted_source})."
        )
    return (
        f"{opening}\n"
        "`link --all` builds a shared namespace from a catalogue checkout. The "
        "restricted cache is not built that way: every entry in it is one authorised "
        "installation of licensed data, registered deliberately by somebody entitled "
        "to hold it.\n"
        "    ethos-data link <dataset> /path/to/<dataset>      # register one installation\n"
        "    ethos-data materialize <dataset> --from <dir>     # copy one in, owned\n"
        "    ethos-data unlink <dataset>                       # take one out again\n"
        "Nothing was read and nothing was changed."
    )


@dataclass
class _Checkout:
    """What one checkout declares, read once and sorted out by name.

    The three are computed together because they are one piece of arithmetic
    over one set of names, and computing them apart is how they came to
    disagree: the planner's idea of a namespace was "has a dataset directory as
    a direct child", the manifest builder's was "has a dataset below it at any
    depth", and a family with one ordinary directory in the middle fell between
    them -- into both ``datasets`` and ``prefixes`` at once.
    """

    #: The datasets to plan entries for: every declared name that is not also a
    #: namespace node.
    datasets: list[tuple[str, dict]] = field(default_factory=list)
    #: The names that exist only to hold others. Disjoint from ``datasets`` by
    #: construction, which is what :func:`_namespace_prefixes` relies on.
    prefixes: set[str] = field(default_factory=set)
    #: Namespace nodes that also claim files of their own, with one member to
    #: name in the report.
    conflicts: list[tuple[str, str]] = field(default_factory=list)


def _declared(catalog_root: Path) -> _Checkout:
    """Every dataset with a dataset.yaml, at any depth, sorted into its kind.

    Not a listing of the top level, because a nested family is described as a
    dataset.yaml naming the family with the datasets that actually hold files
    *below* it. Reading only the top level found the family node, reported it as
    having no ``source_dir`` -- true, and not its job to have one -- and left
    every member unlinked, which is the whole family missing from the cache.

    The name is the path below ``datasets/``, so a member is ``family/member``
    and its entry is ``<root>/family/member``: the same name the manifest
    builder writes, the collections file uses, and the reader looks up.

    Which names are namespace nodes is set arithmetic over the names already
    collected -- a name is one exactly when another collected name starts with
    it and a slash -- rather than a filesystem test per directory. That is the
    same relation :func:`_namespace_prefixes` computes, so the two definitions of
    "member" cannot drift apart again; it costs no extra I/O; and it makes the
    datasets and the prefixes disjoint by construction instead of by argument.

    A namespace node owning no files is dropped rather than reported: a
    namespace owns no files, so "no source_dir" is not a finding about it. One
    that *does* claim files is handed back as a conflict, because dropping it
    silently is the same wrong the paragraph above describes, inverted.
    """
    root = datasets_dir(catalog_root)
    declared: list[tuple[str, dict]] = []
    for directory in iter_dataset_dirs(root):
        meta = (
            yaml.safe_load((directory / "dataset.yaml").read_text(encoding="utf-8"))
            or {}
        )
        declared.append((dataset_name_for(root, directory), meta))

    names = {name for name, _ in declared}
    checkout = _Checkout(prefixes=_namespace_prefixes(names))
    for name, meta in declared:
        if name not in checkout.prefixes:
            checkout.datasets.append((name, meta))
        elif meta.get("source_dir"):
            member = next(
                (other for other in sorted(names) if other.startswith(f"{name}/")),
                f"{name}/...",
            )
            checkout.conflicts.append((name, member))
    return checkout


def _namespace_prefixes(names: set[str]) -> set[str]:
    """Every name that is a prefix of a declared one: the namespaces, by implication.

    :func:`_declared` drops namespace nodes on purpose -- a namespace owns no
    files, so "no source_dir" is not a finding about it -- and that left
    ``family`` out of the only set ``--prune`` consults before it deletes. A
    cache still holding ``<root>/family`` as a link from before the family
    existed was therefore removed, under the line ``prune  family  not in the
    catalogue any more``, which is the one thing that was not true of it. Every
    member entry written under that link went with it, and the run reported
    success for entries that no longer existed.

    Derived from the members rather than read out of the checkout a second time,
    because that is the definition that cannot drift: a name is a namespace
    prefix exactly when the catalogue describes a dataset below it, whether or
    not anybody wrote a ``dataset.yaml`` at that level. Taken from *every*
    declared dataset, including the ones the planner goes on to exclude -- a
    family whose only member has just been reclassified as restricted is still a
    family the catalogue names, and deleting its prefix would be a deletion
    justified by a false sentence, in the one flag that deletes.

    This set can only ever protect, and cannot hide a dataset entry from
    ``--prune``: :func:`_declared` plans entries for exactly the names that are
    *not* in here, so the two sets are disjoint because they are cut from one
    another rather than because anything keeps them in step.
    """
    found: set[str] = set()
    for name in names:
        parts = name.split("/")
        for cut in range(1, len(parts)):
            found.add("/".join(parts[:cut]))
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
    another link, which is exactly what source_dir is allowed to do. Contrast
    :func:`ethos_data.access.which_cache`, which asks whether two paths are the
    same directory and therefore resolves on purpose; neither comparison is the
    other one written badly.
    """
    return str(_as_typed(current)) == str(_as_typed(source))


def _spelling_on_disk(
    root: Path, name: str, listings: dict[Path, dict[str, Path] | None]
) -> tuple[Path, Path | None] | None:
    """Where the cache spells a component of this name differently, if it does.

    Windows and macOS call ``Example`` and ``example`` one path, so a cache made
    by hand, or by an older catalogue, can hold an entry under a spelling that
    is not the dataset's name. Both loops of :func:`plan` then find it and
    disagree: the declared loop resolves it and says ``unchanged``, while the
    prune loop reads the real spelling off the disk, does not find it among the
    catalogue names, and says "not in the catalogue any more" -- and ``--prune``
    deletes a working entry that a moment earlier was reported correct.

    Detected rather than folded away, and refused rather than renamed. Folding
    the comparison would leave the cache holding a name that
    :func:`ethos_data.access.entry_for`, the collections files and the manifest
    builder do not look for, and the Linux machines that read this cache over a
    share do not consider the same directory at all -- so the tool would be
    calling a cache correct that is a cache with a dataset missing, for exactly
    the people it is built for. Renaming automatically is worse: it is an unlink
    and a symlink of a working entry to settle a question about spelling.

    The test is the filesystem's own two answers and none of ours: the path
    resolves, and its name is not in its parent's listing. A folding table is
    used only to *name* the offender, so a spelling this Python cannot fold --
    an 8.3 short name, a dotless I -- costs the message its second half rather
    than costing the finding. Every component is checked, not just the last, so
    a collision in a prefix is caught too; the listings are memoised because a
    catalogue of two hundred datasets would otherwise list the root two hundred
    times.
    """
    current = root
    for part in Path(name).parts:
        if current not in listings:
            try:
                listings[current] = {child.name: child for child in current.iterdir()}
            except OSError:
                listings[current] = None
        listing = listings[current]
        if listing is None:
            return None
        wanted = current / part
        if part in listing:
            current = wanted
            continue
        if not (wanted.exists() or wanted.is_symlink()):
            return None
        folded = [
            child
            for spelling, child in listing.items()
            if spelling.casefold() == part.casefold()
        ]
        return wanted, folded[0] if len(folded) == 1 else None
    return None


def _owns_data(entry: Path) -> bool:
    """Whether this real directory holds a file of its own, at any depth.

    The question ``keep`` has always meant to ask and never did. ``--prune``
    removes ``<root>/family/member`` and cannot remove ``<root>/family`` with
    it: that directory is not an entry, so
    :func:`ethos_data.access.cache_entries` never yields it and no ``prune``
    action ever names it. What is left is a husk -- a namespace prefix this
    command made itself -- and the moment the catalogue collapses the family
    back into one flat dataset, that husk stands exactly where the dataset's
    entry belongs. Testing only ``entry.exists()`` called it ``keep``, "a real
    directory the cache owns", on every run for ever, about a directory holding
    nothing this cache ever downloaded, while the declared dataset got no entry
    on any rerun and the run exited 0.

    One file at any depth is the test, which is the rule
    :func:`ethos_data.access.cache_entries` already uses to tell a downloaded
    dataset from a directory that merely holds other names -- so the two halves
    of the cache agree about what "the cache owns this" means. A symbolic link
    below is not descended into and does not count: those bytes are borrowed,
    and nothing under a link is the cache's. A directory that cannot be listed
    counts as owned, because "I could not look" and "there is nothing there" are
    the same answer only to a command that deletes on the strength of it.
    """
    pending = [entry]
    while pending:
        try:
            children = list(pending.pop().iterdir())
        except OSError:
            return True
        for child in children:
            if child.is_symlink():
                continue
            if child.is_dir():
                pending.append(child)
            else:
                return True
    return False


def _emptied_prefix(entry: Path, going: set[Path]) -> bool:
    """Whether this real directory holds nothing, once this run's removals are done.

    Asked only of a directory :func:`_owns_data` has already disowned, and it
    decides one thing: whether the husk can be taken away *in this run* rather
    than merely reported. Anything at all left inside means no -- one file, one
    link, one thing that is neither, at any depth -- and a directory that cannot
    be listed means no as well.

    ``going`` holds the entries this same plan is removing. Without it a family
    re-flattened in one step needs two runs -- one to prune the members, one to
    see the husk -- and the run in between reports success about a name that
    resolves to nothing. Being optimistic costs nothing, because every removal
    this licenses is an ``rmdir``, which the filesystem refuses on a directory
    that is not empty.
    """
    pending = [entry]
    while pending:
        try:
            children = list(pending.pop().iterdir())
        except OSError:
            return False
        for child in children:
            # Before ``is_symlink()``, because a child this run is pruning *is*
            # a link; and ``is_symlink()`` before ``is_dir()``, because a link
            # to a directory answers True to both and descending into one would
            # walk borrowed data.
            if child in going:
                continue
            if child.is_symlink() or not child.is_dir():
                return False
            pending.append(child)
    return True


def _excluded(
    name: str,
    entry: Path,
    phrase: str,
    advice: str,
    *,
    prune: bool,
    removable: bool,
    borrowed: Path | None,
) -> Action:
    """The action for a declared dataset this namespace must not hold.

    Skipping is the whole answer only while the cache holds nothing for the
    dataset. Access and licensing are edited *after* the namespace was built --
    that is what a reclassification is -- so the run that first reads
    ``ethos:access: restricted`` is looking at a live link it made itself last
    week, still handing the licensed bytes to everybody who reads this cache.
    Reclassification is the only way licensed bytes ever reach a public cache,
    and a planner that reports the skip while leaving the link is what makes
    that permanent: the line reads as though the dataset had never been here,
    the exit code says the namespace was built, and a nightly rebuild has
    nothing to notice for months.

    ``removable`` is whether this exclusion is one this run may act on at all.
    An unresolved licence always is -- there is no namespace in which nobody
    having read the terms is acceptable -- while a restricted dataset depends on
    what the namespace is, which is :func:`authority_for`'s business and not
    something to infer from the path.

    Only a symbolic link is a finding. A link is a pointer, so removing it
    discards nothing; a real directory is the cache's own copy, the only one,
    and this command never removes one whatever the catalogue now says about the
    dataset. That leaves the worse exposure -- licensed bytes downloaded or
    materialised into a public cache before the reclassification -- for somebody
    to deal with deliberately, so the line says the bytes are there rather than
    printing what it would print for a dataset the cache has never held.

    An entry below a borrowed parent is reported and never retracted. It is
    reached through a link this cache does not own, so the thing at that path
    may well be the other project's own entry, and deleting it would be a
    removal inside somebody else's namespace that nobody reviewed. Removing the
    borrowed link is the one move that is certainly this cache's to make.
    """
    if not entry.is_symlink():
        held = (
            ". The cache holds a real directory here, which is its own copy of those "
            "bytes; this command never removes one, so deal with it deliberately"
            if entry.is_dir()
            else ""
        )
        return Action(name, "skip", entry, detail=f"{phrase}: {advice}{held}")

    current = _link_target(entry)
    where = f" to {current}" if current is not None else ""

    if borrowed is not None:
        return Action(
            name,
            "exposed",
            entry,
            current,
            detail=f"{phrase}, and this namespace still links it{where} through "
            f"{borrowed}, which is a link to borrowed data. Remove {borrowed} -- it "
            "discards nothing -- rather than the entry inside it",
            withheld=WITHHELD_BORROWED,
        )

    if not removable:
        return Action(
            name,
            "exposed",
            entry,
            current,
            detail=f"{phrase}, and this namespace still links it{where}; nothing is "
            "removed from a directory this installation cannot identify",
            withheld=WITHHELD_AUTHORITY,
        )

    if prune:
        return Action(
            name,
            "retract",
            entry,
            current,
            detail=f"{phrase}: removing the link{where}; the data itself is untouched",
        )

    return Action(
        name,
        "exposed",
        entry,
        current,
        detail=f"{phrase}, and this namespace still links it{where}; `--prune` "
        "removes it",
    )


def plan(
    catalog_root: Path, root: Path, prune: bool = False, *, authority: str
) -> list[Action]:
    """Decide what the namespace needs, without touching the filesystem.

    Every verb this returns is listed on :class:`Action`. The findings among
    them are produced here, by reading the cache, rather than discovered while
    writing it: by the time an entry has been written the damage is done, and a
    planner that can only describe what it is about to do has no way to report
    what is already wrong.

    ``authority`` says what ``root`` is -- see :func:`authority_for`. It is
    required and has no default, because a default is precisely how a planner
    comes to delete on the strength of an assumption nobody made out loud.

    This writes nothing, and no state the *cache* is in makes it raise: a
    dangling link, an entry removed while the plan is being made, a directory
    that cannot be listed, a reparse point the system will not describe. That is
    what makes ``--dry-run`` safe to point at a cache in any condition, and what
    keeps the exit-code contract -- a caller gets a code and never a stack trace
    where the summary should be. A malformed *checkout* is the other thing
    and still stops the run: that is a fault in what is being read from rather
    than in what is being described.
    """
    actions: list[Action] = []
    checkout = _declared(catalog_root)
    # Every declared dataset, the excluded ones included: the prune loop below
    # must stay out of their way, because this loop is the only place that knows
    # *why* an entry no longer belongs and can say so without --prune. Dropping
    # the excluded ones here would hand the same entry to both loops, and the
    # prune loop's sentence -- "not in the catalogue any more" -- is the one
    # thing that is not true of a dataset that has merely been reclassified.
    names = {name for name, _ in checkout.datasets}

    # First, so that the reason a declared name gets no entry is read before the
    # lines for the datasets below it.
    for name, member in sorted(checkout.conflicts):
        actions.append(
            Action(
                name,
                "conflict",
                detail=f"{member} is a dataset below this name, so {name} holds a "
                f"family and cannot also own files of its own; source_dir says it "
                f"does. Move that data into a member of its own, or move {member} out",
            )
        )

    listings: dict[Path, dict[str, Path] | None] = {}
    for name, meta in checkout.datasets:
        entry = root / name
        access = meta.get("ethos:access", PUBLIC)
        # Read once, before anything decides what to do with this entry: both
        # the exclusion branches and the ordinary cascade need to know that the
        # path they are about to write to, or delete from, is inside data this
        # cache has only borrowed.
        borrowed = borrowed_parent(entry, name)

        if access == RESTRICTED:
            actions.append(
                _excluded(
                    name,
                    entry,
                    RESTRICTED,
                    "belongs in the restricted cache, where each installation is "
                    "registered by name",
                    prune=prune,
                    removable=authority == PUBLIC_CACHE,
                    borrowed=borrowed,
                )
            )
            continue

        if not license_settled(meta):
            # Building this namespace is how a dataset reaches everybody on the
            # machine. An absent licence is a question, not a permission, and
            # answering it is one line in dataset.yaml.
            actions.append(
                _excluded(
                    name,
                    entry,
                    "unresolved licensing",
                    "record the terms in dataset.yaml before linking it into a "
                    "shared cache",
                    prune=prune,
                    removable=True,
                    borrowed=borrowed,
                )
            )
            continue

        source = _source_of(catalog_root, name, meta)
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

        # After the source checks, because "blocked" is a statement about the
        # write and the write is only interesting once there is something to
        # write; before the cascade, because an entry an earlier version of this
        # command already wrote through a borrowed parent *is* a symbolic link
        # and would otherwise be reported "unchanged" -- telling the maintainer
        # that all is well about a link of theirs living in somebody else's
        # directory. The same goes for "keep": a real directory below a borrowed
        # prefix is not a directory this cache owns.
        if borrowed is not None:
            actions.append(
                Action(
                    name,
                    "blocked",
                    entry,
                    source,
                    detail=_borrowed_refusal(entry, borrowed),
                )
            )
            continue

        # After the exclusion branches, so that a reclassified dataset is still
        # retracted whatever its entry is spelled like -- a spelling difference
        # must never be what keeps licensed bytes being served -- and before the
        # cascade, so that this replaces the unchanged/repoint/keep line instead
        # of being printed beside it.
        collision = _spelling_on_disk(root, name, listings)
        if collision is not None:
            wanted, found = collision
            if found is not None:
                detail = (
                    f"the cache spells {wanted} as {found.name!r}. This filesystem "
                    f"calls the two one path; the machines that read this cache over a "
                    f"share do not, and {name!r} is only found there under the "
                    f"spelling the catalogue uses. Rename it:  mv {found} {wanted}"
                )
            else:
                detail = (
                    f"the cache holds {wanted} under a spelling this filesystem treats "
                    f"as the same path. Rename it in {wanted.parent} to {wanted.name!r}"
                )
            actions.append(Action(name, "collides", entry, detail=detail))
            continue

        if entry.is_symlink():
            current = _link_target(entry)
            if current is None:
                # Not known to be correct, and ``repoint`` is the action that
                # makes it correct. If the link really did vanish between the
                # two calls, ``_remove`` reports this one entry ``failed`` --
                # which is a name and "run this again", rather than a traceback.
                actions.append(
                    Action(
                        name,
                        "repoint",
                        entry,
                        source,
                        detail="its current target could not be read",
                    )
                )
            elif _same_target(current, source):
                actions.append(Action(name, "unchanged", entry, source))
            else:
                actions.append(
                    Action(name, "repoint", entry, source, detail=f"was {current}")
                )
        elif entry.is_dir():
            actions.append(
                Action(
                    name,
                    "keep",
                    entry,
                    source,
                    detail="a real directory the cache owns; not replaced with a link",
                )
            )
        elif entry.exists():
            actions.append(
                Action(
                    name,
                    "obstructed",
                    entry,
                    source,
                    detail="a file stands where this entry belongs; nothing here "
                    "removes it, because nothing here put it there",
                )
            )
        else:
            actions.append(Action(name, "link", entry, source))

    # Not while an entry is spelled differently from its name: the one flag that
    # deletes must not run against a namespace whose entries it cannot name, and
    # one rule off the whole pass is reviewable in a way that per-entry
    # bookkeeping on the deleting side is not. ``retract`` is deliberately not
    # gated -- it is planned above, and removing a link this namespace must not
    # hold is not made wrong by a spelling difference elsewhere.
    if prune and root.is_dir() and not any(a.verb == "collides" for a in actions):
        # The reader's own walk, so that a nested entry is found where its name
        # says it is (``family/member``) rather than not at all: listing the top
        # level would see ``family``, never look inside it, and prune nothing.
        for name, existing in cache_entries(root):
            if name in names or name in checkout.prefixes or not existing.is_symlink():
                continue
            actions.append(
                Action(name, "prune", existing, detail="not in the catalogue any more")
            )

    # Last, because it reads the removals both loops planned: a family collapsed
    # back into one flat dataset has its members pruned above, and the directory
    # that held them is empty only once that has happened.
    going = {a.entry for a in actions if a.verb in _REMOVALS}
    for action in actions:
        if action.verb != "keep" or _owns_data(action.entry):
            continue
        if prune and _emptied_prefix(action.entry, going):
            action.verb = "replace"
            action.detail = (
                "an empty directory, left where this family's members used to be; "
                "removing it and linking the dataset here"
            )
        else:
            action.verb = "obstructed"
            action.detail = (
                "this directory holds nothing the cache downloaded -- it is what is "
                "left of the family that used to be below this name -- so the dataset "
                "has no entry. `--prune` clears it and links the dataset here"
            )

    return actions


def _failed(action: Action, detail: str) -> bool:
    """Record why one entry could not be written or removed. Always ``False``.

    The action is edited rather than replaced so that :func:`run` finds the
    outcome in the very list it handed to :func:`apply`: that is what lets a
    failure discovered during the work reach the summary line and the exit code
    without ``apply``'s signature changing. The verb is overwritten with one
    :attr:`Action.changes_anything` does not list, so the same filter that chose
    the work counts what actually happened -- the alternative was a summary
    reading ``2 change(s) applied`` for one link that exists and one that does
    not.
    """
    action.verb = "failed"
    action.detail = detail
    return False


def _already_removed(action: Action) -> str:
    """The sentence a failed creation owes when what stood there is already gone.

    ``repoint`` and ``replace`` both take the old thing away before the new link
    can be written, so a failure after that point leaves the name not resolving
    at all rather than merely resolving to something stale. Read the verb before
    :func:`_failed` overwrites it.
    """
    if action.verb not in ("repoint", "replace"):
        return ""
    return (
        f"\nWhat stood at {action.entry} had already been removed to make room for "
        "this, so that name does not resolve at all now. Running this again, once the "
        "cause above is fixed, recreates it."
    )


def _create(action: Action) -> bool:
    """Write one entry as a symbolic link, or record why it could not be.

    The directories above the entry are created one at a time, and never with
    ``parents=True, exist_ok=True``. That call cannot be made safe: ``exist_ok``
    is tested with ``is_dir()``, which follows a symbolic link, so it silently
    accepts a borrowed parent and writes this cache's entry inside somebody
    else's tree -- where it is reported as made, is invisible to the reader's own
    walk, and disappears the day its owner removes that one link. Refusing a link
    before the ``mkdir`` and again on the ``FileExistsError`` after it leaves no
    moment in which a ``mkdir`` from this run can traverse one, which is the
    guarantee a check against a pre-run snapshot cannot give. ``is_symlink()`` is
    tested before ``is_dir()`` because a link to a directory answers True to
    both.

    :func:`plan` checks the same condition with
    :func:`ethos_data.access.borrowed_parent`, and that check is advice: it
    reports the shape early, in a run that may be a ``--dry-run``. This is the
    guarantee. The two can disagree when the cache changes under a long run, and
    the detail below says so in as many words so that a planned ``link`` turning
    into a ``failed`` does not read as an inconsistency.

    On Windows without Developer Mode or an elevated shell, creating a symbolic
    link is simply refused, and on the Windows-first audience this cache was
    written for that is the likeliest first run of ``ethos-data link --all``.
    Letting the OSError out abandoned the run where it stood: the entries already
    written stayed, the ones after them were never attempted, and the advice the
    single-dataset mode gives for exactly this refusal was nowhere in the
    traceback. The guidance is :func:`ethos_data.linking._refusal`, the same
    sentences that mode has always printed.

    A refused ``mkdir`` and an occupied path each get their own sentence instead.
    They are a permission, a read-only root, or a collision, and answering any of
    them with the Developer Mode advice would send the maintainer to a setting
    that has nothing to do with what stopped them.
    """
    root, parents = entry_ancestry(action.entry, action.dataset)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return _failed(
            action,
            f"could not create {root}, the cache root: {error}"
            + _already_removed(action),
        )

    def refuse_borrowed(parent: Path) -> bool:
        """One sentence, whichever of the two tests below caught the link."""
        return _failed(
            action,
            _borrowed_refusal(action.entry, parent)
            + "\nThe plan for this run was made while that was an ordinary directory, "
            "which is why the line printed for this entry says otherwise."
            + _already_removed(action),
        )

    for parent in parents:
        if parent.is_symlink():
            return refuse_borrowed(parent)
        try:
            parent.mkdir()
        except FileExistsError:
            if parent.is_symlink():
                return refuse_borrowed(parent)
            if not parent.is_dir():
                return _failed(
                    action,
                    f"{parent} is a file, not a directory, and this entry goes "
                    "underneath it" + _already_removed(action),
                )
        except OSError as error:
            return _failed(
                action,
                f"could not create {parent}, a directory this entry goes under: "
                f"{error}" + _already_removed(action),
            )

    try:
        action.entry.symlink_to(action.target)
    except FileExistsError as error:
        return _failed(
            action,
            f"{action.entry} already exists, so the link could not be written there: "
            f"{error}" + _already_removed(action),
        )
    except OSError as error:
        return _failed(
            action,
            _refusal(action.dataset, action.target, error) + _already_removed(action),
        )
    return True


def _remove(action: Action) -> bool:
    """Take one entry away, or record why it could not be.

    ``Path.unlink()`` on a symbolic link removes the link and nothing behind it,
    which is the whole safety argument for every verb that reaches here: the
    planner has already established that the entry is a link, so no copy the
    cache owns can be lost by this call.

    Deliberately not :func:`ethos_data.linking._refusal`. That text answers "the
    system would not create a link", and none of it -- Developer Mode, ``config
    set-root``, the warning against junctions -- is an answer to a refused
    ``unlink``. Removing a link needs no privilege on either platform, so what
    is actually known here is the system's own message, and inventing advice
    around it would only send the reader somewhere useless.

    It is caught for the same reason creation is, and the case is worse: a
    ``--prune`` that dies where it stands fails exactly when pruning matters
    most, because the entry that would not go is the one the namespace has to
    stop serving, and a traceback neither names it nor leaves an exit code
    saying the cache is still wrong.
    """
    intent = action.verb
    try:
        action.entry.unlink()
    except OSError as error:
        detail = f"could not remove {action.entry}: {error}"
        if intent == "retract":
            detail += (
                " -- this namespace is still serving those bytes to everybody who "
                "reads it."
            )
        return _failed(action, detail)
    return True


def _remove_husk(action: Action) -> bool:
    """Take away an emptied namespace prefix, or record why it could not be.

    This is the one removal in this module that is not a symbolic link, so the
    argument that covers the others -- a link is a pointer, and removing it
    discards nothing -- does not cover it, and it needs its own.

    Every removal here is an ``rmdir`` and there is no other call. The operating
    system refuses to remove a directory that is not empty, so a planner that got
    :func:`_emptied_prefix` wrong cannot cost a single byte: it costs an entry
    that is reported ``failed``. The emptiness is re-checked first, because the
    plan was made before this run's own removals and the world may have moved
    since. The directories are taken deepest first, which is the only order in
    which ``rmdir`` can succeed at all, and a link met on the way stops the whole
    removal rather than being followed: the plan promised there was nothing under
    here, and something under here means the plan is out of date.
    """
    if not _emptied_prefix(action.entry, set()):
        return _failed(
            action,
            f"{action.entry} is not empty after all, so it was left alone and the "
            "entry was not made. Run this again to see what is in it.",
        )

    doomed: list[Path] = []
    pending = [action.entry]
    while pending:
        directory = pending.pop()
        try:
            children = list(directory.iterdir())
        except OSError as error:
            return _failed(
                action,
                f"could not look inside {directory}: {error}. Nothing was removed, "
                "and the dataset still has no entry.",
            )
        for child in children:
            if child.is_symlink() or not child.is_dir():
                return _failed(
                    action,
                    f"{child} appeared under {action.entry} while this was running, so "
                    "nothing was removed and the dataset still has no entry.",
                )
            doomed.append(child)
            pending.append(child)

    for directory in (*reversed(doomed), action.entry):
        try:
            directory.rmdir()
        except OSError as error:
            return _failed(
                action,
                f"could not remove the empty directory {directory}: {error}. Nothing "
                "in it was removed, and the dataset still has no entry.",
            )
    return True


def apply(actions: list[Action]) -> list[Action]:
    """Carry out the planned actions, by the verbs in ``_REMOVALS`` and ``_CREATIONS``.

    Removals run before anything is created, and that is not tidiness. A removal
    takes away one link; an entry created underneath a link that is then removed
    goes with it, having been printed as linked and counted in the summary. What
    makes that pair impossible is :func:`_declared` -- no name this run creates
    can be an ancestor or a descendant of another name it creates, because the
    ancestors are not datasets -- together with ``_namespace_prefixes``, which
    keeps ``--prune`` off every ancestor of a declared name. The planner's
    borrowed-parent check is advice against a snapshot taken before the run; the
    guarantee that nothing is written through a link belongs to :func:`_create`.

    Every mutating call is guarded, because the operating system's answer to
    "create a symbolic link" is not always yes. A refused entry becomes a
    ``failed`` action instead of an exception, so the other nineteen are still
    built and :func:`run` can name the one that is not.

    The actions are edited in place, which is what lets ``run`` read the outcome
    out of the same list it passed in.
    """
    for action in actions:
        if action.verb in _REMOVALS:
            _remove(action)

    for action in actions:
        if action.verb not in _CREATIONS:
            continue
        # A symbolic link cannot be written over an occupied path, so what is
        # there has to go first -- and if it would not go, attempting the link
        # would fail a second time and report the wrong reason for it.
        if action.verb == "repoint" and not _remove(action):
            continue
        if action.verb == "replace" and not _remove_husk(action):
            continue
        _create(action)
    return actions


def _rerun(root: Path, catalog_root: Path, *, prune: bool = False) -> str:
    """The one spelling of this command a report may print.

    Both paths in full, and the root named in the *identifying* position: the
    top-level ``--root`` declares what that directory is, so a run started this
    way knows it is a public cache and may remove what a public cache must not
    hold. ``--root`` after ``link`` only names a destination to build, and a
    report that told somebody to re-run that way would be recommending a run
    that cannot do what the report just asked for. ``--catalog-root`` is echoed
    because without it the rerun searches upward from wherever it is typed, and
    may read a different checkout or none.
    """
    line = f"    ethos-data --root {root} link --all --catalog-root {catalog_root}"
    return f"{line} --prune" if prune else line


def _report_findings(
    findings: dict[str, list[Action]],
    refused: list[Action],
    root: Path,
    catalog_root: Path,
) -> None:
    """Say what is still wrong, on every path rather than only after a write.

    Each of these is a property of the plan or of the work, not something
    applying changes discovers, and the run with the most of them is often the
    run with nothing left to apply: a dataset reclassified as restricted has no
    change to make without ``--prune``, and is exactly the case that has to be
    loud. ``nothing to do.`` above an exit code of 1, with no sentence between
    them, is the report of a run that had plenty to do and could not.

    No paragraph prints a command that would delete something this run has just
    said is correct or cannot judge, and the one paragraph that prints a
    deleting command behind a condition prints it *under* the sentence saying
    what it would destroy if the condition is guessed wrong.
    """
    for action in refused:
        print(f"\nfailed  {action.dataset}  {action.entry}")
        print(action.detail)

    if refused:
        print(
            f"\n{len(refused)} change(s) could not be made; the rest of the namespace "
            "was built. Each is named above with the reason. Fix that and run this "
            "again -- the entries that did succeed are seen as unchanged, not made a "
            "second time."
        )

    exposed = findings["exposed"]
    removable = [a for a in exposed if not a.withheld]
    unidentified = [a for a in exposed if a.withheld == WITHHELD_AUTHORITY]
    borrowed = [a for a in exposed if a.withheld == WITHHELD_BORROWED]

    if removable:
        print(
            f"\n{len(removable)} dataset(s) are linked here that no shared namespace "
            "may hold -- restricted, or with licensing nobody has recorded. Nothing "
            f"was removed:\n{_rerun(root, catalog_root, prune=True)}"
        )
    if unidentified:
        print(
            f"\n{len(unidentified)} restricted dataset(s) are linked in this namespace, "
            f"and nothing was removed. This run cannot tell what {root} is: in a public "
            "namespace those links hand licensed bytes to everybody who reads it, and "
            "in another machine's restricted cache each one is an authorised "
            "installation that must stay. Only somebody who knows which can say. If it "
            "is a public cache, name it as one and the same run removes them:\n"
            f"{_rerun(root, catalog_root, prune=True)}\n"
            "If it is a restricted cache, leave them: `link --all` does not build one, "
            "and an installation is registered a dataset at a time with `ethos-data "
            "link <dataset> <directory>`."
        )
    if borrowed:
        print(
            f"\n{len(borrowed)} dataset(s) this namespace must not hold are reached "
            "through a borrowed link, so they are not this cache's to remove and "
            "`--prune` never touches them. Each line above names the link to remove "
            "instead."
        )
    if findings["conflict"]:
        print(
            f"\n{len(findings['conflict'])} name(s) in the checkout own files and also "
            "have datasets below them. Neither shape can have a cache entry while the "
            "other does, so nothing was made or removed for those names; the datasets "
            "below them were linked as usual. Fix the checkout as each line says and "
            "run this again."
        )
    if findings["collides"]:
        print(
            f"\n{len(findings['collides'])} entry/entries are spelled differently from "
            "the catalogue name. This filesystem treats the two spellings as one path; "
            "the machines that read this cache over a share do not, so the dataset is "
            "missing there under the name everything looks it up by. Rename each one as "
            "the line above says and run this again -- `--prune` removes nothing while "
            "an entry is spelled this way, because the one flag that deletes must not "
            "run against a namespace whose entries it cannot name."
        )
    if findings["obstructed"]:
        # No command: the two paragraphs above already print the only rerun this
        # report offers, and each of them says first what that rerun removes.
        # Re-printing it here, for a directory holding nothing, would hand the
        # same deleting line to somebody reading about a different problem.
        print(
            f"\n{len(findings['obstructed'])} dataset(s) have no entry because "
            "something already stands where it belongs. Where that is a directory left "
            "behind when a family below the name was withdrawn, it holds nothing the "
            "cache downloaded and `--prune` clears it; anything else is yours to move."
        )
    if findings["blocked"]:
        print(
            f"\n{len(findings['blocked'])} dataset(s) were not linked because a cache "
            "entry stands where a namespace prefix belongs -- remove those links, which "
            "discard nothing, and run this again."
        )
    if findings["missing"]:
        print(
            f"\n{len(findings['missing'])} dataset(s) have a source_dir that does not "
            "exist -- fix dataset.yaml or the storage, then run this again."
        )


def run(
    catalog_root: Path,
    root: Path,
    *,
    authority: str,
    dry_run: bool = False,
    prune: bool = False,
) -> int:
    """Plan the namespace, report it, and -- unless ``dry_run`` -- build it.

    ``root`` arrives already decided, and deliberately has no default. The
    earlier signature took the argparse namespace and looked the public cache up
    itself when ``--root`` was absent, which put a second cache lookup inside a
    command that had already done one. The two could answer differently -- a
    top-level ``--root`` the second lookup never saw, or ``$ETHOS_DATA_DIR`` read
    at a different moment -- and the result was a full link tree built in a
    directory the rest of the command had never mentioned, printed as a success.
    Deciding once, in the caller, is what makes that impossible rather than
    merely unlikely. ``authority`` arrives the same way and for the same reason,
    and :func:`authority_for` is how the caller works it out.

    An entry the catalogue has reclassified is a finding, not a skip. Only
    ``--prune`` deletes, so a run without it leaves the link in place and
    returns 1: the maintainer sees the line and a rebuild script sees the code,
    and the namespace does not go on serving licensed bytes for months because
    the one line that mentioned them said ``skip``.

    An entry the filesystem refuses is likewise reported and counted here rather
    than raised, and earns the same exit 1 as a missing ``source_dir``. In every
    one of these cases the namespace was built as far as this machine allowed,
    and what the maintainer needs is the name of the entry that is not there,
    not a stack trace where the summary should be.
    """
    actions = plan(catalog_root, root, prune=prune, authority=authority)

    changes = [a for a in actions if a.changes_anything]
    findings = {verb: [a for a in actions if a.verb == verb] for verb in FINDINGS}
    if dry_run:
        # A preview removes nothing, so an entry planned for retraction is still
        # being served the moment this process exits, and the exit code is the
        # only part of a run a rebuild script reads. Deliberately not done for
        # ``replace``: a retraction not carried out is a standing wrong, while a
        # replacement not carried out is work left undone, exactly like a
        # ``link`` a dry run did not make.
        findings["exposed"] += [a for a in actions if a.verb == "retract"]

    print(f"namespace root: {root}")
    print(f"catalogue:      {catalog_root}\n")
    for action in actions:
        print(f"  {action}")

    refused: list[Action] = []
    if dry_run:
        print(f"\n{len(changes)} change(s) would be made. Nothing was written.")
    elif not changes:
        print("\nnothing to do.")
    else:
        apply(changes)
        refused = [a for a in changes if a.verb == "failed"]
        applied = [a for a in changes if a.changes_anything]
        print(f"\n{len(applied)} change(s) applied.")

    _report_findings(findings, refused, root, catalog_root)
    return 1 if refused or any(findings.values()) else 0
