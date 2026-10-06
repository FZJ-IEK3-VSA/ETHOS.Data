"""What ``catalog upload`` does under ``--dry-run`` and ``--verify-only``.

Characterisation tests for [Upload a public dataset]. dCache is a
:class:`~ethos_data.adapters.fakes.FakeStore`, which keeps what it is sent and
answers the anonymous read-back from it.
"""

from __future__ import annotations

import pytest
from support import SourceCatalogue

from ethos_data.adapters.fakes import FakeStore
from ethos_data.maintain import upload

PUBLICATION_URL = "https://store.invalid/ethos-data"


@pytest.fixture
def uploading(tmp_path, monkeypatch):
    catalogue = SourceCatalogue(tmp_path, publication_url=PUBLICATION_URL)
    catalogue.dataset(
        "flat", {"a.csv": "1\n", "b.csv": "22\n"}, ethos_remote_prefix="flat"
    )
    assert catalogue.build()[0] == 0
    dcache = FakeStore()
    monkeypatch.setattr(upload, "DcacheStore", lambda remote: dcache)
    return catalogue, dcache


def test_a_dry_run_is_the_plan_and_contacts_no_store(uploading):
    catalogue, dcache = uploading

    code, out, _ = catalogue.catalog("upload", "flat", "--dry-run")

    assert code == 0
    assert dcache.copies == [] and dcache.chmods == [] and dcache.reads == []
    assert dcache.tokens == []
    assert "transfer     copy 2 files" in out
    assert "permissions  chmod 0755 Helmholtz/FZJ-ICE2/ethos-data/flat" in out
    assert "verify       read the 2 files of flat back anonymously" in out
    assert "record       flat becomes available" in out
    assert "Nothing was written." in out


def test_a_verify_only_dry_run_changes_no_permissions(uploading):
    catalogue, dcache = uploading

    code, out, _ = catalogue.catalog("upload", "flat", "--verify-only", "--dry-run")

    assert code == 0
    assert dcache.chmods == [] and dcache.reads == []
    assert "transfer" not in out
    assert "permissions  chmod 0755" in out


def test_an_upload_transfers_the_inventory_opens_it_and_reads_it_back(uploading):
    catalogue, dcache = uploading

    code, out, _ = catalogue.catalog("upload", "flat")

    assert code == 0
    assert [copy["paths"] for copy in dcache.copies] == [["a.csv", "b.csv"]]
    assert dcache.chmods == [("Helmholtz/FZJ-ICE2/ethos-data/flat", 493)]
    assert sorted(dcache.reads) == [
        f"{PUBLICATION_URL}/flat/a.csv",
        f"{PUBLICATION_URL}/flat/b.csv",
    ]
    assert "readable       2/2" in out


def test_verify_only_without_chmod_only_reads(uploading):
    catalogue, dcache = uploading
    dcache.objects.update(
        {"ethos-data/flat/a.csv": b"1\n", "ethos-data/flat/b.csv": b"22\n"}
    )

    code, out, _ = catalogue.catalog("upload", "flat", "--verify-only", "--no-chmod")

    assert code == 0
    assert dcache.copies == [] and dcache.chmods == []
    assert len(dcache.reads) == 2
    assert "readable       2/2" in out


def test_verify_only_fails_on_a_file_the_store_does_not_serve(uploading):
    catalogue, dcache = uploading
    dcache.objects["ethos-data/flat/a.csv"] = b"1\n"

    code, out, err = catalogue.catalog("upload", "flat", "--verify-only", "--no-chmod")

    assert code == 1
    assert "NOT READABLE   1" in out
    assert "b.csv is not readable: HTTP 404" in out
    assert "1 file(s) of flat are not readable" in err


def test_a_folder_nobody_may_read_fails_the_read_back(uploading):
    catalogue, dcache = uploading
    dcache.readable = False

    code, out, _ = catalogue.catalog("upload", "flat")

    assert code == 1
    assert "NOT READABLE   2" in out and "HTTP 401" in out


def test_a_dataset_without_a_prefix_goes_to_the_folder_named_after_it(
    tmp_path, monkeypatch
):
    """The documented default, and the folder the reader downloads from."""
    catalogue = SourceCatalogue(tmp_path, publication_url=PUBLICATION_URL)
    catalogue.dataset("plain", {"a.csv": "1\n"})
    assert catalogue.build()[0] == 0
    dcache = FakeStore()
    monkeypatch.setattr(upload, "DcacheStore", lambda remote: dcache)

    code, _, err = catalogue.catalog("upload", "plain")

    assert code == 0, err
    assert dcache.copies[0]["destination"] == "ethos-data/plain"
