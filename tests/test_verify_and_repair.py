"""Checking files against the catalogue, and repairing downloads.

Characterisation tests for [Check and repair the cache]: each finding the
guide's table lists, what ``--deep`` adds, what ``--repair`` re-fetches and
what it never touches. Run through a package's command, as the guide does.
"""

from __future__ import annotations

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

        with pytest.warns(UserWarning, match="staging"):
            code = verify(wind, "--deep")

        out = capsys.readouterr().out
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
        monkeypatch.setenv("ETHOS_RESTRICTED_DIR", str(restricted))

        assert verify(collections, "--deep", "--repair") == 1

        assert "restricted: never downloaded" in capsys.readouterr().out
        assert (restricted / "wind" / "u.nc").read_bytes() == b"uu"
        assert store.downloads() == []

    def test_staged_data_is_left_alone(
        self, wind, reader, store, tmp_path, monkeypatch
    ):
        """A staging entry replaces the dataset's description, so nothing official is
        compared or fetched while it is there, damaged cache copy or not."""
        staging = tmp_path / "staging"
        (staging / "wind").mkdir(parents=True)
        (staging / "wind" / "u.nc").write_bytes(b"u")
        monkeypatch.setenv("ETHOS_STAGING_DIR", str(staging))
        (reader.cache / "wind" / "u.nc").write_bytes(b"uu")

        with pytest.warns(UserWarning, match="staging"):
            code = verify(wind, "--deep", "--repair")

        assert code == 0
        assert (staging / "wind" / "u.nc").read_bytes() == b"u"
        assert (reader.cache / "wind" / "u.nc").read_bytes() == b"uu"
        assert store.downloads() == []
