"""Every file this package writes is UTF-8 with LF, on every platform.

The case these exist for: a catalogue is a git repository, built on Linux and
read from Windows through the same share, so a descriptor's bytes must not
depend on who ran the build.

``Path.read_text`` and ``Path.write_text`` do not give that. They use the
*locale* encoding, which on a German Windows is cp1252:

  * reading a UTF-8 descriptor there turns "Jülich" into "JÃ¼lich" without
    raising anything -- the catalogue is not corrupted, but every attribution
    and licence statement read out of it is
  * writing one raises UnicodeEncodeError for any character cp1252 cannot
    spell, so a dataset whose contributor has a Polish or Chinese name simply
    fails to build
  * ``write_text`` also rewrites every "\\n" as "\\r\\n", so a catalogue built
    on Windows differs from the same catalogue built on Linux in every line of
    every file

These tests write their fixtures as explicit UTF-8 bytes, exactly as the real
catalogue is stored, rather than through ``write_text`` -- which on Windows
would encode the fixture with the locale codec and quietly test nothing.

Run with pytest, or directly:  python tests/test_portable_files.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ethos_data import cli, config
from ethos_data.maintain.manifest import render_dataset, write_dataset
from ethos_data.maintain.manifest import run as build_run
from ethos_data.maintain.publish import render

CATALOG = (
    "name: t\n"
    "ethos:catalog_role: source\n"
    "ethos:publication_url: https://example.invalid/store\n"
)

#: Three ways a name can leave the ASCII range, chosen for what each one breaks.
#: "ü" and "—" exist in cp1252, so they survive a mis-encoded write and come back
#: as mojibake -- the silent half of the bug. "气候" does not exist in cp1252 at
#: all, so it turns the same write into a crash. A real catalogue holds both
#: kinds: German institute names, and upstream datasets named by their authors.
UMLAUT = "Forschungszentrum Jülich — ICE-2"
CJK = "气候数据"


def write_utf8(path: Path, text: str) -> None:
    """Write a fixture the way the catalogue really stores it."""
    path.write_bytes(text.encode("utf-8"))


def build_catalog(root: Path) -> Path:
    """A one-dataset catalogue whose metadata is not ASCII."""
    source = root / "src"
    source.mkdir(parents=True)
    write_utf8(source / "a.txt", "hello")

    dataset_dir = root / "datasets" / "d"
    dataset_dir.mkdir(parents=True)
    write_utf8(root / "catalog.yaml", CATALOG)
    write_utf8(
        dataset_dir / "dataset.yaml",
        f"name: d\ntitle: {CJK}\ndescription: {UMLAUT}\n"
        f"source_dir: {source}\nethos:remote_prefix: d\n"
        f"ethos:attribution: {UMLAUT}\n",
    )
    return root


@pytest.fixture
def catalog(tmp_path):
    return build_catalog(tmp_path / "cat")


class TestBuildingADescriptor:
    def test_non_ascii_metadata_survives_the_round_trip(self, catalog):
        """The silent failure: cp1252 would give back "JÃ¼lich" and raise nothing."""
        write_dataset(
            catalog / "datasets" / "d", render_dataset(catalog / "datasets" / "d")
        )

        raw = (catalog / "datasets" / "d" / "datapackage.json").read_bytes()
        package = json.loads(raw.decode("utf-8"))
        assert package["title"] == CJK
        assert package["description"] == UMLAUT
        assert package["ethos:attribution"] == UMLAUT

    def test_a_descriptor_is_written_with_lf_only(self, catalog):
        # Not cosmetic: a CRLF descriptor is a diff in every line of the file the
        # next time somebody on Linux rebuilds the same dataset.
        write_dataset(
            catalog / "datasets" / "d", render_dataset(catalog / "datasets" / "d")
        )
        raw = (catalog / "datasets" / "d" / "datapackage.json").read_bytes()
        assert b"\r" not in raw

    def test_the_catalogue_index_is_utf8_and_lf(self, catalog):
        assert build_run(catalog, []) == 0
        raw = (catalog / "datacatalog.json").read_bytes()
        assert b"\r" not in raw
        assert CJK in json.loads(raw.decode("utf-8"))["datasets"][0]["title"]

    def test_a_freshly_built_catalogue_reports_itself_up_to_date(self, catalog):
        """--check re-reads what build wrote. Mis-encode either half and it drifts."""
        assert build_run(catalog, []) == 0
        assert build_run(catalog, [], check=True) == 0


class TestPublishing:
    def test_the_public_tree_is_utf8_and_lf(self, catalog, tmp_path):
        from ethos_data.maintain.publish import run as publish_run

        assert build_run(catalog, []) == 0
        destination = tmp_path / "public"
        destination.mkdir()
        assert publish_run(catalog, str(destination)) == 0

        for path in sorted(destination.rglob("*")):
            if not path.is_file() or path.suffix == ".pdf":
                continue
            raw = path.read_bytes()
            assert b"\r" not in raw, f"{path.name} was written with CRLF"
            raw.decode("utf-8")  # raises if it is not UTF-8

        # The generated README says "Jülich" in its own text, so it is the file
        # that would have crashed a cp1252 write outright.
        readme = (destination / "README.md").read_bytes().decode("utf-8")
        assert "Jülich" in readme
        assert CJK in readme

    def test_render_keys_are_posix_paths(self, catalog):
        """The published tree is addressed with forward slashes on every platform."""
        assert build_run(catalog, []) == 0
        assert "datasets/d/datapackage.json" in {p.as_posix() for p in render(catalog)}


class TestCommandLineOutput:
    def test_a_non_ascii_title_survives_a_redirected_run(self, catalog, tmp_path):
        """`ethos-data list > file` on Windows, which is not `ethos-data list`.

        Redirected, sys.stdout falls back to the locale encoding, and printing a
        collection titled in Chinese raised UnicodeEncodeError -- while the very
        same command printed fine on screen, because a Windows console uses its
        own UTF-16 API. Run as a real subprocess, because that difference only
        exists for a process that owns its streams.
        """
        assert build_run(catalog, []) == 0
        collections = tmp_path / "collections.yaml"
        write_utf8(
            collections,
            f"catalog: {catalog / 'datacatalog.json'}\n"
            f"collections:\n  one:\n    title: {CJK}\n"
            f"    include:\n      - dataset: d\n",
        )

        destination = tmp_path / "listing.txt"
        # A configured catalogue override beats the file's pin, so pin it explicitly.
        env = {
            **os.environ,
            "PYTHONPATH": str(Path(config.__file__).parent.parent),
            "ETHOS_DATA_CATALOG": str(catalog / "datacatalog.json"),
        }
        with open(destination, "wb") as redirected:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ethos_data.cli",
                    "-c",
                    str(collections),
                    "list",
                ],
                stdout=redirected,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
        assert CJK in destination.read_bytes().decode("utf-8")

    def test_reconfiguring_output_is_safe_when_streams_are_captured(self):
        """pytest replaces sys.stdout; the CLI must not care what it got."""
        cli._use_utf8_output()


class TestConfiguration:
    def test_a_non_ascii_cache_path_can_be_written_and_read_back(
        self, tmp_path, monkeypatch
    ):
        """A Windows user called Jürgen has a home directory with a "ü" in it."""
        written = tmp_path / "config.yaml"
        monkeypatch.setattr(
            config, "writable_config_path", lambda scope="user": written
        )

        value = str(tmp_path / f"caches-{UMLAUT}")
        config.set_option(config.PUBLIC_CACHE_KEY, value)

        raw = written.read_bytes()
        assert b"\r" not in raw
        assert yaml.safe_load(raw.decode("utf-8"))[config.PUBLIC_CACHE_KEY] == value


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
