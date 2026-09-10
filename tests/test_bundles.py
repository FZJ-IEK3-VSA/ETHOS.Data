"""Offline fixture copies retain canonical identity through development edits."""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

import pooch
import pytest
import yaml

from ethos_data.bundles import (
    BundleError, ModifiedBundleWarning, export_bundle, load_bundle,
)


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("bundle operation attempted network access")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(pooch, "retrieve", forbidden)


@pytest.fixture
def catalogue(tmp_path):
    source = tmp_path / "existing-fixtures"
    source.mkdir()
    payloads = {"sites.shp": b"shape", "sites.dbf": b"table", "nested/a.bin": b"123", "empty.bin": b""}
    resources = []
    for name, data in payloads.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        record = {"name": name.replace("/", "-"), "path": name, "bytes": len(data), "hash": digest(data)}
        if name == "sites.shp":
            record["ethos:sidecars"] = ["sites.dbf"]
            record["licenses"] = [{"name": "CC-BY-4.0", "path": "https://example.invalid/licence"}]
            record["ethos:provenance"] = {"derived_from": "example-source"}
            record["ethos:license_note"] = "private per-resource review"
        resources.append(record)
    package = {
        "name": "fixture", "title": "Fixture dataset", "ethos:access": "public",
        "ethos:license_status": "resolved", "licenses": [{"name": "CC0-1.0"}],
        "sources": [{"title": "Generated example", "path": "https://example.invalid/provenance"}],
        "ethos:embargo": {"reason": "old private review"}, "ethos:license_note": "private review",
        "ethos:uploaded": True, "source_dir": "/private/workstation/path",
        "resources": resources,
    }
    descriptor = tmp_path / "datapackage.json"
    descriptor.write_text(json.dumps(package))
    index = tmp_path / "datacatalog.json"
    index.write_text(json.dumps({
        "name": "test-catalog", "version": "v1", "ethos:catalog_role": "published",
        "ethos:publication_url": "https://dcache.invalid/data",
        "datasets": [{"name": "fixture", "path": "datapackage.json", "ethos:access": "public",
                      "ethos:license_status": "resolved", "ethos:remote_prefix": "immutable/fixture/v1"}],
    }))
    collections = tmp_path / "collections.yaml"
    collections.write_text(yaml.safe_dump({
        "catalog": "datacatalog.json",
        "collections": {
            "shape": {"include": [{"dataset": "fixture", "files": ["sites.shp"]}]},
            "test_suite": {"extends": ["shape"], "include": [{"dataset": "fixture", "files": ["nested/*", "empty.bin"]}]},
        },
    }))
    return {"source": source, "collections": collections, "index": index,
            "descriptor": descriptor, "payloads": payloads}


def export(catalogue, target, **kwargs):
    return export_bundle(catalogue["collections"], ["shape", "test_suite"], target,
                         dataset_roots={"fixture": catalogue["source"]}, source_revision="commit-123", **kwargs)


def rewrite(bundle, mutate):
    path = bundle.path / "bundle.json"
    document = json.loads(path.read_text())
    mutate(document)
    path.write_text(json.dumps(document))


def test_portable_snapshot_with_sidecars_and_provenance(catalogue, tmp_path, monkeypatch):
    staging = tmp_path / "staging" / "fixture"
    staging.mkdir(parents=True)
    (staging / "sites.shp").write_bytes(b"uncatalogued development")
    monkeypatch.setenv("ETHOS_STAGING_DIR", str(staging.parent))
    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "empty-cache"))
    (tmp_path / "ethos-data.yaml").write_text("dataset_roots:\n  fixture: /missing/ambient/override\n")
    monkeypatch.chdir(tmp_path)
    bundle = export(catalogue, tmp_path / "bundle")
    assert bundle.names() == ["shape", "test_suite"]
    assert bundle.source["catalog"] == str(catalogue["index"])
    assert bundle.source["revision"] == "commit-123"
    assert bundle.source["catalog_version"] == "v1"
    assert bundle.datasets["fixture"]["licenses"] == [{"name": "CC0-1.0"}]
    assert bundle.datasets["fixture"]["sources"][0]["title"] == "Generated example"
    package = bundle.datasets["fixture"]
    assert not ({"ethos:embargo", "ethos:license_note", "ethos:uploaded", "source_dir"} & package.keys())
    shape_record = next(record for record in package["resources"] if record["path"] == "sites.shp")
    assert shape_record["licenses"] == [{"name": "CC-BY-4.0", "path": "https://example.invalid/licence"}]
    assert shape_record["ethos:provenance"] == {"derived_from": "example-source"}
    assert "ethos:license_note" not in shape_record
    assert set(bundle.fetch("shape")) == {"fixture/sites.shp", "fixture/sites.dbf"}

    # The snapshot and files move together and no longer need their source.
    shutil.rmtree(catalogue["source"])
    catalogue["index"].unlink()
    catalogue["descriptor"].unlink()
    moved = tmp_path / "different-package" / "fixtures"
    moved.parent.mkdir()
    bundle.path.rename(moved)
    monkeypatch.chdir(tmp_path.parent)
    loaded = load_bundle(moved / "bundle.json")
    files = loaded.fetch("test_suite")
    assert {key: path.read_bytes() for key, path in files.items()} == {
        "fixture/" + name: data for name, data in catalogue["payloads"].items()
    }
    assert all(finding.ok for finding in loaded.verify("test_suite"))
    assert not (tmp_path / "empty-cache").exists()


@pytest.mark.parametrize("changed", [b"abc", b"longer changed file", b""])
def test_development_override_reports_changes_and_preserves_hashes(catalogue, tmp_path, changed):
    bundle = export(catalogue, tmp_path / "bundle")
    manifest = (bundle.path / "bundle.json").read_bytes()
    key = "fixture/nested/a.bin"
    path = bundle.fetch("test_suite")[key]
    path.write_bytes(changed)
    with pytest.raises(BundleError, match="differ from the catalogue.*fixture/nested/a.bin"):
        bundle.fetch("test_suite")
    with pytest.warns(ModifiedBundleWarning, match="fixture/nested/a.bin"):
        assert bundle.fetch("test_suite", allow_modified=True)[key] == path
    finding = next(finding for finding in bundle.verify("test_suite") if finding.key == key)
    assert finding.status == "modified"
    assert finding.expected_hash == digest(b"123")
    assert finding.actual_hash == digest(changed)
    assert (bundle.path / "bundle.json").read_bytes() == manifest
    with pytest.raises(BundleError, match="differ from the catalogue"):
        load_bundle(bundle.path).fetch("test_suite")
    # The override is local to each call and does not affect other collections.
    assert len(bundle.fetch("shape")) == 2


def test_missing_file_is_an_error_even_during_development(catalogue, tmp_path):
    bundle = export(catalogue, tmp_path / "bundle")
    bundle.fetch("shape")["fixture/sites.dbf"].unlink()
    assert any(f.status == "missing" for f in bundle.verify("shape"))
    with pytest.raises(BundleError, match="missing bundled files: fixture/sites.dbf"):
        bundle.fetch("shape", allow_modified=True)


def test_missing_manifest_is_not_replaced_or_fetched(catalogue, tmp_path):
    bundle = export(catalogue, tmp_path / "bundle")
    (bundle.path / "bundle.json").unlink()
    with pytest.raises(BundleError, match="cannot read bundle metadata"):
        load_bundle(bundle.path)
    assert not (bundle.path / "bundle.json").exists()


def test_export_input_errors_are_actionable(catalogue, tmp_path):
    with pytest.raises(BundleError, match="unknown collections: typo"):
        export_bundle(catalogue["collections"], "typo", tmp_path / "bundle")
    with pytest.raises(BundleError, match="cannot load collections"):
        export_bundle(tmp_path / "missing.yaml", "shape", tmp_path / "bundle")
    catalogue["descriptor"].unlink()
    with pytest.raises(BundleError, match="cannot resolve collection 'shape'"):
        export(catalogue, tmp_path / "bundle")


@pytest.mark.parametrize("bad_record", [None, "resource", [], {}, {"name": "a", "path": "a", "bytes": 1, "hash": ""}])
def test_invalid_resource_metadata_errors_cleanly(catalogue, tmp_path, bad_record):
    bundle = export(catalogue, tmp_path / "bundle")
    rewrite(bundle, lambda doc: doc["datasets"]["fixture"].update(resources=[bad_record]))
    with pytest.raises(BundleError):
        load_bundle(bundle.path)


@pytest.mark.parametrize("access", ["staging", "internal", "restricted", "unknown"])
def test_unsupported_access_snapshot_is_rejected(catalogue, tmp_path, access):
    bundle = export(catalogue, tmp_path / "bundle")
    rewrite(bundle, lambda doc: doc["datasets"]["fixture"].update({"ethos:access": access}))
    with pytest.raises(BundleError, match="not a public catalogue snapshot"):
        load_bundle(bundle.path)


def test_missing_resource_metadata_and_sidecars_fail(catalogue, tmp_path):
    bundle = export(catalogue, tmp_path / "bundle")
    rewrite(bundle, lambda doc: doc["collections"]["shape"].remove("fixture/sites.dbf"))
    with pytest.raises(BundleError, match="lacks sidecar metadata"):
        load_bundle(bundle.path)
    rewrite(bundle, lambda doc: doc["collections"]["shape"].append("fixture/missing.bin"))
    with pytest.raises(BundleError, match="missing resource metadata"):
        load_bundle(bundle.path)


@pytest.mark.parametrize("unsafe", ["../escaped", "/absolute", "a/../escaped", "a//b", "a/./b", "C:/drive", "a\\b"])
def test_unsafe_metadata_paths_are_rejected(catalogue, tmp_path, unsafe):
    bundle = export(catalogue, tmp_path / "bundle")
    rewrite(bundle, lambda doc: doc["datasets"]["fixture"]["resources"][0].update(path=unsafe))
    with pytest.raises(BundleError, match="unsafe resource path"):
        load_bundle(bundle.path)


def test_symlink_escape_cannot_bypass_verification(catalogue, tmp_path):
    bundle = export(catalogue, tmp_path / "bundle")
    fixture = bundle.fetch("shape")["fixture/sites.shp"]
    fixture.unlink()
    fixture.symlink_to(catalogue["source"] / "sites.shp")
    with pytest.raises(BundleError, match="escapes"):
        bundle.fetch("shape", allow_modified=True)
    manifest = bundle.path / "bundle.json"
    original = tmp_path / "outside-manifest.json"
    manifest.rename(original)
    manifest.symlink_to(original)
    with pytest.raises(BundleError, match="escapes"):
        load_bundle(bundle.path)


def test_export_rejects_changed_input_and_preserves_existing_bundle(catalogue, tmp_path):
    target = tmp_path / "bundle"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("existing")
    with pytest.raises(BundleError, match="target already exists"):
        export(catalogue, target)
    assert sentinel.read_text() == "existing"
    (catalogue["source"] / "nested/a.bin").write_bytes(b"abc")
    with pytest.raises(BundleError, match="input fixture differs.*fixture/nested/a.bin"):
        export(catalogue, tmp_path / "new-bundle")
    assert not (tmp_path / "new-bundle").exists()
    assert not list(tmp_path.glob(".ethos-bundle-*"))


def test_export_rejects_source_symlink_escape(catalogue, tmp_path):
    path = catalogue["source"] / "sites.shp"
    outside = tmp_path / "outside.shp"
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(BundleError, match="escapes"):
        export(catalogue, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_export_from_shards_flattens_snapshot(catalogue, tmp_path):
    package = json.loads(catalogue["descriptor"].read_text())
    (tmp_path / "root.json").write_text(json.dumps({"resources": [r for r in package["resources"] if "/" not in r["path"]]}))
    (tmp_path / "nested.json").write_text(json.dumps({"resources": [r for r in package["resources"] if "/" in r["path"]]}))
    package.pop("resources")
    package.update({"ethos:shard_depth": 1, "ethos:shards": [
        {"prefix": "_root", "path": "root.json"}, {"prefix": "nested", "path": "nested.json"},
    ]})
    catalogue["descriptor"].write_text(json.dumps(package))
    bundle = export(catalogue, tmp_path / "bundle")
    assert "ethos:shards" not in bundle.datasets["fixture"]
    shape = next(record for record in bundle.datasets["fixture"]["resources"] if record["path"] == "sites.shp")
    assert shape["licenses"][0]["name"] == "CC-BY-4.0"
    assert shape["ethos:provenance"] == {"derived_from": "example-source"}
    (tmp_path / "root.json").unlink()
    (tmp_path / "nested.json").unlink()
    assert len(load_bundle(bundle.path).fetch("test_suite")) == 4


def test_subset_export_never_loads_unselected_shards(catalogue, tmp_path):
    package = json.loads(catalogue["descriptor"].read_text())
    (tmp_path / "root.json").write_text(json.dumps({"resources": [r for r in package["resources"] if "/" not in r["path"]]}))
    package.pop("resources")
    package.update({"ethos:shard_depth": 1, "ethos:shards": [
        {"prefix": "_root", "path": "root.json"},
        {"prefix": "nested", "path": "https://must-not-fetch.invalid/nested.json"},
    ]})
    catalogue["descriptor"].write_text(json.dumps(package))
    bundle = export_bundle(catalogue["collections"], "shape", tmp_path / "bundle",
                           dataset_roots={"fixture": catalogue["source"]})
    assert len(bundle.fetch("shape")) == 2
    assert len(bundle.datasets["fixture"]["resources"]) == 2


@pytest.mark.parametrize("field,value", [("ethos:access", "restricted"), ("ethos:visibility", "hidden")])
def test_export_rejects_non_public_index_and_descriptor(catalogue, tmp_path, field, value):
    document = json.loads(catalogue["descriptor"].read_text())
    document[field] = value
    catalogue["descriptor"].write_text(json.dumps(document))
    with pytest.raises(BundleError, match="descriptor is not public"):
        export(catalogue, tmp_path / "descriptor-bundle")
    index = json.loads(catalogue["index"].read_text())
    index["datasets"][0][field] = value
    catalogue["index"].write_text(json.dumps(index))
    with pytest.raises(BundleError, match="portable fixture bundles require public data"):
        export(catalogue, tmp_path / "index-bundle")


def test_remote_export_uses_authoritative_url_not_ambient_settings(catalogue, tmp_path, monkeypatch):
    monkeypatch.setenv("ETHOS_PUBLICATION_URL", "https://wrong.invalid/data")
    monkeypatch.setenv("ETHOS_STAGING_DIR", str(tmp_path / "staging"))
    calls = []

    def retrieve(*, url, known_hash, fname, path, progressbar):
        calls.append(url)
        resource_path = url.removeprefix("https://dcache.invalid/data/immutable/fixture/v1/")
        payload = catalogue["payloads"][resource_path]
        assert known_hash == digest(payload)
        destination = Path(path) / fname
        destination.write_bytes(payload)
        return str(destination)

    monkeypatch.setattr(pooch, "retrieve", retrieve)
    bundle = export_bundle(catalogue["collections"], "shape", tmp_path / "bundle")
    assert len(calls) == 2
    assert all(url.startswith("https://dcache.invalid/data/immutable/fixture/v1/") for url in calls)
    assert len(bundle.fetch("shape")) == 2


def test_fetch_leaves_read_only_bundle_unchanged(catalogue, tmp_path):
    bundle = export(catalogue, tmp_path / "bundle")
    paths = sorted(bundle.path.rglob("*"))
    before = {path: path.read_bytes() for path in paths if path.is_file()}
    try:
        for path in paths:
            path.chmod(0o555 if path.is_dir() else 0o444)
        bundle.path.chmod(0o555)
        assert len(load_bundle(bundle.path).fetch("test_suite")) == 4
        with pytest.raises(BundleError, match="not bundled"):
            bundle.fetch("not-exported", allow_modified=True)
        assert before == {path: path.read_bytes() for path in before}
    finally:
        bundle.path.chmod(0o755)
        for path in paths:
            path.chmod(0o755 if path.is_dir() else 0o644)
