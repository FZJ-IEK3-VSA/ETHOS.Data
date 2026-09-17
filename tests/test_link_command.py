"""``ethos-data link``: pointing cache entries at data already on this machine.

One command, two modes. ``link <dataset>`` registers a single entry by name;
``link --all`` builds a whole public cache from a catalogue checkout. Those were
two separate commands until the second was folded into the first, and the merge
is why both now have to be tested here: the modes differ on purpose -- catalogue
mode skips restricted datasets, dataset mode links one into the restricted cache
deliberately -- and an asymmetry that cannot be read in one place is an asymmetry
somebody eventually "fixes".

The entry has to be a *symbolic link* specifically, because that is how the cache
records that the bytes are borrowed: retrieval reads them in place and refuses to
write through them. So the tests worth having are the ones about what an entry
is, not about whether a file appeared.

Three more get the same treatment, because all three shipped wrong. What stands
*above* an entry: ``mkdir(parents=True, exist_ok=True)`` succeeds through a
parent that is already a link to a directory, so an entry could be written
inside a tree the cache had only borrowed, and reported as made. What the
catalogue says about a dataset *later*: access and licensing are edited after a
namespace has been built, and answering that with ``skip`` left the link this
command made itself still serving the bytes. And what the operating system says:
Windows without Developer Mode simply refuses to create a symbolic link, which
used to end the run in a traceback with no summary and no exit code worth
reading.

A later round adds four more, all of them about a cache that is not in the state
the planner assumed. A declared name that holds a family *and* claims files of
its own; a directory this installation cannot say is its own public cache; a
directory left standing when a family below it was withdrawn; and a cache that
spells an entry differently from the catalogue name. Each of those ended in a
write or a deletion somewhere nobody was looking -- inside another dataset's
source directory, in an authorised installation of licensed data, or over a
working entry that the same run had just called correct -- so what is asserted
here is the state of the disk afterwards, and only then the wording that
explains it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from ethos_data.access import ORIGIN_LINK, locate
from ethos_data.catalogs import Catalog, Dataset, Resource, UnknownDataset
from ethos_data.cli import main
from ethos_data.config import Roots
from ethos_data.linking import LinkError, link, unlink
from ethos_data.maintain import namespace

CONTENT = {"a.txt": b"first file", "sub/b.txt": b"second file"}

#: Linking into a cache needs terms somebody has read; see test_license_gate.py.
LICENCE = "licenses:\n  - name: CC-BY-4.0\n"


def _catalog(access: str = "public", name: str = "example") -> Catalog:
    resources = {
        path: Resource(
            name,
            path.replace("/", "-"),
            path,
            len(payload),
            "sha256:" + hashlib.sha256(payload).hexdigest(),
            "text/plain",
        )
        for path, payload in CONTENT.items()
    }
    # license_status in the index: the cache commands refuse a dataset whose
    # terms nobody has read, and these tests are about linking, not licensing.
    dataset = Dataset(
        name,
        "Example",
        entry={"ethos:access": access, "ethos:license_status": "resolved"},
        _descriptor={"resources": []},
        _resources=resources,
    )
    return Catalog("local", {}, {name: dataset})


def _write(directory):
    for path, payload in CONTENT.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return directory


def _borrowed(tmp_path, name: str = "borrowed") -> Path:
    """Another project's directory, which this cache has only borrowed a link to.

    Deliberately not ``_write``: what makes the assertions about it worth
    anything is that its contents can be listed exactly, so an entry this cache
    wrote into somebody else's tree shows up as an extra name rather than
    having to be guessed at.
    """
    directory = tmp_path / name
    directory.mkdir()
    (directory / "a.txt").write_bytes(b"somebody else's data")
    return directory


@pytest.fixture
def workspace(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    return cache, _write(tmp_path / "data"), Roots(public=cache)


def test_creates_a_symbolic_link_in_the_cache(workspace):
    cache, data, roots = workspace
    report = link(_catalog(), "example", data, roots)

    entry = cache / "example"
    assert report.verb == "linked"
    assert entry.is_symlink()
    assert (entry / "a.txt").read_bytes() == CONTENT["a.txt"]


def test_the_link_is_what_makes_retrieval_read_in_place(workspace):
    _, data, roots = workspace
    catalog = _catalog()
    link(catalog, "example", data, roots)

    resources = list(catalog.dataset("example").resources.values())
    located = locate(catalog, resources, roots)

    assert all(location.in_place for location in located)
    assert {location.origin for location in located} == {ORIGIN_LINK}


def test_records_the_directory_it_was_given(workspace, tmp_path):
    """Not the resolved one: a curated path that itself goes through a link is
    the one that stays correct when the storage behind it moves."""
    cache, data, roots = workspace
    through = tmp_path / "curated"
    through.symlink_to(data, target_is_directory=True)

    link(_catalog(), "example", through, roots)

    # By final component: Windows records the link with a \\?\ extended-length
    # prefix, so the part that carries the meaning is which directory was named.
    recorded = (cache / "example").readlink()
    assert recorded.name == through.name == "curated"
    assert recorded.name != data.name


def test_a_relative_directory_is_made_absolute(workspace, monkeypatch, tmp_path):
    cache, data, roots = workspace
    monkeypatch.chdir(tmp_path)

    link(_catalog(), "example", "data", roots)

    # Resolved rather than compared literally: a link recorded relative to the
    # cache directory would point at nothing at all.
    assert (cache / "example").resolve() == data.resolve()


def test_refuses_a_directory_that_is_not_there(workspace, tmp_path):
    cache, _, roots = workspace
    with pytest.raises(LinkError, match="not a directory"):
        link(_catalog(), "example", tmp_path / "nowhere", roots)
    assert not (cache / "example").exists()


def test_will_not_replace_a_directory_the_cache_owns(workspace):
    cache, data, roots = workspace
    owned = cache / "example"
    owned.mkdir()
    (owned / "a.txt").write_bytes(b"downloaded earlier")

    with pytest.raises(LinkError, match="data the cache owns"):
        link(_catalog(), "example", data, roots)
    assert (owned / "a.txt").read_bytes() == b"downloaded earlier"


def test_force_will_not_replace_a_directory_the_cache_owns_either(workspace):
    """``--force`` overrules "that entry already exists", never "that is data".

    The two refusals above read alike from the terminal and are nothing alike in
    consequence: repointing a link discards a pointer, and replacing a real
    directory discards the only copy of a dataset somebody downloaded. What
    keeps the flag away from the second one today is only the order of the
    branches inside ``link`` -- the ``force`` test sits under ``is_symlink()``
    and the real directory is caught in the ``elif`` below it -- and nothing
    else states it, so a reshuffle of that cascade would make ``--force`` a
    delete with no test to say it had stopped being safe.
    """
    cache, data, roots = workspace
    owned = cache / "example"
    owned.mkdir()
    (owned / "a.txt").write_bytes(b"downloaded earlier")

    with pytest.raises(LinkError, match="data the cache owns"):
        link(_catalog(), "example", data, roots, force=True)

    assert not owned.is_symlink()
    assert (owned / "a.txt").read_bytes() == b"downloaded earlier"


def test_will_not_write_an_entry_below_a_borrowed_parent(tmp_path):
    """The write-through that ``mkdir(parents=True, exist_ok=True)`` makes silent.

    ``mkdir`` swallows the ``FileExistsError`` for a parent that is already a
    link to a directory, and ``is_dir()`` follows it, so the entry was created
    *inside* the borrowed tree and reported as made. That is the one thing a
    borrowed entry promises cannot happen -- the cache reads those bytes in
    place precisely because it never writes there -- and the entry also
    disappears the day its owner removes that one link.

    The shape here is the reorganisation that produces it: ``family`` was a flat
    dataset, this machine still holds yesterday's link for it, and the catalogue
    now describes ``family/member`` one level below that name.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    borrowed = _borrowed(tmp_path)
    (cache / "family").symlink_to(borrowed, target_is_directory=True)
    data = _write(tmp_path / "member")

    with pytest.raises(LinkError, match="borrowed"):
        link(_catalog(name="family/member"), "family/member", data, Roots(public=cache))

    assert [child.name for child in borrowed.iterdir()] == ["a.txt"]


def test_force_below_a_borrowed_parent_refuses_before_it_removes_anything(tmp_path):
    """Refusing late costs the entry the refusal was protecting.

    The borrowed parent is checked above the whole cascade rather than just
    above the ``mkdir`` that would do the damage, because a ``--force`` repoint
    reaches ``entry.unlink()`` first: a guard placed where the write happens
    would destroy the existing entry in the course of declining to replace it.
    The entry standing here is the damage an earlier version wrote into
    somebody else's tree, which makes it exactly the one a maintainer is most
    likely to aim ``--force`` at.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    borrowed = _borrowed(tmp_path)
    (cache / "family").symlink_to(borrowed, target_is_directory=True)
    stale, data = _write(tmp_path / "stale"), _write(tmp_path / "member")
    (borrowed / "member").symlink_to(stale, target_is_directory=True)

    with pytest.raises(LinkError, match="borrowed"):
        link(
            _catalog(name="family/member"),
            "family/member",
            data,
            Roots(public=cache),
            force=True,
        )

    assert (borrowed / "member").is_symlink()
    assert sorted(child.name for child in borrowed.iterdir()) == ["a.txt", "member"]


def test_force_says_what_it_destroyed_when_the_system_refuses_the_new_link(
    tmp_path, monkeypatch
):
    """A repoint that fails is a deletion, and it destroys the address as well.

    There is no atomic repoint to fall back on -- renaming a fresh symbolic link
    over an existing one is refused by Windows whichever call is used -- so
    ``--force`` removes the entry before it attempts the replacement. When the
    attempt is then refused, which is the ordinary answer on a machine without
    Developer Mode and therefore the machine this flag is most often typed on,
    the person asked for a repoint and got a deletion. The message said only that
    the link could not be created, and the one thing the deletion destroyed was
    the record of where the entry pointed, which is also the only thing needed to
    put it back.

    So the refusal has to say that the entry is gone, where it used to point, and
    how to restore it -- and the line it prints has to survive being pasted: a
    source directory with a space in it is unremarkable on a Windows share, and a
    recovery command that silently splits in two is the same failure again.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    old, new = _write(tmp_path / "old data"), _write(tmp_path / "new")
    (cache / "example").symlink_to(old, target_is_directory=True)

    def refuse(self, target, target_is_directory=False):
        raise OSError(1314, "A required privilege is not held by the client")

    monkeypatch.setattr(Path, "symlink_to", refuse)

    with pytest.raises(LinkError) as refusal:
        link(_catalog(), "example", new, Roots(public=cache), force=True)

    message = str(refusal.value)
    assert "--force had already removed" in message
    assert str(old) in message
    assert f'ethos-data link example "{old}"' in message
    # Asserted because the message is only worth having if it is true: the entry
    # really is gone, and the data it pointed at really is not.
    assert list(cache.iterdir()) == []
    assert (old / "a.txt").read_bytes() == CONTENT["a.txt"]


def test_unlink_still_reaches_an_entry_below_a_borrowed_parent(tmp_path):
    """The one place the guard is deliberately absent, asserted so it stays absent.

    An entry an earlier version wrote through a borrowed link can only be
    cleaned up by removing it, and removing a link discards nothing. Guarding
    ``unlink`` for symmetry with ``link`` would leave that damage unreachable by
    the tool that made it, which is why the asymmetry is on purpose rather than
    an oversight somebody should tidy up.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    borrowed = _borrowed(tmp_path)
    (cache / "family").symlink_to(borrowed, target_is_directory=True)
    stale = _write(tmp_path / "stale")
    (borrowed / "member").symlink_to(stale, target_is_directory=True)

    report = unlink(
        _catalog(name="family/member"), "family/member", Roots(public=cache)
    )

    assert report.verb == "removed"
    assert [child.name for child in borrowed.iterdir()] == ["a.txt"]
    assert (stale / "a.txt").read_bytes() == CONTENT["a.txt"]


def test_repointing_needs_force(workspace, tmp_path):
    cache, data, roots = workspace
    other = _write(tmp_path / "other")
    link(_catalog(), "example", other, roots)

    with pytest.raises(LinkError, match="already points at"):
        link(_catalog(), "example", data, roots)

    report = link(_catalog(), "example", data, roots, force=True)
    assert report.verb == "repointed"
    assert (cache / "example").resolve() == data.resolve()


def test_restricted_data_is_linked_in_the_restricted_root(workspace, tmp_path):
    cache, data, _ = workspace
    restricted = tmp_path / "restricted"
    roots = Roots(public=cache, restricted=restricted)

    link(_catalog("restricted"), "example", data, roots)

    assert (restricted / "example").is_symlink()
    assert not (cache / "example").exists()


def test_restricted_data_without_a_restricted_cache_is_refused(workspace):
    cache, data, roots = workspace
    with pytest.raises(LinkError, match="no restricted cache is configured"):
        link(_catalog("restricted"), "example", data, roots)
    # Never the public cache: that is the one place licensed bytes may not go.
    assert not (cache / "example").exists()


def test_an_unknown_dataset_is_not_linked(workspace):
    _, data, roots = workspace
    with pytest.raises(UnknownDataset):
        link(_catalog(), "mystery", data, roots)


def test_a_link_one_level_wrong_is_reported_but_still_made(workspace, tmp_path):
    cache, data, roots = workspace
    report = link(_catalog(), "example", data.parent, roots)

    assert report.missing == "a.txt"
    assert (cache / "example").is_symlink()


def test_unlink_removes_the_entry_and_not_the_data(workspace):
    cache, data, roots = workspace
    link(_catalog(), "example", data, roots)

    report = unlink(_catalog(), "example", roots)

    assert report.verb == "removed"
    assert not (cache / "example").exists()
    assert (data / "a.txt").read_bytes() == CONTENT["a.txt"]


def test_unlink_refuses_a_real_directory(workspace):
    cache, _, roots = workspace
    owned = cache / "example"
    owned.mkdir()
    (owned / "a.txt").write_bytes(b"downloaded earlier")

    with pytest.raises(LinkError, match="real directory"):
        unlink(_catalog(), "example", roots)
    assert (owned / "a.txt").exists()


def _checkout(tmp_path, datasets: dict[str, str]) -> pytest.TempPathFactory:
    """A source catalogue: catalog.yaml and hand-written dataset.yaml files.

    source_dir lives here and nowhere else -- it is popped out of the descriptor
    when the manifest is built -- so this is what `link` without a directory has
    to read.

    A key may be a nested name such as ``family/member``: a dataset directory is
    allowed to hold more dataset directories, and the planner reads a family as
    a namespace node plus the members that actually own files.
    """
    root = tmp_path / "catalogue"
    (root / "datasets").mkdir(parents=True)
    (root / "catalog.yaml").write_text("name: test\ntitle: Test\n")
    for name, body in datasets.items():
        directory = root / "datasets" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "dataset.yaml").write_text(body)
    return root


def test_links_the_source_dir_when_no_directory_is_given(workspace, tmp_path):
    cache, data, roots = workspace
    checkout = _checkout(
        tmp_path,
        {"example": f"name: example\ntitle: Example\nsource_dir: {data.as_posix()}\n"},
    )

    report = link(_catalog(), "example", roots=roots, catalog_root=checkout)

    assert report.target == data
    assert (cache / "example").is_symlink()
    assert (cache / "example" / "a.txt").read_bytes() == CONTENT["a.txt"]


def test_a_dataset_with_no_source_dir_says_what_to_do_instead(workspace, tmp_path):
    """An uploaded dataset has none by design: dCache holds it."""
    cache, _, roots = workspace
    checkout = _checkout(
        tmp_path, {"example": "name: example\ntitle: Example\nethos:uploaded: true\n"}
    )

    with pytest.raises(LinkError, match="no source_dir"):
        link(_catalog(), "example", roots=roots, catalog_root=checkout)
    assert not (cache / "example").exists()


def test_a_dataset_the_checkout_does_not_have(workspace, tmp_path):
    _, _, roots = workspace
    checkout = _checkout(tmp_path, {})

    with pytest.raises(LinkError, match="no dataset called"):
        link(_catalog(), "example", roots=roots, catalog_root=checkout)


def test_cli_all_links_every_source_dir_into_the_configured_cache(
    tmp_path, monkeypatch, capsys
):
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    one, two = _write(tmp_path / "one"), _write(tmp_path / "two")
    checkout = _checkout(
        tmp_path,
        {
            "one": f"name: one\ntitle: One\nsource_dir: {one.as_posix()}\n{LICENCE}",
            "two": f"name: two\ntitle: Two\nsource_dir: {two.as_posix()}\n{LICENCE}",
        },
    )

    assert main(["link", "--all", "--catalog-root", str(checkout), "--dry-run"]) == 0
    assert not (cache / "one").exists()

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert (cache / "one").is_symlink() and (cache / "two").is_symlink()

    # Run twice: an entry that is already right is left alone rather than
    # repointed, which on Windows means looking past the \\?\ prefix.
    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert "nothing to do" in capsys.readouterr().out


def _two_dataset_checkout(tmp_path):
    """A settled, public, two-dataset checkout: the ordinary catalogue-mode case.

    Two datasets rather than one throughout, because almost everything catalogue
    mode can get wrong is about a *namespace* rather than an entry: that
    refusing one entry still leaves the rest of the cache built, and that
    pruning one entry does not take its neighbour with it.
    """
    one, two = _write(tmp_path / "one"), _write(tmp_path / "two")
    return (
        _checkout(
            tmp_path,
            {
                "one": f"name: one\ntitle: One\nsource_dir: {one.as_posix()}\n{LICENCE}",
                "two": f"name: two\ntitle: Two\nsource_dir: {two.as_posix()}\n{LICENCE}",
            },
        ),
        one,
        two,
    )


def _reclassify(checkout, name: str, line: str) -> None:
    """Edit one dataset.yaml the way a reclassification actually happens.

    One line added to a file in the checkout, long after the namespace was
    built. That order is the whole point of the tests below: the cache is
    already holding a live link at the moment the planner first reads the new
    line, so "skip it" is an answer about a dataset that is very much here.
    """
    descriptor = checkout / "datasets" / name / "dataset.yaml"
    descriptor.write_text(descriptor.read_text() + line)


def _family_checkout(tmp_path):
    """A checkout where ``family`` is a namespace node and ``family/member`` owns files.

    Plus an unrelated ``one``, for the same reason ``_two_dataset_checkout`` has
    two: what a refusal in a namespace has to prove is that the rest of the
    cache was still built.
    """
    member, one = _write(tmp_path / "member"), _write(tmp_path / "one")
    return (
        _checkout(
            tmp_path,
            {
                "family": "name: family\ntitle: Family\n",
                "family/member": (
                    f"name: family/member\ntitle: Member\n"
                    f"source_dir: {member.as_posix()}\n{LICENCE}"
                ),
                "one": f"name: one\ntitle: One\nsource_dir: {one.as_posix()}\n{LICENCE}",
            },
        ),
        member,
        one,
    )


def _restricted_checkout(tmp_path):
    """A checkout with one ordinary dataset and one the catalogue calls restricted.

    Both carry settled terms. What keeps the restricted one out of a shared
    namespace is its access class and nothing else, so a checkout that also left
    its licensing unanswered would let every test below pass for the wrong
    reason -- an unresolved licence is removed from any namespace at all, which
    is the exact distinction these tests exist to draw.
    """
    open_data, licensed = _write(tmp_path / "open"), _write(tmp_path / "licensed-bytes")
    return (
        _checkout(
            tmp_path,
            {
                "open": (
                    f"name: open\ntitle: Open\n"
                    f"source_dir: {open_data.as_posix()}\n{LICENCE}"
                ),
                "licensed": (
                    f"name: licensed\ntitle: Licensed\nethos:access: restricted\n"
                    f"source_dir: {licensed.as_posix()}\n{LICENCE}"
                ),
            },
        ),
        open_data,
        licensed,
    )


def _register_one_installation(cache: Path, licensed: Path) -> Path:
    """One authorised installation of licensed data, made the way the tool makes it.

    Deliberately ``link`` itself rather than a hand-written symlink. The question
    every test that uses this asks is whether catalogue mode will destroy what
    dataset mode is for, and an answer is only worth anything if the thing
    standing in the cache is what dataset mode actually writes -- a symbolic
    link, in whichever root the access class chooses, which for a restricted
    dataset is the restricted one.
    """
    report = link(
        _catalog("restricted", "licensed"),
        "licensed",
        licensed,
        Roots(public=cache / "not-this-one", restricted=cache),
    )
    return report.entry


def _printed_commands(text: str) -> list[str]:
    """Every line of a report that is a command somebody might paste.

    Indented, and starting with the program's name: that is the one shape these
    reports use for something to run, as opposed to a flag named inside a
    sentence.
    """
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("ethos-data")
    ]


def _assert_no_unaimed_prune(text: str, root: Path) -> list[str]:
    """No command a report prints may delete from a cache the report never named.

    ``--prune`` is the only flag here that removes anything, so a printed command
    carrying it has to say which directory it is about, in the position that
    decides it: ``ethos-data --root DIR link --all`` declares DIR to be this
    installation's public cache, while ``--root`` after ``link`` only names a
    destination. The rootless spelling is what made this worth asserting -- it
    resolves the public cache wherever it happens to be typed, so a report about
    one directory handed out a deleting command aimed at another, and the report
    that printed it most was the one about a directory nobody had identified.

    The commands it checked are returned so that a caller can say how many it
    expected. A rule applied to nothing passes, and a report that has stopped
    offering its remedy is a change worth failing on rather than one to be
    congratulated for breaking no rule.
    """
    checked = []
    for command in _printed_commands(text):
        if "--prune" not in command:
            continue
        words = command.split()
        assert words[:2] == ["ethos-data", "--root"], command
        assert Path(words[2]).resolve() == root.resolve(), command
        assert words[3:5] == ["link", "--all"], command
        assert "--catalog-root" in words, command
        checked.append(command)
    return checked


def test_cli_all_honours_an_explicit_root(tmp_path, monkeypatch):
    """``--root`` names the cache to build, which is rarely this account's own.

    The namespace for a whole machine is built once, by somebody who knows where
    the storage is; their personal ``$ETHOS_DATA_DIR`` is beside the point. So
    the decoy cache here is not a contrived case, it is the normal one -- and
    the failure it guards against, a shared namespace quietly assembled in the
    maintainer's home directory instead, looks exactly like success from the
    terminal.
    """
    decoy = tmp_path / "decoy"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(decoy))
    shared = tmp_path / "shared"
    checkout, _, _ = _two_dataset_checkout(tmp_path)

    code = main(
        ["link", "--all", "--root", str(shared), "--catalog-root", str(checkout)]
    )

    assert code == 0
    assert (shared / "one").is_symlink() and (shared / "two").is_symlink()
    assert not decoy.exists()


def test_cli_all_takes_both_where_and_whose_from_the_top_level_root(
    tmp_path, monkeypatch
):
    """Where ``--root`` sits decides what the directory *is*, not only where it is.

    Two runs, one destination, opposite outcomes, and nothing between them but
    the position of the flag. ``link --all --root DIR`` names somewhere to build
    and says nothing about it, so a restricted dataset found linked there may be
    another machine's authorised installation -- registered deliberately by
    somebody entitled to hold the bytes -- and is reported rather than removed.
    ``ethos-data --root DIR link --all`` is the top-level override every other
    subcommand in the process reads, and it declares DIR to be *this*
    installation's public cache, which is the only thing that licenses
    ``--prune`` to retract licensed bytes from it.

    Asserted as a pair, because either half on its own is satisfied by a run that
    never reads the flag at all. The decoy cache is why the pair is worth having
    at this level rather than the planner's: the namespace for a whole machine is
    built by somebody whose own ``$ETHOS_DATA_DIR`` is beside the point, and a
    shared namespace quietly assembled in their home directory instead looks
    exactly like success from the terminal.
    """
    ignored = tmp_path / "ignored"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(ignored))
    monkeypatch.delenv("ETHOS_RESTRICTED_DIR", raising=False)
    checkout, _, licensed = _restricted_checkout(tmp_path)
    chosen = tmp_path / "chosen"
    entry = _register_one_installation(chosen, licensed)

    destination_only = main(
        [
            "link",
            "--all",
            "--root",
            str(chosen),
            "--catalog-root",
            str(checkout),
            "--prune",
        ]
    )

    assert destination_only == 1
    assert entry.is_symlink()
    assert (chosen / "open").is_symlink()

    identified = main(
        [
            "--root",
            str(chosen),
            "link",
            "--all",
            "--catalog-root",
            str(checkout),
            "--prune",
        ]
    )

    assert identified == 0
    assert not entry.is_symlink() and not entry.exists()
    assert (licensed / "a.txt").read_bytes() == CONTENT["a.txt"]
    assert (chosen / "open").is_symlink()
    assert not ignored.exists()


def test_cli_all_prune_removes_a_link_the_catalogue_no_longer_names(
    tmp_path, monkeypatch
):
    """Removing entries is opt-in, because a checkout is not an authority.

    A checkout on the wrong branch, or one part-way through a rename, disagrees
    with the cache for entirely boring reasons; if a routine rebuild deleted on
    the strength of that, everybody on the machine would lose entries they are
    reading. So the stale link is asserted twice: still there after a run
    without ``--prune``, and gone only after the run with it.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert (cache / "two").is_symlink()

    shutil.rmtree(checkout / "datasets" / "two")

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert (cache / "two").is_symlink()

    assert main(["link", "--all", "--prune", "--catalog-root", str(checkout)]) == 0
    assert not (cache / "two").exists()
    assert (cache / "one").is_symlink()


def test_cli_all_prune_leaves_a_real_directory_alone(tmp_path, monkeypatch):
    """Pruning removes links. A real directory is data, and data is never stale.

    An entry the cache owns was downloaded from dCache or materialised here, and
    the catalogue no longer naming it says something about the catalogue rather
    than about the bytes. Deleting them on that evidence is the one mistake this
    command could make that nobody can undo.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    owned = cache / "downloaded"
    owned.mkdir(parents=True)
    (owned / "a.txt").write_bytes(b"downloaded earlier")

    assert main(["link", "--all", "--prune", "--catalog-root", str(checkout)]) == 0

    assert not owned.is_symlink()
    assert (owned / "a.txt").read_bytes() == b"downloaded earlier"
    assert (cache / "one").is_symlink()


def test_cli_all_prune_writes_nothing_on_a_dry_run(tmp_path, monkeypatch, capsys):
    """``--prune`` is the only flag here that removes anything, which makes it
    the only one whose preview has to be shown inert rather than assumed so."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    shutil.rmtree(checkout / "datasets" / "two")

    code = main(
        ["link", "--all", "--prune", "--dry-run", "--catalog-root", str(checkout)]
    )

    assert code == 0
    assert (cache / "two").is_symlink()
    assert "Nothing was written" in capsys.readouterr().out


def test_cli_all_never_replaces_a_directory_the_cache_owns(tmp_path, monkeypatch):
    """The catalogue-mode half of ``test_will_not_replace_a_directory_the_cache_owns``.

    Both modes refuse, and they refuse differently on purpose: naming one
    dataset raises, because the person asked for something impossible and wants
    to hear so, whereas building a namespace keeps the entry and carries on,
    because one downloaded dataset is no reason to leave the other twenty
    unlinked. That is what the neighbour asserts here -- a refusal that
    abandoned the rest of the run would satisfy the first two assertions.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    owned = cache / "one"
    owned.mkdir(parents=True)
    (owned / "a.txt").write_bytes(b"downloaded earlier")

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0

    assert not owned.is_symlink()
    assert (owned / "a.txt").read_bytes() == b"downloaded earlier"
    assert (cache / "two").is_symlink()


def test_cli_all_skips_restricted_data_that_link_by_name_still_takes(
    tmp_path, monkeypatch
):
    """The asymmetry between the two modes, asserted in one place on purpose.

    ``--all`` builds a namespace everybody on the machine reads, so a licensed
    dataset stays out of it however settled its terms are: the entry would hand
    the bytes to people the licence never covered. Naming that same dataset is
    the opposite act -- one authorised installation, registered deliberately --
    and it is the supported path, into the restricted cache and never the public
    one. Both halves here read the same checkout, so that nothing but the mode
    differs between them.
    """
    cache = tmp_path / "cache"
    restricted = tmp_path / "restricted"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    open_data, licensed = _write(tmp_path / "open"), _write(tmp_path / "licensed")
    checkout = _checkout(
        tmp_path,
        {
            "open": (
                f"name: open\ntitle: Open\n"
                f"source_dir: {open_data.as_posix()}\n{LICENCE}"
            ),
            "example": (
                f"name: example\ntitle: Example\nethos:access: restricted\n"
                f"source_dir: {licensed.as_posix()}\n{LICENCE}"
            ),
        },
    )

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert (cache / "open").is_symlink()
    assert not (cache / "example").exists()

    link(
        _catalog("restricted"),
        "example",
        roots=Roots(public=cache, restricted=restricted),
        catalog_root=checkout,
    )

    assert (restricted / "example").is_symlink()
    assert not (cache / "example").exists()


def test_cli_all_reports_a_source_dir_that_is_not_there(tmp_path, monkeypatch):
    """A namespace that is silently incomplete is worse than one that says so.

    The exit code is the only thing the maintainer's rebuild script can read, so
    a source_dir that has moved has to make the run fail -- while everything
    that can still be linked is linked, because stopping at the first casualty
    would hold a whole machine's cache hostage to one stale path.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    one = _write(tmp_path / "one")
    moved_away = tmp_path / "moved-away"
    checkout = _checkout(
        tmp_path,
        {
            "one": f"name: one\ntitle: One\nsource_dir: {one.as_posix()}\n{LICENCE}",
            "gone": (
                f"name: gone\ntitle: Gone\n"
                f"source_dir: {moved_away.as_posix()}\n{LICENCE}"
            ),
        },
    )

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 1
    assert (cache / "one").is_symlink()
    assert not (cache / "gone").exists()


def test_cli_all_retracts_a_link_for_a_dataset_reclassified_as_restricted(
    tmp_path, monkeypatch, capsys
):
    """Reclassification is the only way licensed bytes ever reach a public cache.

    Access is edited *after* the namespace was built -- that is what a
    reclassification is -- so the run that first reads ``ethos:access:
    restricted`` is looking at a live link it made itself last week, still
    handing the bytes to everybody who reads this cache. Reporting that as
    ``skip`` and exiting 0 is what made the exposure permanent: the line reads
    as though the dataset had never been here, the exit code says the namespace
    was built, and a nightly rebuild has nothing to notice for months.

    So the link is asserted at every step -- made, still there and reported
    after a run without ``--prune``, gone only after the run with it -- and an
    exit code beside each, because the exit code is the only part of a run a
    rebuild script reads. The sentence is asserted too: ``--prune``'s own line
    for an entry it removes says the catalogue does not describe the dataset any
    more, which is the one thing that is not true of a reclassified one, and a
    maintainer who reads it goes looking in the wrong file.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, two = _two_dataset_checkout(tmp_path)

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert (cache / "two").is_symlink()

    _reclassify(checkout, "two", "ethos:access: restricted\n")

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 1
    reported = capsys.readouterr().out
    assert "exposed" in reported and "restricted" in reported
    assert str(two) in reported
    assert (cache / "two").is_symlink()

    assert main(["link", "--all", "--prune", "--catalog-root", str(checkout)]) == 0
    removed = capsys.readouterr().out
    assert "retract" in removed
    assert "not in the catalogue any more" not in removed
    assert not (cache / "two").is_symlink() and not (cache / "two").exists()
    assert (two / "a.txt").read_bytes() == CONTENT["a.txt"]
    assert (cache / "one").is_symlink()


def test_cli_all_dry_run_still_fails_while_the_link_is_being_served(
    tmp_path, monkeypatch
):
    """A preview of a retraction has retracted nothing.

    ``--dry-run`` returning 0 for a plan it did not carry out is right for every
    other verb -- nothing is wrong, the work is simply still to do -- and wrong
    for this one: the link is still serving licensed bytes at the moment the
    process exits, and a rebuild script that reads only the exit code would
    treat the preview as an all-clear. It is the same 1 the run without
    ``--prune`` returns, for the same reason.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    _reclassify(checkout, "two", "ethos:access: restricted\n")

    code = main(
        ["link", "--all", "--prune", "--dry-run", "--catalog-root", str(checkout)]
    )

    assert code == 1
    assert (cache / "two").is_symlink()


def test_cli_all_never_removes_a_real_directory_for_a_reclassified_dataset(
    tmp_path, monkeypatch, capsys
):
    """Retracting removes links, and a real directory is not one.

    The entry a reclassification finds may be data the cache owns -- downloaded
    or materialised here before anybody edited dataset.yaml -- and that is a
    worse exposure than a link and still not one this command can answer:
    removing it discards the only copy, on the strength of an edit to a YAML
    file. So the excluded dataset stays the ``skip`` it has always been, with no
    effect on the exit code, and the bytes are left for somebody to deal with
    deliberately.

    The line itself is asserted because it is the only thing the maintainer gets.
    It says two things, and both have to survive a rewording: where this dataset
    belongs -- the restricted cache, where each installation is registered by
    name, which is what ``ethos-data link <dataset> <directory>`` does -- and
    that what is standing here is a real directory holding the cache's own copy.
    Without the second half the line reads exactly like the one printed for a
    dataset this cache has never held, and the worse exposure goes unmentioned.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    owned = cache / "two"
    owned.mkdir(parents=True)
    (owned / "a.txt").write_bytes(b"downloaded earlier")
    _reclassify(checkout, "two", "ethos:access: restricted\n")

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert main(["link", "--all", "--prune", "--catalog-root", str(checkout)]) == 0

    assert not owned.is_symlink()
    assert (owned / "a.txt").read_bytes() == b"downloaded earlier"
    reported = capsys.readouterr().out
    assert (
        "restricted: belongs in the restricted cache, where each installation is "
        "registered by name" in reported
    )
    assert "The cache holds a real directory here" in reported


def test_cli_all_refuses_to_write_an_entry_inside_borrowed_data(
    tmp_path, monkeypatch, capsys
):
    """Catalogue mode's half of ``test_will_not_write_an_entry_below_a_borrowed_parent``.

    One run, two defects, because this is one situation: the machine holds
    yesterday's flat ``family`` link and the catalogue now describes
    ``family/member``. The entry was written *into* the borrowed tree, and
    ``--prune`` then removed the link it had just been written under -- because
    a namespace node owns no files and so was missing from the only set the
    prune loop consults -- leaving a stray link in somebody else's data, no
    entry at ``family/member``, and ``2 change(s) applied.`` above exit 0.

    The neighbour is asserted for the usual reason: refusing one entry must not
    abandon the rest of the namespace.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _family_checkout(tmp_path)
    borrowed = _borrowed(tmp_path)
    cache.mkdir()
    (cache / "family").symlink_to(borrowed, target_is_directory=True)

    code = main(["link", "--all", "--prune", "--catalog-root", str(checkout)])

    assert [child.name for child in borrowed.iterdir()] == ["a.txt"]
    assert code == 1
    assert (cache / "family").is_symlink()
    assert (cache / "one").is_symlink()
    reported = capsys.readouterr().out
    assert "blocked" in reported
    assert "not in the catalogue any more" not in reported


def test_cli_all_prune_still_removes_a_family_that_has_left_the_catalogue(
    tmp_path, monkeypatch
):
    """Protecting namespace prefixes must not become an amnesty for families.

    The set that stops ``--prune`` deleting ``family`` is derived from the
    members the catalogue declares below it, so it lasts exactly as long as they
    do. Without this, the obvious way to keep the prefix safe -- a name with a
    slash in it anywhere, or anything else that never expires -- would look
    correct in the test above and quietly leave a whole family's stale link in
    every cache forever.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _family_checkout(tmp_path)

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert (cache / "family" / "member").is_symlink()

    shutil.rmtree(checkout / "datasets" / "family")

    assert main(["link", "--all", "--prune", "--catalog-root", str(checkout)]) == 0
    assert not (cache / "family" / "member").exists()
    assert (cache / "one").is_symlink()


def test_cli_all_never_writes_into_the_source_of_a_name_that_holds_a_family(
    tmp_path, monkeypatch, capsys
):
    """The write-through whose damage lands in curated data, not in a cache.

    ``a`` claims files of its own and ``a/x/y`` is a dataset below it, with no
    dataset.yaml in ``a/x``. That one ordinary directory in the middle was enough
    to make "does this name hold a family?" answer no, so ``a`` went into the
    datasets to link *and* into the prefixes to protect at once: ``<cache>/a``
    became a symbolic link to the first dataset's source directory, and the
    member below it was then created through that link -- ``mkdir(parents=True,
    exist_ok=True)`` follows one -- so ``x/y`` appeared inside ``a-src`` itself.
    The run printed both links, ``2 change(s) applied.`` and exited 0, and the
    damage was not in the cache at all but in somebody's curated data elsewhere
    on the machine. That is why what is asserted here is the state of ``a-src``
    rather than the state of the cache.

    Membership is read at any depth now, so ``a`` is a namespace node whatever
    the directories between it and its member look like, and a node that also
    claims files is a ``conflict`` for the checkout to answer rather than two
    entries that cannot both exist. The member is linked meanwhile: one
    contradictory name is no reason to leave a family out of the cache.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    outer, inner = _write(tmp_path / "a-src"), _write(tmp_path / "y-src")
    checkout = _checkout(
        tmp_path,
        {
            "a": f"name: a\ntitle: A\nsource_dir: {outer.as_posix()}\n{LICENCE}",
            "a/x/y": (
                f"name: a/x/y\ntitle: Y\nsource_dir: {inner.as_posix()}\n{LICENCE}"
            ),
        },
    )

    code = main(["link", "--all", "--catalog-root", str(checkout)])

    assert sorted(path.name for path in outer.rglob("*")) == ["a.txt", "b.txt", "sub"]
    assert code == 1
    assert (cache / "a" / "x" / "y").is_symlink()
    assert not (cache / "a").is_symlink()
    reported = capsys.readouterr().out
    conflicts = [line.split() for line in reported.split("\n") if "conflict" in line]
    assert [words[1] for words in conflicts] == ["a"]
    assert "a/x/y" in reported

    # Run twice, because the second run is where the first one's damage used to
    # surface: the directory was already inside `a-src`, and the FileExistsError
    # that produced came back as advice about Developer Mode.
    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 1
    assert sorted(path.name for path in outer.rglob("*")) == ["a.txt", "b.txt", "sub"]
    assert "failed" not in capsys.readouterr().out


def test_cli_all_reports_the_conflict_when_every_level_between_is_declared(
    tmp_path, monkeypatch, capsys
):
    """The same contradiction with nothing missing from the checkout.

    ``family`` claims files, ``family/sub`` is an ordinary namespace node with a
    dataset.yaml of its own, and ``family/sub/member`` is the dataset that holds
    bytes. No descriptor is absent here, so this is the shape a real catalogue
    grows into rather than a half-finished one -- and ``family`` still cannot
    have an entry, because ``<cache>/family`` would have to be a link and a
    directory at the same time.

    Two things besides the source directory. ``family/sub`` gets no line at all:
    a namespace owns no files, so "no source_dir" is not a finding about it, and
    printing one would bury the finding that is real. And the conflict is
    reported against the name that claims the files rather than against the
    member below it, which is linked exactly as it would be otherwise.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    outer, inner = _write(tmp_path / "family-src"), _write(tmp_path / "member-src")
    checkout = _checkout(
        tmp_path,
        {
            "family": (
                f"name: family\ntitle: Family\n"
                f"source_dir: {outer.as_posix()}\n{LICENCE}"
            ),
            "family/sub": "name: family/sub\ntitle: Sub\n",
            "family/sub/member": (
                f"name: family/sub/member\ntitle: Member\n"
                f"source_dir: {inner.as_posix()}\n{LICENCE}"
            ),
        },
    )

    code = main(["link", "--all", "--catalog-root", str(checkout)])

    assert sorted(path.name for path in outer.rglob("*")) == ["a.txt", "b.txt", "sub"]
    assert code == 1
    assert (cache / "family" / "sub" / "member").is_symlink()
    assert not (cache / "family").is_symlink()
    reported = capsys.readouterr().out
    conflicts = [line.split() for line in reported.split("\n") if "conflict" in line]
    assert [words[1] for words in conflicts] == ["family"]
    assert "no source_dir" not in reported


def test_cli_all_refuses_the_restricted_cache_before_it_reads_anything(
    tmp_path, monkeypatch, capsys
):
    """``link --all`` has no work it may legitimately do in the restricted cache.

    Every entry there is one authorised installation of licensed data, registered
    by somebody entitled to hold it -- which is what ``ethos-data link <dataset>
    <directory>`` writes, and what this fixture therefore writes with that
    function rather than by hand. Catalogue mode may not create restricted
    entries in bulk from a checkout, and a public entry written there would sit
    where nothing looks for it.

    What made this worth refusing outright is what the run used to do instead:
    the planner read ``ethos:access: restricted``, saw a link at that name, and
    called it an exposure, so the report ended in a ``--prune`` line with the
    restricted cache already substituted into it. The tool recommended deleting
    the installation it exists to create. Refusing before the checkout is read is
    what leaves no plan to print and no remedy line to copy.
    """
    restricted = tmp_path / "restricted"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "public"))
    monkeypatch.setenv("ETHOS_RESTRICTED_DIR", str(restricted))
    checkout, _, licensed = _restricted_checkout(tmp_path)
    entry = _register_one_installation(restricted, licensed)

    code = main(
        [
            "link",
            "--all",
            "--root",
            str(restricted),
            "--catalog-root",
            str(checkout),
            "--prune",
        ]
    )

    assert code == 2
    assert entry.is_symlink()
    assert (entry / "a.txt").read_bytes() == CONTENT["a.txt"]
    refused = capsys.readouterr().err
    assert "is the restricted cache on this machine" in refused
    assert "Nothing was read and nothing was changed" in refused
    # Nothing in the refusal names a command that would remove what it protects.
    assert "--prune" not in refused
    _assert_no_unaimed_prune(refused, restricted)
    # And no namespace was started anywhere else on the way to refusing.
    assert not (tmp_path / "public").exists()


def test_cli_all_prune_keeps_an_installation_in_a_directory_it_cannot_place(
    tmp_path, monkeypatch, capsys
):
    """Most machines have no restricted cache configured, and that is not consent.

    Building a cache for another machine is the documented cluster workflow, so
    an unidentified directory is ordinary rather than exotic -- and a restricted
    link inside one may be that machine's authorised installation. Retracting on
    the strength of "this dataset is restricted" alone never asked which cache
    ``--root`` names, so the answer was the same in both, and in one of them it
    destroyed the thing dataset mode exists to create.

    Reported, never removed, whatever ``--prune`` says, and the rest of the
    namespace is still built: the point is that this run cannot judge one entry,
    not that it cannot do its work.
    """
    elsewhere = tmp_path / "another-machines-cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "public"))
    monkeypatch.delenv("ETHOS_RESTRICTED_DIR", raising=False)
    checkout, _, licensed = _restricted_checkout(tmp_path)
    entry = _register_one_installation(elsewhere, licensed)

    code = main(
        [
            "link",
            "--all",
            "--root",
            str(elsewhere),
            "--catalog-root",
            str(checkout),
            "--prune",
        ]
    )

    assert code == 1
    assert entry.is_symlink()
    assert (entry / "a.txt").read_bytes() == CONTENT["a.txt"]
    assert (elsewhere / "open").is_symlink()
    reported = capsys.readouterr().out
    assert "exposed" in reported
    assert "retract" not in reported
    assert f"This run cannot tell what {elsewhere} is" in reported


def test_no_report_offers_a_command_that_prunes_a_cache_it_did_not_name(
    tmp_path, monkeypatch, capsys
):
    """Every remedy a report prints, read as what running it would actually do.

    A report is read at the moment somebody is looking for something to type, so
    the commands in it are the part most likely to be run without being reasoned
    about first. The one that deletes is ``--prune``, and the spelling it used to
    be offered in -- ``ethos-data link --all --prune``, with no root at all --
    resolves the public cache wherever it happens to be typed. Printed under a
    paragraph about a directory the run could not identify, it meant: paste this,
    and the installation you were just told to protect is removed from a cache
    the report never mentioned.

    Three reports rather than one, because the remedies are written in three
    different paragraphs and only one of them was ever wrong -- which is exactly
    the condition under which the next one to be added is wrong again.
    """
    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "public"))
    monkeypatch.delenv("ETHOS_RESTRICTED_DIR", raising=False)
    checkout, _, licensed = _restricted_checkout(tmp_path)
    public, elsewhere = tmp_path / "public", tmp_path / "elsewhere"
    _register_one_installation(public, licensed)
    _register_one_installation(elsewhere, licensed)
    catalogue = ["--catalog-root", str(checkout)]

    # This installation's own public cache, with the exposure still standing.
    assert main(["--root", str(public), "link", "--all", *catalogue]) == 1
    assert _assert_no_unaimed_prune(capsys.readouterr().out, public)

    # A directory nobody has identified, with and without the flag that deletes.
    for extra in ([], ["--prune"]):
        assert (
            main(["link", "--all", "--root", str(elsewhere), *catalogue, *extra]) == 1
        )
        assert _assert_no_unaimed_prune(capsys.readouterr().out, elsewhere)


def test_the_remedy_a_public_cache_exposure_prints_is_the_one_that_fixes_it(
    tmp_path, monkeypatch, capsys
):
    """The printed command is run as printed, because advice nobody ran is advice.

    The exposure paragraph is the only place a report offers something that
    deletes, so it is the one whose line has to be exactly right: the root in the
    position that declares what the directory is, the catalogue it was built
    from, and nothing that needs editing before it will work. Reconstructing it
    in the test would assert the sentence and not the command, so the line is
    taken out of the report and fed back to ``main`` word for word.

    What it must then do is the retraction it promised and nothing else: the
    neighbour stays linked, and the bytes behind the entry it removed are still
    there, because removing a link discards nothing.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, two = _two_dataset_checkout(tmp_path)
    built = ["--root", str(cache), "link", "--all", "--catalog-root", str(checkout)]
    assert main(built) == 0
    _reclassify(checkout, "two", "ethos:access: restricted\n")

    assert main(built) == 1
    reported = capsys.readouterr().out
    offered = [
        command for command in _printed_commands(reported) if "--prune" in command
    ]

    _assert_no_unaimed_prune(reported, cache)
    assert len(offered) == 1
    assert main(offered[0].split()[1:]) == 0
    assert not (cache / "two").exists() and not (cache / "two").is_symlink()
    assert (cache / "one").is_symlink()
    assert (two / "a.txt").read_bytes() == CONTENT["a.txt"]


def _flatten_the_family(checkout, source: Path) -> None:
    """Collapse a family back into one flat dataset, the way a catalogue does it.

    The member's directory goes and the name that held it is given a source_dir
    of its own. Both edits at once, because that is one commit in a checkout and
    therefore one run of this command -- and the run in between, which the
    planner used to need before it could see the empty directory, is a run that
    reports success about a name resolving to nothing.
    """
    shutil.rmtree(checkout / "datasets" / "family" / "member")
    (checkout / "datasets" / "family" / "dataset.yaml").write_text(
        f"name: family\ntitle: Family\nsource_dir: {source.as_posix()}\n{LICENCE}"
    )


def test_cli_all_prune_gives_a_re_flattened_family_its_entry_back(
    tmp_path, monkeypatch, capsys
):
    """A husk is not data the cache owns, and a ``keep`` about one never expires.

    ``--prune`` removes ``<root>/family/member`` and cannot remove
    ``<root>/family`` with it: that directory is not an entry, so the reader's
    walk never yields it and no prune action ever names it. What is left is a
    real directory this command made itself, holding nothing, standing exactly
    where the flattened dataset's entry belongs -- and ``keep`` tested only
    ``entry.exists()``, so every run from then on printed ``a real directory the
    cache owns; not replaced with a link`` about it and exited 0, while the
    declared dataset got no entry on any rerun at all.

    The run without ``--prune`` is asserted first and on its own. Nothing may be
    removed without that flag, so the answer there is to say the dataset has no
    entry and why -- neither quietly doing the removal, nor calling the husk
    data. The report says nothing to type, either: the only command this report
    ever prints is one that deletes, and handing it to somebody reading about an
    empty directory would be answering a different question with it.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _family_checkout(tmp_path)
    flat = _write(tmp_path / "flat")

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 0
    assert (cache / "family" / "member").is_symlink()

    _flatten_the_family(checkout, flat)

    assert main(["link", "--all", "--catalog-root", str(checkout)]) == 1
    without_prune = capsys.readouterr().out
    assert "obstructed" in without_prune
    assert "a real directory the cache owns" not in without_prune
    assert (cache / "family" / "member").is_symlink()
    assert _printed_commands(without_prune) == []

    assert main(["link", "--all", "--prune", "--catalog-root", str(checkout)]) == 0
    assert (cache / "family").is_symlink()
    assert (cache / "family" / "a.txt").read_bytes() == CONTENT["a.txt"]
    assert (cache / "one").is_symlink()

    # One run, not two: the husk was seen and removed while the members it used
    # to hold were being pruned in the same plan.
    assert main(["link", "--all", "--prune", "--catalog-root", str(checkout)]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_cli_all_reports_a_file_standing_where_an_entry_belongs(
    tmp_path, monkeypatch, capsys
):
    """Not a directory the cache owns, and not this command's to remove either.

    The branch that says "a real directory the cache owns" was reached by
    ``entry.exists()``, which is true of a file as well, so a file in the cache
    was described as downloaded data and the run exited 0 with the dataset
    unlinked. It is neither: nothing here put it there, so nothing here takes it
    away, and the dataset has no entry until somebody moves it.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    (cache / "one").write_bytes(b"not a directory at all")

    code = main(["link", "--all", "--prune", "--catalog-root", str(checkout)])

    assert code == 1
    assert (cache / "one").read_bytes() == b"not a directory at all"
    assert (cache / "two").is_symlink()
    reported = capsys.readouterr().out
    assert "a file stands where this entry belongs" in reported
    assert "a real directory the cache owns" not in reported


def test_no_run_ever_removes_a_directory_that_holds_downloaded_bytes(
    tmp_path, monkeypatch
):
    """The one mistake nobody can undo, asserted along every path that deletes.

    Three verbs remove things: ``prune`` a link the catalogue no longer names,
    ``retract`` a link this namespace must not hold, and ``replace`` an emptied
    namespace prefix -- the last being the first removal here that is not a
    symbolic link at all, and so the first that is not covered by "removing a
    link discards nothing". Each arrived at a different time with its own reason
    for being safe, and they share exactly one thing that must never be among
    them: a real directory holding files, which is the cache's own copy and the
    only one.

    So one run drives all three past four directories at once -- a downloaded
    dataset the catalogue no longer names, one it still names, one it has just
    reclassified as restricted, and a genuine husk -- and the bytes are read back
    afterwards. ``_owns_data`` is the single test that separates the husk from
    the other three, which is what makes asserting them beside each other worth
    more than asserting each beside its own verb.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    kept, reclassified = _write(tmp_path / "kept"), _write(tmp_path / "reclassified")
    member, flat = _write(tmp_path / "member"), _write(tmp_path / "flat")
    checkout = _checkout(
        tmp_path,
        {
            "kept": f"name: kept\ntitle: Kept\nsource_dir: {kept.as_posix()}\n{LICENCE}",
            "licensed": (
                f"name: licensed\ntitle: Licensed\nethos:access: restricted\n"
                f"source_dir: {reclassified.as_posix()}\n{LICENCE}"
            ),
            "family": (
                f"name: family\ntitle: Family\nsource_dir: {flat.as_posix()}\n{LICENCE}"
            ),
        },
    )
    downloaded = {
        cache / "kept": b"still in the catalogue",
        cache / "licensed": b"downloaded before the reclassification",
        cache / "stale": b"a name the catalogue dropped",
    }
    for directory, payload in downloaded.items():
        (directory / "deep").mkdir(parents=True)
        (directory / "deep" / "data.nc").write_bytes(payload)
    (cache / "family").mkdir()
    (cache / "family" / "member").symlink_to(member, target_is_directory=True)

    code = main(["link", "--all", "--prune", "--catalog-root", str(checkout)])

    assert code == 0
    for directory, payload in downloaded.items():
        assert not directory.is_symlink()
        assert (directory / "deep" / "data.nc").read_bytes() == payload
    # The husk, which held nothing, is the only real directory that went.
    assert (cache / "family").is_symlink()
    assert (cache / "family" / "a.txt").read_bytes() == CONTENT["a.txt"]


def _case_insensitive(directory: Path) -> bool:
    """Whether this filesystem calls two spellings of one name the same path.

    Asked of the directory the test is about to use rather than of the platform.
    Windows and macOS are the usual answer, a case-sensitive volume mounted on
    either of them is not, and what the defect turns on is the filesystem the
    cache sits on and nothing else.
    """
    probe = directory / "CaseProbe"
    probe.mkdir()
    folded = (directory / "caseprobe").is_dir()
    probe.rmdir()
    return folded


def test_cli_all_prune_does_not_delete_an_entry_the_cache_spells_differently(
    tmp_path, monkeypatch, capsys
):
    """One filesystem, two loops, and a working entry deleted between them.

    The declared loop looks the catalogue name up and this filesystem hands it
    the entry spelled another way, so the entry is reported ``unchanged``. The
    prune loop reads the spelling off the disk, does not find it among the
    catalogue names, and says "not in the catalogue any more" -- and ``--prune``
    removes what the line above it had just called correct. Both loops are right
    about what they asked; the cache is what is wrong, and saying so is the only
    answer that does not either delete a working entry or quietly accept a name
    that the Linux machines reading this cache over a share cannot find at all.

    The consequences of that answer are asserted too. Pruning is off for the
    whole run, because the one flag that deletes must not work against a
    namespace whose entries it cannot name -- so the genuinely stale link
    survives this run and is removed by the run after the rename. Retraction is
    not part of that pass and keeps going: a spelling difference somewhere else
    must never be what keeps licensed bytes being served.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    if not _case_insensitive(cache):
        pytest.skip(
            "this filesystem spells the two names apart, so neither loop collides"
        )
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, one, two = _two_dataset_checkout(tmp_path)
    _reclassify(checkout, "two", "ethos:access: restricted\n")
    (cache / "One").symlink_to(one, target_is_directory=True)
    (cache / "two").symlink_to(two, target_is_directory=True)
    (cache / "gone").symlink_to(_write(tmp_path / "gone"), target_is_directory=True)

    code = main(["link", "--all", "--prune", "--catalog-root", str(checkout)])

    assert code == 1
    assert (cache / "One").is_symlink()
    assert (cache / "One" / "a.txt").read_bytes() == CONTENT["a.txt"]
    assert (cache / "gone").is_symlink()
    assert not (cache / "two").exists() and not (cache / "two").is_symlink()
    reported = capsys.readouterr().out
    assert "collides" in reported
    assert "not in the catalogue any more" not in reported


def test_cli_all_does_not_answer_an_occupied_path_with_developer_mode(
    tmp_path, monkeypatch, capsys
):
    """Not every refusal is Windows declining to make symbolic links.

    Creation funnelled every OSError into the advice the single-dataset mode
    gives for a privilege refusal, and ``FileExistsError`` is an OSError. So a
    path occupied between the plan and the write -- which is what a second run
    over the damage an earlier version left behind looked like -- sent the
    maintainer to Developer Mode and told them to pin the dataset with ``config
    set-root``, neither of which has anything to do with a name already being
    taken. A wrong remedy costs more than none: it is acted on.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    create = Path.symlink_to

    def occupied(self, target, target_is_directory=False):
        if self == cache / "one":
            raise FileExistsError(17, "File exists")
        return create(self, target, target_is_directory=target_is_directory)

    monkeypatch.setattr(Path, "symlink_to", occupied)

    code = main(["link", "--all", "--catalog-root", str(checkout)])

    assert code == 1
    assert (cache / "two").is_symlink()
    reported = capsys.readouterr().out
    assert "failed  one" in reported
    assert "already exists, so the link could not be written there" in reported
    assert "Developer Mode" not in reported
    assert "config set-root" not in reported


def test_cli_all_survives_a_link_that_vanishes_while_the_plan_is_made(
    tmp_path, monkeypatch, capsys
):
    """Planning reads a cache, and a cache can change while it is being read.

    ``plan`` promises that no state the cache is in makes it raise. That promise
    is what makes ``--dry-run`` safe to point at one in any condition, and it is
    what keeps the exit-code contract: an OSError escaping the planner leaves the
    caller with a stack trace where the summary should be, and a rebuild script
    with nothing it can read at all. The main cascade still called
    ``entry.readlink()`` raw, so a link removed between the ``is_symlink()`` test
    and that call -- or a reparse point the system will not describe -- broke the
    promise at the one point every ordinary rebuild goes through.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, one, _ = _two_dataset_checkout(tmp_path)
    (cache / "one").symlink_to(one, target_is_directory=True)

    def vanished(self):
        raise OSError(2, "no such file or directory")

    monkeypatch.setattr(Path, "readlink", vanished)

    code = main(["link", "--all", "--dry-run", "--catalog-root", str(checkout)])

    assert code == 0
    reported = capsys.readouterr().out
    assert "repoint" in reported
    assert "its current target could not be read" in reported


def test_cli_all_names_the_old_target_the_way_somebody_typed_it(
    tmp_path, monkeypatch, capsys
):
    """The line a maintainer reads most often, printed as a path they can check.

    Windows stores a symbolic link with an extended-length prefix, so reading one
    back and printing it shows a path nobody wrote, which cannot be compared with
    the source_dir on the same line. ``repoint``'s detail is where that surfaces
    in an ordinary rebuild -- the comparison that decides whether the entry is
    correct at all has always stripped the prefix, and only the sentence
    explaining the decision did not.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    moved_from = _write(tmp_path / "moved-from")
    (cache / "one").symlink_to(moved_from, target_is_directory=True)

    assert main(["link", "--all", "--dry-run", "--catalog-root", str(checkout)]) == 0

    reported = capsys.readouterr().out
    assert f"was {moved_from}" in reported
    assert "\\\\?\\" not in reported


def test_cli_all_survives_a_directory_in_the_cache_it_cannot_list(
    tmp_path, monkeypatch
):
    """A directory the walk cannot open is an entry, not an absence.

    "I could not look" and "there is nothing there" are the same answer only to a
    command that deletes on the strength of it.

    A directory the walk could not open was skipped silently, which put it
    outside everything that reads a cache -- including the flag that removes
    entries from one. It is reported as an entry instead, and every caller here
    either leaves an entry alone or offers to remove it, so reporting one is the
    conservative answer in each of them. It is also half of what lets ``plan``
    promise it cannot raise.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    opaque = cache / "opaque"
    opaque.mkdir()
    listing = Path.iterdir

    def refuse_one(self):
        if self == opaque:
            raise OSError(5, "access is denied")
        return listing(self)

    monkeypatch.setattr(Path, "iterdir", refuse_one)

    code = main(["link", "--all", "--prune", "--catalog-root", str(checkout)])

    assert code == 0
    assert opaque.is_dir() and not opaque.is_symlink()
    assert (cache / "one").is_symlink() and (cache / "two").is_symlink()


def test_apply_removes_every_entry_before_it_creates_any(tmp_path):
    """Ordering, asked of ``apply`` directly, because no plan can demonstrate it.

    A removal takes away one link, and an entry created underneath a link that
    is then removed goes with it -- printed as linked, counted in the summary,
    and not there afterwards. The planner now makes that pair impossible on its
    own, which is why this is asked of ``apply`` with the two actions in the
    order that used to strand the entry: the creation first, the removal of the
    link standing in its way second. Doing every removal while no entry from
    this run exists yet leaves the failure no moment in which to occur, whatever
    a later planner decides.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    borrowed = _borrowed(tmp_path)
    member = _write(tmp_path / "member")
    (cache / "family").symlink_to(borrowed, target_is_directory=True)

    applied = namespace.apply(
        [
            namespace.Action(
                "family/member", "link", cache / "family" / "member", member
            ),
            namespace.Action(
                "family", "prune", cache / "family", detail="not in the catalogue"
            ),
        ]
    )

    assert [action.verb for action in applied] == ["link", "prune"]
    assert not (cache / "family").is_symlink()
    assert (cache / "family" / "member").is_symlink()
    assert (cache / "family" / "member").readlink().name == member.name
    assert [child.name for child in borrowed.iterdir()] == ["a.txt"]


def test_cli_all_reports_a_link_the_system_refused_instead_of_a_traceback(
    tmp_path, monkeypatch, capsys
):
    """Windows without Developer Mode simply will not create a symbolic link.

    On the audience this cache was written for that is the likeliest first run
    of the newly merged command, and letting the OSError out abandoned the run
    where it stood: the entries already written stayed, the ones after them were
    never attempted, the summary never printed, and the advice the
    single-dataset mode has always given for exactly this refusal was nowhere in
    the traceback. The exit-code contract was bypassed with it, so a rebuild
    script could not even tell what had happened.

    Both assertions about the neighbour matter. ``two`` being linked says the
    run carried on past the refusal, and ``1 change(s) applied.`` says the
    summary counts what happened rather than what was planned -- ``2`` there
    would be a line claiming a link that is not on the disk.
    """
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))
    checkout, _, _ = _two_dataset_checkout(tmp_path)
    create = Path.symlink_to

    def refuse_the_first(self, target, target_is_directory=False):
        if self == cache / "one":
            raise OSError(1314, "A required privilege is not held by the client")
        return create(self, target, target_is_directory=target_is_directory)

    monkeypatch.setattr(Path, "symlink_to", refuse_the_first)

    code = main(["link", "--all", "--catalog-root", str(checkout)])

    assert code == 1
    assert not (cache / "one").exists()
    assert (cache / "two").is_symlink()
    reported = capsys.readouterr().out
    assert "failed  one" in reported
    assert "1 change(s) applied." in reported
    # The summary no longer says what refused, because a `failed` action is not
    # always the filesystem saying no -- it is also a parent that turned into a
    # link mid-run, or a path already occupied. It says where to read the reason
    # instead, which is the one thing true of all of them.
    assert "1 change(s) could not be made" in reported
    assert "Each is named above with the reason" in reported
    # The advice is platform-specific, and the Windows branch is the one that
    # exists because the OS refuses: elsewhere there is nothing to advise.
    if os.name == "nt":
        assert "Developer Mode" in reported
        assert "mklink /J" in reported
    else:
        assert "could not create the link" in reported


@pytest.mark.parametrize(
    "arguments, message",
    [
        (["link", "--all", "example"], "takes no names"),
        (["link"], "name a dataset, or use --all"),
        # The mode-only flags. What is asserted is the name of the flag that was
        # refused rather than the sentence around it: the guidance is free to be
        # reworded, but a refusal that never says which flag it means leaves the
        # person guessing which of the two modes they were actually in.
        #
        # One case per flag, and no case that varies something the guard does not
        # read. `ethos-data link example somewhere --root elsewhere` was a fifth
        # row here, and it could never fail while the row above it passed: the
        # test is `args.cache_root is not None or args.prune`, which never looks
        # at the positional directory at all.
        (["link", "--all", "--force"], "--force"),
        (["link", "example", "--root", "elsewhere"], "--root"),
        (["link", "example", "--prune"], "--prune"),
    ],
)
def test_cli_rejects_a_contradictory_invocation(
    tmp_path, monkeypatch, capsys, arguments, message
):
    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "cache"))
    assert main(arguments) == 2
    assert message in capsys.readouterr().err


def _cli_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("ETHOS_RESTRICTED_DIR", raising=False)
    catalog = tmp_path / "datacatalog.json"
    catalog.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "name": "example",
                        "title": "Example",
                        "path": "example/datapackage.json",
                        "ethos:access": "public",
                        "ethos:file_count": 1,
                        "ethos:total_bytes": 10,
                        "ethos:license_status": "resolved",
                    }
                ]
            }
        )
    )
    package = tmp_path / "example"
    package.mkdir()
    (package / "datapackage.json").write_text(
        json.dumps(
            {
                "name": "example",
                "resources": [
                    {
                        "name": "a",
                        "path": "a.txt",
                        "bytes": 10,
                        "mediatype": "text/plain",
                        "hash": "sha256:"
                        + hashlib.sha256(CONTENT["a.txt"]).hexdigest(),
                    }
                ],
            }
        )
    )
    return catalog, _write(tmp_path / "data")


def test_cli_links_and_unlinks(tmp_path, monkeypatch, capsys):
    catalog, data = _cli_workspace(tmp_path, monkeypatch)

    assert main(["--catalog", str(catalog), "link", "example", str(data)]) == 0
    assert (tmp_path / "cache" / "example").is_symlink()
    assert "linked" in capsys.readouterr().out

    assert main(["--catalog", str(catalog), "unlink", "example"]) == 0
    assert not (tmp_path / "cache" / "example").exists()
    assert (data / "a.txt").exists()


def test_cli_dry_run_is_ignored_when_a_dataset_is_named(tmp_path, monkeypatch):
    """Documented as a no-op in dataset mode, and kept one rather than tightened.

    A dry run earns its place where the plan is long enough to be worth reading
    before it is written -- a whole namespace. One entry is not: the preview and
    the act would print the same single line. Turning the flag into a refusal
    here would buy nothing and break every wrapper that passes it uniformly.
    """
    catalog, data = _cli_workspace(tmp_path, monkeypatch)

    code = main(["--catalog", str(catalog), "link", "example", str(data), "--dry-run"])

    assert code == 0
    assert (tmp_path / "cache" / "example").is_symlink()


def test_cli_reports_a_refusal_without_a_traceback(tmp_path, monkeypatch, capsys):
    catalog, _ = _cli_workspace(tmp_path, monkeypatch)

    code = main(
        ["--catalog", str(catalog), "link", "example", str(tmp_path / "nowhere")]
    )

    assert code == 2
    assert "error: not a directory" in capsys.readouterr().err
