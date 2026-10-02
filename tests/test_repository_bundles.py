"""Repository bundles: test data a package keeps, reads first, and has the catalogue updated from.

Tests for "Keep data in the repository" and the bundle locator of the lookup
chain: ``bundle create`` and ``bundle update`` keep ``bundle.json``, a
package's handle reads its bundles before the catalogue, the download switch
takes the catalogue route, and ``catalog add-bundle`` brings the catalogue's
family up to the bundle, a published member by its next revision.
"""

from __future__ import annotations

import json
import warnings

import pytest
import yaml
from support import SourceCatalogue

import ethos_data
from ethos_data import bundles
from ethos_data.adapters.fakes import FakeStore
from ethos_data.bundles import (
    BundleError,
    UnpublishedBundleWarning,
    create_bundle,
    load_bundle,
    update_bundle,
)
from ethos_data.catalogs import load_catalog
from ethos_data.maintain import upload

LICENCE = "licenses:\n  - name: CC-BY-4.0\n    path: https://creativecommons.org/licenses/by/4.0/\n"


def lay_out(directory, files):
    for relative, content in files.items():
        target = directory / "data" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode() if isinstance(content, str) else content)


@pytest.fixture
def bundle_dir(tmp_path):
    """A package's bundle directory with two members, created and described."""
    directory = tmp_path / "pkg" / "test_data"
    lay_out(
        directory,
        {"fam/era5/a.nc": "1\n", "fam/era5/b.nc": "22\n", "fam/gwa/x.tif": "x"},
    )
    create_bundle(directory, "fam")
    for member in ("era5", "gwa"):
        draft = directory / "datasets" / "fam" / member / "dataset.yaml"
        draft.write_bytes(draft.read_bytes() + LICENCE.encode())
    return directory


@pytest.fixture(autouse=True)
def fresh_process(monkeypatch):
    """Each test a fresh process: nothing hashed, nobody warned yet."""
    monkeypatch.setattr(bundles, "_CHECKED", {})
    monkeypatch.setattr(bundles, "_WARNED", set())


class TestCreate:
    def test_it_inventories_the_files_and_drafts_the_descriptions(self, tmp_path):
        directory = tmp_path / "test_data"
        lay_out(directory, {"fam/era5/a.nc": "1\n", "fam/era5/sub/b.nc": "22\n"})

        bundle = create_bundle(directory, "fam")

        manifest = json.loads((directory / "bundle.json").read_text("utf-8"))
        assert (manifest["format"], manifest["family"]) == (
            "ethos-data-bundle-v2",
            "fam",
        )
        assert (manifest["version"], manifest["release"]) == (1, None)
        paths = [r["path"] for r in manifest["datasets"]["fam/era5"]["resources"]]
        assert paths == ["a.nc", "sub/b.nc"]
        draft = yaml.safe_load(
            (directory / "datasets/fam/era5/dataset.yaml").read_text("utf-8")
        )
        assert draft["name"] == "fam/era5"
        assert draft["source_dir"] == "../../../data/fam/era5"
        assert (
            yaml.safe_load((directory / "datasets/fam/dataset.yaml").read_text())[
                "name"
            ]
            == "fam"
        )
        assert bundle.repository and not bundle.published

    @pytest.mark.parametrize(
        "files, message",
        [
            ({}, "no data/fam/"),
            ({"fam/loose.txt": "x"}, "lie directly in data/fam/"),
        ],
    )
    def test_what_is_no_bundle_is_refused(self, tmp_path, files, message):
        directory = tmp_path / "test_data"
        directory.mkdir()
        lay_out(directory, files)

        with pytest.raises(BundleError, match=message):
            create_bundle(directory, "fam")

    def test_a_bundle_is_not_created_twice(self, bundle_dir):
        with pytest.raises(BundleError, match="is a bundle already"):
            create_bundle(bundle_dir, "fam")


class TestUpdate:
    def test_changes_go_into_the_unpublished_version(self, bundle_dir):
        lay_out(bundle_dir, {"fam/era5/b.nc": "23\n", "fam/era5/c.nc": "333\n"})

        update = update_bundle(bundle_dir)

        assert update.changed == {"fam/era5": ["b.nc"]}
        assert update.added == {"fam/era5": ["c.nc"]}
        assert update.bundle.version == 1

    def test_a_published_version_is_never_changed(self, bundle_dir, tmp_path):
        manifest = json.loads((bundle_dir / "bundle.json").read_text("utf-8"))
        manifest["release"] = "v2026.10.1"
        (bundle_dir / "bundle.json").write_text(json.dumps(manifest), encoding="utf-8")
        lay_out(bundle_dir, {"fam/era5/b.nc": "23\n"})

        update = update_bundle(bundle_dir)

        assert (update.bundle.version, update.bundle.release) == (2, None)

    def test_moves_gone_files_and_new_members_are_told_apart(self, bundle_dir):
        (bundle_dir / "data/fam/era5/a.nc").rename(
            bundle_dir / "data/fam/era5/moved.nc"
        )
        (bundle_dir / "data/fam/era5/b.nc").unlink()
        lay_out(bundle_dir, {"fam/new/n.csv": "n"})

        update = update_bundle(bundle_dir)

        assert update.moved == {"fam/era5": [("a.nc", "moved.nc")]}
        assert update.removed == {"fam/era5": ["b.nc"]}
        assert update.new_members == ["fam/new"]
        assert (bundle_dir / "datasets/fam/new/dataset.yaml").is_file()

    def test_the_release_that_holds_the_version_is_recorded(self, bundle_dir, reader):
        for name in ("fam/era5", "fam/gwa"):
            reader.dataset(
                name,
                {
                    r.path: (bundle_dir / "data" / r.key).read_bytes()
                    for r in load_bundle(bundle_dir).resources.values()
                    if r.dataset == name
                },
                where="nowhere",
            )
        catalog = load_catalog(str(reader.write(version="v2026.10.1")))

        update = update_bundle(bundle_dir, catalog)

        assert update.released == "v2026.10.1"
        assert load_bundle(bundle_dir).published

    def test_an_exported_bundle_is_exported_again_instead(self, tmp_path):
        directory = tmp_path / "exported"
        directory.mkdir()
        (directory / "bundle.json").write_text(
            json.dumps({"format": "ethos-data-bundle-v1"}), encoding="utf-8"
        )

        with pytest.raises(BundleError):
            update_bundle(directory)


@pytest.fixture
def package(bundle_dir, reader):
    """A package whose collection reads fam/era5, which only its bundle holds."""
    collections = reader.collections(
        """
        inputs:
          include:
            - dataset: fam/era5
        """
    )
    return collections, bundle_dir


class TestBundleFirst:
    def test_a_handle_reads_what_its_bundle_holds_and_says_it_is_unpublished(
        self, package, store
    ):
        collections, bundle_dir = package
        data = ethos_data.collections(collections, bundles=[bundle_dir])

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            files = data.fetch("inputs")
            data.fetch("inputs")

        assert files["fam/era5/a.nc"] == bundle_dir / "data/fam/era5/a.nc"
        assert store.downloads() == []
        unpublished = [w for w in caught if w.category is UnpublishedBundleWarning]
        assert len(unpublished) == 1
        assert "version 1 is not in the catalogue yet" in str(unpublished[0].message)

    def test_an_altered_bundled_file_is_an_error_not_a_download(self, package, store):
        collections, bundle_dir = package
        (bundle_dir / "data/fam/era5/a.nc").write_bytes(b"changed by hand\n")
        data = ethos_data.collections(collections, bundles=[bundle_dir])

        with pytest.raises(BundleError, match="never a reason to download"):
            data.fetch("inputs")

        assert store.downloads() == []
        with pytest.warns(UnpublishedBundleWarning):
            plan = data.plan("inputs")
        assert [r.path for r in plan["unavailable"]] == ["a.nc"]

    def test_the_download_switch_takes_the_catalogue_route(
        self, package, reader, monkeypatch
    ):
        collections, bundle_dir = package
        manifest = json.loads((bundle_dir / "bundle.json").read_text("utf-8"))
        records = {r["path"]: r for r in manifest["datasets"]["fam/era5"]["resources"]}
        reader.dataset(
            "fam/era5",
            {
                path: (bundle_dir / "data/fam/era5" / path).read_bytes()
                for path in records
            },
            where="store",
        )
        reader.write()
        manifest["release"] = "v2026.10.1"
        (bundle_dir / "bundle.json").write_text(json.dumps(manifest), encoding="utf-8")
        monkeypatch.setenv("ETHOS_DATA_DOWNLOAD", "1")

        files = ethos_data.collections(collections, bundles=[bundle_dir]).fetch(
            "inputs"
        )

        assert files["fam/era5/a.nc"] == reader.cache / "fam/era5/a.nc"

    def test_the_catalogue_route_refuses_a_version_it_does_not_hold(self, package):
        collections, bundle_dir = package
        data = ethos_data.collections(collections, bundles=[bundle_dir], download=True)

        with pytest.raises(BundleError, match="is not in the catalogue yet"):
            data.fetch("inputs")


class TestCommands:
    def test_create_update_and_verify_from_the_package_command(self, package, tmp_path):
        collections, bundle_dir = package
        directory = tmp_path / "fresh"
        lay_out(directory, {"fam2/m/a.csv": "1"})

        def tool(*argv):
            return run_cli_tool(collections, [bundle_dir], *argv)

        code, out, _ = tool("bundle", "create", str(directory), "--family", "fam2")
        assert code == 0 and "version 1 created" in out
        lay_out(directory, {"fam2/m/a.csv": "2"})
        code, out, _ = tool("bundle", "update", str(directory))
        assert code == 0
        assert "changed    fam2/m/a.csv" in out
        code, out, _ = tool("bundle", "verify", str(bundle_dir))
        assert code == 0 and out.count("ok:") == 3


def run_cli_tool(collections, bundle_dirs, *argv):
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ethos_data.tool_main(
            collections, tool="pkg", bundles=bundle_dirs, argv=list(argv)
        )
    return code, out.getvalue(), err.getvalue()


class TestAddBundle:
    @pytest.fixture
    def catalogue(self, tmp_path, store, monkeypatch):
        source = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
        dcache = FakeStore(put=store.put)
        monkeypatch.setattr(upload, "DcacheStore", lambda remote, frontend: dcache)
        return source

    def test_new_members_are_added_and_built_from_the_bundle(
        self, catalogue, bundle_dir
    ):
        code, out, err = catalogue.catalog("add-bundle", str(bundle_dir))

        assert code == 0, err
        assert (catalogue.directory("fam") / "dataset.yaml").is_file()
        status = catalogue.status("fam/era5")
        assert status["state"] == "built"
        assert status["source_dir"] == str(bundle_dir / "data/fam/era5")
        assert sorted(r["name"] for r in catalogue.index()["datasets"]) == [
            "fam",
            "fam/era5",
            "fam/gwa",
        ]
        assert "update       add fam/era5, 2 file(s)" in out

    def test_a_published_member_is_revised_and_an_unpublished_one_rebuilt(
        self, catalogue, bundle_dir
    ):
        assert catalogue.catalog("add-bundle", str(bundle_dir))[0] == 0
        assert catalogue.catalog("upload", "fam/era5")[0] == 0
        lay_out(bundle_dir, {"fam/era5/b.nc": "23\n", "fam/gwa/x.tif": "y"})
        update_bundle(bundle_dir)

        code, out, err = catalogue.catalog("add-bundle", str(bundle_dir))

        assert code == 0, err
        assert "update       revise fam/era5: revision 2 from the bundle" in out
        assert "update       rebuild fam/gwa from the bundle" in out
        assert catalogue.status("fam/era5")["revision"] == 2
        era5 = {r["path"]: r for r in catalogue.package("fam/era5")["resources"]}
        assert (
            era5["b.nc"]["ethos:revision"] == 2 and "ethos:revision" not in era5["a.nc"]
        )
        assert "ethos:revision" not in catalogue.package("fam/gwa")

    def test_a_published_file_the_bundle_dropped_is_refused_before_anything(
        self, catalogue, bundle_dir
    ):
        assert catalogue.catalog("add-bundle", str(bundle_dir))[0] == 0
        assert catalogue.catalog("upload", "fam/era5")[0] == 0
        (bundle_dir / "data/fam/era5/a.nc").unlink()
        lay_out(bundle_dir, {"fam/gwa/x.tif": "y"})
        update_bundle(bundle_dir)
        before = catalogue.package("fam/gwa")

        code, _, err = catalogue.catalog("add-bundle", str(bundle_dir))

        assert code == 1
        assert "no longer has a.nc of fam/era5" in err and "successor" in err
        assert catalogue.package("fam/gwa") == before

    def test_a_changed_description_is_taken(self, catalogue, bundle_dir):
        assert catalogue.catalog("add-bundle", str(bundle_dir))[0] == 0
        draft = bundle_dir / "datasets/fam/gwa/dataset.yaml"
        draft.write_bytes(draft.read_bytes() + b"title: Wind atlas cut-out\n")

        code, out, _ = catalogue.catalog("add-bundle", str(bundle_dir))

        assert code == 0
        assert "update       describe fam/gwa" in out
        assert catalogue.package("fam/gwa")["title"] == "Wind atlas cut-out"

    def test_a_dry_run_writes_nothing(self, catalogue, bundle_dir):
        code, out, _ = catalogue.catalog("add-bundle", str(bundle_dir), "--dry-run")

        assert code == 0
        assert "Nothing was written." in out
        assert not catalogue.directory("fam/era5").exists()
