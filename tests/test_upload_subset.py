"""Uploading a subset of the catalogue -- several datasets, or one, in one run.

`catalog upload` takes a list because publishing a subset is the normal case: a
catalogue holds a dozen datasets and a release usually touches two of them. The
shell loop it replaces is not equivalent, and that is the whole point of the
tests below -- a loop checks each dataset only as it reaches it, so it happily
uploads 70 GB and *then* discovers that the next name was restricted, or a typo.

Run with pytest, or directly:  python tests/test_upload_subset.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from ethos_data.adapters.fakes import FakeStore
from ethos_data.errors import UploadError
from ethos_data.maintain import upload
from ethos_data.maintain.manifest import render_dataset, write_dataset
from ethos_data.maintain.manifest import run as build_run

CATALOG = (
    "name: t\n"
    "ethos:catalog_role: source\n"
    "ethos:publication_url: https://example.invalid/ice2-data-files\n"
)


def make_catalog(root: Path, datasets: dict[str, dict]) -> Path:
    """A source catalogue with built manifests, ready to upload from."""
    (root / "catalog.yaml").write_text(CATALOG)
    for name, extra in datasets.items():
        source = root / "src" / name
        source.mkdir(parents=True)
        (source / "a.txt").write_bytes(b"hello")

        dataset_dir = root / "datasets" / name
        dataset_dir.mkdir(parents=True)
        # A licence, because upload refuses a dataset whose terms nobody has
        # read. These tests are about *which* datasets a subset selects, so they
        # declare one; the licensing tests override it through `extra`.
        meta = {
            "name": name,
            "title": name,
            "source_dir": str(source),
            "ethos:remote_prefix": name,
            "licenses": [{"name": "CC-BY-4.0"}],
        }
        meta.update(extra)
        # The catalogue refuses to build a restricted dataset that declares a
        # remote prefix -- it is never uploaded, so it has nowhere to be.
        if meta.get("ethos:access") == "restricted":
            del meta["ethos:remote_prefix"]
        (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))
        write_dataset(dataset_dir, render_dataset(dataset_dir))
    return root


def make_args(
    datasets: list[str], **overrides
) -> tuple[list[str], upload.UploadOptions]:
    """The datasets and the options ``upload.run`` takes; a dry run by default."""
    return datasets, upload.UploadOptions(**{"dry_run": True, **overrides})


@pytest.fixture
def workspace():
    path = Path(tempfile.mkdtemp())
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def store(monkeypatch):
    """The publication store every upload in the test gets: a fake that records."""
    fake = FakeStore()
    monkeypatch.setattr(upload, "DcacheStore", lambda remote: fake)
    return fake


@pytest.fixture
def no_rclone(store):
    """The destination of every copy the store was asked for, in order."""
    return store.copies


def destinations(copies: list[dict]) -> list[str]:
    return [copy["destination"] for copy in copies]


class TestNamingDatasets:
    def test_a_bare_name_is_taken_as_written(self, workspace):
        assert (
            upload.resolve_name(workspace, "global-wind-atlas-v4")
            == "global-wind-atlas-v4"
        )

    def test_a_path_into_the_catalogue_resolves_to_its_name(self, workspace):
        make_catalog(workspace, {"gwa": {}})
        path = workspace / "datasets" / "gwa"
        assert upload.resolve_name(workspace, str(path)) == "gwa"

    def test_a_path_into_the_published_catalogue_is_refused_by_name(self, workspace):
        # The easy mistake: same datasets/<name> layout, no bytes behind it.
        make_catalog(workspace, {"gwa": {}})
        published = workspace / "public"
        (published / "datasets" / "gwa").mkdir(parents=True)
        (published / "datacatalog.json").write_text(
            '{"ethos:catalog_role": "published"}'
        )

        with pytest.raises(UploadError, match="published catalogue"):
            upload.resolve_name(workspace, str(published / "datasets" / "gwa"))

    def test_a_path_somewhere_else_entirely_names_both_directories(self, workspace):
        make_catalog(workspace, {"gwa": {}})
        stray = workspace / "elsewhere" / "datasets" / "gwa"
        stray.mkdir(parents=True)
        with pytest.raises(UploadError, match="not a dataset of the catalogue"):
            upload.resolve_name(workspace, str(stray))


class TestSubsetIsCheckedBeforeAnythingUploads:
    def test_a_restricted_dataset_stops_the_run_before_its_neighbour_uploads(
        self, workspace, no_rclone
    ):
        # The failure a shell loop cannot prevent: `a` is fine, `b` may never be
        # published, and a loop would already have uploaded `a` before finding out.
        make_catalog(workspace, {"a": {}, "b": {"ethos:access": "restricted"}})

        with pytest.raises(UploadError, match="restricted"):
            upload.run(workspace, *make_args(["a", "b"]))
        assert no_rclone == [], "nothing may be uploaded once any dataset is ineligible"

    def test_a_mistyped_name_stops_the_run_the_same_way(self, workspace, no_rclone):
        make_catalog(workspace, {"a": {}})
        with pytest.raises(UploadError, match="no dataset called 'typo'"):
            upload.run(workspace, *make_args(["a", "typo"]))
        assert no_rclone == []


class TestUploadingTheSubset:
    def test_each_named_dataset_gets_its_own_rclone_call(self, workspace, no_rclone):
        make_catalog(workspace, {"a": {}, "b": {}})
        assert upload.run(workspace, *make_args(["a", "b"])).ok

        found = destinations(no_rclone)
        assert found == ["ice2-data-files/a", "ice2-data-files/b"]

    def test_the_order_asked_for_is_the_order_uploaded(self, workspace, no_rclone):
        make_catalog(workspace, {"a": {}, "b": {}})
        upload.run(workspace, *make_args(["b", "a"]))
        assert destinations(no_rclone) == [
            "ice2-data-files/b",
            "ice2-data-files/a",
        ]

    def test_naming_a_dataset_twice_costs_one_upload(self, workspace, no_rclone):
        make_catalog(workspace, {"a": {}})
        upload.run(workspace, *make_args(["a", "a", str(workspace / "datasets" / "a")]))
        assert len(no_rclone) == 1

    def test_a_path_and_a_name_may_be_mixed_in_one_run(self, workspace, no_rclone):
        make_catalog(workspace, {"a": {}, "b": {}})
        upload.run(workspace, *make_args([str(workspace / "datasets" / "a"), "b"]))
        assert destinations(no_rclone) == [
            "ice2-data-files/a",
            "ice2-data-files/b",
        ]

    def test_the_result_names_each_failure_with_rclones_status(self, workspace, store):
        make_catalog(workspace, {"a": {}})
        store.copy_status = 7
        (why,) = upload.run(workspace, *make_args(["a"])).failed.values()
        assert "rclone exited 7" in why

    def test_a_failure_is_reported_per_dataset_and_fails_the_run(
        self, workspace, store
    ):
        make_catalog(workspace, {"a": {}, "b": {}})
        store.copy_status = 7
        result = upload.run(workspace, *make_args(["a", "b"]))
        assert not result.ok
        assert sorted(result.failed) == ["a", "b"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


def make_family(root: Path, members: dict[str, dict]) -> Path:
    """A source catalogue with one family ``fam`` and the given members, built."""
    (root / "catalog.yaml").write_text(CATALOG)
    family = root / "datasets" / "fam"
    family.mkdir(parents=True)
    # A namespace names the family and describes no files of its own.
    (family / "dataset.yaml").write_text(
        "title: the family" + chr(10) + "description: members only" + chr(10)
    )
    for member, extra in members.items():
        source = root / "src" / "fam" / member
        source.mkdir(parents=True)
        (source / "a.txt").write_bytes(b"hello")
        meta = {
            "title": member,
            "source_dir": str(source),
            "ethos:remote_prefix": f"fam/{member}",
            "licenses": [{"name": "CC-BY-4.0"}],
        }
        meta.update(extra)
        if meta.get("ethos:access") == "restricted":
            del meta["ethos:remote_prefix"]
        (family / member).mkdir()
        (family / member / "dataset.yaml").write_text(yaml.safe_dump(meta))
    assert build_run(root, []).ok
    return root


class TestNamingAFamily:
    def test_the_family_name_uploads_each_member_once_in_name_order(
        self, workspace, no_rclone
    ):
        make_family(workspace, {"b": {}, "a": {}})
        assert upload.run(workspace, *make_args(["fam"])).ok
        found = destinations(no_rclone)
        assert found == [
            "ice2-data-files/fam/a",
            "ice2-data-files/fam/b",
        ]

    def test_a_family_and_one_of_its_members_still_cost_one_upload_each(
        self, workspace, no_rclone
    ):
        make_family(workspace, {"a": {}, "b": {}})
        upload.run(workspace, *make_args(["fam/b", "fam"]))
        assert destinations(no_rclone) == [
            "ice2-data-files/fam/b",
            "ice2-data-files/fam/a",
        ]

    def test_an_ineligible_member_stops_the_whole_family(self, workspace, no_rclone):
        make_family(workspace, {"a": {}, "b": {"ethos:access": "restricted"}})
        with pytest.raises(UploadError, match="restricted"):
            upload.run(workspace, *make_args(["fam"]))
        assert no_rclone == []
