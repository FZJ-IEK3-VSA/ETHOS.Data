"""The rules ``catalog build`` enforces, and what ``--check`` compares.

Characterisation tests for [Add a dataset] and the classification rules of
[File formats]: the access and visibility pairs the build refuses, the keys
restricted data may not carry, and the staleness check. Exit codes are only
asserted to be non-zero, and messages by their subject, so the tests keep
their meaning when library code stops exiting the process.
"""

from __future__ import annotations

import pytest

EMBARGO = {"until": "unspecified", "reason": "Not reviewed yet.", "becomes": "public"}


class TestClassification:
    def test_a_hidden_dataset_needs_an_embargo(self, source):
        source.dataset(
            "draft",
            {"a.csv": "1"},
            ethos_access="restricted",
            ethos_visibility="hidden",
        )
        code, _, err = source.build()
        assert code != 0
        assert "ethos:embargo" in err

    def test_public_data_cannot_be_hidden(self, source):
        source.dataset(
            "draft",
            {"a.csv": "1"},
            ethos_access="public",
            ethos_visibility="hidden",
            ethos_embargo=EMBARGO,
        )
        code, _, err = source.build()
        assert code != 0
        assert "access=public with visibility=hidden" in err

    @pytest.mark.parametrize(
        "key, value", [("ethos_access", "secret"), ("ethos_visibility", "listed")]
    )
    def test_an_unknown_class_is_refused(self, source, key, value):
        source.dataset("draft", {"a.csv": "1"}, **{key: value})
        code, _, err = source.build()
        assert code != 0
        assert repr(value) in err

    def test_restricted_data_declares_no_remote_prefix(self, source):
        source.dataset(
            "licensed",
            {"a.csv": "1"},
            ethos_access="restricted",
            ethos_visibility="hidden",
            ethos_embargo=EMBARGO,
            ethos_remote_prefix="licensed",
        )
        code, _, err = source.build()
        assert code != 0
        assert "ethos:remote_prefix" in err

    def test_restricted_data_is_frozen_rather_than_marked_uploaded(self, source):
        source.dataset(
            "licensed",
            {"a.csv": "1"},
            ethos_access="restricted",
            ethos_visibility="hidden",
            ethos_embargo=EMBARGO,
        )
        assert source.build()[0] == 0
        source.edit("licensed", ethos_uploaded=True, source_dir=None)
        code, _, err = source.build()
        assert code != 0
        assert "ethos:frozen" in err


class TestStaleness:
    def test_check_reports_changed_source_bytes_and_writes_nothing(self, source):
        directory = source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        before = (directory / "datapackage.json").read_bytes()
        (source.bytes / "flat" / "a.csv").write_bytes(b"12345")

        code, _, err = source.build(check=True)

        assert code == 1
        assert "datasets/flat/datapackage.json" in err.replace("\\", "/")
        assert (directory / "datapackage.json").read_bytes() == before

    def test_a_fresh_build_checks_clean(self, source):
        source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        code, out, _ = source.build(check=True)
        assert code == 0
        assert "up to date" in out

    def test_building_one_dataset_leaves_the_others_alone(self, source):
        source.dataset("one", {"a.csv": "1"})
        source.dataset("two", {"b.csv": "2"})
        assert source.build()[0] == 0
        source.edit("one", title="Renamed one")
        source.edit("two", title="Renamed two")

        assert source.build("one")[0] == 0

        assert source.package("one")["title"] == "Renamed one"
        assert source.package("two")["title"] == "The two dataset"
        titles = {row["name"]: row["title"] for row in source.index()["datasets"]}
        assert titles == {"one": "Renamed one", "two": "The two dataset"}

    def test_an_empty_catalogue_builds_and_checks(self, source):
        assert source.build()[0] == 0
        assert source.index()["datasets"] == []
        assert source.build(check=True)[0] == 0

    def test_an_uploaded_dataset_keeps_its_inventory_without_its_source(self, source):
        source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        inventory = source.package("flat")["resources"]
        source.edit("flat", ethos_uploaded=True, source_dir=None)
        (source.bytes / "flat" / "a.csv").unlink()

        assert source.build()[0] == 0

        assert source.package("flat")["resources"] == inventory


class TestWarnings:
    def test_an_unknown_ethos_key_is_named_and_the_build_goes_on(self, source):
        source.dataset("flat", {"a.csv": "1"}, ethos_acess="restricted")

        code, _, err = source.build()

        assert code == 0
        assert (
            "warning: flat: ethos:acess is not a key of the dataset.yaml format" in err
        )

    def test_an_empty_descriptor_is_refused_with_its_reason(self, source):
        directory = source.directory("empty")
        directory.mkdir(parents=True)
        (directory / "dataset.yaml").write_bytes(b"")

        code, _, err = source.build()

        assert code == 1
        assert "empty: source_dir is required" in err
