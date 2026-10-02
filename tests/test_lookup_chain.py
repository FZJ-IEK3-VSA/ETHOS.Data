"""Where a file is read: one chain of places, the first that has it wins.

Characterisation tests for the lookup chain of the architecture decisions,
and for ``fetch=False`` in [Use data in a script]. The places are a
per-dataset root, the staging root, the restricted cache, a link in the public
cache, a copy in it, and a download. A place that may not serve a file
refuses instead of letting it fall through to a later one.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import ethos_data
from ethos_data import Roots, locate
from ethos_data.access import (
    ORIGIN_CACHED,
    ORIGIN_CONFIGURED,
    ORIGIN_DOWNLOAD,
    ORIGIN_LINK,
    ORIGIN_RESTRICTED,
    ORIGIN_STAGING,
    chain_for,
)
from ethos_data.catalogs import load_catalog
from ethos_data.errors import AccessError, NotFetched


def link(entry: Path, target: Path) -> None:
    entry.parent.mkdir(parents=True, exist_ok=True)
    try:
        entry.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links need a privilege this account lacks")


def place(reader, name: str, path: str, roots: Roots) -> tuple[str, Path | None]:
    """Where the chain reads one file from, as ``(origin, path)``."""
    catalog = load_catalog(str(reader.write()))
    resource = catalog.dataset(name).resource_at(path)
    [found] = locate(catalog, [resource], roots)
    return found.origin, found.path


class TestTheOrder:
    def test_a_dataset_root_wins_over_staging(self, reader, tmp_path):
        reader.dataset("flat", {"a.csv": "1\n"})
        own = tmp_path / "own"
        (tmp_path / "staging" / "flat").mkdir(parents=True)
        roots = Roots(
            public=reader.cache,
            staging=tmp_path / "staging",
            datasets={"flat": str(own)},
        )

        assert place(reader, "flat", "a.csv", roots) == (
            ORIGIN_CONFIGURED,
            own / "a.csv",
        )

    def test_staging_wins_over_the_public_cache(self, reader, tmp_path):
        reader.dataset("flat", {"a.csv": "1\n"})
        staged = tmp_path / "staging" / "flat"
        staged.mkdir(parents=True)
        roots = Roots(public=reader.cache, staging=tmp_path / "staging")

        with pytest.warns(UserWarning, match="read from the staging root"):
            assert place(reader, "flat", "a.csv", roots) == (
                ORIGIN_STAGING,
                staged / "a.csv",
            )

    def test_staging_never_shadows_restricted_data(self, reader, tmp_path):
        reader.dataset(
            "licensed", {"a.csv": "1\n"}, access="restricted", where="nowhere"
        )
        (tmp_path / "staging" / "licensed").mkdir(parents=True)
        (tmp_path / "restricted" / "licensed").mkdir(parents=True)
        roots = Roots(
            public=reader.cache,
            staging=tmp_path / "staging",
            restricted=tmp_path / "restricted",
        )

        assert place(reader, "licensed", "a.csv", roots) == (
            ORIGIN_RESTRICTED,
            tmp_path / "restricted" / "licensed" / "a.csv",
        )

    def test_restricted_data_refuses_rather_than_use_a_copy_in_the_public_cache(
        self, reader
    ):
        """The copy may be anyone's; licensed bytes come from the restricted cache only."""
        reader.dataset("licensed", {"a.csv": "1\n"}, access="restricted", where="cache")
        roots = Roots(public=reader.cache)

        with pytest.raises(AccessError, match="is restricted, and this machine cannot"):
            place(reader, "licensed", "a.csv", roots)

    def test_a_link_wins_over_a_download(self, reader, tmp_path):
        reader.dataset("linked", {"a.csv": "1\n"}, where="nowhere")
        target = tmp_path / "elsewhere"
        target.mkdir()
        link(reader.cache / "linked", target)

        assert place(reader, "linked", "a.csv", Roots(public=reader.cache)) == (
            ORIGIN_LINK,
            reader.cache / "linked" / "a.csv",
        )

    def test_a_copy_of_the_recorded_size_is_used_and_any_other_is_replaced(
        self, reader
    ):
        reader.dataset("flat", {"a.csv": "1\n"}, where="cache")
        roots = Roots(public=reader.cache)
        copy = reader.cache / "flat" / "a.csv"

        assert place(reader, "flat", "a.csv", roots) == (ORIGIN_CACHED, copy)

        copy.write_bytes(b"")
        assert place(reader, "flat", "a.csv", roots) == (ORIGIN_DOWNLOAD, copy)

    def test_the_chain_names_each_place_in_order(self, tmp_path):
        roots = Roots(public=tmp_path / "public", restricted=tmp_path / "restricted")

        places = [line.split(". ", 1)[1] for line in str(chain_for(roots)).splitlines()]

        assert [place.split(" ", 1)[0] for place in places] == [
            "per-dataset",
            "staging",
            "restricted",
            "links",
            "copies",
            "a",
        ]
        assert places[-1].endswith("for public data only")


class TestFamiliesAndClasses:
    def test_a_member_of_a_linked_family_is_read_through_the_familys_link(
        self, reader, tmp_path
    ):
        """It used to be a download target, written into the borrowed directory."""
        reader.namespace("family")
        reader.dataset("family/member", {"a.csv": "1\n"}, where="nowhere")
        target = tmp_path / "family-data"
        (target / "member").mkdir(parents=True)
        (target / "member" / "a.csv").write_bytes(b"1\n")
        link(reader.cache / "family", target)
        roots = Roots(public=reader.cache)

        assert place(reader, "family/member", "a.csv", roots) == (
            ORIGIN_LINK,
            reader.cache / "family" / "member" / "a.csv",
        )
        catalog = load_catalog(str(reader.index))
        files = ethos_data.download(
            catalog, list(catalog.dataset("family/member").resources.values()), roots
        )
        assert files["family/member/a.csv"] == reader.cache / "family/member/a.csv"

    def test_internal_data_is_never_downloaded(self, reader):
        reader.dataset("held", {"a.csv": "1\n"}, access="internal", where="store")

        with pytest.raises(AccessError, match="is internal: it is not published"):
            place(reader, "held", "a.csv", Roots(public=reader.cache))


WIND = """
    wind:
      include:
        - dataset: wind
      paths:
        u: wind/u.nc
"""


class TestFetchFalse:
    @pytest.fixture
    def wind(self, reader):
        reader.dataset("wind", {"u.nc": "uuuu"}, where="store")
        return ethos_data.collections(reader.collections(WIND))

    def test_a_file_that_is_here_is_returned_without_asking_the_store(
        self, reader, store
    ):
        reader.dataset("wind", {"u.nc": "uuuu"}, where="cache")
        data = ethos_data.collections(reader.collections(WIND))

        inputs = data.paths("wind", fetch=False)

        assert inputs["u"] == reader.cache / "wind" / "u.nc"
        assert store.requests == []

    def test_a_missing_file_is_named_with_the_path_it_belongs_at(
        self, wind, reader, store
    ):
        with pytest.raises(NotFetched) as refused:
            wind.paths("wind", fetch=False)

        message = refused.value.message
        assert "wind/u.nc" in message
        assert f"belongs at {reader.cache / 'wind' / 'u.nc'}" in message
        assert "The same call with fetch=True downloads them to those paths." in message
        assert store.requests == []
        assert not (reader.cache / "wind").exists()

    def test_fetch_true_puts_it_where_the_refusal_said(self, wind, reader):
        with pytest.raises(NotFetched):
            wind.fetch("wind", fetch=False)

        fetched = wind.fetch("wind", progressbar=False)

        assert fetched["wind/u.nc"] == reader.cache / "wind" / "u.nc"
        assert wind.fetch("wind", fetch=False) == fetched

    def test_a_catalogue_handle_takes_it_too(self, wind, reader):
        handle = ethos_data.catalog(str(reader.index))

        with pytest.raises(NotFetched, match="wind/u.nc"):
            handle.path("wind/u.nc", fetch=False)

    def test_the_one_call_form_takes_it_too(self, wind, reader):
        with pytest.raises(NotFetched):
            ethos_data.paths(
                "wind", reader.root.parent / "collections.yaml", fetch=False
            )


class TestOneCatalogueResolver:
    def test_an_explicit_location_then_the_environment_then_the_file_then_the_pin(
        self, tmp_path, monkeypatch
    ):
        settings = ethos_data.read_settings()
        pin = str(tmp_path / "pinned.json")

        assert settings.choose_catalog(pin=pin) == (pin, "a collections file's pin")
        assert settings.choose_catalog()[1] == "built-in public catalogue"

        ethos_data.set_option("catalog", str(tmp_path / "file.json"))
        from_file = ethos_data.read_settings().choose_catalog(pin=pin)
        assert from_file[0] == str(tmp_path / "file.json")
        assert from_file[1].startswith("settings file")

        monkeypatch.setenv("ETHOS_DATA_CATALOG", str(tmp_path / "env.json"))
        assert ethos_data.read_settings().choose_catalog(pin=pin) == (
            str(tmp_path / "env.json"),
            "$ETHOS_DATA_CATALOG",
        )
        assert ethos_data.read_settings().choose_catalog(
            explicit="x.json", pin=pin
        ) == (
            "x.json",
            "explicit argument",
        )

    def test_loading_a_collections_file_follows_the_same_order(
        self, reader, tmp_path, monkeypatch
    ):
        """It used to take the pin over $ETHOS_DATA_CATALOG, unlike every handle."""
        collections = reader.collections(WIND)
        other = replace_index(reader, tmp_path)
        monkeypatch.setenv("ETHOS_DATA_CATALOG", str(other))

        loaded = ethos_data.load_collections(collections)

        assert loaded.catalog.location == str(other)
        assert loaded.settings.catalog_source == "$ETHOS_DATA_CATALOG"


def replace_index(reader, tmp_path: Path) -> Path:
    """A second, empty catalogue index beside the reader's."""
    other = tmp_path / "other" / "datacatalog.json"
    other.parent.mkdir()
    other.write_bytes(b'{"name": "other", "datasets": []}')
    return other


def test_locate_keeps_taking_a_mapping_of_dataset_roots(reader, tmp_path):
    reader.dataset("flat", {"a.csv": "1\n"})
    catalog = load_catalog(str(reader.write()))
    resource = catalog.dataset("flat").resource_at("a.csv")
    roots = replace(Roots(public=reader.cache), datasets={"flat": str(tmp_path / "x")})

    [from_roots] = locate(catalog, [resource], roots)
    [given] = locate(catalog, [resource], roots, {"flat": tmp_path / "y"})

    assert from_roots.path == tmp_path / "x" / "a.csv"
    assert given.path == tmp_path / "y" / "a.csv"
