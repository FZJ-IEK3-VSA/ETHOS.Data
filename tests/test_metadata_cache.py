"""The on-disk cache of catalogue metadata read over HTTP.

Characterisation tests for the switch [Report a problem] tells people about:
a catalogue read from a pinned URL is cached and reused, one read from a
moving branch is not, and ``ETHOS_CATALOG_NO_CACHE`` turns the cache off.
The catalogue is served by :class:`support.Store`, so these are real reads.
"""

from __future__ import annotations

import json

import pytest

import ethos_data

INDEX = {
    "name": "served",
    "ethos:publication_url": "https://example.invalid",
    "datasets": [
        {
            "name": "flat",
            "path": "datasets/flat/datapackage.json",
            "ethos:license_status": "resolved",
        }
    ],
}
PACKAGE = {
    "name": "flat",
    "resources": [
        {"name": "a", "path": "a.csv", "bytes": 1, "hash": "sha256:" + "0" * 64}
    ],
}


@pytest.fixture
def serve(store, tmp_path, monkeypatch):
    """Publish the catalogue under a ref on the store; returns the index URL."""
    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "cache"))

    def publish(ref: str) -> str:
        store.put(ref, "datacatalog.json", json.dumps(INDEX))
        store.put(ref, "datasets/flat/datapackage.json", json.dumps(PACKAGE))
        return f"{store.url}/{ref}/datacatalog.json"

    return publish


def withdraw(store, ref: str) -> None:
    for path in sorted((store.root / ref).rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()


def test_a_pinned_catalogue_is_read_once_and_reused(serve, store):
    url = serve("v2026.09.1")
    assert list(ethos_data.load_catalog(url).dataset("flat").resources) == ["a.csv"]

    withdraw(store, "v2026.09.1")

    again = ethos_data.load_catalog(url)
    assert list(again.dataset("flat").resources) == ["a.csv"], "index and descriptor"


def test_a_moving_branch_is_never_cached(serve, store):
    url = serve("main")
    _ = ethos_data.load_catalog(url).dataset("flat").resources
    withdraw(store, "main")

    with pytest.raises(ethos_data.CatalogUnavailable):
        ethos_data.load_catalog(url)


def test_the_cache_can_be_switched_off_for_one_shell(serve, store, monkeypatch):
    monkeypatch.setenv("ETHOS_CATALOG_NO_CACHE", "1")
    url = serve("v2026.09.1")
    ethos_data.load_catalog(url)
    withdraw(store, "v2026.09.1")

    with pytest.raises(ethos_data.CatalogUnavailable):
        ethos_data.load_catalog(url)


def test_an_index_the_store_does_not_serve_is_catalogue_unavailable(store, tmp_path):
    with pytest.raises(ethos_data.CatalogUnavailable, match="v2099.01.1"):
        ethos_data.load_catalog(f"{store.url}/v2099.01.1/datacatalog.json")
