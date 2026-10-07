"""The self-test, ``--meta``, ``ethos-data verify <key>`` and staging's dataset.yaml.

Characterisation tests for [Set up your machine] (the self-test), [Use data in
a script] (``--meta``), [Check and repair the cache] (verifying by key) and
[Stage development data] (the ``dataset.yaml`` that ``staging add`` writes).
"""

from __future__ import annotations

from pathlib import Path

import pooch
import pytest
import yaml
from support import drop_from_rows, run_cli

import ethos_data
from ethos_data import staging

ROOT = Path(__file__).resolve().parents[1]

#: The files the shipped collections file names, by dataset.
EXAMPLE = {
    "reskit-test-data/gebco": {"water_depth_northsea.tif": "depth"},
    "reskit-test-data/dist2coast": {"coast_distance_northsea.tif": "distance"},
    "reskit-test-data/placements": {
        "turbine_placements.csv": "x,y\n",
        "turbinePlacements.shp": "shape",
        "turbinePlacements.dbf": "table",
    },
}


@pytest.fixture
def example(reader):
    """The datasets of the shipped collections file, on the local store."""
    reader.namespace("reskit-test-data")
    for name, files in EXAMPLE.items():
        sidecars = (
            {"turbinePlacements.shp": ["turbinePlacements.dbf"]}
            if name.endswith("placements")
            else None
        )
        reader.dataset(name, files, where="store", sidecars=sidecars)
    return reader.write(version="v-test")


class TestSelfTest:
    def test_it_downloads_checks_and_passes(self, example, tmp_path):
        code, out, _ = run_cli(
            ["--catalog", str(example), "--root", str(tmp_path / "fresh"), "selftest"]
        )

        assert code == 0
        assert (
            out.index("1. settings") < out.index("2. catalogue") < out.index("3. files")
        )
        assert "   version v-test" in out
        downloaded = [line for line in out.splitlines() if "downloaded" in line]
        assert len(downloaded) == 5, "four files and the shapefile's sidecar"
        assert out.rstrip().endswith("selftest passed")

    def test_files_already_here_are_reported_as_such(self, example, tmp_path):
        argv = [
            "--catalog",
            str(example),
            "--root",
            str(tmp_path / "fresh"),
            "selftest",
        ]
        assert run_cli(argv)[0] == 0

        code, out, _ = run_cli(argv)

        assert code == 0
        assert "downloaded" not in out
        assert out.count("already present") == 5

    def test_an_unreachable_catalogue_fails_the_second_step(self, tmp_path):
        code, out, err = run_cli(
            ["--catalog", "https://example.invalid/datacatalog.json", "selftest"]
        )

        assert code == 1
        assert "2. catalogue" in out and "3. files" not in out
        assert "selftest FAILED at catalogue" in err

    def test_an_index_another_version_wrote_fails_the_second_step(
        self, example, tmp_path
    ):
        drop_from_rows(example, "ethos:remote_prefix")

        code, out, err = run_cli(
            ["--catalog", str(example), "--root", str(tmp_path / "fresh"), "selftest"]
        )

        assert code == 1
        assert "3. files" not in out
        assert "selftest FAILED at catalogue" in err
        assert "lacks ethos:remote_prefix" in out + err

    def test_a_file_that_does_not_match_fails_the_third_step(
        self, example, store, tmp_path, monkeypatch
    ):
        # pooch sleeps between its retries; a refused download need not wait.
        monkeypatch.setattr(pooch.core.time, "sleep", lambda seconds: None)
        store.put("reskit-test-data/gebco", "water_depth_northsea.tif", "DEPTH")

        code, _, err = run_cli(
            ["--catalog", str(example), "--root", str(tmp_path / "fresh"), "selftest"]
        )

        assert code == 1
        assert "selftest FAILED at files" in err

    def test_a_missing_settings_file_fails_the_first_step(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ETHOS_DATA_CONFIG", str(tmp_path / "missing.yaml"))

        result = ethos_data.run_selftest()

        assert result.failed == "settings"
        assert "does not exist" in result.error

    @pytest.mark.repository
    def test_the_documentation_uses_the_file_that_ships(self):
        shipped = ethos_data.EXAMPLE_COLLECTIONS.read_bytes()
        documented = (
            ROOT / "docs" / "assets" / "examples" / "collections.yaml"
        ).read_bytes()

        assert shipped == documented


class TestVerifyAKey:
    @pytest.fixture
    def flat(self, reader):
        reader.dataset("flat", {"a.csv": "1\n", "b.csv": "22\n"}, where="both")
        return reader.write()

    def test_matching_files_pass(self, flat):
        code, out, _ = run_cli(["--catalog", str(flat), "verify", "flat", "--deep"])

        assert code == 0
        assert "2 file(s) match the catalogue." in out

    def test_a_changed_file_is_found_and_the_repair_named(self, flat, reader):
        (reader.cache / "flat" / "a.csv").write_bytes(b"9\n")

        code, out, _ = run_cli(
            ["--catalog", str(flat), "verify", "flat/a.csv", "--deep"]
        )

        assert code == 1
        assert "wrong checksum: 1" in out
        assert "ethos-data verify flat/a.csv --repair --deep" in out

    def test_repair_re_fetches_it(self, flat, reader):
        (reader.cache / "flat" / "a.csv").write_bytes(b"9\n")

        code, _, _ = run_cli(
            ["--catalog", str(flat), "verify", "flat", "--deep", "--repair"]
        )

        assert code == 0
        assert (reader.cache / "flat" / "a.csv").read_bytes() == b"1\n"


DESCRIBED = {
    "title": "GEBCO water depth",
    "version": "2023",
    "ethos:origin": "downloaded",
    "licenses": [{"name": "CC0-1.0"}],
    "ethos:contact": "maintainers",
}


class TestMeta:
    def test_ls_prints_the_description_of_a_dataset(self, reader, store):
        reader.dataset("gebco", {"d.tif": "d"}, where="store", descriptor=DESCRIBED)

        code, out, _ = run_cli(
            ["--catalog", str(reader.write()), "ls", "gebco", "--meta"]
        )

        assert code == 0
        for line in (
            "gebco",
            "  GEBCO water depth  (version 2023)",
            "  access   public",
            "  origin   downloaded",
            "  licence  CC0-1.0",
            "  contact  maintainers",
        ):
            assert line in out.splitlines(), line
        assert store.downloads() == []

    def test_show_prints_every_dataset_a_collection_selects(self, reader, store):
        reader.dataset("gebco", {"d.tif": "d"}, where="store", descriptor=DESCRIBED)
        reader.dataset("other", {"o.csv": "o"}, where="store")
        collections = reader.collections(
            """
    both:
      include:
        - dataset: gebco
        - dataset: other
"""
        )

        code = ethos_data.tool_main(
            collections, tool="faketool", argv=["show", "both", "--meta"]
        )

        assert code == 0
        assert store.downloads() == []

    def test_the_description_covers_every_user_facing_key(self):
        """The format marks the keys --meta prints; each one is printed."""
        from ethos_data.formats import dataset as dataset_format
        from ethos_data.formats.derived import reader_description

        described = {
            "title": "GADM administrative areas",
            "version": "3.6",
            "description": "Boundaries of every country and its subdivisions.",
            "homepage": "https://gadm.org",
            "sources": [{"title": "GADM download", "path": "https://gadm.org/x"}],
            "licenses": [{"name": "GADM-licence", "path": "https://gadm.org/l"}],
            "ethos:access": "restricted",
            "ethos:attribution": "GADM, version 3.6.",
            "ethos:restriction": "Licensed for academic use.",
            "ethos:upstream": {"status": "available", "note": "4.1 is current."},
            "ethos:contact": "data-custodian@example.org",
        }
        printed = "\n".join(reader_description(described))

        for key in dataset_format.USER_FACING:
            value = described[key]
            if isinstance(value, list):
                value = value[0].get("title") or value[0]["name"]
            elif isinstance(value, dict):
                value = value["status"]
            assert str(value) in printed, key


class TestStagingWritesADescription:
    @pytest.fixture
    def work(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ETHOS_STAGING_DIR", str(tmp_path / "staging"))
        directory = tmp_path / "work"
        directory.mkdir()
        (directory / "new.nc").write_bytes(b"new")
        return directory

    def test_add_writes_the_minimal_descriptor_with_the_note(self, work):
        staged = staging.add("candidate", work, note="candidate: for review # soon")

        written = yaml.safe_load((work / "dataset.yaml").read_text(encoding="utf-8"))
        assert written == {
            "name": "candidate",
            "source_dir": ".",
            "description": "candidate: for review # soon",
        }
        assert staged.descriptor == work / "dataset.yaml"
        assert staged.files == 1, "the description is not one of the dataset's files"

    def test_a_copy_is_described_and_its_source_only_read(self, work):
        staged = staging.add("candidate", work, note="for review", copy=True)

        assert [path.name for path in work.iterdir()] == ["new.nc"]
        assert staged.descriptor == staged.entry / "dataset.yaml"
        written = yaml.safe_load(staged.descriptor.read_text(encoding="utf-8"))
        assert written["description"] == "for review"
        assert staged.files == 1, "the description is not one of the dataset's files"

    def test_an_existing_descriptor_is_left_alone(self, work):
        (work / "dataset.yaml").write_bytes(b"name: mine\n")

        staged = staging.add("candidate", work, copy=True)

        assert staged.descriptor is None
        assert (work / "dataset.yaml").read_bytes() == b"name: mine\n"
        assert (staged.entry / "dataset.yaml").read_bytes() == b"name: mine\n"
