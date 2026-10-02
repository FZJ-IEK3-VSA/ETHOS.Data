"""The format specifications: templates, schemas, rules and what they derive.

The parity tests compare the specifications with the code that still enforces
the same rules today (``maintain.manifest`` and ``maintain.publish``). They
are what makes switching that code over to the specifications safe, and they
go when it has switched.
"""

from __future__ import annotations

import copy

import pytest
import yaml

from ethos_data import formats
from ethos_data.errors import DescriptorError
from ethos_data.formats import keys as k

SAMPLE = {
    "name": "sample-data",
    "description": "A sample",
    "title": "Sample data",
    "source_dir": "/data/sample",
    "contact": "a.person",
    "publication_url": "https://example.org/ethos-data",
    "collection": "my_workflow",
    "dataset": "sample-data",
}


def render(name: str) -> dict:
    values = {key: SAMPLE[key] for key in formats.placeholders(name)}
    return yaml.safe_load(formats.template(name, **values))


class TestTemplates:
    @pytest.mark.parametrize(
        "name", [n for n in formats.template_names() if n.startswith("dataset-")]
    )
    def test_every_dataset_template_passes_the_build_rules_and_lints_clean(self, name):
        meta = render(name)
        formats.dataset.check(meta)
        assert formats.dataset.lint(meta) == []

    def test_the_catalogue_template_is_a_valid_catalog_yaml(self):
        meta = render("catalog")
        formats.catalogue.check(meta)
        formats.CatalogMeta.model_validate(meta)

    def test_the_collections_template_is_a_valid_collections_file(self):
        document = render("collections")
        formats.CollectionsFile.model_validate(document)
        assert formats.collections_file.lint(document) == []

    def test_the_minimal_template_is_what_staging_documents(self):
        assert render("dataset-minimal") == {
            "name": "sample-data",
            "source_dir": ".",
            "description": "A sample",
        }

    def test_a_placeholder_left_unfilled_is_refused(self):
        with pytest.raises(KeyError):
            formats.template("dataset-minimal", name="only-a-name")


class TestSchemas:
    def test_the_committed_schemas_are_current(self, tmp_path):
        """Run `python -m ethos_data.formats` after changing a specification."""
        written = formats.write_schemas(tmp_path)
        committed = formats.schemas_dir()
        for path in written:
            assert (committed / path.name).read_text(
                encoding="utf-8"
            ) == path.read_text(encoding="utf-8"), f"{path.name} is stale"
        assert {p.name for p in committed.glob("*.schema.json")} == {
            p.name for p in written
        }

    def test_a_schema_names_keys_as_files_spell_them(self):
        properties = formats.schema("dataset")["properties"]
        assert properties[k.ACCESS]["enum"] == list(k.ACCESS_CLASSES)
        assert properties[k.SOURCE_DIR]["x-ethos"]["published"] is False


class TestLint:
    def test_an_unknown_ethos_key_is_named(self):
        meta = {"source_dir": ".", "ethos:acess": "public"}
        assert formats.dataset.lint(meta) == [
            "ethos:acess is not a key of the dataset.yaml format; a typo?"
        ]

    def test_a_value_of_the_wrong_type_is_named(self):
        warnings = formats.dataset.lint({"source_dir": ".", "title": 2024})
        assert warnings == ["title: Input should be a valid string"]

    def test_a_number_where_a_quoted_version_belongs(self):
        (warning,) = formats.dataset.lint({"source_dir": ".", "version": 4})
        assert 'version: "4"' in warning

    def test_a_licence_status_outside_the_vocabulary(self):
        (warning,) = formats.dataset.lint(
            {"source_dir": ".", k.LICENSE_STATUS: "pending"}
        )
        assert "'pending'" in warning

    def test_keys_the_format_does_not_know_otherwise_pass(self):
        meta = {"source_dir": ".", "keywords": ["wind"], "ethos:mood": {"zoom": 7}}
        assert formats.dataset.lint(meta) == [
            "ethos:mood is not a key of the dataset.yaml format; a typo?"
        ]

    def test_keys_the_catalogue_used_before_the_reference_named_them_are_known(self):
        meta = {
            "source_dir": ".",
            "ethos:provenance": "Copied unchanged from the archive.",
            "ethos:verified": "2026-09-10",
            "ethos:input_datasets": ["a", "b"],
            "ethos:tiling": {"scheme": "web-mercator-xyz", "zoom": 7},
            "ethos:additional_variables": {"blh": "Boundary-layer height [m]"},
        }
        assert formats.dataset.lint(meta) == []


# -- parity with the code that enforces the same rules today ---------------------

BROKEN = [
    {"ethos:access": "secret"},
    {"ethos:visibility": "listed"},
    {"ethos:visibility": "hidden", "ethos:access": "public"},
    {"ethos:visibility": "hidden", "ethos:access": "internal"},
    {
        "ethos:access": "restricted",
        "ethos:visibility": "hidden",
        "ethos:embargo": {"until": "unspecified", "reason": "x"},
        "ethos:remote_prefix": "x",
    },
    {"ethos:origin": "found"},
    {"contributors": "a person"},
    {"contributors": ["a person"]},
    {"contributors": [{"roles": ["author"]}]},
    {"contributors": [{"title": "A", "roles": "author"}]},
    {"contributors": [{"title": "A", "roles": {"author": 1}}]},
    {"contributors": [{"title": "A", "roles": ["writer"]}]},
    {"ethos:origin": "created"},
    {
        "ethos:origin": "derived",
        "contributors": [{"title": "A", "roles": ["author"]}],
    },
    {
        "ethos:origin": "derived",
        "contributors": [{"title": "A", "roles": ["author"]}],
        "sources": [{"title": "x"}],
    },
    {"licenses": {"name": "CC-BY-4.0"}},
    {"licenses": ["CC-BY-4.0"]},
    {"licenses": [{"title": "Some terms"}]},
    {"licenses": [{"name": "CC0-1.0", "ethos:applies_to": "*.tif"}]},
]


def _legacy_message(meta: dict) -> str | None:
    """What the build's own validators say about ``meta``, without the name."""
    from ethos_data.maintain import manifest

    meta = copy.deepcopy(meta)
    try:
        manifest.validate_classification("n", meta)
        manifest.validate_provenance("n", meta)
        manifest.validate_licenses("n", meta)
    except DescriptorError as error:
        return error.message.removeprefix("n: ")
    return None


@pytest.mark.parametrize("meta", BROKEN, ids=lambda m: ",".join(m))
def test_the_rules_say_what_the_build_says(meta):
    expected = _legacy_message({"source_dir": ".", **meta})
    assert expected is not None, "a broken example the build accepts"
    with pytest.raises(DescriptorError) as raised:
        formats.dataset.check({"source_dir": ".", **meta})
    assert raised.value.message == expected


def test_the_strip_list_is_the_one_publish_applies():
    from ethos_data.maintain.publish import STRIP_FROM_PACKAGE

    assert set(formats.dataset.STRIPPED) == set(STRIP_FROM_PACKAGE)


def test_the_inherited_keys_are_the_ones_the_build_hands_down():
    from ethos_data.maintain import INHERITED_KEYS

    assert formats.dataset.INHERITED == INHERITED_KEYS


@pytest.mark.parametrize(
    "package",
    [
        {
            "name": "flat",
            "title": "Flat",
            "version": "2.0",
            "ethos:access": "internal",
            "ethos:visibility": "hidden",
            "ethos:total_bytes": 3,
            "ethos:file_count": 1,
            "licenses": [{"name": "CC0-1.0"}],
        },
        {"name": "bare", "ethos:total_bytes": 0, "ethos:file_count": 0},
        {
            "name": "family",
            "title": "A family",
            "ethos:namespace": True,
            "ethos:total_bytes": 5,
            "ethos:file_count": 2,
        },
    ],
    ids=["dataset", "defaults", "namespace"],
)
def test_the_index_row_is_the_one_the_build_writes(package, tmp_path):
    import json

    from ethos_data.maintain import manifest

    root = tmp_path / "catalogue"
    directory = root / "datasets" / package["name"]
    directory.mkdir(parents=True)
    (directory / "datapackage.json").write_text(json.dumps(package), encoding="utf-8")
    (root / "catalog.yaml").write_text("name: test\n", encoding="utf-8")

    (row,) = manifest.build_catalog(root, [directory])["datasets"]

    assert formats.index_row(package, row["path"]) == row


@pytest.mark.parametrize(
    "meta",
    [
        {},
        {"licenses": [{"name": "CC0-1.0"}]},
        {"ethos:license_status": "resolved"},
        {"ethos:license_status": "unresolved"},
        {"licenses": []},
    ],
)
def test_the_licence_question_is_answered_as_the_reader_answers_it(meta):
    from ethos_data.catalogs import license_settled

    assert formats.license_settled(meta) == license_settled(meta)
