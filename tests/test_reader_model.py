"""One model under every reader: digests, records, sidecars, names, source paths.

Each rule here used to be written in several modules, and the copies
disagreed: a hash spelled in capitals failed ``verify --deep`` but passed a
bundle, sidecars were followed one level in a selection and every level in a
bundle export, staging saw only top-level names, and an empty ``source_dir``
built a dataset from its own descriptor. ``ethos_data.model`` holds each rule
once; these tests hold the rules, and the cases where the copies differed.
"""

from __future__ import annotations

import hashlib
import json

import pytest

import ethos_data
from ethos_data import staging
from ethos_data.errors import StagingError
from ethos_data.maintain.manifest import build_resource
from ethos_data.model import digest, names
from ethos_data.model.resource import (
    Resource,
    checked,
    extras_of,
    from_record,
    to_record,
    with_sidecars,
)

HEX = hashlib.sha256(b"uuuu").hexdigest()


class TestDigests:
    @pytest.mark.parametrize(
        "spelled",
        [f"sha256:{HEX}", f"SHA256:{HEX.upper()}", HEX, HEX.upper(), f" sha256:{HEX} "],
    )
    def test_every_spelling_of_a_sha256_names_the_same_digest(self, spelled):
        assert digest.expected(spelled) == HEX
        assert digest.matches(spelled, HEX)
        assert digest.matches(spelled, digest.recorded(HEX))

    @pytest.mark.parametrize(
        "unusable", [None, "", 42, "md5:" + "0" * 32, "sha256:xyz", f"sha256:{HEX}0"]
    )
    def test_a_record_that_names_no_sha256_matches_nothing(self, unusable):
        assert digest.expected(unusable) is None
        assert not digest.matches(unusable, HEX)

    def test_a_file_hashes_as_its_bytes_whatever_the_read_size(self, tmp_path):
        path = tmp_path / "u.nc"
        path.write_bytes(b"uuuu")

        assert digest.of_file(path, chunk=3) == digest.of_bytes(b"uuuu") == HEX
        assert digest.recorded(HEX.upper()) == f"sha256:{HEX}"


class TestNames:
    @pytest.mark.parametrize(
        "value", ["a", "a/b.txt", "reskit-test-data/era5", "a.b/c_d"]
    )
    def test_a_relative_path_is_kept_as_spelled(self, value):
        assert names.relative(value).as_posix() == value

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "/a",
            "C:/a",
            "c:a",
            "a\\b",
            "a//b",
            "./a",
            "a/.",
            "a/../b",
            "..",
            "a\x00",
            None,
        ],
    )
    def test_a_path_that_could_land_elsewhere_is_refused(self, value):
        with pytest.raises(ValueError, match="unsafe dataset name"):
            names.relative(value, "dataset name")

    def test_a_family_holds_its_members_on_a_segment_boundary(self):
        assert names.ancestors("a/b/c") == ["a", "a/b"]
        assert names.ancestors("a") == []
        assert names.within("era5/monthly", "era5")
        assert names.within("era5", "era5")
        assert not names.within("era5-land", "era5")

    def test_two_names_that_would_share_a_directory_are_found(self):
        assert names.nested(["b", "a/x", "a"]) == ("a/x", "a")
        assert names.nested(["era5", "era5-land", "family/era5"]) is None


RECORD = {
    "name": "sites-shp",
    "path": "sites.shp",
    "bytes": 5,
    "hash": f"sha256:{HEX}",
    "mediatype": "application/x-esri-shape",
    "licenses": [{"name": "CC0-1.0"}],
    "ethos:sidecars": ["sites.dbf"],
}


class TestResourceRecords:
    def test_a_record_reads_into_a_resource_and_back(self):
        resource = from_record("fixture", RECORD)

        assert resource == Resource(
            "fixture",
            "sites-shp",
            "sites.shp",
            5,
            f"sha256:{HEX}",
            "application/x-esri-shape",
            ("sites.dbf",),
        )
        assert resource.key == "fixture/sites.shp"
        assert extras_of(RECORD) == {"licenses": [{"name": "CC0-1.0"}]}
        assert to_record(resource, extras_of(RECORD)) == RECORD

    def test_the_build_writes_the_record_the_reader_reads(self, tmp_path):
        """Key for key and in order, so a descriptor rebuilt from records is the same file."""
        (tmp_path / "sites.shp").write_bytes(b"shape")
        (tmp_path / "sites.dbf").write_bytes(b"table")

        built = build_resource(tmp_path / "sites.shp", tmp_path, 5, HEX)

        assert built["ethos:sidecars"] == ["sites.dbf"]
        assert list(to_record(from_record("fixture", built)).items()) == list(
            built.items()
        )

    @pytest.mark.parametrize(
        "change, message",
        [
            ({"hash": None}, "needs its catalogue sha256 hash"),
            ({"hash": "md5:" + "0" * 32}, "needs its catalogue sha256 hash"),
            ({"path": "../x"}, "unsafe resource path"),
            ({"bytes": -1}, "invalid resource metadata"),
            ({"bytes": True}, "invalid resource metadata"),
            ({"ethos:sidecars": "sites.dbf"}, "invalid sidecars"),
            ({"ethos:sidecars": ["/etc/passwd"]}, "unsafe sidecar path"),
        ],
    )
    def test_a_record_nobody_vouches_for_is_checked(self, change, message):
        with pytest.raises(ValueError, match=message):
            checked("fixture", {**RECORD, **change})

    def test_a_record_without_its_keys_is_incomplete(self):
        with pytest.raises(
            ValueError, match="incomplete resource metadata for 'fixture'"
        ):
            checked("fixture", {"name": "sites-shp"})

    def test_a_bare_digest_is_as_good_as_a_prefixed_one(self):
        assert checked("fixture", {**RECORD, "hash": HEX.upper()}).hash == HEX.upper()


def shapefile(*sidecars_of: tuple[str, tuple[str, ...]]) -> dict[str, Resource]:
    return {
        path: Resource("d", path, path, 1, "", "", sidecars)
        for path, sidecars in sidecars_of
    }


class TestSidecars:
    def test_a_file_brings_its_sidecars_and_theirs(self):
        inventory = shapefile(
            ("a.shp", ("a.dbf",)), ("a.dbf", ("a.cpg",)), ("a.cpg", ())
        )

        found, missing = with_sidecars(
            [inventory["a.shp"]], lambda dataset, path: inventory.get(path)
        )

        assert sorted(found) == ["d/a.cpg", "d/a.dbf", "d/a.shp"]
        assert missing == []

    def test_a_sidecar_without_a_record_is_reported_not_invented(self):
        inventory = shapefile(("a.shp", ("a.dbf", "a.shx")), ("a.dbf", ()))

        found, missing = with_sidecars(
            [inventory["a.shp"], inventory["a.shp"]],
            lambda dataset, path: inventory.get(path),
        )

        assert sorted(found) == ["d/a.dbf", "d/a.shp"]
        assert missing == ["d/a.shx"]


WIND = """
    wind:
      include:
        - dataset: wind
"""


@pytest.mark.parametrize(
    "spell",
    [str.upper, lambda value: value.removeprefix("sha256:")],
    ids=["capitals", "bare"],
)
def test_a_matching_file_verifies_however_its_hash_is_spelled(reader, spell, capsys):
    reader.dataset("wind", {"u.nc": "uuuu"})
    collections = reader.collections(WIND)
    descriptor = reader.root / "datasets" / "wind" / "datapackage.json"
    package = json.loads(descriptor.read_text(encoding="utf-8"))
    for record in package["resources"]:
        record["hash"] = spell(record["hash"])
    descriptor.write_bytes(json.dumps(package).encode("utf-8"))

    code = ethos_data.tool_main(
        collections, tool="faketool", argv=["verify", "wind", "--deep"]
    )

    assert code == 0
    assert "1 file(s) match the catalogue." in capsys.readouterr().out


class TestStagingAFamilyMember:
    @pytest.fixture
    def staging_root(self, tmp_path, monkeypatch):
        root = tmp_path / "staging"
        monkeypatch.setenv("ETHOS_STAGING_DIR", str(root))
        return root

    @pytest.fixture
    def work(self, tmp_path):
        directory = tmp_path / "work"
        directory.mkdir()
        (directory / "new.nc").write_bytes(b"new bytes")
        return directory

    def test_a_member_is_staged_inside_its_family_folder(self, staging_root, work):
        staged = staging.add("family/member", work, copy=True)

        assert staged.entry == staging_root / "family" / "member"
        assert staging.staged_names() == ["family/member"]
        assert [entry.name for entry in staging.list_staged()] == ["family/member"]

    def test_the_staged_member_replaces_the_catalogues_member_only(
        self, reader, staging_root, work
    ):
        reader.namespace("family")
        reader.dataset("family/member", {"old.nc": "old"})
        reader.dataset("family/other", {"o.nc": "o"})
        collections = reader.collections(
            """
    member:
      include:
        - dataset: family
"""
        )
        staging.add("family/member", work, copy=True)

        with pytest.warns(UserWarning) as caught:
            files = ethos_data.fetch("member", collections, progressbar=False)

        warned = [str(warning.message) for warning in caught]
        assert any("staging is active: family/member is read" in w for w in warned)
        assert dict(files) == {
            "family/member/new.nc": staging_root / "family" / "member" / "new.nc",
            "family/other/o.nc": reader.cache / "family" / "other" / "o.nc",
        }

    def test_removing_the_member_removes_the_folder_staging_made(
        self, staging_root, work
    ):
        staging.add("family/member", work)

        staging.remove("family/member")

        assert not (staging_root / "family").exists()
        assert (work / "new.nc").read_bytes() == b"new bytes"

    def test_a_family_folder_is_not_itself_staged(self, staging_root, work):
        staging.add("family/member", work, copy=True)

        with pytest.raises(StagingError, match="'family' is not staged"):
            staging.remove("family", force=True)

        assert (staging_root / "family" / "member" / "new.nc").is_file()

    @pytest.mark.parametrize(
        "first, second", [("family/member", "family"), ("family", "family/member")]
    )
    def test_a_family_and_its_member_are_never_staged_together(
        self, staging_root, work, first, second
    ):
        staging.add(first, work, copy=True)

        with pytest.raises(
            StagingError, match=f"cannot stage '{second}' while '{first}' is staged"
        ):
            staging.add(second, work, copy=True)

    @pytest.mark.parametrize("name", ["../outside", "/outside", "a//b", "a\\b", ""])
    def test_a_name_that_could_leave_the_staging_root_is_refused(
        self, staging_root, work, name
    ):
        with pytest.raises(StagingError, match="unsafe dataset name"):
            staging.add(name, work, copy=True)

        assert not (staging_root.parent / "outside").exists()


class TestDescriptorsAreReadOnce:
    @pytest.mark.legacy(
        reason="status files: source_dir moves into status.yaml, whose rules "
        "refuse an empty one the same way"
    )
    def test_an_empty_source_dir_is_refused_rather_than_read_as_the_dataset(
        self, source
    ):
        source.dataset("flat", {"a.csv": "1"}, legacy=True)
        source.edit("flat", source_dir="")

        code, _, err = source.build()

        assert code == 1
        assert "flat: source_dir is required" in err

    def test_a_descriptor_that_is_not_yaml_is_refused_with_its_path(self, source):
        directory = source.dataset("flat", {"a.csv": "1"})
        (directory / "dataset.yaml").write_bytes(b"title: [unclosed\n")

        code, _, err = source.build()

        assert code == 1
        assert "dataset.yaml is not valid YAML" in err

    def test_a_descriptor_that_is_a_list_is_refused(self, source):
        directory = source.dataset("flat", {"a.csv": "1"})
        (directory / "dataset.yaml").write_bytes(b"- one\n- two\n")

        code, _, err = source.build()

        assert code == 1
        assert "must hold keys and their values, not a list" in err

    @pytest.mark.parametrize("spelled", ["./terms.txt", "licenses//terms.txt"])
    def test_a_licence_document_is_spelled_as_a_bundle_reads_it(self, source, spelled):
        source.dataset(
            "flat",
            {"a.csv": "1"},
            licenses=[{"name": "CC-BY-4.0", "ethos:document": spelled}],
            documents={"licenses/terms.txt": "terms", "terms.txt": "terms"},
        )

        code, _, err = source.build()

        assert code == 1
        assert "must be a relative path inside the dataset directory" in err
