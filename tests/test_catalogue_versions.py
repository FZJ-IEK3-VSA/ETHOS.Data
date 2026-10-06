"""Catalogue releases, and the bounds a collections file sets on them.

Characterisation tests for [Write a collections file]: releases are numbered
``vMAJOR.MINOR.PATCH`` and compare as numbers; a collections file accepts one
release or a range, each bound a release or a prefix such as ``v1.3``; the
catalogue the settings choose is refused outside the bounds, naming both; with
no catalogue set, a public release within the bounds is read; and ``publish``
keeps the list of public releases that makes that possible.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import ethos_data
from ethos_data import config
from ethos_data.errors import CatalogVersionError, CollectionError
from ethos_data.formats import collections_file
from ethos_data.model.versions import Bounds, Version


def admitted(bounds: dict, *versions: str) -> list[str]:
    """Which of ``versions`` the ``catalog:`` mapping ``bounds`` admits."""
    parsed = Bounds.from_document(bounds)
    return [v for v in versions if parsed.admits(Version.parse(v))]


class TestReleases:
    def test_they_compare_as_numbers(self):
        assert Version.parse("v1.10.0") > Version.parse("v1.9.3")
        assert Version.parse("v2.0.0") > Version.parse("v1.12.4")
        assert str(Version.parse("v1.2.0")) == "v1.2.0"

    @pytest.mark.parametrize(
        "text", ["v1.2", "1.2.0", "v01.2.0", "v1.2.0-rc1", " v1.2.0", "v2026.09", 1]
    )
    def test_anything_else_is_refused_with_the_form(self, text):
        with pytest.raises(ValueError, match="vMAJOR.MINOR.PATCH"):
            Version.parse(text)


class TestBounds:
    def test_they_accept_a_range_or_one_release(self):
        versions = ("v1.1.9", "v1.2.0", "v1.3.5", "v1.4.1", "v1.4.2")
        assert admitted(
            {"min_version": "v1.2.0", "max_version": "v1.4.1"}, *versions
        ) == ["v1.2.0", "v1.3.5", "v1.4.1"]
        assert admitted({"exact_version": "v1.3.5"}, *versions) == ["v1.3.5"]

    def test_a_prefix_as_min_version_is_its_first_release(self):
        assert admitted({"min_version": "v1.3"}, "v1.2.9", "v1.3.0", "v2.0.0") == [
            "v1.3.0",
            "v2.0.0",
        ]

    def test_a_prefix_as_max_version_is_its_last_release(self):
        assert admitted(
            {"min_version": "v1", "max_version": "v1.3"}, "v1.0.0", "v1.3.12", "v1.4.0"
        ) == ["v1.0.0", "v1.3.12"]

    def test_a_prefix_as_exact_version_is_every_release_it_starts(self):
        versions = ("v1.2.9", "v1.3.0", "v1.3.12", "v1.4.0", "v2.0.0")
        assert admitted({"exact_version": "v1.3"}, *versions) == ["v1.3.0", "v1.3.12"]
        assert admitted({"exact_version": "v1"}, *versions) == [
            "v1.2.9",
            "v1.3.0",
            "v1.3.12",
            "v1.4.0",
        ]

    def test_only_a_full_exact_version_names_one_release(self):
        assert Bounds.from_document({"exact_version": "v1.3.0"}).release() == (
            Version(1, 3, 0)
        )
        assert Bounds.from_document({"exact_version": "v1.3"}).release() is None
        assert Bounds.from_document({"min_version": "v1.3.0"}).release() is None

    @pytest.mark.parametrize(
        "document, message",
        [
            (
                {"exact_version": "v1.2.0", "min_version": "v1.1.0"},
                "cannot be combined",
            ),
            ({"min_version": "v1.4", "max_version": "v1.3.9"}, "is older than"),
            ({"max_version": "v1.2.0"}, "needs min_version"),
            ({"min_version": "v1.02"}, "is not a catalogue release or a prefix"),
        ],
    )
    def test_bounds_that_make_no_sense_are_refused(self, document, message):
        with pytest.raises(ValueError, match=message):
            Bounds.from_document(document)

    def test_a_prefix_maximum_within_the_minimum_is_a_range(self):
        assert admitted(
            {"min_version": "v1.3.2", "max_version": "v1.3"}, "v1.3.1", "v1.3.2"
        ) == ["v1.3.2"]

    def test_an_unknown_key_is_a_lint_warning(self):
        document = {"catalog": {"min_version": "v1", "newest": True}}

        assert collections_file.lint(document) == [
            "catalog.newest is not a release bound"
        ]


class TestTheStamp:
    def test_a_release_in_catalog_yaml_reaches_the_index(self, tmp_path):
        from support import SourceCatalogue

        source = SourceCatalogue(tmp_path, version="v1.2.0")
        source.dataset("flat", {"a.csv": "1"})

        assert source.build()[0] == 0
        assert source.index()["version"] == "v1.2.0"

    def test_a_release_that_is_not_one_is_refused(self, tmp_path):
        from support import SourceCatalogue

        source = SourceCatalogue(tmp_path, version="1.0")

        code, _, err = source.build()

        assert code == 1
        assert "catalog.yaml: version: '1.0' is not a catalogue release" in err

    def test_publish_lists_every_public_release(self, tmp_path):
        from support import SourceCatalogue

        source = SourceCatalogue(tmp_path, version="v1.0.0")
        source.dataset("flat", {"a.csv": "1"})
        target = tmp_path / "public"
        target.mkdir()
        assert source.build()[0] == 0
        assert source.publish(target)[0] == 0

        source.catalog_yaml["version"] = "v1.1.0"
        source._write_yaml(source.root / "catalog.yaml", source.catalog_yaml)
        assert source.build()[0] == 0
        assert source.publish(target)[0] == 0

        published = json.loads(
            (target / "datacatalog.json").read_text(encoding="utf-8")
        )
        assert published["version"] == "v1.1.0"
        assert published["ethos:releases"] == ["v1.0.0", "v1.1.0"]
        assert source.publish(target, check=True)[0] == 0


def bounded(reader, bounds: object) -> Path:
    """A collections file that bounds the catalogue release."""
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
        collections = bounded(reader, {"min_version": "v1.1"})
        monkeypatch.setenv("ETHOS_DATA_CATALOG", str(reader.write(version="v1.2.0")))

        data = ethos_data.collections(collections)

        assert data.settings.catalog_version == "v1.2.0"

    def test_one_outside_them_is_refused_naming_both(self, reader, monkeypatch):
        collections = bounded(reader, {"min_version": "v1.1"})
        monkeypatch.setenv("ETHOS_DATA_CATALOG", str(reader.write(version="v1.0.3")))

        with pytest.raises(CatalogVersionError) as refused:
            ethos_data.collections(collections)

        message = refused.value.message
        assert "is release v1.0.3" in message
        assert "bounded.yaml accepts only min_version v1.1" in message

    def test_a_catalogue_without_a_release_is_refused(self, reader):
        collections = bounded(reader, {"exact_version": "v1.2.0"})

        with pytest.raises(CatalogVersionError, match="records no release"):
            ethos_data.collections(collections, catalog=str(reader.write()))

    def test_bounds_that_make_no_sense_are_a_collection_error(self, reader):
        collections = bounded(reader, {"max_version": "v1.2.0"})

        with pytest.raises(
            CollectionError,
            match="bounded.yaml is not a valid collections file:\n  catalog: needs min_version",
        ):
            ethos_data.collections(collections, catalog=str(reader.write()))

    def test_every_problem_is_named_with_its_place(self, reader):
        collections = bounded(reader, {"min_version": "1.2", "max_version": "v1.x"})

        with pytest.raises(CollectionError) as refused:
            ethos_data.collections(collections, catalog=str(reader.write()))

        lines = refused.value.message.splitlines()[1:]
        assert [line.split(":")[0] for line in lines] == [
            "  catalog.min_version",
            "  catalog.max_version",
        ]

    def test_a_location_is_not_a_bound(self, reader):
        collections = bounded(reader, "https://example.invalid/datacatalog.json")

        with pytest.raises(
            CollectionError, match="catalog: must be a mapping, got str"
        ):
            ethos_data.collections(collections, catalog=str(reader.write()))


#: The public releases the ``public`` fixture serves, oldest first.
PUBLISHED = ("v1.0.0", "v1.1.0", "v1.1.1", "v2.0.0")


@pytest.fixture
def public(reader, tmp_path, monkeypatch):
    """Public releases as directories, and the latest one where the public catalogue is."""
    releases = tmp_path / "releases"
    template = str(releases / "{version}" / "datacatalog.json")
    monkeypatch.setattr(config, "PUBLIC_RELEASE_URL", template)
    reader.dataset("flat", {"a.csv": "1\n"}, where="store")
    for version in PUBLISHED:
        index = Path(template.format(version=version))
        index.parent.mkdir(parents=True)
        written = json.loads(reader.write(version=version).read_text(encoding="utf-8"))
        # The release's own descriptors, beside its index.
        written["datasets"][0]["path"] = str(
            reader.root / "datasets" / "flat" / "datapackage.json"
        )
        index.write_bytes(json.dumps(written).encode("utf-8"))
    latest = json.loads(
        Path(template.format(version=PUBLISHED[-1])).read_text(encoding="utf-8")
    )
    latest["ethos:releases"] = list(PUBLISHED)
    main = tmp_path / "main" / "datacatalog.json"
    main.parent.mkdir()
    main.write_bytes(json.dumps(latest).encode("utf-8"))
    monkeypatch.setattr(config, "DEFAULT_CATALOG", str(main))
    return template


class TestAPublicRelease:
    def test_exact_version_reads_that_release(self, reader, public, monkeypatch):
        # The release's tag is read without consulting the list on main.
        monkeypatch.setattr(config, "DEFAULT_CATALOG", "https://example.invalid/x")

        data = ethos_data.collections(bounded(reader, {"exact_version": "v1.1.0"}))

        assert data.catalog.location == public.format(version="v1.1.0")
        assert data.settings.catalog_source == "the public release v1.1.0"

    def test_a_prefix_reads_the_newest_release_it_starts(self, reader, public):
        data = ethos_data.collections(bounded(reader, {"exact_version": "v1.1"}))

        assert data.catalog.location == public.format(version="v1.1.1")
        assert data.settings.catalog_source == (
            "the public release v1.1.1, the newest within exact_version v1.1"
        )

    def test_a_range_reads_the_newest_release_within_it(self, reader, public):
        data = ethos_data.collections(
            bounded(reader, {"min_version": "v1.0.0", "max_version": "v1"})
        )

        assert data.catalog.location == public.format(version="v1.1.1")

    def test_a_range_no_release_meets_says_which_there_are(self, reader, public):
        with pytest.raises(CatalogVersionError) as refused:
            ethos_data.collections(bounded(reader, {"min_version": "v3"}))

        assert "v1.0.0, v1.1.0, v1.1.1, v2.0.0" in refused.value.message
