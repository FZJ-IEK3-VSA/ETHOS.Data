"""ethos:origin, contributors and multi-licence datasets.

The case these exist for: most of the catalogue is mirrored data whose terms are
somebody else's, but some of it is ours -- the GeoTIFF conversions in
``landcover``, the whole of ``geothermal-resource`` -- and a dataset can hold
both at once, under different licences.

Run with pytest, or directly:  python tests/test_provenance.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from ethos_data.maintain.manifest import (
    apply_resource_licenses,
    render_dataset,
    validate_licenses,
    validate_provenance,
)


# -- ethos:origin -----------------------------------------------------------

def test_origin_defaults_to_downloaded():
    """The common case, and the conservative one: claim no authorship."""
    meta = {}
    assert validate_provenance("d", meta) == "downloaded"
    assert meta["ethos:origin"] == "downloaded"


def test_downloaded_needs_no_author():
    """Every dataset written before ethos:origin existed must keep building."""
    assert validate_provenance("d", {"sources": [{"title": "up"}]}) == "downloaded"


def test_unknown_origin_is_rejected():
    with pytest.raises(SystemExit, match="must be one of"):
        validate_provenance("d", {"ethos:origin": "invented"})


@pytest.mark.parametrize("origin", ["created", "derived"])
def test_authorship_claim_must_name_an_author(origin):
    """Claiming the data was made here without saying by whom is not a claim."""
    with pytest.raises(SystemExit, match="has to say by whom"):
        validate_provenance("d", {"ethos:origin": origin})


def test_derived_needs_sources_and_a_derivation():
    author = [{"title": "A Researcher", "roles": ["author"]}]

    with pytest.raises(SystemExit, match="derived FROM"):
        validate_provenance("d", {"ethos:origin": "derived", "contributors": author})

    with pytest.raises(SystemExit, match="needs ethos:derivation"):
        validate_provenance("d", {
            "ethos:origin": "derived",
            "contributors": author,
            "sources": [{"title": "upstream"}],
        })

    assert validate_provenance("d", {
        "ethos:origin": "derived",
        "contributors": author,
        "sources": [{"title": "upstream"}],
        "ethos:derivation": "gdalwarp to EPSG:3035, nearest neighbour.",
    }) == "derived"


def test_created_needs_only_an_author():
    """Created from scratch has no upstream to name -- that is the difference."""
    assert validate_provenance("d", {
        "ethos:origin": "created",
        "contributors": [{"title": "A Researcher", "roles": ["author"]}],
    }) == "created"


# -- contributors ----------------------------------------------------------

def test_v1_scalar_role_is_rejected_not_coerced():
    """Half-following two versions of the spec is worse than being told which."""
    with pytest.raises(SystemExit, match="list in Data Package v2"):
        validate_provenance("d", {"contributors": [{"title": "X", "roles": "author"}]})


def test_unknown_role_is_rejected():
    with pytest.raises(SystemExit, match="unknown role"):
        validate_provenance("d", {"contributors": [{"title": "X", "roles": ["archivist"]}]})


def test_contributor_needs_a_title():
    with pytest.raises(SystemExit, match="needs a 'title'"):
        validate_provenance("d", {"contributors": [{"roles": ["author"]}]})


# -- licences --------------------------------------------------------------

def test_licenses_may_hold_several():
    entries = [
        {"name": "CC-BY-4.0", "path": "https://creativecommons.org/licenses/by/4.0/"},
        {"name": "CC0-1.0", "path": "https://creativecommons.org/publicdomain/zero/1.0/"},
    ]
    assert validate_licenses("d", {"licenses": entries}) == entries


def test_licence_needs_a_name_or_a_path():
    """A bare title reads as a licence and identifies nothing."""
    with pytest.raises(SystemExit, match="neither 'name' nor 'path'"):
        validate_licenses("d", {"licenses": [{"title": "Some terms"}]})


def test_licenses_must_be_a_list():
    with pytest.raises(SystemExit, match="must be a list"):
        validate_licenses("d", {"licenses": {"name": "MIT"}})


def test_applies_to_must_be_a_list_of_patterns():
    with pytest.raises(SystemExit, match="list of glob patterns"):
        validate_licenses("d", {"licenses": [{"name": "MIT", "ethos:applies_to": "*.tif"}]})


def test_narrowed_licence_lands_on_matching_resources_only():
    resources = [{"path": "originals/a.nc"}, {"path": "converted/a.tif"}]
    apply_resource_licenses("d", resources, [
        {"name": "CC-BY-4.0", "ethos:applies_to": ["originals/**"]},
        {"name": "CC0-1.0"},
    ])
    assert resources[0]["licenses"] == [{"name": "CC-BY-4.0"}]
    # The unnarrowed licence stays at package level; the resource inherits it.
    assert "licenses" not in resources[1]


def test_applies_to_strips_itself_from_the_resource_copy():
    """On the file it was attached to, applies_to answers nobody's question."""
    resources = [{"path": "a.nc"}]
    apply_resource_licenses("d", resources, [{"name": "MIT", "ethos:applies_to": ["*.nc"]}])
    assert resources[0]["licenses"] == [{"name": "MIT"}]


def test_applies_to_matching_nothing_is_an_error():
    """Silently licensing no files is how data ships under terms nobody applied."""
    with pytest.raises(SystemExit, match="matches none of"):
        apply_resource_licenses("d", [{"path": "a.nc"}],
                                [{"name": "MIT", "ethos:applies_to": ["nope/**"]}])


def test_uncovered_files_warn_when_every_licence_is_narrowed(capsys):
    resources = [{"path": "a.nc"}, {"path": "b.tif"}]
    apply_resource_licenses("d", resources, [{"name": "MIT", "ethos:applies_to": ["*.nc"]}])
    assert "covered by no licence at all" in capsys.readouterr().err


# -- end to end ------------------------------------------------------------

def test_build_renders_package_and_resource_licences():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "src"
        (source / "originals").mkdir(parents=True)
        (source / "converted").mkdir(parents=True)
        (source / "originals" / "a.nc").write_text("upstream")
        (source / "converted" / "a.tif").write_text("ours")

        dataset_dir = root / "datasets" / "demo"
        dataset_dir.mkdir(parents=True)
        (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump({
            "name": "demo",
            "title": "Mixed provenance",
            "source_dir": str(source),
            "ethos:access": "public",
            "ethos:visibility": "public",
            "ethos:origin": "derived",
            "ethos:derivation": "gdalwarp, lossless.",
            "sources": [{"title": "upstream", "path": "https://example.invalid/"}],
            "contributors": [{"title": "A Researcher", "roles": ["author"]}],
            "licenses": [
                {"name": "CC-BY-4.0", "ethos:applies_to": ["originals/**"]},
                {"name": "CC0-1.0"},
            ],
        }))

        package = json.loads(render_dataset(dataset_dir)["datapackage.json"])

    assert package["ethos:origin"] == "derived"
    assert [c["title"] for c in package["contributors"]] == ["A Researcher"]
    # Both licences stay at package level, so a reader that never looks at a
    # resource still sees the full set.
    assert [entry["name"] for entry in package["licenses"]] == ["CC-BY-4.0", "CC0-1.0"]

    by_path = {r["path"]: r for r in package["resources"]}
    assert by_path["originals/a.nc"]["licenses"] == [{"name": "CC-BY-4.0"}]
    assert "licenses" not in by_path["converted/a.tif"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
