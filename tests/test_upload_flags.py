"""What ``catalog upload`` does under ``--dry-run`` and ``--verify-only``.

Characterisation tests for [Upload a public dataset]. dCache is a
:class:`~ethos_data.adapters.fakes.FakeStore` that puts what it is sent on
:class:`support.Store`, so the anonymous read check runs for real against the
publication root.
"""

from __future__ import annotations

import pytest
from support import SourceCatalogue

from ethos_data.adapters.fakes import FakeStore
from ethos_data.maintain import upload


@pytest.fixture
def uploading(tmp_path, store, monkeypatch):
    catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
    catalogue.dataset(
        "flat", {"a.csv": "1\n", "b.csv": "22\n"}, ethos_remote_prefix="flat"
    )
    assert catalogue.build()[0] == 0
    dcache = FakeStore(put=store.put)
    monkeypatch.setattr(upload, "DcacheStore", lambda remote: dcache)
    return catalogue, dcache


def heads(store) -> list[str]:
    return [path for method, path in store.requests if method == "HEAD"]


def test_a_dry_run_transfers_nothing_and_checks_nothing(uploading, store):
    catalogue, dcache = uploading

    code, out, _ = catalogue.catalog("upload", "flat", "--dry-run")

    assert code == 0
    assert [copy["dry_run"] for copy in dcache.copies] == [True]
    assert dcache.chmods == []
    assert heads(store) == []
    assert "Dry run only; nothing was uploaded." in out


def test_an_upload_transfers_the_inventory_opens_it_and_reads_it_back(uploading, store):
    catalogue, dcache = uploading

    code, out, _ = catalogue.catalog("upload", "flat")

    assert code == 0
    assert [copy["paths"] for copy in dcache.copies] == [["a.csv", "b.csv"]]
    assert dcache.chmods == [("Helmholtz/FZJ-ICE2/ethos-data/flat", 493)]
    assert sorted(heads(store)) == ["/ethos-data/flat/a.csv", "/ethos-data/flat/b.csv"]
    assert "readable       2/2" in out


def test_verify_only_without_chmod_only_reads(uploading, store):
    catalogue, dcache = uploading
    store.put("ethos-data/flat", "a.csv", "1\n")
    store.put("ethos-data/flat", "b.csv", "22\n")

    code, out, _ = catalogue.catalog("upload", "flat", "--verify-only", "--no-chmod")

    assert code == 0
    assert dcache.copies == [] and dcache.chmods == []
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
    dcache = FakeStore()
    monkeypatch.setattr(upload, "DcacheStore", lambda remote: dcache)

    code, _, err = catalogue.catalog("upload", "plain", "--dry-run")

    assert code == 0, err
    assert dcache.copies[0]["destination"] == "ethos-data/plain"
