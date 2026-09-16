"""``materialize --from``: filling a cache entry from bytes already on the machine.

The point of the flag is speed -- uploading a dataset and downloading it back is
a slow way to put files where they already are -- so the tests that matter are
the ones proving it buys speed and nothing else: the copy is still checked
against the manifest, and it still refuses to write over data the cache owns.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from ethos_data.catalogs import Catalog, Dataset, Resource
from ethos_data.cli import main
from ethos_data.config import Roots
from ethos_data.materialize import PROVENANCE_FILE, materialize, plan_materialize

CONTENT = {"a.txt": b"first file", "sub/b.txt": b"second file"}


def _resource(path: str, payload: bytes) -> Resource:
    return Resource(
        "example",
        path.replace("/", "-"),
        path,
        len(payload),
        "sha256:" + hashlib.sha256(payload).hexdigest(),
        "text/plain",
    )


def _catalog(access: str = "public") -> Catalog:
    resources = {path: _resource(path, payload) for path, payload in CONTENT.items()}
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


def _write(directory, content=CONTENT):
    for path, payload in content.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return directory


@pytest.fixture
def workspace(tmp_path):
    """A cache root, and a directory holding the dataset's files elsewhere."""
    cache = tmp_path / "cache"
    cache.mkdir()
    return cache, _write(tmp_path / "elsewhere"), Roots(public=cache)


def test_fills_an_entry_that_does_not_exist(workspace):
    cache, source, roots = workspace
    reports = materialize(_catalog(), ["example"], roots, source=source)

    assert [r.action for r in reports] == ["materialized"]
    entry = cache / "example"
    assert entry.is_dir() and not entry.is_symlink()
    assert (entry / "a.txt").read_bytes() == CONTENT["a.txt"]
    assert (entry / "sub/b.txt").read_bytes() == CONTENT["sub/b.txt"]


def test_the_original_is_left_exactly_as_it_was(workspace, tmp_path):
    """The transition outlasts the copy, so nothing here may touch the source.

    Old code still reads the original path, and nobody can say in advance when it
    can go. Both forms are checked: copying from a link's target, and copying from
    a directory named with --from.
    """
    cache, source, roots = workspace
    linked = _write(tmp_path / "linked")
    (cache / "example").symlink_to(linked, target_is_directory=True)

    materialize(_catalog(), ["example"], roots)

    assert linked.is_dir()
    assert sorted(p.name for p in linked.rglob("*") if p.is_file()) == [
        "a.txt",
        "b.txt",
    ]
    assert (linked / "a.txt").read_bytes() == CONTENT["a.txt"]

    (cache / "example").rename(cache / "done")  # clear the entry for the second form
    materialize(_catalog(), ["example"], roots, source=source)

    assert source.is_dir()
    assert (source / "a.txt").read_bytes() == CONTENT["a.txt"]


def test_records_that_no_link_was_replaced(workspace):
    cache, source, roots = workspace
    materialize(_catalog(), ["example"], roots, source=source)

    provenance = json.loads((cache / "example" / PROVENANCE_FILE).read_text())
    assert provenance["materialized_from"] == str(source)
    # Not the entry path: nothing was ever linked there, and saying otherwise
    # would send the next person looking for a link that never existed.
    assert provenance["was_a_link_at"] is None
    assert provenance["verified"] is True


def test_copies_from_the_given_directory_not_the_link_target(workspace, tmp_path):
    cache, source, roots = workspace
    stale = _write(tmp_path / "stale", {"a.txt": b"outdated", "sub/b.txt": b"outdated"})
    (cache / "example").symlink_to(stale, target_is_directory=True)

    reports = materialize(_catalog(), ["example"], roots, source=source)

    # The link target's bytes do not match the manifest, so a copy that verifies
    # can only have come from --from.
    assert [r.action for r in reports] == ["materialized"]
    assert (cache / "example" / "a.txt").read_bytes() == CONTENT["a.txt"]
    provenance = json.loads((cache / "example" / PROVENANCE_FILE).read_text())
    assert provenance["was_a_link_at"] == str(cache / "example")


def test_a_dangling_link_is_no_longer_a_dead_end(workspace, tmp_path):
    cache, source, roots = workspace
    (cache / "example").symlink_to(tmp_path / "gone", target_is_directory=True)

    assert plan_materialize(_catalog(), ["example"], roots)[0].action == "dangling"
    reports = materialize(_catalog(), ["example"], roots, source=source)
    assert [r.action for r in reports] == ["materialized"]
    assert (cache / "example" / "a.txt").read_bytes() == CONTENT["a.txt"]


def test_the_copy_is_still_checked_against_the_manifest(workspace, tmp_path):
    cache, _, roots = workspace
    wrong = _write(
        tmp_path / "wrong", {"a.txt": b"not it", "sub/b.txt": CONTENT["sub/b.txt"]}
    )

    reports = materialize(_catalog(), ["example"], roots, source=wrong)

    assert [r.action for r in reports] == ["failed"]
    assert "a.txt" in reports[0].failures[0]
    # Nothing half-copied is left behind for the next reader to trip over.
    assert not (cache / "example").exists()
    assert not list(cache.glob("example.materializing.*"))


def test_a_failed_copy_leaves_an_existing_link_alone(workspace, tmp_path):
    cache, _, roots = workspace
    original = _write(tmp_path / "original")
    (cache / "example").symlink_to(original, target_is_directory=True)
    wrong = _write(tmp_path / "wrong", {"a.txt": b"not it", "sub/b.txt": b"not it"})

    reports = materialize(_catalog(), ["example"], roots, source=wrong)

    assert [r.action for r in reports] == ["failed"]
    assert (cache / "example").is_symlink()
    # resolve() rather than readlink(): Windows records the link with a \\?\
    # extended-length prefix, which is the same directory spelled differently.
    assert (cache / "example").resolve() == original.resolve()


def test_refuses_to_write_over_a_directory_the_cache_owns(workspace):
    cache, source, roots = workspace
    owned = cache / "example"
    owned.mkdir()
    (owned / "a.txt").write_bytes(b"downloaded earlier")

    reports = materialize(_catalog(), ["example"], roots, source=source)

    assert [r.action for r in reports] == ["already real"]
    assert (owned / "a.txt").read_bytes() == b"downloaded earlier"


def test_a_source_that_is_not_a_directory_is_reported(workspace, tmp_path):
    cache, _, roots = workspace
    not_a_directory = tmp_path / "file.txt"
    not_a_directory.write_text("x")

    reports = materialize(_catalog(), ["example"], roots, source=not_a_directory)

    assert [r.action for r in reports] == ["cannot"]
    assert not (cache / "example").exists()


def test_dry_run_writes_nothing(workspace):
    cache, source, roots = workspace
    reports = materialize(_catalog(), ["example"], roots, source=source, dry_run=True)

    assert [r.action for r in reports] == ["would copy"]
    assert reports[0].bytes == sum(len(payload) for payload in CONTENT.values())
    assert not (cache / "example").exists()


def test_restricted_data_is_copied_into_the_restricted_root(workspace, tmp_path):
    cache, source, _ = workspace
    restricted = tmp_path / "restricted"
    roots = Roots(public=cache, restricted=restricted)

    reports = materialize(_catalog("restricted"), ["example"], roots, source=source)

    assert [r.action for r in reports] == ["materialized"]
    assert (restricted / "example" / "a.txt").read_bytes() == CONTENT["a.txt"]
    assert not (cache / "example").exists()


@pytest.mark.parametrize(
    "arguments",
    [
        ["materialize", "--all", "--from", "DIR"],
        ["materialize", "one", "two", "--from", "DIR"],
        ["materialize", "--from", "DIR"],
    ],
)
def test_cli_requires_exactly_one_dataset(tmp_path, monkeypatch, capsys, arguments):
    """One directory holds one dataset: spreading it over several names, or over
    whatever --all finds, could only copy the same bytes into the wrong entries."""
    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "cache"))
    catalog = tmp_path / "datacatalog.json"
    catalog.write_text(json.dumps({"datasets": []}))
    source = _write(tmp_path / "elsewhere")

    code = main(
        [
            "--catalog",
            str(catalog),
            *[str(source) if a == "DIR" else a for a in arguments],
        ]
    )

    assert code == 2
    assert "--from copies one named dataset" in capsys.readouterr().err
    assert not (tmp_path / "cache" / "example").exists()
