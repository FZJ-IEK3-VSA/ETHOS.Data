"""Nested datasets -- a family described as a namespace plus its members.

The case these exist for: one logical dataset whose parts carry different
licences, and therefore different access classes. Access is a property of a
whole dataset and always will be -- a dataset is one entry in the cache root,
and whether it is read in place or downloaded is decided by whether that entry
is a symbolic link. Nesting keeps that rule intact by making each member a
dataset in its own right, addressed as ``family/member``, while the family still
has one name.

Run with pytest, or directly:  python tests/test_nested_datasets.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ethos_data.access import cache_entries
from ethos_data.maintain import dataset_name_for, is_namespace, iter_dataset_dirs
from ethos_data.maintain.manifest import render_dataset, run as build_run

CATALOG = (
    "name: t\n"
    "ethos:catalog_role: source\n"
    "ethos:publication_url: https://example.invalid/store\n"
)

NAMESPACE = """\
title: The family
description: A namespace naming two members.
homepage: https://example.invalid/family
ethos:contact: a-maintainer
ethos:attribution: Contains data from Somewhere.
"""

MEMBER = """\
title: {title}
description: {description}
source_dir: {source}
ethos:access: {access}
ethos:visibility: {visibility}
{extra}"""


def build(tmp: Path, members: dict[str, dict], namespace: str = NAMESPACE) -> Path:
    """A catalogue with one namespace and the members described by `members`."""
    catalog = tmp / "cat"
    (catalog / "datasets" / "family").mkdir(parents=True)
    (catalog / "catalog.yaml").write_text(CATALOG)
    if namespace is not None:
        (catalog / "datasets" / "family" / "dataset.yaml").write_text(namespace)
    for name, spec in members.items():
        source = tmp / "src" / name
        source.mkdir(parents=True)
        for filename in spec.get("files", ["one.txt"]):
            (source / filename).write_text(filename)
        directory = catalog / "datasets" / "family" / name
        directory.mkdir(parents=True, exist_ok=True)
        directory.joinpath("dataset.yaml").write_text(
            MEMBER.format(
                title=name.title(),
                description=f"Member {name}.",
                source=source,
                access=spec.get("access", "public"),
                visibility=spec.get("visibility", "public"),
                extra=spec.get("extra", "ethos:license_status: unresolved\n"),
            )
        )
    return catalog


PUBLIC_MEMBER = {"access": "public", "visibility": "public"}


class TestDiscovery:
    def test_a_dataset_inside_a_dataset_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(Path(tmp), {"alpha": PUBLIC_MEMBER, "beta": PUBLIC_MEMBER})
            root = catalog / "datasets"
            names = sorted(dataset_name_for(root, d) for d in iter_dataset_dirs(root))
            assert names == ["family", "family/alpha", "family/beta"]

    def test_a_directory_with_members_is_a_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(Path(tmp), {"alpha": PUBLIC_MEMBER})
            assert is_namespace(catalog / "datasets" / "family")
            assert not is_namespace(catalog / "datasets" / "family" / "alpha")

    def test_a_name_that_disagrees_with_its_directory_is_refused(self):
        """A half-done rename must fail here, not somewhere far away later."""
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(Path(tmp), {"alpha": PUBLIC_MEMBER})
            directory = catalog / "datasets" / "family" / "alpha"
            text = directory.joinpath("dataset.yaml").read_text()
            directory.joinpath("dataset.yaml").write_text("name: something-else\n" + text)
            with pytest.raises(SystemExit, match="the directory it is in makes it"):
                render_dataset(directory, name="family/alpha")


class TestNamespaces:
    def test_a_namespace_reports_the_totals_of_its_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(
                Path(tmp),
                {
                    "alpha": {**PUBLIC_MEMBER, "files": ["one.txt", "two.txt"]},
                    "beta": {**PUBLIC_MEMBER, "files": ["three.txt"]},
                },
            )
            build_run(catalog, [])
            package = json.loads(
                (catalog / "datasets" / "family" / "datapackage.json").read_text()
            )
            assert package["ethos:namespace"] is True
            assert package["ethos:file_count"] == 3
            # A namespace owns no files, so it must offer nothing to download.
            assert "resources" not in package
            assert "ethos:shards" not in package

    def test_a_namespace_may_not_describe_files_of_its_own(self):
        """Otherwise `family` means two things: its own inventory, or everything."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalog = build(tmp, {"alpha": PUBLIC_MEMBER})
            (tmp / "stray").mkdir()
            (catalog / "datasets" / "family" / "dataset.yaml").write_text(
                NAMESPACE + f"source_dir: {tmp / 'stray'}\n"
            )
            with pytest.raises(SystemExit, match="cannot also describe files of its own"):
                build_run(catalog, [])

    def test_a_namespace_may_not_carry_licensing(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(
                Path(tmp),
                {"alpha": PUBLIC_MEMBER},
                namespace=NAMESPACE + "licenses:\n  - name: CC-BY-4.0\n",
            )
            with pytest.raises(SystemExit, match="must not carry licensing"):
                build_run(catalog, [])

    def test_a_namespace_may_not_declare_an_access_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(
                Path(tmp),
                {"alpha": PUBLIC_MEMBER},
                namespace=NAMESPACE + "ethos:access: internal\n",
            )
            with pytest.raises(SystemExit, match="must not declare ethos:access"):
                build_run(catalog, [])


class TestInheritance:
    def test_descriptive_keys_come_down_from_the_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(Path(tmp), {"alpha": PUBLIC_MEMBER})
            build_run(catalog, [])
            package = json.loads(
                (catalog / "datasets" / "family" / "alpha" / "datapackage.json").read_text()
            )
            assert package["homepage"] == "https://example.invalid/family"
            assert package["ethos:contact"] == "a-maintainer"
            assert package["ethos:attribution"] == "Contains data from Somewhere."

    def test_a_member_overrides_what_it_restates(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(
                Path(tmp),
                {"alpha": {**PUBLIC_MEMBER, "extra": (
                    "ethos:license_status: unresolved\n"
                    "ethos:contact: someone-else\n"
                )}},
            )
            build_run(catalog, [])
            package = json.loads(
                (catalog / "datasets" / "family" / "alpha" / "datapackage.json").read_text()
            )
            assert package["ethos:contact"] == "someone-else"

    def test_licence_and_access_are_never_inherited(self):
        """The point of the whole exercise: a member states its own terms.

        Inheriting a licence is how a dataset ends up published under terms
        nobody read it against; inheriting an access class is how bytes end up
        readable by people the licence never covered.
        """
        from ethos_data.maintain import INHERITED_KEYS

        for key in ("licenses", "ethos:access", "ethos:visibility", "ethos:origin", "source_dir"):
            assert key not in INHERITED_KEYS


class TestMembersDifferInAccess:
    """The reason nesting exists: one family, parts of it publishable."""

    def test_members_keep_independent_access_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build(
                Path(tmp),
                {
                    "alpha": PUBLIC_MEMBER,
                    "beta": {
                        "access": "internal",
                        "visibility": "hidden",
                        "extra": (
                            "ethos:license_status: unresolved\n"
                            "ethos:embargo:\n"
                            "  until: unspecified\n"
                            "  reason: Not settled.\n"
                            "  becomes: public\n"
                        ),
                    },
                },
            )
            build_run(catalog, [])
            index = json.loads((catalog / "datacatalog.json").read_text())
            rows = {entry["name"]: entry for entry in index["datasets"]}
            assert rows["family/alpha"]["ethos:access"] == "public"
            assert rows["family/beta"]["ethos:access"] == "internal"
            # The namespace row classifies nothing -- it has no bytes.
            assert "ethos:access" not in rows["family"]
            assert rows["family"]["ethos:namespace"] is True

    def test_publishing_withholds_a_hidden_member_and_keeps_the_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalog = build(
                tmp,
                {
                    "alpha": PUBLIC_MEMBER,
                    "beta": {
                        "access": "internal",
                        "visibility": "hidden",
                        "extra": (
                            "ethos:license_status: unresolved\n"
                            "ethos:embargo:\n"
                            "  until: unspecified\n"
                            "  reason: Not settled.\n"
                            "  becomes: public\n"
                        ),
                    },
                },
            )
            build_run(catalog, [])
            from ethos_data.maintain.publish import render

            files = render(catalog)
            # as_posix, not str: render() keys are relative Paths, which stringify
            # with backslashes on Windows. The catalogue they describe is a git
            # tree addressed with forward slashes on every platform, so that is
            # the spelling to compare against.
            written = sorted(p.as_posix() for p in files)
            assert "datasets/family/alpha/datapackage.json" in written
            assert "datasets/family/datapackage.json" in written
            assert not any("beta" in p for p in written)


class TestAddressing:
    def test_a_member_resolves_at_its_nested_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalog = build(tmp, {"alpha": PUBLIC_MEMBER, "beta": PUBLIC_MEMBER})
            build_run(catalog, [])
            collections = tmp / "collections.yaml"
            collections.write_text(
                f"catalog: {catalog / 'datacatalog.json'}\n"
                "collections:\n"
                "  family:\n"
                "    include:\n"
                "      - dataset: family\n"
                "  one:\n"
                "    include:\n"
                "      - dataset: family/alpha\n"
                "  globbed:\n"
                "    include:\n"
                "      - dataset: family/*\n"
            )
            from ethos_data.selection import load_collections

            loaded = load_collections(str(collections))
            whole = [r.key for r in loaded.resolve("family")]
            assert whole == ["family/alpha/one.txt", "family/beta/one.txt"]
            assert [r.key for r in loaded.resolve("one")] == ["family/alpha/one.txt"]
            assert [r.key for r in loaded.resolve("globbed")] == whole

    def test_the_download_url_follows_the_nested_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalog = build(tmp, {"alpha": PUBLIC_MEMBER})
            build_run(catalog, [])
            from ethos_data.catalogs import load_catalog

            loaded = load_catalog(str(catalog / "datacatalog.json"))
            dataset = loaded.dataset("family/alpha")
            resource = dataset.resources["one.txt"]
            assert loaded.url_for(resource) == (
                "https://example.invalid/store/family/alpha/one.txt"
            )


class TestCacheLayout:
    def test_a_nested_entry_is_found_at_its_own_depth(self):
        """A top-level listing would see `family` and never look inside it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "flat").mkdir()
            (root / "flat" / "x.txt").write_text("x")
            (root / "family" / "alpha").mkdir(parents=True)
            (root / "family" / "alpha" / "y.txt").write_text("y")
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            (root / "family" / "beta").symlink_to(elsewhere)

            found = dict(cache_entries(root))
            assert sorted(found) == ["family/alpha", "family/beta", "flat"]
            assert found["family/beta"].is_symlink()

    def test_a_downloaded_datasets_subdirectories_are_not_more_datasets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one" / "sub").mkdir(parents=True)
            (root / "one" / "top.txt").write_text("t")
            (root / "one" / "sub" / "deep.txt").write_text("d")
            assert sorted(name for name, _ in cache_entries(root)) == ["one"]


class TestFlatCataloguesAreUnaffected:
    def test_a_dataset_with_no_members_behaves_exactly_as_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalog = tmp / "cat"
            (catalog / "datasets" / "solo").mkdir(parents=True)
            (catalog / "catalog.yaml").write_text(CATALOG)
            source = tmp / "src"
            source.mkdir()
            (source / "a.txt").write_text("a")
            (catalog / "datasets" / "solo" / "dataset.yaml").write_text(
                f"title: Solo\ndescription: Flat.\nsource_dir: {source}\n"
                "ethos:access: public\nethos:visibility: public\n"
                "ethos:license_status: unresolved\n"
            )
            build_run(catalog, [])
            package = json.loads(
                (catalog / "datasets" / "solo" / "datapackage.json").read_text()
            )
            assert package["name"] == "solo"
            assert "ethos:namespace" not in package
            assert len(package["resources"]) == 1
            index = json.loads((catalog / "datacatalog.json").read_text())
            assert index["datasets"][0]["path"] == "datasets/solo/datapackage.json"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
