"""Checking files against the catalogue, and repairing downloads.

Characterisation tests for [Check and repair the cache]: each finding the
guide's table lists, what ``--deep`` adds, what ``--repair`` re-fetches and
what it never touches. Run through a package's command, as the guide does.
"""

from __future__ import annotations

import os

import pytest

import ethos_data

WIND = """
    wind:
      title: Wind inputs
      include:
        - dataset: wind
"""


def verify(collections, *args: str) -> int:
    return ethos_data.tool_main(
        collections, tool="faketool", argv=["verify", "wind", *args]
    )


@pytest.fixture
def wind(reader):
    """Two files, in the cache and on the store; returns the collections file."""
    reader.dataset("wind", {"u.nc": "uuuu", "v.nc": "vvvv"}, where="both")
    return reader.collections(WIND)


class TestFindings:
    def test_files_that_match_are_ok(self, wind, capsys):
        assert verify(wind, "--deep") == 0
        assert "2 file(s) match the catalogue." in capsys.readouterr().out

    def test_a_file_of_the_wrong_size_is_found_by_the_cheap_check(
        self, wind, reader, capsys
    ):
        (reader.cache / "wind" / "u.nc").write_bytes(b"uu")

        assert verify(wind) == 1
        out = capsys.readouterr().out
        assert "wrong size: 1" in out
        assert "faketool-data verify wind --repair" in out

    def test_changed_bytes_of_the_same_size_need_the_deep_check(
        self, wind, reader, capsys
    ):
        (reader.cache / "wind" / "u.nc").write_bytes(b"uuuX")

        assert verify(wind) == 0, "sizes alone cannot see this"
        capsys.readouterr()
        assert verify(wind, "--deep") == 1
        assert "wrong checksum: 1" in capsys.readouterr().out

    def test_a_missing_file_is_reported_as_missing(self, wind, reader, capsys):
        (reader.cache / "wind" / "u.nc").unlink()

        assert verify(wind) == 1
        assert "missing: 1" in capsys.readouterr().out

    def test_a_link_whose_target_moved_is_dangling(self, reader, tmp_path, capsys):
        reader.dataset("wind", {"u.nc": "uuuu"}, where="store")
        collections = reader.collections(WIND)
        reader.cache.mkdir(parents=True, exist_ok=True)
        (reader.cache / "wind").symlink_to(tmp_path / "gone", target_is_directory=True)

        assert verify(collections) == 1
        assert "dangling: 1" in capsys.readouterr().out

    def test_staged_data_cannot_be_checked_and_says_so(
        self, wind, tmp_path, monkeypatch, capsys
    ):
        staging = tmp_path / "staging"
        (staging / "wind").mkdir(parents=True)
        (staging / "wind" / "u.nc").write_bytes(b"new!")
        monkeypatch.setenv("ETHOS_STAGING_DIR", str(staging))

        code = verify(wind, "--deep")

        captured = capsys.readouterr()
        out = captured.out
        assert "read from the staging root" in captured.err
        assert code == 0, "nothing is wrong; nothing could be compared"
        assert "unverifiable: 1" in out
        assert "could NOT be checked" in out

    def test_a_catalogue_record_without_sha256_fails_the_deep_check(
        self, wind, reader, store, capsys
    ):
        package = reader.root / "datasets" / "wind" / "datapackage.json"
        package.write_text(
            package.read_text("utf-8").replace('"sha256:', '"md5:', 1), "utf-8"
        )

        assert verify(wind) == 0, "sizes still match"
        capsys.readouterr()
        assert verify(wind, "--deep") == 1
        out = capsys.readouterr().out
        assert "unverifiable: 1" in out
        assert "the catalogue records no SHA-256" in out
        assert "--repair" not in out, "a download cannot fix the record"

        assert verify(wind, "--deep", "--repair") == 1
        assert "no download can be checked" in capsys.readouterr().out
        assert store.downloads() == []

    def test_unsettled_licensing_is_warned_about_as_a_fetch_does(self, reader):
        reader.dataset(
            "wind", {"u.nc": "uuuu"}, where="cache", license_status="unresolved"
        )
        catalog = ethos_data.catalog(str(reader.write()))

        with pytest.warns(UserWarning, match="'wind' has unresolved licensing"):
            ethos_data.verify(catalog, catalog.resources("wind"))

    def test_the_api_reports_the_same_findings(self, wind, reader):
        (reader.cache / "wind" / "v.nc").write_bytes(b"v")
        catalog = ethos_data.catalog(str(reader.index))

        findings = ethos_data.verify(catalog, catalog.resources("wind"), deep=True)

        assert {f.resource.key: (f.status, f.ok) for f in findings} == {
            "wind/u.nc": ("ok", True),
            "wind/v.nc": ("wrong size", False),
        }


class TestRepair:
    def test_a_damaged_download_is_fetched_again(self, wind, reader, store, capsys):
        (reader.cache / "wind" / "u.nc").write_bytes(b"uu")

        assert verify(wind, "--deep", "--repair") == 0

        assert (reader.cache / "wind" / "u.nc").read_bytes() == b"uuuu"
        assert store.downloads() == ["/wind/u.nc"]
        assert "re-fetched 1 file(s)." in capsys.readouterr().out
        assert verify(wind, "--deep") == 0

    def test_changed_bytes_of_the_same_size_are_fetched_again(
        self, wind, reader, store, capsys
    ):
        """A fetch takes this copy as it is; the deep check is what finds it."""
        (reader.cache / "wind" / "u.nc").write_bytes(b"uuuX")

        assert verify(wind, "--deep", "--repair") == 0

        assert (reader.cache / "wind" / "u.nc").read_bytes() == b"uuuu"
        assert store.downloads() == ["/wind/u.nc"]
        assert "re-fetched 1 file(s)." in capsys.readouterr().out

    def test_a_dry_run_says_what_it_would_fetch_and_changes_nothing(
        self, wind, reader, store, capsys
    ):
        (reader.cache / "wind" / "u.nc").write_bytes(b"uu")

        assert verify(wind, "--deep", "--repair", "--dry-run") == 1

        assert (
            "would re-fetch 1 file(s). Nothing was changed." in capsys.readouterr().out
        )
        assert (reader.cache / "wind" / "u.nc").read_bytes() == b"uu"
        assert store.downloads() == []

    def test_restricted_data_is_never_repaired(
        self, reader, store, tmp_path, monkeypatch, capsys
    ):
        reader.dataset("wind", {"u.nc": "uuuu"}, access="restricted", where="store")
        collections = reader.collections(WIND)
        restricted = tmp_path / "restricted"
        (restricted / "wind").mkdir(parents=True)
        (restricted / "wind" / "u.nc").write_bytes(b"uu")
        monkeypatch.setenv("ETHOS_RESTRICTED_DIRS", str(restricted))

        assert verify(collections, "--deep", "--repair") == 1

        assert "restricted: never downloaded" in capsys.readouterr().out
        assert (restricted / "wind" / "u.nc").read_bytes() == b"uu"
        assert store.downloads() == []

    def test_a_link_is_never_removed_or_replaced(self, reader, store, tmp_path, capsys):
        """On the cluster every user reads the public cache; a link is the maintainers'."""
        reader.dataset("wind", {"u.nc": "uuuu"}, where="store")
        collections = reader.collections(WIND)
        linked = tmp_path / "project" / "wind"
        linked.mkdir(parents=True)
        (linked / "u.nc").write_bytes(b"uu")
        reader.cache.mkdir(parents=True, exist_ok=True)
        (reader.cache / "wind").symlink_to(linked, target_is_directory=True)

        assert verify(collections, "--deep", "--repair") == 1

        assert "repair never changes a link" in capsys.readouterr().out
        assert (reader.cache / "wind").is_symlink()
        assert (linked / "u.nc").read_bytes() == b"uu"
        assert store.downloads() == []

    def test_a_broken_link_is_reported_naming_the_cache_and_left_alone(
        self, reader, store, tmp_path, capsys
    ):
        reader.dataset("wind", {"u.nc": "uuuu"}, where="store")
        collections = reader.collections(WIND)
        reader.cache.mkdir(parents=True, exist_ok=True)
        (reader.cache / "wind").symlink_to(tmp_path / "gone", target_is_directory=True)

        assert verify(collections, "--repair") == 1

        out = capsys.readouterr().out
        assert f"in the public cache {reader.cache}" in out
        assert "a broken link: repair never changes a link" in out
        assert (reader.cache / "wind").is_symlink()
        assert store.downloads() == []


class TestNotesOnTheRestrictedCaches:
    """What verify says about a cache rather than about the file it read."""

    def test_an_entry_passed_over_in_an_earlier_cache_is_noted(
        self, reader, tmp_path, monkeypatch, capsys
    ):
        reader.dataset("wind", {"u.nc": "uuuu"}, access="restricted", where="nowhere")
        collections = reader.collections(WIND)
        first, second = tmp_path / "group-a", tmp_path / "group-b"
        first.mkdir()
        (first / "wind").symlink_to(tmp_path / "moved", target_is_directory=True)
        (second / "wind").mkdir(parents=True)
        (second / "wind" / "u.nc").write_bytes(b"uuuu")
        monkeypatch.setenv(
            "ETHOS_RESTRICTED_DIRS", os.pathsep.join([str(first), str(second)])
        )

        assert verify(collections, "--deep") == 0, "a note is not a failure"

        out = capsys.readouterr().out
        assert "note: 1" in out
        assert f"The entry in {first} is dangling" in out
        assert "1 file(s) match the catalogue." in out

    def test_a_public_datasets_entry_in_a_restricted_cache_is_noted(
        self, wind, reader, tmp_path, monkeypatch, capsys
    ):
        restricted = tmp_path / "restricted"
        (restricted / "wind").mkdir(parents=True)
        monkeypatch.setenv("ETHOS_RESTRICTED_DIRS", str(restricted))

        assert verify(wind) == 0

        out = capsys.readouterr().out
        assert "but the dataset is public" in out
        assert f"ethos-data --root {restricted} unlink wind" in out

    def test_staged_data_is_left_alone(
        self, wind, reader, store, tmp_path, monkeypatch, capsys
    ):
        """A staging entry replaces the dataset's description, so nothing official is
        compared or fetched while it is there, damaged cache copy or not."""
        staging = tmp_path / "staging"
        (staging / "wind").mkdir(parents=True)
        (staging / "wind" / "u.nc").write_bytes(b"u")
        monkeypatch.setenv("ETHOS_STAGING_DIR", str(staging))
        (reader.cache / "wind" / "u.nc").write_bytes(b"uu")

        code = verify(wind, "--deep", "--repair")

        assert "read from the staging root" in capsys.readouterr().err
        assert code == 0
        assert (staging / "wind" / "u.nc").read_bytes() == b"u"
        assert (reader.cache / "wind" / "u.nc").read_bytes() == b"uu"
        assert store.downloads() == []
