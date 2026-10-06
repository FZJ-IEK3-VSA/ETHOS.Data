"""Revisions and successors: new versions of a dataset, under the same keys or new ones.

Tests for the decision "Revisions and successors". A revision keeps a
dataset's keys and publishes only its changed and new files, under
``<remote_prefix>@<revision>/``; a reader keeps it in its own cache entry,
``<dataset>@<revision>/``, and takes unchanged files from the entry before. A
successor is a new dataset whose description names the one it replaces.
"""

from __future__ import annotations

import json
import warnings

import pytest
from support import SourceCatalogue, run_cli

import ethos_data
from ethos_data.adapters.fakes import FakeGit, FakeStore
from ethos_data.catalogs import load_catalog
from ethos_data.config import Roots
from ethos_data.maintain import manifest, release, remove, revision, upload
from ethos_data.selection import load_collections


@pytest.fixture
def published(tmp_path, store, monkeypatch):
    """flat: two files, uploaded, verified and frozen, with dCache a fake on the store."""
    catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
    catalogue.dataset("flat", {"a.csv": "1\n", "b.csv": "22\n"})
    assert catalogue.build()[0] == 0
    dcache = FakeStore(put=store.put, remove=store.remove)
    monkeypatch.setattr(upload, "DcacheStore", lambda remote, frontend: dcache)
    assert catalogue.catalog("upload", "flat")[0] == 0
    assert catalogue.catalog("record", "flat")[0] == 0
    return catalogue, dcache


@pytest.fixture
def corrected(tmp_path):
    """The corrected files: a.csv unchanged, b.csv changed, c.csv new."""
    directory = tmp_path / "corrected"
    directory.mkdir()
    (directory / "a.csv").write_bytes(b"1\n")
    (directory / "b.csv").write_bytes(b"23\n")
    (directory / "c.csv").write_bytes(b"333\n")
    return directory


def revise(catalogue, directory, *flags):
    return catalogue.catalog(
        "build", "flat", "--revision", "--from", str(directory), *flags
    )


def resources(catalogue):
    return {r["path"]: r for r in catalogue.package("flat")["resources"]}


class TestMakingARevision:
    def test_changed_and_new_files_get_the_new_revision(self, published, corrected):
        catalogue, _ = published

        code, out, err = revise(catalogue, corrected)

        assert code == 0, err
        recorded = resources(catalogue)
        assert "ethos:revision" not in recorded["a.csv"]
        assert recorded["b.csv"]["ethos:revision"] == 2
        assert recorded["c.csv"]["ethos:revision"] == 2
        assert catalogue.package("flat")["ethos:revision"] == 2
        row = next(r for r in catalogue.index()["datasets"] if r["name"] == "flat")
        assert row["ethos:revision"] == 2
        status = catalogue.status("flat")
        assert (status["state"], status["revision"]) == ("built", 2)
        assert status["source_dir"] == str(corrected)
        assert status["history"][-1]["note"] == "revision 2: 1 changed, 1 new, 0 gone"
        assert "changed      b.csv" in out and "new          c.csv" in out

    def test_its_new_bytes_go_to_their_own_folder_and_nothing_is_overwritten(
        self, published, corrected, store
    ):
        catalogue, dcache = published
        assert revise(catalogue, corrected)[0] == 0

        code, _, err = catalogue.catalog("upload", "flat")

        assert code == 0, err
        copies = {copy["destination"]: copy["paths"] for copy in dcache.copies[-2:]}
        assert copies == {
            "ethos-data/flat": ["a.csv"],
            "ethos-data/flat@2": ["b.csv", "c.csv"],
        }
        assert (store.root / "ethos-data/flat/b.csv").read_bytes() == b"22\n"
        assert (store.root / "ethos-data/flat@2/b.csv").read_bytes() == b"23\n"
        assert catalogue.status("flat")["state"] == "available"
        assert catalogue.catalog("record", "flat")[0] == 0
        assert catalogue.status("flat")["state"] == "frozen"

    def test_a_reader_keeps_the_revision_beside_the_one_before(
        self, published, corrected, store, tmp_path
    ):
        catalogue, _ = published
        cache = tmp_path / "cache"
        index = str(catalogue.root / "datacatalog.json")
        first = load_catalog(index)
        ethos_data.download(
            first, list(first.dataset("flat").resources.values()), Roots(public=cache)
        )
        assert revise(catalogue, corrected)[0] == 0
        assert catalogue.catalog("upload", "flat")[0] == 0
        store.requests.clear()

        second = load_catalog(index)
        files = ethos_data.download(
            second, list(second.dataset("flat").resources.values()), Roots(public=cache)
        )

        assert files["flat/b.csv"] == cache / "flat@2" / "b.csv"
        assert files["flat/b.csv"].read_bytes() == b"23\n"
        assert files["flat/a.csv"].read_bytes() == b"1\n"
        assert (cache / "flat" / "b.csv").read_bytes() == b"22\n", "the first stays"
        assert sorted(store.downloads()) == [
            "/ethos-data/flat@2/b.csv",
            "/ethos-data/flat@2/c.csv",
        ], "a.csv came from the entry before"

    def test_a_rebuild_within_the_revision_keeps_each_files_revision(
        self, published, corrected
    ):
        catalogue, _ = published
        assert revise(catalogue, corrected)[0] == 0
        (corrected / "b.csv").write_bytes(b"24\n")

        assert catalogue.build("flat")[0] == 0

        recorded = resources(catalogue)
        assert "ethos:revision" not in recorded["a.csv"]
        assert recorded["b.csv"]["ethos:revision"] == 2

    def test_a_dry_run_writes_nothing(self, published, corrected):
        catalogue, _ = published
        before = catalogue.package("flat")

        code, out, _ = revise(catalogue, corrected, "--dry-run")

        assert code == 0
        assert "write and record revision 2 of flat: 1 changed, 1 new, 0 gone" in out
        assert catalogue.package("flat") == before
        assert catalogue.status("flat")["state"] == "frozen"


class TestWhatARevisionIsNot:
    def test_files_that_go_are_refused_unless_meant(self, published, tmp_path):
        catalogue, _ = published
        fewer = tmp_path / "fewer"
        fewer.mkdir()
        (fewer / "a.csv").write_bytes(b"1\n")

        code, _, err = revise(catalogue, fewer)
        assert code == 1
        assert "leave out b.csv" in err and "ethos:supersedes: flat" in err

        code, _, err = revise(catalogue, fewer, "--remove-missing")
        assert code == 0, err
        assert list(resources(catalogue)) == ["a.csv"]

    def test_nothing_changed_is_no_revision(self, published, tmp_path):
        catalogue, _ = published
        same = tmp_path / "same"
        same.mkdir()
        (same / "a.csv").write_bytes(b"1\n")
        (same / "b.csv").write_bytes(b"22\n")

        code, _, err = revise(catalogue, same)

        assert code == 1
        assert "nothing to make a revision of" in err

    def test_a_dataset_never_published_is_rebuilt_instead(self, source, corrected):
        source.dataset("flat", {"a.csv": "1\n"})
        assert source.build()[0] == 0

        code, _, err = revise(source, corrected)

        assert code == 1
        assert "flat is built" in err and "needs it available or frozen" in err

    def test_a_dataset_that_is_only_linked_changes_in_place(
        self, source, corrected, tmp_path
    ):
        source.dataset("flat", {"a.csv": "1\n"})
        assert source.build()[0] == 0
        index = str(source.root / "datacatalog.json")
        code, _, err = run_cli(
            ["--catalog", index, "--root", str(tmp_path / "cache"), "link", "flat",
             "--catalog-root", str(source.root)]
        )  # fmt: skip
        assert code == 0, err

        code, _, err = revise(source, corrected)

        assert code == 1
        assert "only links to its source, so it has no revisions" in err

    def test_published_bytes_never_change_under_a_rebuild(
        self, tmp_path, store, monkeypatch
    ):
        catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
        catalogue.dataset("flat", {"a.csv": "1\n"})
        assert catalogue.build()[0] == 0
        monkeypatch.setattr(
            upload, "DcacheStore", lambda remote, frontend: FakeStore(put=store.put)
        )
        assert catalogue.catalog("upload", "flat")[0] == 0
        before = catalogue.package("flat")
        (catalogue.bytes / "flat" / "a.csv").write_bytes(b"2\n")

        code, _, err = catalogue.build()

        assert code == 1
        assert "published bytes never change" in err
        assert "ethos-data catalog build flat --revision" in err
        assert catalogue.package("flat") == before

    def test_purging_takes_every_revision_folder(self, published, corrected, tmp_path):
        catalogue, dcache = published
        assert revise(catalogue, corrected)[0] == 0
        assert catalogue.catalog("upload", "flat")[0] == 0
        assert catalogue.catalog("remove", "flat")[0] == 0
        public = tmp_path / "public"
        public.mkdir()
        release.run(
            catalogue.root,
            "v1.0.0",
            public,
            source_git=FakeGit(),
            public_git=FakeGit(),
        )

        remove.run(catalogue.root, ["flat"], purge=True, store=dcache)

        assert dcache.purges == ["ethos-data/flat", "ethos-data/flat@2"]

    def test_a_revision_has_no_authoritative_copy_yet(self, published, corrected):
        catalogue, _ = published
        assert catalogue.status("flat")["authority"]

        assert revise(catalogue, corrected)[0] == 0

        status = catalogue.status("flat")
        assert (status["state"], status.get("authority")) == ("built", None)

    def test_a_revision_interrupted_before_its_record_is_recorded_on_a_rerun(
        self, published, corrected
    ):
        catalogue, _ = published
        stopped = revision.Revision(catalogue.root, "flat", corrected)
        revision.Compare().plan(stopped)
        manifest.write_dataset(stopped.directory, stopped.files)

        code, out, err = revise(catalogue, corrected)

        assert code == 0, err
        assert "record revision 2 of flat: written before an interruption" in out
        assert catalogue.status("flat")["revision"] == 2

    def test_link_all_links_the_revision_and_keeps_the_one_before(
        self, published, corrected, tmp_path
    ):
        catalogue, _ = published
        cache = tmp_path / "public"
        (cache / "flat").parent.mkdir(parents=True)
        (cache / "flat").symlink_to(catalogue.bytes / "flat", target_is_directory=True)
        assert revise(catalogue, corrected)[0] == 0

        code, _, err = run_cli(
            ["link", "--all", "--prune", "--root", str(cache),
             "--catalog-root", str(catalogue.root)]
        )  # fmt: skip

        assert code == 0, err
        assert (cache / "flat@2").resolve() == corrected.resolve()
        assert (cache / "flat").is_symlink(), "an earlier release may name it"


class TestSuccessors:
    @pytest.fixture
    def succeeded(self, source):
        source.dataset("old", {"a.csv": "1\n"})
        source.dataset("new", {"x/a.csv": "1\n"}, ethos_supersedes="old")
        assert source.build()[0] == 0
        return source

    def test_the_build_says_who_replaces_whom(self, succeeded):
        rows = {row["name"]: row for row in succeeded.index()["datasets"]}

        assert rows["new"]["ethos:supersedes"] == "old"
        assert rows["old"]["ethos:superseded_by"] == ["new"]
        assert succeeded.package("old")["ethos:superseded_by"] == ["new"]
        assert succeeded.build(check=True)[0] == 0
        assert succeeded.catalog("status", "--check")[0] == 0

    def test_building_the_successor_alone_updates_the_one_it_replaces(self, source):
        source.dataset("old", {"a.csv": "1\n"})
        assert source.build()[0] == 0
        source.dataset("new", {"x/a.csv": "1\n"}, ethos_supersedes="old")

        assert source.build("new")[0] == 0

        assert source.package("old")["ethos:superseded_by"] == ["new"]

    def test_a_successor_of_nothing_is_refused(self, source):
        source.dataset("new", {"a.csv": "1\n"}, ethos_supersedes="never-was")

        code, _, err = source.build()

        assert code == 1
        assert "ethos:supersedes names 'never-was'" in err

    def test_a_reader_is_told(self, succeeded, tmp_path, monkeypatch):
        index = str(succeeded.root / "datacatalog.json")

        _, out, _ = run_cli(["--catalog", index, "ls"])
        assert "(superseded by new)" in out

        collections = tmp_path / "collections.yaml"
        collections.write_text(
            "collections:\n  inputs:\n    include:\n      - dataset: old\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("ETHOS_DATA_CATALOG", index)
        loaded = load_collections(collections)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            loaded.resolve("inputs")
        assert any("which new supersedes" in str(w.message) for w in caught)

    def test_the_successor_is_a_dataset_of_its_own(self, succeeded):
        catalog = load_catalog(str(succeeded.root / "datacatalog.json"))

        assert catalog.dataset("new").supersedes == "old"
        assert catalog.dataset("old").superseded_by == ["new"]
        assert (
            json.loads(
                (succeeded.directory("new") / "datapackage.json").read_text("utf-8")
            )["resources"][0]["path"]
            == "x/a.csv"
        )
