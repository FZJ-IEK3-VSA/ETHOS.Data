"""Filling and converting the shared cache: ``link --all`` and ``materialize``.

Characterisation tests for [Link existing data into the cache] and
[Materialize linked data]: what ``link --all`` reports when a source is
missing, that ``materialize`` copies the catalogued files and nothing else,
and that it refuses to fill the disk.
"""

from __future__ import annotations

import shutil
from collections import namedtuple

import pytest
from support import run_cli


class TestLinkAll:
    def test_a_missing_source_is_reported_and_the_rest_is_linked(
        self, source, tmp_path
    ):
        source.dataset("here", {"a.csv": "1"})
        source.dataset("gone", {"b.csv": "2"})
        assert source.build()[0] == 0
        shutil.rmtree(source.bytes / "gone")
        cache = tmp_path / "public"

        code, out, _ = run_cli(
            ["link", "--all", "--catalog-root", str(source.root), "--root", str(cache)]
        )

        assert code == 1
        assert f"namespace root: {cache}" in out
        assert f"catalogue:      {source.root}" in out
        assert any(line.split()[:2] == ["missing", "gone"] for line in out.splitlines())
        assert (cache / "here").is_symlink()
        assert not (cache / "gone").exists()

    def test_a_dry_run_writes_nothing(self, source, tmp_path):
        source.dataset("here", {"a.csv": "1"})
        assert source.build()[0] == 0
        cache = tmp_path / "public"

        code, out, _ = run_cli(
            [
                "link",
                "--all",
                "--dry-run",
                "--catalog-root",
                str(source.root),
                "--root",
                str(cache),
            ]
        )

        assert code == 0
        assert "apply        link " in out
        assert "record       here becomes available" in out
        assert "Nothing was written." in out
        assert not cache.exists()


@pytest.fixture
def linked(reader, tmp_path):
    """``flat`` linked into the public cache from a project directory with a stray."""
    reader.dataset("flat", {"a.csv": "1,2\n"}, where="nowhere")
    project = tmp_path / "project" / "flat"
    project.mkdir(parents=True)
    (project / "a.csv").write_bytes(b"1,2\n")
    (project / "stray.txt").write_bytes(b"not in the catalogue")
    reader.cache.mkdir(parents=True, exist_ok=True)
    (reader.cache / "flat").symlink_to(project, target_is_directory=True)
    return reader.write(), project


class TestMaterialize:
    def test_every_link_becomes_a_verified_copy_of_the_catalogued_files(
        self, reader, linked
    ):
        index, project = linked

        code, _, err = run_cli(["--catalog", str(index), "materialize", "--all"])

        assert code == 0, err
        entry = reader.cache / "flat"
        assert entry.is_dir() and not entry.is_symlink()
        assert (entry / "a.csv").read_bytes() == b"1,2\n"
        assert not (entry / "stray.txt").exists(), "only catalogued files are copied"
        assert (entry / ".ethos-data-materialized.json").is_file()
        assert (project / "stray.txt").exists(), "the original is left alone"

    def test_a_copy_that_would_fill_the_disk_is_refused(
        self, reader, linked, monkeypatch
    ):
        index, _ = linked
        usage = namedtuple("usage", "total used free")
        monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(1000, 990, 10))

        code, out, _ = run_cli(["--catalog", str(index), "materialize", "flat"])

        assert code == 1
        assert "not enough room" in out
        assert (reader.cache / "flat").is_symlink(), "the link is untouched"

    def test_a_copy_that_does_not_verify_keeps_the_link(self, reader, linked):
        index, project = linked
        (project / "a.csv").write_bytes(b"9,9\n")

        code, out, _ = run_cli(["--catalog", str(index), "materialize", "flat"])

        assert code == 1
        assert "did not copy or did not verify" in out
        assert (reader.cache / "flat").is_symlink()
