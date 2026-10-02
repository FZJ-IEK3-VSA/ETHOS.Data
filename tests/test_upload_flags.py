"""What ``catalog upload`` does under ``--dry-run`` and ``--verify-only``.

Characterisation tests for [Upload a public dataset]. rclone and the dCache
REST interface are replaced by recorders; the anonymous read check runs for
real, against :class:`support.Store` serving the publication root.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from support import SourceCatalogue

from ethos_data.maintain import upload


@pytest.fixture
def uploading(tmp_path, store, monkeypatch):
    catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
    catalogue.dataset(
        "flat", {"a.csv": "1\n", "b.csv": "22\n"}, ethos_remote_prefix="flat"
    )
    assert catalogue.build()[0] == 0
    calls: dict[str, list] = {"rclone": [], "chmod": []}

    def rclone(command, *args, **kwargs):
        calls["rclone"].append(command)
        if "--dry-run" not in command:
            origin = Path(command[2])
            destination = command[3].split(":", 1)[1]
            listing = Path(command[command.index("--files-from") + 1])
            for relative in listing.read_text(encoding="utf-8").split():
                store.put(destination, relative, (origin / relative).read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(upload.subprocess, "run", rclone)
    monkeypatch.setattr(upload, "token", lambda profile: "token")
    monkeypatch.setattr(
        upload, "chmod", lambda path, mode, bearer: calls["chmod"].append(path) or 200
    )
    monkeypatch.setattr(upload, "locality", lambda path, bearer: "ONLINE")
    return catalogue, calls


def heads(store) -> list[str]:
    return [path for method, path in store.requests if method == "HEAD"]


def test_a_dry_run_transfers_nothing_and_checks_nothing(uploading, store):
    catalogue, calls = uploading

    code, out, _ = catalogue.catalog("upload", "flat", "--dry-run")

    assert code == 0
    assert len(calls["rclone"]) == 1 and "--dry-run" in calls["rclone"][0]
    assert "--immutable" in calls["rclone"][0]
    assert calls["chmod"] == []
    assert heads(store) == []
    assert "Dry run only; nothing was uploaded." in out


def test_an_upload_transfers_the_inventory_opens_it_and_reads_it_back(uploading, store):
    catalogue, calls = uploading

    code, out, _ = catalogue.catalog("upload", "flat")

    assert code == 0
    assert len(calls["rclone"]) == 1
    assert calls["chmod"] == ["Helmholtz/FZJ-ICE2/ethos-data/flat"]
    assert sorted(heads(store)) == ["/ethos-data/flat/a.csv", "/ethos-data/flat/b.csv"]
    assert "readable       2/2" in out


def test_verify_only_without_chmod_only_reads(uploading, store):
    catalogue, calls = uploading
    store.put("ethos-data/flat", "a.csv", "1\n")
    store.put("ethos-data/flat", "b.csv", "22\n")

    code, out, _ = catalogue.catalog("upload", "flat", "--verify-only", "--no-chmod")

    assert code == 0
    assert calls["rclone"] == [] and calls["chmod"] == []
    assert len(heads(store)) == 2
    assert "readable       2/2" in out


def test_verify_only_fails_on_a_file_the_store_does_not_serve(uploading, store):
    catalogue, _ = uploading
    store.put("ethos-data/flat", "a.csv", "1\n")

    code, out, _ = catalogue.catalog("upload", "flat", "--verify-only", "--no-chmod")

    assert code == 1
    assert "NOT READABLE   1" in out


def test_a_dataset_without_a_prefix_goes_to_the_folder_named_after_it(
    tmp_path, store, monkeypatch
):
    """The documented default, and the folder the reader downloads from."""
    catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
    catalogue.dataset("plain", {"a.csv": "1\n"})
    assert catalogue.build()[0] == 0
    commands = []
    monkeypatch.setattr(
        upload.subprocess,
        "run",
        lambda command, *a, **k: (
            commands.append(command) or subprocess.CompletedProcess(command, 0)
        ),
    )

    code, _, err = catalogue.catalog("upload", "plain", "--dry-run")

    assert code == 0, err
    assert commands[0][3] == "HIFIS:ethos-data/plain"
