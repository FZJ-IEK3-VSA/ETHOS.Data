"""The external systems behind their ports, and the fakes that stand in for them.

Characterisation tests for the adapter layer of the four-layer decision: each
real adapter and its fake satisfy the same port and fail with the typed error
it names, the dCache adapter copies exactly the inventory and reads it back
anonymously, downloads check their hashes, and git commits, tags and pushes a
real checkout.
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
from ethos_data.errors import (
    AccessError,
    DownloadError,
    MaintenanceError,
    UploadError,
)


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

        dcache.DcacheStore("HIFIS").copy(
            tmp_path,
            "ethos-data/fam/a",
            ["x.csv", "sub/y.csv"],
            transfers=4,
        )

        command = seen["command"]
        assert command[:4] == [
            "rclone",
            "copy",
            str(tmp_path),
            "HIFIS:ethos-data/fam/a",
        ]
        assert "--immutable" in command
        assert command[command.index("--transfers") + 1] == "4"
        assert seen["listing"] == b"x.csv\nsub/y.csv\n", "LF, whatever the platform"
        assert not Path(command[command.index("--files-from") + 1]).exists()

    def test_a_failed_copy_names_rclones_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            dcache,
            "_run",
            lambda command, **kwargs: subprocess.CompletedProcess(command, 7),
        )

        with pytest.raises(UploadError, match="rclone exited 7 copying to HIFIS:d"):
            dcache.DcacheStore("HIFIS").copy(tmp_path, "d", ["x.csv"], transfers=1)

    def test_the_read_back_is_anonymous_and_names_what_is_not_served(self, store):
        store.put("ethos-data/flat", "a.csv", "1\n")
        adapter = dcache.DcacheStore()

        assert adapter.served(f"{store.url}/ethos-data/flat/a.csv") == 2
        missing = f"{store.url}/ethos-data/flat/b.csv"
        with pytest.raises(UploadError, match="b.csv is not readable: HTTP 404"):
            adapter.served(missing)
        assert store.requests[-1] == ("HEAD", "/ethos-data/flat/b.csv")

    @pytest.mark.repository
    def test_the_login_hint_matches_the_guide(self, monkeypatch):
        """The redirect port the guide forwards is the one the hint registers."""
        monkeypatch.setattr(
            dcache,
            "_run",
            lambda command, **kwargs: subprocess.CompletedProcess(
                command, 1, stdout="", stderr=""
            ),
        )
        guide = (
            Path(__file__).resolve().parents[1]
            / "docs/how-to/catalogue-maintainers/set-up-dcache-access.md"
        ).read_text(encoding="utf-8")

        with pytest.raises(UploadError) as refused:
            dcache.DcacheStore().token("HIFIS")

        assert "--redirect-uri=http://localhost:8080" in refused.value.message
        assert "--redirect-uri=http://localhost:8080" in guide

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

    def test_a_recorded_hash_is_read_however_it_is_spelled(self, store, tmp_path):
        store.put("flat", "a.csv", "1\n")
        bare = digest(b"1\n").removeprefix("sha256:").upper()

        found = PoochDownloader().fetch(
            f"{store.url}/flat/", tmp_path / "flat", {"a.csv": bare}
        )

        assert found["a.csv"].read_bytes() == b"1\n"

    def test_pooch_refuses_bytes_that_do_not_match(self, store, tmp_path, monkeypatch):
        import pooch

        monkeypatch.setattr(pooch.core.time, "sleep", lambda seconds: None)
        store.put("flat", "a.csv", "changed\n")

        with pytest.raises(DownloadError, match=f"{store.url}/flat/a.csv") as refused:
            PoochDownloader(retries=0).fetch(
                f"{store.url}/flat/", tmp_path / "flat", {"a.csv": digest(b"1\n")}
            )

        assert isinstance(refused.value, AccessError)
        assert refused.value.exit_code == 2

    def test_a_missing_object_names_its_url(self, store, tmp_path, monkeypatch):
        import pooch

        monkeypatch.setattr(pooch.core.time, "sleep", lambda seconds: None)

        with pytest.raises(DownloadError, match=f"{store.url}/flat/gone.csv"):
            PoochDownloader(retries=0).fetch(
                f"{store.url}/flat/", tmp_path / "flat", {"gone.csv": digest(b"1\n")}
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
        with pytest.raises(DownloadError, match="does not match"):
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


class TestTheFakeStore:
    def test_it_reads_back_what_it_was_sent(self, tmp_path):
        (tmp_path / "a.csv").write_bytes(b"1\n")
        fake = FakeStore()

        fake.copy(tmp_path, "root/flat", ["a.csv"], transfers=1)

        assert fake.served("https://store.invalid/root/flat/a.csv") == 2
        with pytest.raises(UploadError, match="HTTP 404"):
            fake.served("https://store.invalid/root/flat/b.csv")

    def test_it_rehearses_a_failed_copy_and_a_missing_chmod(self, tmp_path):
        (tmp_path / "a.csv").write_bytes(b"1\n")

        with pytest.raises(UploadError, match="rclone exited 7"):
            FakeStore(copy_status=7).copy(tmp_path, "root/flat", ["a.csv"], transfers=1)
        closed = FakeStore(readable=False)
        closed.copy(tmp_path, "root/flat", ["a.csv"], transfers=1)
        with pytest.raises(UploadError, match="HTTP 401"):
            closed.served("https://store.invalid/root/flat/a.csv")


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
        commit = repository.commit("Release v1.0.0")
        repository.tag("v1.0.0", "Release v1.0.0")
        repository.push("origin", "HEAD:refs/heads/main", "v1.0.0")

        assert repository.is_clean() and repository.head() == commit
        tags = subprocess.run(
            ["git", "tag"], cwd=remote, check=True, capture_output=True, text=True
        )
        assert tags.stdout.split() == ["v1.0.0"]

    def test_a_failing_command_says_what_git_said(self, checkout):
        work, _ = checkout

        with pytest.raises(MaintenanceError, match="git tag"):
            GitRepository(work).tag("v1.0.0", "no commit to tag yet")
