"""One settings file per account, or the one ``ETHOS_DATA_CONFIG`` names, read once.

Characterisation tests for [Set up your machine] and [Use data in a script]:
where the settings come from, what the files of an earlier release mean now,
and the snapshot a handle keeps for the rest of a script.
"""

from __future__ import annotations

import json
from pathlib import Path

import platformdirs
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
            ["config", "set-restricted-cache", str(tmp_path / "account-restricted")]
        )
        named = write(
            tmp_path / "named.yaml", public_cache=str(tmp_path / "named-cache")
        )
        monkeypatch.setenv("ETHOS_DATA_CONFIG", str(named))

        settings = ethos_data.read_settings()

        assert (settings.file, settings.file_source) == (named, "$ETHOS_DATA_CONFIG")
        assert settings.roots.public == tmp_path / "named-cache"
        assert settings.roots.restricted is None, "nothing is merged from the account"

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
        assert config.resolve_public_cache().value == tmp_path / "cache"

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
        run_cli(["config", "set-restricted-cache", str(tmp_path / "restricted")])
        monkeypatch.delenv("ETHOS_DATA_CONFIG")

        assert not config.account_config_path().exists()
        assert config.resolve_restricted_cache() is None

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
        assert config.resolve_publication_url("https://catalogue.example")[0] == (
            "https://door.example"
        )

        assert run_cli(["config", "unset-publication-url"])[0] == 0
        assert config.resolve_publication_url("https://catalogue.example") == (
            "https://catalogue.example",
            "catalogue",
        )


class TestFilesOfEarlierReleases:
    def test_none_of_them_is_read_and_config_show_names_each(
        self, _isolated_settings, tmp_path, monkeypatch
    ):
        home = _isolated_settings
        project = write(tmp_path / "work" / "ethos-data.yaml", public_cache="/project")
        environment = write(
            home / "env" / "etc" / "ethos-data" / "config.yaml", catalog="/environment"
        )
        site = write(home / "site-config" / "config.yaml", restricted_cache="/site")
        monkeypatch.chdir(project.parent)

        settings = ethos_data.read_settings()
        code, out, _ = run_cli(["config", "show"])

        assert settings.roots.public_source.startswith("built-in default")
        assert settings.catalog is None and settings.roots.restricted is None
        assert code == 0
        for path in (project, environment, site):
            line = next(line for line in out.splitlines() if str(path) in line)
            assert line.startswith("ignored") and "no longer read" in line


@pytest.fixture
def windows_locations(_isolated_settings, monkeypatch):
    """platformdirs as on Windows: the old paths repeat the application name."""
    home = _isolated_settings

    def located(kind: str):
        def where(app, appauthor=None, *args, **kwargs):
            old = "" if appauthor is False else "ethos-data/"
            return str(home / "LocalAppData" / "ethos-data" / old / kind)

        return where

    monkeypatch.setattr(platformdirs, "user_config_dir", located(""))
    monkeypatch.setattr(platformdirs, "user_cache_dir", located("Cache"))
    return home / "LocalAppData" / "ethos-data"


class TestWindowsLocations:
    def test_the_file_at_the_old_location_is_read_and_moved_by_the_first_setter(
        self, windows_locations, tmp_path
    ):
        old = write(
            windows_locations / "ethos-data" / "config.yaml",
            restricted_cache=str(tmp_path / "restricted"),
        )
        new = windows_locations / "config.yaml"

        with pytest.warns(UserWarning, match="move the file to"):
            assert config.resolve_restricted_cache().value == tmp_path / "restricted"

        run_cli(["config", "set-public-cache", str(tmp_path / "public")])

        moved = yaml.safe_load(new.read_text(encoding="utf-8"))
        assert moved == {
            "public_cache": str(tmp_path / "public"),
            "restricted_cache": str(tmp_path / "restricted"),
        }
        assert old.is_file(), "the old file is left for the person to delete"

    def test_the_old_default_cache_is_used_until_the_new_one_exists(
        self, windows_locations
    ):
        old = windows_locations / "ethos-data" / "Cache"
        old.mkdir(parents=True)

        found = config.resolve_public_cache()

        assert found.value == old
        assert f"move it to {windows_locations / 'Cache'}" in found.source

        (windows_locations / "Cache").mkdir()
        assert config.resolve_public_cache().value == windows_locations / "Cache"


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
        reader.write(version="v2026.10.1")
        return collections

    def test_it_names_the_file_the_catalogue_and_the_caches(self, wind, reader):
        settings = ethos_data.collections(wind).settings

        report = str(settings)
        assert settings.catalog == str(reader.index)
        assert settings.catalog_source == "the pin in collections.yaml"
        assert "catalogue version  v2026.10.1" in report
        assert f"public cache       {reader.cache}  ($ETHOS_DATA_DIR)" in report
        assert "restricted cache   not set" in report
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
        assert handle.settings.catalog_version == "v2026.10.1"

    def test_an_explicit_root_is_reported_as_one(self, wind, tmp_path):
        settings = ethos_data.collections(wind, root=tmp_path / "mine").settings

        assert settings.roots.public == tmp_path / "mine"
        assert settings.roots.public_source == "explicit argument"

    def test_it_is_plain_data_for_a_results_file(self, wind, reader):
        recorded = json.loads(
            json.dumps(ethos_data.collections(wind).settings.as_dict())
        )

        assert recorded["catalog"]["version"] == "v2026.10.1"
        assert recorded["public_cache"] == {
            "path": str(reader.cache),
            "source": "$ETHOS_DATA_DIR",
        }
        assert recorded["restricted_cache"] is None
