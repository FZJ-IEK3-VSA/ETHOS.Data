"""One settings file per account, or the one ``ETHOS_DATA_CONFIG`` names, read once.

Characterisation tests for [Set up your machine] and [Use data in a script]:
where the settings come from, what the settings file may hold, and the
snapshot a handle or a command keeps.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from support import run_cli

import ethos_data
from ethos_data import config


def write(path: Path, **values) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(yaml.safe_dump(values).encode("utf-8"))
    return path


class TestOneFile:
    def test_a_named_file_replaces_the_file_in_the_account(self, tmp_path, monkeypatch):
        run_cli(["config", "set-public-cache", str(tmp_path / "account-cache")])
        run_cli(
            ["config", "add-restricted-cache", str(tmp_path / "account-restricted")]
        )
        named = write(
            tmp_path / "named.yaml", public_cache=str(tmp_path / "named-cache")
        )
        monkeypatch.setenv("ETHOS_DATA_CONFIG", str(named))

        settings = ethos_data.read_settings()

        assert (settings.file, settings.file_source) == (named, "$ETHOS_DATA_CONFIG")
        assert settings.roots.public == tmp_path / "named-cache"
        assert settings.roots.restricted == (), "nothing is merged from the account"

    def test_a_named_file_that_is_missing_stops_every_command_but_a_setter(
        self, tmp_path, monkeypatch
    ):
        named = tmp_path / "ci" / "settings.yaml"
        monkeypatch.setenv("ETHOS_DATA_CONFIG", str(named))

        for argv in (["config", "show"], ["config", "unset-public-cache"], ["ls"]):
            code, _, err = run_cli(argv)
            assert code == 2, argv
            assert str(named) in err and "does not exist" in err, argv

        code, _, _ = run_cli(["config", "set-public-cache", str(tmp_path / "cache")])

        assert code == 0
        assert ethos_data.read_settings().roots.public == tmp_path / "cache"

    def test_unsetting_the_last_value_keeps_the_named_file(self, tmp_path, monkeypatch):
        named = write(tmp_path / "named.yaml", catalog=str(tmp_path / "index.json"))
        monkeypatch.setenv("ETHOS_DATA_CONFIG", str(named))

        code, out, _ = run_cli(["config", "unset-catalog"])

        assert code == 0
        assert f"removed from {named}" in out
        assert named.is_file()
        assert run_cli(["config", "show"])[0] == 0

    def test_a_setting_written_with_a_named_file_stays_out_of_the_account(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("ETHOS_DATA_CONFIG", str(tmp_path / "lesson.yaml"))
        run_cli(["config", "add-restricted-cache", str(tmp_path / "restricted")])
        monkeypatch.delenv("ETHOS_DATA_CONFIG")

        assert not config.account_config_path().exists()
        assert ethos_data.read_settings().roots.restricted == ()

    def test_the_setters_take_no_scope(self, tmp_path):
        code, _, err = run_cli(
            ["config", "set-public-cache", str(tmp_path), "--scope", "user"]
        )

        assert code == 2
        assert "unrecognized arguments: --scope" in err

    def test_the_publication_url_is_set_and_unset(self, monkeypatch):
        assert (
            run_cli(["config", "set-publication-url", "https://door.example"])[0] == 0
        )
        assert ethos_data.read_settings().publication_url == "https://door.example"

        assert run_cli(["config", "unset-publication-url"])[0] == 0
        assert ethos_data.read_settings().publication_url is None

    def test_a_file_that_breaks_its_specification_names_every_problem(
        self, tmp_path, monkeypatch
    ):
        named = write(
            tmp_path / "named.yaml",
            public_cache=["one", "two"],
            staging_cache={"not": "a path"},
        )
        monkeypatch.setenv("ETHOS_DATA_CONFIG", str(named))

        code, _, err = run_cli(["config", "show"])

        assert code == 2
        assert f"{named} is not a valid settings file" in err
        assert "public_cache:" in err and "staging_cache:" in err

    def test_its_keys_are_the_ones_the_formats_name(self):
        from ethos_data.formats import SettingsFile
        from ethos_data.formats import keys as k

        assert set(SettingsFile.model_fields) == {
            k.SETTING_CATALOG,
            k.SETTING_PUBLIC_CACHE,
            k.SETTING_RESTRICTED_CACHES,
            k.SETTING_STAGING_CACHE,
            k.SETTING_PUBLICATION_URL,
        }


WIND = """
    wind:
      include:
        - dataset: wind
"""


class TestTheSnapshotOfAHandle:
    @pytest.fixture
    def wind(self, reader):
        reader.dataset("wind", {"u.nc": "uuuu"}, where="store")
        collections = reader.collections(WIND)
        reader.write(version="v1.2.0")
        return collections

    def test_it_names_the_file_the_catalogue_and_the_caches(self, wind, reader):
        settings = ethos_data.collections(wind).settings

        report = str(settings)
        assert settings.catalog == str(reader.index)
        assert settings.catalog_source == "the pin in collections.yaml"
        assert "catalogue version  v1.2.0" in report
        assert f"public cache       {reader.cache}  ($ETHOS_DATA_DIR)" in report
        assert "restricted caches  none listed: public data only" in report
        assert report.startswith(f"settings file      {config.account_config_path()}")

    def test_it_is_read_once_so_later_changes_do_not_move_the_cache(
        self, wind, reader, tmp_path, monkeypatch
    ):
        data = ethos_data.collections(wind)
        monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "elsewhere"))

        files = data.fetch("wind", progressbar=False)

        assert files["wind/u.nc"] == reader.cache / "wind" / "u.nc"
        assert not (tmp_path / "elsewhere").exists()
        assert data.settings.roots.public == reader.cache

    def test_a_catalogue_handle_says_why_it_reads_that_catalogue(self, wind, reader):
        handle = ethos_data.catalog(str(reader.index))

        assert handle.settings.catalog_source == "explicit argument"
        assert handle.settings.catalog_version == "v1.2.0"

    def test_an_explicit_root_is_reported_as_one(self, wind, tmp_path):
        settings = ethos_data.collections(wind, root=tmp_path / "mine").settings

        assert settings.roots.public == tmp_path / "mine"
        assert settings.roots.public_source == "explicit argument"

    def test_a_package_command_keeps_its_catalogue_and_root_in_one_snapshot(
        self, wind, reader, tmp_path
    ):
        mine = tmp_path / "mine"
        argv = ["--catalog", str(reader.index), "--root", str(mine), "fetch", "wind"]

        code = ethos_data.tool_main(wind, tool="faketool", argv=argv)

        assert code == 0
        assert (mine / "wind" / "u.nc").read_bytes() == b"uuuu"
        assert not (reader.cache / "wind").exists()

    def test_it_is_plain_data_for_a_results_file(self, wind, reader):
        recorded = json.loads(
            json.dumps(ethos_data.collections(wind).settings.as_dict())
        )

        assert recorded["catalog"]["version"] == "v1.2.0"
        assert recorded["public_cache"] == {
            "path": str(reader.cache),
            "source": "$ETHOS_DATA_DIR",
        }
        assert recorded["restricted_caches"] == []
