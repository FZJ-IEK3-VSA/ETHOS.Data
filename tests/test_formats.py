"""The format specifications: templates, schemas, rules and what they derive."""

from __future__ import annotations

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

    def test_provenance_tiling_and_input_keys_are_known(self):
        meta = {
            "source_dir": ".",
            "ethos:provenance": "Copied unchanged from the archive.",
            "ethos:verified": "2026-09-10",
            "ethos:input_datasets": ["a", "b"],
            "ethos:tiling": {"scheme": "web-mercator-xyz", "zoom": 7},
            "ethos:additional_variables": {"blh": "Boundary-layer height [m]"},
        }
        assert formats.dataset.lint(meta) == []


# -- the rules, with the messages maintainers know -----------------------------

BROKEN = [
    ({"ethos:access": "secret"}, "ethos:access must be one of ('public', 'restricted'), got 'secret'"),
    ({"ethos:access": "internal"}, "ethos:access must be one of ('public', 'restricted'), got 'internal'"),
    ({"ethos:visibility": "listed"}, "ethos:visibility must be one of ('public', 'hidden'), got 'listed'"),
    ({"ethos:visibility": "hidden", "ethos:access": "public"}, "access=public with visibility=hidden makes no sense"),
    ({"ethos:visibility": "hidden", "ethos:access": "restricted"}, "visibility=hidden needs an ethos:embargo block"),
    (
        {
            "ethos:access": "restricted",
            "ethos:visibility": "hidden",
            "ethos:embargo": {"until": "unspecified", "reason": "x"},
            "ethos:remote_prefix": "x",
        },
        "restricted data must not declare ethos:remote_prefix",
    ),
    ({"ethos:origin": "found"}, "ethos:origin must be one of ('downloaded', 'derived', 'created'), got 'found'"),
    ({"contributors": "a person"}, "contributors must be a list of mappings."),
    ({"contributors": ["a person"]}, "contributors[0] must be a mapping with at least a 'title'."),
    ({"contributors": [{"roles": ["author"]}]}, "contributors[0] needs a 'title'"),
    (
        {"contributors": [{"title": "A", "roles": "author"}]},
        "contributors[0]: 'roles' is a list in Data Package v2 -- write roles: [author], not roles: author.",
    ),
    ({"contributors": [{"title": "A", "roles": {"author": 1}}]}, "contributors[0]: 'roles' must be a list."),
    ({"contributors": [{"title": "A", "roles": ["writer"]}]}, "contributors[0]: unknown role 'writer'."),
    ({"ethos:origin": "created"}, "ethos:origin is 'created', which claims this data was made here"),
    (
        {"ethos:origin": "derived", "contributors": [{"title": "A", "roles": ["author"]}]},
        "ethos:origin: derived needs 'sources'",
    ),
    (
        {
            "ethos:origin": "derived",
            "contributors": [{"title": "A", "roles": ["author"]}],
            "sources": [{"title": "x"}],
        },
        "ethos:origin: derived needs ethos:derivation",
    ),
    ({"licenses": {"name": "CC-BY-4.0"}}, "licenses must be a list, even with one entry"),
    ({"licenses": ["CC-BY-4.0"]}, "licenses[0] must be a mapping with 'name' and/or 'path'."),
    ({"licenses": [{"title": "Some terms"}]}, "licenses[0] has neither 'name' nor 'path'."),
    (
        {"licenses": [{"name": "CC0-1.0", "ethos:applies_to": "*.tif"}]},
        "licenses[0]: ethos:applies_to must be a list of glob patterns.",
    ),
    ({"ethos:include": "*.tif"}, "ethos:include must be a list of patterns, got str"),
    ({"ethos:exclude": []}, "ethos:exclude is an empty list, which would select nothing."),
    ({"ethos:shard_depth": -1}, "ethos:shard_depth must not be negative"),
    ({"ethos:uploaded": True}, "declares ethos:uploaded: true and still has source_dir"),
]  # fmt: skip


@pytest.mark.parametrize(
    "meta, message",
    BROKEN,
    ids=lambda case: ",".join(case) if isinstance(case, dict) else None,
)
def test_each_rule_says_what_is_wrong_in_the_words_maintainers_know(meta, message):
    with pytest.raises(DescriptorError) as raised:
        formats.dataset.check({"source_dir": ".", **meta})
    assert raised.value.message.startswith(message)


def test_a_frozen_dataset_needs_no_source_and_a_built_one_does():
    formats.dataset.check({"ethos:frozen": True})
    with pytest.raises(DescriptorError, match="source_dir is required"):
        formats.dataset.check({})


def test_defaults_are_written_in_the_fixed_key_order():
    meta = {"name": "x", "title": "X"}
    formats.dataset.apply_defaults(meta)
    assert list(meta) == [
        "name",
        "title",
        "ethos:access",
        "ethos:visibility",
        "ethos:origin",
    ]
    assert (
        formats.dataset.apply_defaults({"ethos:access": "restricted"})["ethos:access"]
        == "restricted"
    )


def test_a_family_may_not_describe_files_access_or_terms():
    for meta, subject in (
        ({"source_dir": "."}, "source_dir says it does"),
        ({"ethos:access": "public"}, "must not declare ethos:access"),
        ({"licenses": [{"name": "CC0-1.0"}]}, "must not carry licensing"),
    ):
        with pytest.raises(DescriptorError, match=subject):
            formats.dataset.check_namespace(meta)


def test_publish_strips_what_the_specification_marks_unpublished():
    from ethos_data.maintain.publish import STRIP_FROM_PACKAGE

    assert set(STRIP_FROM_PACKAGE) == {
        "source_dir",
        "ethos:uploaded",
        "ethos:frozen",
        "ethos:embargo",
        "ethos:license_note",
    }


def test_an_index_row_holds_the_promoted_keys_and_what_the_build_counts():
    package = {
        **formats.dataset.apply_defaults({"name": "x", "title": "X"}),
        "version": "1.0",
        "ethos:total_bytes": 3,
        "ethos:file_count": 1,
    }

    row = formats.index_row(package, "datasets/x/datapackage.json")

    assert set(row) == set(formats.dataset.PROMOTED) | {
        "path",
        "ethos:total_bytes",
        "ethos:file_count",
    }


def test_a_family_hands_down_homepage_contact_and_attribution_only():
    from ethos_data.maintain import INHERITED_KEYS

    assert INHERITED_KEYS == ("homepage", "ethos:contact", "ethos:attribution")


@pytest.mark.parametrize(
    "meta, settled",
    [
        ({}, False),
        ({"licenses": [{"name": "CC0-1.0"}]}, True),
        ({"ethos:license_status": "resolved"}, True),
        ({"ethos:license_status": "unresolved"}, False),
        ({"licenses": []}, False),
    ],
)
def test_the_licence_question_is_settled_by_a_licence_or_an_explicit_resolved(
    meta, settled
):
    assert formats.license_settled(meta) is settled
