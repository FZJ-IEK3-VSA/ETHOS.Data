"""Unresolved licensing stops distribution, not development.

An absent licence is a question, not a permission. The two operations that hand
a dataset to other people -- putting it in a shared cache, and publishing it to
dCache -- refuse until somebody has answered it. Staging does not: a staged
dataset is one person's, on one machine, and is unverifiable by construction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from ethos_data.catalogs import Catalog, Dataset, Resource, license_settled
from ethos_data.config import Roots
from ethos_data.linking import LinkError, link
from ethos_data.maintain import namespace
from ethos_data.maintain.manifest import render_dataset, write_dataset
from ethos_data.maintain.upload import preflight

PAYLOAD = b"first file"
RESOLVED = {"licenses": [{"name": "CC-BY-4.0"}]}


class TestTheRule:
    """What counts as settled, asked of a plain descriptor."""

    def test_a_named_licence_settles_it(self):
        assert license_settled({"licenses": [{"name": "CC-BY-4.0"}]})

    def test_so_does_an_explicit_resolved(self):
        assert license_settled({"ethos:license_status": "resolved"})

    @pytest.mark.parametrize(
        "meta",
        [
            {},  # nobody has looked
            {"licenses": []},  # an empty list says nothing
            {"ethos:license_status": "unresolved"},  # somebody looked and could not say
            {"ethos:license_status": "unknown"},
        ],
    )
    def test_everything_else_is_unanswered(self, meta):
        assert not license_settled(meta)


def _catalog(status: str | None) -> Catalog:
    entry = {"ethos:access": "public"}
    if status is not None:
        entry["ethos:license_status"] = status
    resource = Resource(
        "example",
        "a",
        "a.txt",
        len(PAYLOAD),
        "sha256:" + hashlib.sha256(PAYLOAD).hexdigest(),
        "text/plain",
    )
    dataset = Dataset(
        "example",
        "Example",
        entry=entry,
        _descriptor={"resources": []},
        _resources={"a.txt": resource},
    )
    return Catalog("local", {}, {"example": dataset})


@pytest.fixture
def workspace(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.txt").write_bytes(PAYLOAD)
    return cache, data, Roots(public=cache)


@pytest.mark.parametrize("status", [None, "unresolved", "unknown"])
def test_link_refuses_a_dataset_nobody_has_licensed(workspace, status):
    cache, data, roots = workspace
    with pytest.raises(LinkError, match="unresolved licensing"):
        link(_catalog(status), "example", data, roots)
    assert not (cache / "example").exists()


def test_link_says_to_stage_it_instead(workspace):
    _, data, roots = workspace
    with pytest.raises(LinkError, match="staging add"):
        link(_catalog("unresolved"), "example", data, roots)


def test_link_allows_a_settled_licence(workspace):
    cache, data, roots = workspace
    link(_catalog("resolved"), "example", data, roots)
    assert (cache / "example").is_symlink()


def _checkout(root: Path, extra: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "catalog.yaml").write_text("name: t\nethos:catalog_role: source\n")
    source = root / "src"
    source.mkdir(parents=True)
    (source / "a.txt").write_bytes(PAYLOAD)
    dataset_dir = root / "datasets" / "example"
    dataset_dir.mkdir(parents=True)
    meta = {
        "name": "example",
        "title": "Example",
        "source_dir": str(source),
        "ethos:remote_prefix": "example",
        **extra,
    }
    (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))
    write_dataset(dataset_dir, render_dataset(dataset_dir))
    return root


def test_link_all_skips_it_rather_than_linking_it(tmp_path):
    """Catalogue mode -- ``ethos-data link --all`` -- asked of its planner.

    The planner is where the refusal has to live rather than in the command that
    calls it: by the time an entry has been written, a dataset nobody licensed
    is already sitting in a directory everybody on the machine reads, and
    removing it afterwards does not unsee it. Skipping is also the right shape
    for a namespace: the one unanswered dataset is left out and the rest of the
    cache is still built.
    """
    checkout = _checkout(tmp_path / "catalogue", {"ethos:license_status": "unresolved"})
    cache = tmp_path / "cache"

    actions = namespace.plan(checkout, cache, authority=namespace.PUBLIC_CACHE)

    assert [(a.verb, a.dataset) for a in actions] == [("skip", "example")]
    assert "unresolved licensing" in actions[0].detail
    namespace.apply([a for a in actions if a.changes_anything])
    assert not (cache / "example").exists()


def test_link_all_links_it_once_the_terms_are_recorded(tmp_path):
    """The gate is a question, so answering it in dataset.yaml has to open it.

    Worth asserting alongside the refusal: a check nobody can satisfy is not a
    gate, it is a wall, and the next person to meet it works around it instead
    of recording the terms.
    """
    checkout = _checkout(tmp_path / "catalogue", RESOLVED)
    cache = tmp_path / "cache"

    actions = namespace.plan(checkout, cache, authority=namespace.PUBLIC_CACHE)

    assert [(a.verb, a.dataset) for a in actions] == [("link", "example")]


def _withdraw_the_licence(checkout: Path) -> None:
    """Take the recorded terms back out of a checkout's dataset.yaml.

    Both edits are needed, and the reason is the rule itself: a ``licenses``
    entry settles the question on its own, so a status of ``unresolved`` left
    beside a named licence would still read as settled and this would be a test
    of nothing.
    """
    descriptor = checkout / "datasets" / "example" / "dataset.yaml"
    meta = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    meta.pop("licenses", None)
    meta["ethos:license_status"] = "unresolved"
    descriptor.write_text(yaml.safe_dump(meta))


def test_link_all_retracts_the_link_when_the_terms_are_withdrawn(tmp_path, capsys):
    """The gate has to close behind a namespace that was built while it was open.

    Terms are recorded by hand and can be taken back by hand -- somebody looked
    again, and what dataset.yaml claimed turned out not to be settled after all.
    By then this cache is holding a live link that this same planner made, so
    the answer that is right for a dataset the cache has never seen is the
    dangerous one here: reporting ``skip`` left the link in place, returned 0,
    and the shared namespace went on handing the bytes to everybody reading it
    with nothing in the output or the exit code to say so.

    Removing a link discards nothing -- the data behind it is asserted still
    readable afterwards -- which is what makes retracting the safe answer and
    leaving it the unsafe one. It still takes ``--prune``, because that is the
    only flag here that deletes anything, so the run without it says the cache
    is wrong and the run with it puts it right.

    The ``authority`` these tests pass describes the shape they set up and
    nothing more. A restricted dataset is retracted only where the run can say
    the directory is this installation's own public cache -- see
    ``test_link_command.py`` -- but an unrecorded licence is retracted in any of
    them, because there is no namespace in which nobody having read the terms is
    acceptable, so every assertion below holds whichever answer is given.
    """
    checkout = _checkout(tmp_path / "catalogue", RESOLVED)
    cache = tmp_path / "cache"
    assert namespace.run(checkout, cache, authority=namespace.PUBLIC_CACHE) == 0
    entry = cache / "example"
    assert entry.is_symlink()

    _withdraw_the_licence(checkout)

    assert namespace.run(checkout, cache, authority=namespace.PUBLIC_CACHE) == 1
    reported = capsys.readouterr().out
    assert "exposed" in reported and "unresolved licensing" in reported
    assert entry.is_symlink()

    assert (
        namespace.run(checkout, cache, prune=True, authority=namespace.PUBLIC_CACHE)
        == 0
    )
    assert "retract" in capsys.readouterr().out
    assert not entry.is_symlink() and not entry.exists()
    assert (checkout / "src" / "a.txt").read_bytes() == PAYLOAD


def _package(extra: dict) -> dict:
    return {
        "name": "example",
        "ethos:access": "public",
        "ethos:remote_prefix": "example",
        **extra,
    }


def test_upload_refuses_it(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    with pytest.raises(SystemExit, match="unresolved licensing"):
        preflight(
            "example",
            _package({"ethos:license_status": "unresolved"}),
            source,
            allow_internal=False,
            verify_only=False,
        )


def test_upload_refuses_a_descriptor_that_says_nothing_at_all(tmp_path):
    """The default has to be "nobody has looked", not "nothing applies"."""
    source = tmp_path / "src"
    source.mkdir()
    with pytest.raises(SystemExit, match="unresolved licensing"):
        preflight(
            "example", _package({}), source, allow_internal=False, verify_only=False
        )


def test_verify_only_still_works(tmp_path):
    """Rechecking what is already published copies nothing."""
    source = tmp_path / "src"
    source.mkdir()
    assert (
        preflight(
            "example",
            _package({"ethos:license_status": "unresolved"}),
            source,
            allow_internal=False,
            verify_only=True,
        )
        == "example"
    )


def test_upload_allows_a_settled_licence(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    assert (
        preflight(
            "example",
            _package(RESOLVED),
            source,
            allow_internal=False,
            verify_only=False,
        )
        == "example"
    )


def test_staging_is_not_gated(tmp_path, monkeypatch):
    """The escape hatch the refusals point at has to actually be open."""
    from ethos_data import staging

    monkeypatch.setenv("ETHOS_STAGING_DIR", str(tmp_path / "staging"))
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.txt").write_bytes(PAYLOAD)

    staged = staging.add("example", data, note="terms not settled yet")

    assert staged.entry.is_symlink()
    assert staged.files == 1


def test_the_whole_command_line_refuses(tmp_path, monkeypatch, capsys):
    from ethos_data.cli import main

    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "cache"))
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
                        "ethos:license_status": "unresolved",
                    }
                ]
            }
        )
    )
    data = tmp_path / "data"
    data.mkdir()

    code = main(["--catalog", str(catalog), "link", "example", str(data)])

    assert code == 2
    assert "unresolved licensing" in capsys.readouterr().err
    assert not (tmp_path / "cache" / "example").exists()
