"""Catalogue releases, and the bounds a collections file sets on them.

Characterisation tests for [Write a collections file]: releases are numbered
``vYYYY.MM.N`` and compare as numbers; a collections file accepts one release
or a range; the catalogue the settings choose is refused outside the range,
naming both; with no catalogue set, a public release within the range is read;
and ``publish`` keeps the list of public releases that makes that possible.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import ethos_data
from ethos_data import config
from ethos_data.errors import CatalogVersionError, CollectionError
from ethos_data.model.versions import Bounds, Version


class TestReleases:
    def test_they_compare_as_numbers(self):
        assert Version.parse("v2026.09.10") > Version.parse("v2026.09.9")
        assert Version.parse("v2026.10.1") > Version.parse("v2026.09.12")
        assert str(Version.parse(" v2026.09.2 ")) == "v2026.09.2"

    @pytest.mark.parametrize(
        "text", ["v2026.9.1", "2026.09.1", "v2026.13.1", "v2026.09.0", "v2026.09", 2026]
    )
    def test_anything_else_is_refused_with_the_form(self, text):
        with pytest.raises(ValueError, match="vYYYY.MM.N"):
            Version.parse(text)

    def test_bounds_accept_a_range_or_one_release(self):
        between = Bounds.from_document(
            {"min_version": "v2026.09.1", "max_version": "v2026.12.9"}
        )
        assert between.admits(Version.parse("v2026.10.3"))
        assert not between.admits(Version.parse("v2027.01.1"))
        assert not between.admits(Version.parse("v2026.08.1"))
        exact = Bounds.from_document({"exact_version": "v2026.09.2"})
        assert exact.admits(Version.parse("v2026.09.2"))
        assert not exact.admits(Version.parse("v2026.09.3"))

    @pytest.mark.parametrize(
        "document, message",
        [
            (
                {"exact_version": "v2026.09.2", "min_version": "v2026.09.1"},
                "cannot be combined",
            ),
            (
                {"min_version": "v2026.10.1", "max_version": "v2026.09.1"},
                "is older than",
            ),
            ({"max_version": "v2026.09.1"}, "needs min_version"),
            (
                {"min_version": "v2026.09.1", "newest": True},
                "newest is not one of them",
            ),
        ],
    )
    def test_bounds_that_make_no_sense_are_refused(self, document, message):
        with pytest.raises(ValueError, match=message):
            Bounds.from_document(document)


class TestTheStamp:
    def test_a_release_in_catalog_yaml_reaches_the_index(self, tmp_path):
        from support import SourceCatalogue

        source = SourceCatalogue(tmp_path, version="v2026.09.2")
        source.dataset("flat", {"a.csv": "1"})

        assert source.build()[0] == 0
        assert source.index()["version"] == "v2026.09.2"

    def test_a_release_that_is_not_one_is_refused(self, tmp_path):
        from support import SourceCatalogue

        source = SourceCatalogue(tmp_path, version="1.0")

        code, _, err = source.build()

        assert code == 1
        assert "catalog.yaml: version: '1.0' is not a catalogue release" in err

    def test_publish_lists_every_public_release(self, tmp_path):
        from support import SourceCatalogue

        source = SourceCatalogue(tmp_path, version="v2026.09.1")
        source.dataset("flat", {"a.csv": "1"})
        target = tmp_path / "public"
        target.mkdir()
        assert source.build()[0] == 0
        assert source.publish(target)[0] == 0

        source.catalog_yaml["version"] = "v2026.09.2"
        source._write_yaml(source.root / "catalog.yaml", source.catalog_yaml)
        assert source.build()[0] == 0
        assert source.publish(target)[0] == 0

        published = json.loads(
            (target / "datacatalog.json").read_text(encoding="utf-8")
        )
        assert published["version"] == "v2026.09.2"
        assert published["ethos:releases"] == ["v2026.09.1", "v2026.09.2"]
        assert source.publish(target, check=True)[0] == 0


def bounded(reader, bounds: dict) -> Path:
    """A collections file that bounds the catalogue release instead of pinning one."""
    reader.dataset("flat", {"a.csv": "1\n"}, where="store")
    path = reader.root.parent / "bounded.yaml"
    document = {
        "catalog": bounds,
        "collections": {"flat": {"include": [{"dataset": "flat"}]}},
    }
    path.write_bytes(yaml.safe_dump(document).encode("utf-8"))
    return path


class TestTheBoundsOnLoad:
    def test_a_configured_catalogue_within_them_is_read(self, reader, monkeypatch):
        collections = bounded(reader, {"min_version": "v2026.09.1"})
        monkeypatch.setenv(
            "ETHOS_DATA_CATALOG", str(reader.write(version="v2026.10.1"))
        )

        data = ethos_data.collections(collections)

        assert data.settings.catalog_version == "v2026.10.1"

    def test_one_outside_them_is_refused_naming_both(self, reader, monkeypatch):
        collections = bounded(reader, {"min_version": "v2026.09.1"})
        monkeypatch.setenv(
            "ETHOS_DATA_CATALOG", str(reader.write(version="v2026.08.3"))
        )

        with pytest.raises(CatalogVersionError) as refused:
            ethos_data.collections(collections)

        message = refused.value.message
        assert "is release v2026.08.3" in message
        assert "bounded.yaml accepts only min_version v2026.09.1" in message

    def test_a_catalogue_without_a_release_is_refused(self, reader):
        collections = bounded(reader, {"exact_version": "v2026.09.2"})

        with pytest.raises(CatalogVersionError, match="records no release"):
            ethos_data.collections(collections, catalog=str(reader.write()))

    def test_a_bounds_mapping_that_makes_no_sense_is_a_collection_error(self, reader):
        collections = bounded(reader, {"max_version": "v2026.09.1"})

        with pytest.raises(
            CollectionError, match="bounded.yaml: catalog: needs min_version"
        ):
            ethos_data.collections(collections, catalog=str(reader.write()))


@pytest.fixture
def public(reader, tmp_path, monkeypatch):
    """Public releases as directories, and the latest one where the public catalogue is."""
    releases = tmp_path / "releases"
    template = str(releases / "{version}" / "datacatalog.json")
    monkeypatch.setattr(config, "PUBLIC_RELEASE_URL", template)
    reader.dataset("flat", {"a.csv": "1\n"}, where="store")
    for version in ("v2026.09.1", "v2026.09.2", "v2026.10.1"):
        index = Path(template.format(version=version))
        index.parent.mkdir(parents=True)
        written = json.loads(reader.write(version=version).read_text(encoding="utf-8"))
        # The release's own descriptors, beside its index.
        written["datasets"][0]["path"] = str(
            reader.root / "datasets" / "flat" / "datapackage.json"
        )
        index.write_bytes(json.dumps(written).encode("utf-8"))
    latest = json.loads(
        Path(template.format(version="v2026.10.1")).read_text(encoding="utf-8")
    )
    latest["ethos:releases"] = ["v2026.09.1", "v2026.09.2", "v2026.10.1"]
    main = tmp_path / "main" / "datacatalog.json"
    main.parent.mkdir()
    main.write_bytes(json.dumps(latest).encode("utf-8"))
    monkeypatch.setattr(config, "DEFAULT_CATALOG", str(main))
    return template


class TestAPublicRelease:
    def test_exact_version_reads_that_release(self, reader, public):
        data = ethos_data.collections(bounded(reader, {"exact_version": "v2026.09.2"}))

        assert data.catalog.location == public.format(version="v2026.09.2")
        assert data.settings.catalog_source == "the public release v2026.09.2"

    def test_a_range_reads_the_newest_release_within_it(self, reader, public):
        data = ethos_data.collections(
            bounded(reader, {"min_version": "v2026.09.1", "max_version": "v2026.09.9"})
        )

        assert data.catalog.location == public.format(version="v2026.09.2")
        assert data.settings.catalog_source.startswith("the public release v2026.09.2")

    def test_a_range_no_release_meets_says_which_there_are(self, reader, public):
        with pytest.raises(CatalogVersionError) as refused:
            ethos_data.collections(bounded(reader, {"min_version": "v2027.01.1"}))

        assert "v2026.09.1, v2026.09.2, v2026.10.1" in refused.value.message
