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
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from ethos_data.access import ORIGIN_LINK, locate
from ethos_data.catalogs import Catalog, Dataset, Resource, UnknownDataset
from ethos_data.cli import main
from ethos_data.config import Roots
from ethos_data.linking import LinkError, link, unlink

CONTENT = {"a.txt": b"first file", "sub/b.txt": b"second file"}

#: Linking into a cache needs terms somebody has read; see test_license_gate.py.
LICENCE = "licenses:\n  - name: CC-BY-4.0\n"


def _catalog(access: str = "public") -> Catalog:
    resources = {
        path: Resource(
            "example",
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
        "example",
        "Example",
        entry={"ethos:access": access, "ethos:license_status": "resolved"},
        _descriptor={"resources": []},
        _resources=resources,
    )
    return Catalog("local", {}, {"example": dataset})


def _write(directory):
    for path, payload in CONTENT.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
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
    """
    root = tmp_path / "catalogue"
    (root / "datasets").mkdir(parents=True)
    (root / "catalog.yaml").write_text("name: test\ntitle: Test\n")
    for name, body in datasets.items():
        directory = root / "datasets" / name
        directory.mkdir()
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
