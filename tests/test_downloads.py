"""Where a file is read from, and the real download path behind it.

Characterisation tests for [Use data in a script] and [Caches, classes and
roots]: the order in which a file is looked for (a link in the public
cache, the restricted cache, a download), what a download
checks, and what a plan reports. Downloads run against :class:`support.Store`,
a local HTTP server, so pooch, the checksums and the cache layout are the real
ones and nothing reaches the network.
"""

from __future__ import annotations

import pooch
import pytest
from support import Store

import ethos_data


@pytest.fixture
def no_retry_delay(monkeypatch):
    """pooch sleeps between its retries; a refused download need not wait for them."""
    monkeypatch.setattr(pooch.core.time, "sleep", lambda seconds: None)


def catalogue(reader):
    return ethos_data.catalog(str(reader.write()))


class TestDownloading:
    def test_a_missing_file_is_downloaded_into_the_public_cache(self, reader, store):
        reader.dataset("flat", {"a.csv": "1,2\n", "sub/b.csv": "3\n"}, where="store")

        path = catalogue(reader).path("flat/sub/b.csv")

        assert path.samefile(reader.cache / "flat" / "sub" / "b.csv")
        assert path.read_text() == "3\n"
        assert store.downloads() == ["/flat/sub/b.csv"], "only the file asked for"

    def test_a_file_already_in_the_cache_is_not_downloaded_again(self, reader, store):
        reader.dataset("flat", {"a.csv": "1,2\n"}, where="store")
        handle = catalogue(reader)

        first = handle.path("flat/a.csv")
        second = handle.path("flat/a.csv")

        assert first == second
        assert store.downloads() == ["/flat/a.csv"]

    def test_bytes_that_differ_from_the_catalogue_are_refused(
        self, reader, store, no_retry_delay
    ):
        reader.dataset("flat", {"a.csv": "1,2\n"}, where="store")
        store.put("flat", "a.csv", "tampered\n")

        with pytest.raises(Exception, match=r"(?i)hash|checksum"):
            catalogue(reader).path("flat/a.csv")
        assert not (reader.cache / "flat" / "a.csv").exists()

    def test_a_file_the_store_does_not_serve_is_an_error_naming_its_url(
        self, reader, store, no_retry_delay
    ):
        reader.dataset("flat", {"a.csv": "1,2\n"}, where="nowhere")

        with pytest.raises(Exception) as raised:
            catalogue(reader).path("flat/a.csv")
        assert f"{store.url}/flat/a.csv" in str(raised.value)

    def test_the_remote_prefix_names_the_folder_on_the_store(self, reader, store):
        reader.dataset(
            "flat", {"a.csv": "1,2\n"}, where="store", remote_prefix="flat-v1"
        )

        catalogue(reader).path("flat/a.csv")

        assert store.downloads() == ["/flat-v1/a.csv"]
        assert (reader.cache / "flat" / "a.csv").is_file(), "the cache uses the name"

    def test_the_publication_url_can_be_redirected_for_one_shell(
        self, reader, tmp_path, monkeypatch
    ):
        mirror = Store(tmp_path / "mirror")
        try:
            reader.dataset("flat", {"a.csv": "1,2\n"}, where="nowhere")
            mirror.put("flat", "a.csv", "1,2\n")
            monkeypatch.setenv("ETHOS_PUBLICATION_URL", mirror.url)

            assert catalogue(reader).path("flat/a.csv").read_text() == "1,2\n"
            assert mirror.downloads() == ["/flat/a.csv"]
        finally:
            mirror.close()

    def test_a_folder_key_fetches_every_file_under_it_and_returns_the_folder(
        self, reader, store
    ):
        reader.dataset(
            "flat",
            {"sub/a.csv": "1\n", "sub/b.csv": "2\n", "c.csv": "3\n"},
            where="store",
        )

        folder = catalogue(reader).path("flat/sub")

        assert folder.samefile(reader.cache / "flat" / "sub")
        assert sorted(store.downloads()) == ["/flat/sub/a.csv", "/flat/sub/b.csv"]

    def test_a_shapefile_brings_its_sidecars(self, reader, store):
        reader.dataset(
            "shapes",
            {"sites.shp": "shp", "sites.dbf": "dbf", "other.shp": "x"},
            where="store",
            sidecars={"sites.shp": ["sites.dbf"]},
        )

        catalogue(reader).path("shapes/sites.shp")

        assert sorted(store.downloads()) == ["/shapes/sites.dbf", "/shapes/sites.shp"]


class TestWhereAFileIsRead:
    """First match wins: override, link, restricted cache, download."""

    def test_a_link_in_the_public_cache_is_read_in_place(self, reader, store, tmp_path):
        reader.dataset("flat", {"a.csv": "1,2\n"}, where="store")
        project = tmp_path / "project" / "flat"
        project.mkdir(parents=True)
        (project / "a.csv").write_bytes(b"1,2\n")
        reader.cache.mkdir(parents=True, exist_ok=True)
        (reader.cache / "flat").symlink_to(project, target_is_directory=True)

        path = catalogue(reader).path("flat/a.csv")

        assert path.samefile(project / "a.csv")
        assert store.downloads() == [], "a link is never downloaded into"

    def test_restricted_data_is_never_downloaded(self, reader, store):
        reader.dataset(
            "licensed",
            {"secret.tif": "s"},
            access="restricted",
            visibility="hidden",
            where="store",
        )

        with pytest.raises(ethos_data.AccessError, match="licensed"):
            catalogue(reader).path("licensed/secret.tif")
        assert store.downloads() == []

    def test_restricted_data_is_read_in_place_and_nothing_is_written_there(
        self, reader, store, tmp_path, monkeypatch
    ):
        reader.dataset(
            "licensed", {"secret.tif": "s"}, access="restricted", where="store"
        )
        restricted = tmp_path / "restricted"
        (restricted / "licensed").mkdir(parents=True)
        (restricted / "licensed" / "secret.tif").write_bytes(b"s")
        monkeypatch.setenv("ETHOS_RESTRICTED_DIR", str(restricted))
        before = sorted(restricted.rglob("*"))

        path = catalogue(reader).path("licensed/secret.tif")

        assert path.samefile(restricted / "licensed" / "secret.tif")
        assert sorted(restricted.rglob("*")) == before
        assert not (reader.cache / "licensed").exists()
        assert store.downloads() == []

    def test_a_restricted_file_missing_from_its_cache_is_an_error_not_a_download(
        self, reader, store, tmp_path, monkeypatch
    ):
        reader.dataset(
            "licensed", {"secret.tif": "s"}, access="restricted", where="store"
        )
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        monkeypatch.setenv("ETHOS_RESTRICTED_DIR", str(restricted))

        with pytest.raises(ethos_data.AccessError, match="secret.tif"):
            catalogue(reader).path("licensed/secret.tif")
        assert store.downloads() == []


class TestPlan:
    BOTH = """
        both:
          title: Both files
          include:
            - dataset: flat
    """

    def test_a_plan_reports_what_a_fetch_would_download_and_downloads_nothing(
        self, reader, store
    ):
        reader.dataset("flat", {"a.csv": "1,2\n", "b.csv": "345\n"}, where="store")
        (reader.cache / "flat").mkdir(parents=True)
        (reader.cache / "flat" / "a.csv").write_bytes(b"1,2\n")
        data = ethos_data.collections(reader.collections(self.BOTH))

        report = data.plan("both")

        assert [r.key for r in report["present"]] == ["flat/a.csv"]
        assert [r.key for r in report["missing"]] == ["flat/b.csv"]
        assert report["bytes_to_download"] == 4
        assert store.downloads() == []

    def test_fetch_plan_names_each_file_it_would_download(self, reader, store, capsys):
        reader.dataset("flat", {"a.csv": "1,2\n", "b.csv": "345\n"}, where="store")
        collections = reader.collections(self.BOTH)

        code = ethos_data.tool_main(
            collections, tool="faketool", argv=["fetch", "both", "--plan"]
        )

        out = capsys.readouterr().out
        assert code == 0
        assert "to download:" in out
        assert "+ flat/a.csv" in out and "+ flat/b.csv" in out
        assert store.downloads() == []

    def test_fetch_downloads_what_the_plan_listed(self, reader, store, capsys):
        reader.dataset("flat", {"a.csv": "1,2\n", "b.csv": "345\n"}, where="store")
        collections = reader.collections(self.BOTH)

        code = ethos_data.tool_main(
            collections, tool="faketool", argv=["fetch", "both"]
        )

        assert code == 0
        assert sorted(store.downloads()) == ["/flat/a.csv", "/flat/b.csv"]
        assert (reader.cache / "flat" / "b.csv").read_text() == "345\n"
