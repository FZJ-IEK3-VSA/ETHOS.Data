"""The external systems behind their ports, and the fakes that stand in for them.

Characterisation tests for the adapter layer of the four-layer decision: each
real adapter and its fake satisfy the same port, the dCache adapter builds the
transfer it always built, downloads check their hashes, and git commits, tags
and pushes a real checkout.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from support import digest

import ethos_data
from ethos_data.adapters import Downloader, Git, Store, dcache
from ethos_data.adapters.downloads import PoochDownloader
from ethos_data.adapters.fakes import FakeDownloader, FakeGit, FakeStore
from ethos_data.adapters.git import GitRepository
from ethos_data.catalogs import load_catalog
from ethos_data.errors import MaintenanceError, UploadError


def test_each_adapter_and_its_fake_satisfy_the_port():
    assert isinstance(dcache.DcacheStore(), Store) and isinstance(FakeStore(), Store)
    assert isinstance(PoochDownloader(), Downloader)
    assert isinstance(FakeDownloader(), Downloader)
    assert isinstance(GitRepository("."), Git) and isinstance(FakeGit(), Git)


class TestDcache:
    def test_a_copy_transfers_exactly_the_inventory_and_never_overwrites(
        self, tmp_path, monkeypatch
    ):
        seen = {}

        def run(command, **kwargs):
            listing = Path(command[command.index("--files-from") + 1])
            seen["command"] = command
            seen["listing"] = listing.read_bytes()
            return subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(dcache, "_run", run)

        status = dcache.DcacheStore("HIFIS").copy(
            tmp_path,
            "ethos-data/fam/a",
            ["x.csv", "sub/y.csv"],
            transfers=4,
            dry_run=True,
        )

        command = seen["command"]
        assert status == 0
        assert command[:4] == [
            "rclone",
            "copy",
            str(tmp_path),
            "HIFIS:ethos-data/fam/a",
        ]
        assert "--immutable" in command and "--dry-run" in command
        assert command[command.index("--transfers") + 1] == "4"
        assert seen["listing"] == b"x.csv\nsub/y.csv\n", "LF, whatever the platform"
        assert not Path(command[command.index("--files-from") + 1]).exists()

    def test_a_token_that_cannot_be_had_says_how_to_get_one(self, monkeypatch):
        monkeypatch.setattr(
            dcache,
            "_run",
            lambda command, **kwargs: subprocess.CompletedProcess(
                command, 1, stdout="", stderr="agent not running"
            ),
        )

        with pytest.raises(UploadError, match="oidc-gen HIFIS") as refused:
            dcache.DcacheStore().token("HIFIS")

        assert "agent not running" in refused.value.message

    def test_tests_never_reach_the_real_commands(self):
        with pytest.raises(AssertionError, match="tests do not run rclone"):
            dcache._run(["rclone", "version"])


class TestDownloads:
    def test_pooch_fetches_and_checks_against_the_hash(self, store, tmp_path):
        store.put("flat", "a.csv", "1\n")

        found = PoochDownloader().fetch(
            f"{store.url}/flat/", tmp_path / "flat", {"a.csv": digest(b"1\n")}
        )

        assert found["a.csv"].read_bytes() == b"1\n"

    def test_pooch_refuses_bytes_that_do_not_match(self, store, tmp_path, monkeypatch):
        import pooch

        monkeypatch.setattr(pooch.core.time, "sleep", lambda seconds: None)
        store.put("flat", "a.csv", "changed\n")

        with pytest.raises(ValueError):
            PoochDownloader(retries=0).fetch(
                f"{store.url}/flat/", tmp_path / "flat", {"a.csv": digest(b"1\n")}
            )

    def test_the_fake_serves_checks_and_keeps_what_is_there(self, tmp_path):
        url = "https://store.invalid/flat/a.csv"
        fake = FakeDownloader({url: b"1\n"})

        first = fake.fetch(
            "https://store.invalid/flat", tmp_path, {"a.csv": digest(b"1\n")}
        )
        fake.fetch("https://store.invalid/flat", tmp_path, {"a.csv": digest(b"1\n")})

        assert first["a.csv"].read_bytes() == b"1\n"
        assert fake.fetched == [url], "a file already there is not fetched again"
        with pytest.raises(ValueError, match="does not match"):
            FakeDownloader({url: b"2\n"}).fetch(
                "https://store.invalid/flat",
                tmp_path / "other",
                {"a.csv": digest(b"1\n")},
            )

    def test_a_download_can_be_handed_a_downloader(self, reader):
        reader.dataset("flat", {"a.csv": "1\n"}, where="nowhere")
        catalog = load_catalog(str(reader.write()))
        fake = FakeDownloader({f"{reader.publication_url}/flat/a.csv": b"1\n"})

        files = ethos_data.download(
            catalog, list(catalog.dataset("flat").resources.values()), downloader=fake
        )

        assert files["flat/a.csv"] == reader.cache / "flat" / "a.csv"
        assert files["flat/a.csv"].read_bytes() == b"1\n"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
class TestGit:
    @pytest.fixture
    def checkout(self, tmp_path):
        def git(*arguments, cwd):
            subprocess.run(
                ["git", *arguments], cwd=cwd, check=True, capture_output=True
            )

        remote = tmp_path / "remote.git"
        git("init", "--bare", str(remote), cwd=tmp_path)
        work = tmp_path / "work"
        work.mkdir()
        git("init", cwd=work)
        git("config", "user.email", "tests@example.invalid", cwd=work)
        git("config", "user.name", "Tests", cwd=work)
        git("remote", "add", "origin", str(remote), cwd=work)
        return work, remote

    def test_it_commits_tags_and_pushes(self, checkout):
        work, remote = checkout
        repository = GitRepository(work)
        (work / "catalog.yaml").write_bytes(b"name: t\n")

        assert not repository.is_clean()
        commit = repository.commit("Release v2026.10.1")
        repository.tag("v2026.10.1", "Release v2026.10.1")
        repository.push("origin", "HEAD:refs/heads/main", "v2026.10.1")

        assert repository.is_clean() and repository.head() == commit
        tags = subprocess.run(
            ["git", "tag"], cwd=remote, check=True, capture_output=True, text=True
        )
        assert tags.stdout.split() == ["v2026.10.1"]

    def test_a_failing_command_says_what_git_said(self, checkout):
        work, _ = checkout

        with pytest.raises(MaintenanceError, match="git tag"):
            GitRepository(work).tag("v2026.10.1", "no commit to tag yet")
