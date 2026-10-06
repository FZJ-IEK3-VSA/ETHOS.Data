"""Bundles: data a package keeps in its repository, authoritative for that package.

Tests for the decisions "Keep attributed data in bundles that are
authoritative for their package" and "Let a bundle be ahead of the
catalogue, and warn until it is realigned". A bundle holds public, visible
data with settled licensing; a handle reads it first, hash-checked, and
reads no catalogue index when its bundles hold every input; a bundle ahead
of the catalogue is read all the same, with a warning; ``bundle update``
records changes against the alignment and the alignment itself; the
download switch reads a bundled file the catalogue holds through the
catalogue route; ``bundle export`` writes a new bundle through the handle;
``catalog add-bundle`` takes the ahead datasets into the catalogue.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest
import yaml
from support import SourceCatalogue, digest

import ethos_data
from ethos_data import BundleAlignmentWarning
from ethos_data.bundles import (
    _WARNED,
    ModifiedBundleWarning,
    create_bundle,
    export_bundle,
    load_bundle,
    update_bundle,
)
from ethos_data.catalogs import load_catalog
from ethos_data.errors import BundleError

LICENSED = {
    "licenses": [{"name": "CC-BY-4.0", "path": "https://example.invalid/cc-by"}],
}


@pytest.fixture(autouse=True)
def _fresh_warnings():
    _WARNED.clear()
    yield
    _WARNED.clear()


def describe(root: Path, name: str, **meta: object) -> None:
    """Fill a dataset's description in, as a package maintainer does after create."""
    path = root / "datasets" / name / "dataset.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"name": name, "title": f"The {name} data", **LICENSED, **meta}),
        encoding="utf-8",
    )


def bundled(root: Path, datasets: dict[str, dict[str, bytes]], **create) -> Path:
    """A bundle of ``datasets``, created and described, its descriptions recorded."""
    for name, files in datasets.items():
        for relative, data in files.items():
            target = root / "data" / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    create_bundle(root, **create)
    for name in datasets:
        describe(root, name)
    update_bundle(root)
    return root


def manifest(root: Path) -> dict:
    return json.loads((root / "bundle.json").read_text(encoding="utf-8"))


def same_description(name: str) -> dict:
    """The descriptor keys a catalogue holds when it holds the bundle's description."""
    return {"title": f"The {name} data", **LICENSED}


class TestCreate:
    def test_it_inventories_the_files_and_drafts_the_descriptions(self, tmp_path):
        (tmp_path / "data" / "sites").mkdir(parents=True)
        (tmp_path / "data" / "sites" / "a.csv").write_bytes(b"1\n")
        (tmp_path / "data" / "fam" / "era5").mkdir(parents=True)
        (tmp_path / "data" / "fam" / "era5" / "x.nc").write_bytes(b"nc")

        created = create_bundle(tmp_path, family="fam")

        assert created.datasets == ["fam/era5", "sites"]
        assert sorted(created.drafted) == ["fam", "fam/era5", "sites"]
        document = manifest(tmp_path)
        assert document["format"] == "ethos-data-bundle"
        assert document["datasets"]["sites"]["alignment"] is None
        assert document["datasets"]["sites"]["resources"][0]["path"] == "a.csv"
        assert list(document["families"]) == ["fam"]

    def test_a_draft_whose_terms_nobody_read_is_refused_when_read(self, tmp_path):
        (tmp_path / "data" / "sites").mkdir(parents=True)
        (tmp_path / "data" / "sites" / "a.csv").write_bytes(b"1\n")
        create_bundle(tmp_path)

        with pytest.raises(BundleError, match="sites: its licensing is not settled"):
            load_bundle(tmp_path)

    def test_a_bundle_is_not_created_twice(self, tmp_path):
        bundled(tmp_path, {"sites": {"a.csv": b"1\n"}})

        with pytest.raises(BundleError, match="is a bundle already"):
            create_bundle(tmp_path)


class TestWhatABundleHolds:
    @pytest.mark.parametrize(
        "meta, message",
        [
            ({"ethos:access": "restricted"}, "sites is restricted: a bundle holds public data only"),
            ({"ethos:visibility": "hidden"}, "sites is hidden"),
            ({"licenses": None, "ethos:license_status": "unresolved"}, "licensing is not settled"),
        ],
    )  # fmt: skip
    def test_only_public_visible_data_with_settled_terms(self, tmp_path, meta, message):
        root = bundled(tmp_path, {"sites": {"a.csv": b"1\n"}})
        describe(root, "sites", **meta)

        with pytest.raises(BundleError, match=message):
            update_bundle(root)
        with pytest.raises(BundleError, match=message):
            load_bundle(root)

    def test_a_licence_document_travels_with_the_files(self, tmp_path):
        root = bundled(tmp_path, {"sites": {"a.csv": b"1\n"}})
        describe(
            root,
            "sites",
            licenses=[{"name": "Terms", "ethos:document": "terms.txt"}],
        )
        (root / "datasets" / "sites" / "terms.txt").write_bytes(b"the terms")
        update_bundle(root)

        assert load_bundle(root).verify()[-1].key == "datasets/sites/terms.txt"
        (root / "datasets" / "sites" / "terms.txt").unlink()
        with pytest.raises(BundleError, match="lacks datasets/sites/terms.txt"):
            load_bundle(root)

    @pytest.mark.parametrize("name", ["../escaped", "/absolute", "a/../b", "a\\b"])
    def test_an_unsafe_name_is_refused(self, tmp_path, name):
        root = bundled(tmp_path, {"sites": {"a.csv": b"1\n"}})
        document = manifest(root)
        document["datasets"][name] = document["datasets"].pop("sites")
        (root / "bundle.json").write_text(json.dumps(document), encoding="utf-8")

        with pytest.raises(BundleError):
            load_bundle(root)


class TestReading:
    @pytest.fixture
    def package(self, tmp_path, monkeypatch):
        root = bundled(
            tmp_path / "bundle", {"sites": {"a.csv": b"1\n", "b.csv": b"22\n"}}
        )
        collections = tmp_path / "collections.yaml"
        collections.write_text(
            "collections:\n  inputs:\n    include:\n      - dataset: sites\n"
            "    paths:\n      sites: sites\n",
            encoding="utf-8",
        )
        # No catalogue anywhere: a handle whose bundles hold every input reads none.
        monkeypatch.setenv("ETHOS_DATA_CATALOG", str(tmp_path / "nowhere.json"))
        return root, collections

    def test_a_handle_reads_its_bundle_and_no_catalogue_index(self, package):
        root, collections = package
        data = ethos_data.collections(collections, tool="mytool", bundles=[root])

        with pytest.warns(
            BundleAlignmentWarning, match="sites \\(not in the catalogue\\)"
        ):
            inputs = data.paths("inputs")

        assert inputs["sites"] == root / "data" / "sites"
        assert data._catalog is None, "the index was never read"

    def test_the_warning_comes_once_per_bundle(self, package):
        root, collections = package
        data = ethos_data.collections(collections, tool="mytool", bundles=[root])

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            data.fetch("inputs")
            data.fetch("inputs")

        ahead = [w for w in caught if issubclass(w.category, BundleAlignmentWarning)]
        assert len(ahead) == 1
        assert "mytool-data propose" in str(ahead[0].message)

    def test_a_changed_file_is_an_error_never_a_download(self, package):
        root, collections = package
        (root / "data" / "sites" / "a.csv").write_bytes(b"9\n")
        data = ethos_data.collections(collections, bundles=[root])

        with pytest.raises(BundleError, match="sites/a.csv is in the bundle"):
            data.fetch("inputs")

    def test_one_test_may_read_a_change_nobody_recorded(self, package):
        root, _ = package
        (root / "data" / "sites" / "a.csv").write_bytes(b"9\n")
        bundle = load_bundle(root)

        with pytest.raises(BundleError, match="Record the change"):
            bundle.fetch("sites")
        with pytest.warns(ModifiedBundleWarning, match="sites/a.csv"):
            files = bundle.fetch("sites", allow_modified=True)
        assert files["sites/a.csv"].read_bytes() == b"9\n"
        assert next(f.status for f in bundle.verify("sites/a.csv")) == "modified"

        (root / "data" / "sites" / "b.csv").unlink()
        with pytest.raises(BundleError, match="lacks sites/b.csv"):
            bundle.fetch("sites", allow_modified=True)

    def test_verify_names_a_file_nobody_recorded(self, package):
        root, _ = package
        (root / "data" / "sites" / "c.csv").write_bytes(b"333\n")

        statuses = {f.key: f.status for f in load_bundle(root).verify()}

        assert statuses["sites/c.csv"] == "unrecorded"


class TestUpdate:
    def test_changes_are_kept_against_the_alignment(self, tmp_path, reader):
        files = {"a.csv": b"1\n", "b.csv": b"22\n"}
        reader.dataset("sites", files, descriptor=same_description("sites"))
        catalog = load_catalog(str(reader.write()))
        root = bundled(tmp_path / "bundle", {"sites": files})
        update_bundle(root, catalog=catalog)
        assert manifest(root)["datasets"]["sites"]["alignment"] == {
            "revision": 1,
            "release": None,
        }

        (root / "data" / "sites" / "a.csv").write_bytes(b"9\n")
        (root / "data" / "sites" / "c.csv").write_bytes(b"333\n")
        update_bundle(root)
        changes = manifest(root)["datasets"]["sites"]["changes"]
        assert [(c["path"], c["change"]) for c in changes] == [
            ("a.csv", "changed"),
            ("c.csv", "added"),
        ]
        assert load_bundle(root).ahead() == {"sites": "2 files changed"}

        (root / "data" / "sites" / "a.csv").write_bytes(b"1\n")
        (root / "data" / "sites" / "c.csv").unlink()
        update_bundle(root)
        assert manifest(root)["datasets"]["sites"]["changes"] == []

    def test_the_alignment_is_recorded_once_the_catalogue_holds_what_it_holds(
        self, tmp_path, reader
    ):
        files = {"a.csv": b"1\n"}
        root = bundled(tmp_path / "bundle", {"sites": files})
        assert load_bundle(root).ahead() == {"sites": "not in the catalogue"}
        reader.dataset("sites", files, descriptor=same_description("sites"))

        update = update_bundle(root, catalog=load_catalog(str(reader.write())))

        assert update.aligned == {"sites": 1}
        assert load_bundle(root).ahead() == {}

    def test_the_catalogues_version_is_taken(self, tmp_path, reader, store):
        root = bundled(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
        reader.dataset(
            "sites",
            {"a.csv": b"2\n", "b.csv": b"3\n"},
            where="store",
            descriptor=same_description("sites"),
            index={"ethos:revision": 2},
        )
        catalog = load_catalog(str(reader.write()))

        update = update_bundle(
            root,
            catalog=catalog,
            from_catalog=["sites"],
            roots=ethos_data.config.Roots(public=tmp_path / "cache"),
        )

        assert update.taken == ["sites"]
        assert (root / "data" / "sites" / "b.csv").read_bytes() == b"3\n"
        entry = manifest(root)["datasets"]["sites"]
        assert entry["alignment"]["revision"] == 2 and entry["changes"] == []


class TestTheCatalogueReadAnyway:
    @pytest.fixture
    def package(self, tmp_path, reader):
        root = bundled(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
        reader.dataset("sites", {"a.csv": b"1\n"}, descriptor=same_description("sites"))
        reader.dataset("other", {"o.csv": b"o"})
        update_bundle(root, catalog=load_catalog(str(reader.write())))
        return root

    def test_a_later_revision_in_the_catalogue_warns(self, package, reader):
        reader.entries[0]["ethos:revision"] = 2
        collections = reader.collections(
            """
            inputs:
              include:
                - dataset: sites
                - dataset: other
            """
        )
        data = ethos_data.collections(collections, bundles=[package])

        with pytest.warns(BundleAlignmentWarning, match="behind the catalogue: sites"):
            data.fetch("inputs")

    def test_a_withdrawn_dataset_warns(self, package, reader):
        del reader.entries[0]
        collections = reader.collections(
            """
            inputs:
              include:
                - dataset: other
            """
        )
        data = ethos_data.collections(collections, bundles=[package])

        with pytest.warns(BundleAlignmentWarning, match="withdrawn from the catalogue"):
            data.fetch("inputs")


def test_a_bundled_dataset_the_catalogue_withholds_is_refused(tmp_path, reader):
    root = bundled(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
    reader.dataset("sites", {"a.csv": b"1\n"}, access="restricted")
    reader.dataset("other", {"o.csv": b"o"})
    collections = reader.collections(
        """
        inputs:
          include:
            - dataset: other
        """
    )
    data = ethos_data.collections(collections, bundles=[root])

    with pytest.raises(BundleError, match="lists as restricted"):
        data.fetch("inputs")


class TestTheDownloadSwitch:
    def test_a_file_the_catalogue_holds_is_read_through_it(
        self, tmp_path, reader, store
    ):
        root = bundled(
            tmp_path / "bundle", {"sites": {"a.csv": b"1\n", "b.csv": b"22\n"}}
        )
        reader.dataset(
            "sites",
            {"a.csv": b"1\n", "b.csv": b"20\n"},
            where="store",
            descriptor=same_description("sites"),
        )
        collections = reader.collections(
            """
            inputs:
              include:
                - dataset: sites
            """
        )
        data = ethos_data.collections(collections, bundles=[root], download=True)

        files = data.fetch("inputs")

        assert files["sites/a.csv"] == reader.cache / "sites" / "a.csv"
        assert files["sites/b.csv"] == root / "data" / "sites" / "b.csv"
        assert store.downloads() == ["/sites/a.csv"]
        assert not (reader.cache / "sites" / "b.csv").exists(), "never a bundle's bytes"
        assert data.settings.download


class TestExport:
    def test_it_writes_a_new_bundle_through_the_handle(self, tmp_path, reader, store):
        reader.dataset(
            "sites",
            {"a.csv": b"1\n", "b.csv": b"22\n"},
            where="store",
            descriptor=same_description("sites"),
        )
        collections = reader.collections(
            """
            inputs:
              include:
                - dataset: sites
                  files: [a.csv]
            """
        )
        data = ethos_data.collections(collections, tool="mytool")

        bundle = export_bundle(data, tmp_path / "exported", ["inputs"])

        entry = bundle.datasets["sites"]
        assert (entry.alignment.revision, entry.selection) == (1, "some")
        assert sorted(bundle.resources) == ["sites/a.csv"]
        description = yaml.safe_load(
            (bundle.path / "datasets" / "sites" / "dataset.yaml").read_text("utf-8")
        )
        assert description["title"] == "The sites data"
        assert bundle.fetch()["sites/a.csv"].read_bytes() == b"1\n"

    def test_a_bundled_dataset_keeps_its_alignment_and_changes(self, tmp_path):
        root = bundled(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
        collections = tmp_path / "collections.yaml"
        collections.write_text(
            "collections:\n  inputs:\n    include:\n      - dataset: sites\n",
            encoding="utf-8",
        )
        data = ethos_data.collections(collections, bundles=[root])

        with pytest.warns(BundleAlignmentWarning):
            bundle = export_bundle(data, tmp_path / "exported", "inputs")

        assert bundle.datasets["sites"].alignment is None
        assert bundle.datasets["sites"].selection == "all"

    def test_an_existing_target_is_refused(self, tmp_path, reader):
        reader.dataset("sites", {"a.csv": b"1\n"}, descriptor=same_description("sites"))
        collections = reader.collections(
            """
            inputs:
              include:
                - dataset: sites
            """
        )
        (tmp_path / "exported").mkdir()

        with pytest.raises(BundleError, match="exists"):
            export_bundle(
                ethos_data.collections(collections), tmp_path / "exported", "inputs"
            )

    def test_restricted_data_is_refused(self, tmp_path, reader):
        reader.dataset(
            "licensed",
            {"a.csv": b"1\n"},
            access="restricted",
            descriptor={**same_description("licensed"), "ethos:access": "restricted"},
        )
        collections = reader.collections(
            """
            inputs:
              include:
                - dataset: licensed
            """
        )
        data = ethos_data.collections(collections)

        with pytest.raises(Exception, match="restricted"):
            export_bundle(data, tmp_path / "exported", "inputs")


class TestThePackageCommand:
    def test_create_update_verify_and_fetch(self, tmp_path, monkeypatch):
        (tmp_path / "data" / "sites").mkdir(parents=True)
        (tmp_path / "data" / "sites" / "a.csv").write_bytes(b"1\n")
        collections = tmp_path / "collections.yaml"
        collections.write_text("collections: {}\n", encoding="utf-8")
        monkeypatch.setenv("ETHOS_DATA_CATALOG", str(tmp_path / "nowhere.json"))

        def tool(*argv):
            return ethos_data.tool_main(
                str(collections), prog="mytool-data", argv=list(argv)
            )

        assert tool("bundle", "create", str(tmp_path)) == 0
        describe(tmp_path, "sites")
        assert tool("bundle", "update", str(tmp_path)) == 0
        assert tool("bundle", "verify", str(tmp_path)) == 0
        (tmp_path / "data" / "sites" / "a.csv").write_bytes(b"9\n")
        assert tool("bundle", "verify", str(tmp_path)) == 1
        assert tool("bundle", "update", str(tmp_path)) == 0
        assert tool("bundle", "fetch", str(tmp_path), "sites") == 0


class TestAddBundle:
    @pytest.fixture
    def catalogue(self, tmp_path):
        return SourceCatalogue(tmp_path)

    def test_a_new_dataset_is_added_from_a_build_input(self, catalogue, tmp_path):
        root = bundled(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
        into = tmp_path / "inputs"

        code, _, err = catalogue.catalog("add-bundle", str(root), "--into", str(into))

        assert code == 0, err
        assert (into / "sites" / "a.csv").read_bytes() == b"1\n"
        status = catalogue.status("sites")
        assert (status["state"], status["source_dir"]) == ("built", str(into / "sites"))
        assert catalogue.package("sites")["resources"][0]["hash"] == digest(b"1\n")

    def test_an_access_change_from_a_bundle_is_refused(self, catalogue, tmp_path):
        root = bundled(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
        catalogue.dataset(
            "sites",
            {"a.csv": "1\n"},
            ethos_access="restricted",
            ethos_restriction="Ask the custodian.",
        )
        assert catalogue.build()[0] == 0
        document = manifest(root)
        document["datasets"]["sites"]["changes"] = [
            {"path": "dataset.yaml", "change": "changed", "document": True, "was": None}
        ]
        document["datasets"]["sites"]["alignment"] = {"revision": 1, "release": None}
        (root / "bundle.json").write_text(json.dumps(document), encoding="utf-8")

        code, _, err = catalogue.catalog(
            "add-bundle", str(root), "--into", str(tmp_path / "inputs")
        )

        assert code == 1
        assert "not for access or visibility" in err

    def test_an_aligned_bundle_has_nothing_to_take(self, catalogue, tmp_path, reader):
        root = bundled(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
        reader.dataset("sites", {"a.csv": b"1\n"}, descriptor=same_description("sites"))
        update_bundle(root, catalog=load_catalog(str(reader.write())))

        code, out, _ = catalogue.catalog(
            "add-bundle", str(root), "--into", str(tmp_path / "inputs")
        )

        assert code == 0
        assert "is aligned" in out


def test_verify_fails_on_a_changed_bundled_file(tmp_path, monkeypatch):
    root = bundled(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
    collections = tmp_path / "collections.yaml"
    collections.write_text(
        "collections:\n  inputs:\n    include:\n      - dataset: sites\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ETHOS_DATA_CATALOG", str(tmp_path / "nowhere.json"))
    (root / "data" / "sites" / "a.csv").write_bytes(b"9\n")
    data = ethos_data.collections(collections, bundles=[root])

    findings = ethos_data.verify(
        data.view_for(data.resolve("inputs")), data.resolve("inputs")
    )

    assert [(f.status, f.ok) for f in findings] == [("wrong checksum", False)]
