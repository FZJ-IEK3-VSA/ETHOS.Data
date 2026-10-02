"""Each dataset's status.yaml: its state, the steps the commands take, and their record.

Tests for the decision "Datasets record their state in a status file": the
lifecycle's rules, the file's own rules, and every command that takes a step
-- build, upload, link and materialize given --catalog-root, record and
migrate -- checking the state first and recording what it did. ``catalog
status`` lists the result, and ``--check`` compares it with the evidence.
"""

from __future__ import annotations

import shutil

import pytest
import yaml
from support import SourceCatalogue, run_cli

from ethos_data.adapters.fakes import FakeStore
from ethos_data.errors import DescriptorError, TransitionError
from ethos_data.formats import status_file
from ethos_data.formats.status_file import Copy, StatusFile
from ethos_data.maintain import migrate, upload
from ethos_data.maintain import status as dataset_status
from ethos_data.model import lifecycle

EMBARGO = {
    "until": "unspecified",
    "reason": "vendor agreement",
    "becomes": "restricted",
}


@pytest.fixture
def uploading(tmp_path, store, monkeypatch):
    """A built public dataset, and dCache a fake that puts what it is sent on the store."""
    catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
    catalogue.dataset("flat", {"a.csv": "1\n", "b.csv": "22\n"})
    assert catalogue.build()[0] == 0
    dcache = FakeStore(put=store.put)
    monkeypatch.setattr(upload, "DcacheStore", lambda remote, frontend: dcache)
    return catalogue, dcache


@pytest.fixture
def linking(source, tmp_path):
    """A built internal dataset, its catalogue to read, and an empty shared cache."""
    source.dataset("shared", {"a.csv": "1", "sub/b.csv": "22"}, ethos_access="internal")
    assert source.build()[0] == 0
    cache = tmp_path / "public"

    def cli(*argv: str):
        index = str(source.root / "datacatalog.json")
        return run_cli(["--catalog", index, "--root", str(cache), *argv])

    return source, cache, cli


class TestLifecycle:
    @pytest.mark.parametrize(
        "step, before, after",
        [
            ("build", "draft", "built"),
            ("build", "built", "built"),
            ("build", "frozen", "frozen"),
            ("change", "available", "built"),
            ("upload", "built", "available"),
            ("verify", "frozen", "frozen"),
            ("link", "built", "available"),
            ("materialize", "available", "available"),
            ("record", "available", "frozen"),
            ("remove", "frozen", "withdrawn"),
            ("purge", "withdrawn", "purged"),
        ],
    )
    def test_each_step_leads_where_the_table_says(self, step, before, after):
        assert lifecycle.step(step, before) == after

    @pytest.mark.parametrize(
        "step, state, first",
        [
            ("upload", "draft", "ethos-data catalog build era5"),
            ("record", "built", "Make its bytes available first"),
            ("upload", "frozen", "ethos-data catalog upload era5 --verify-only"),
            ("link", "withdrawn", "It was removed from the catalogue."),
            ("purge", "frozen", "needs it withdrawn."),
        ],
    )
    def test_a_step_the_state_does_not_allow_says_what_comes_first(
        self, step, state, first
    ):
        with pytest.raises(TransitionError) as refused:
            lifecycle.step(step, state, "era5")

        assert refused.value.message.startswith(f"era5 is {state} (")
        assert first in refused.value.message

    def test_a_state_outside_the_vocabulary_is_named(self):
        with pytest.raises(TransitionError, match="'uploaded', which is not one of"):
            lifecycle.step("build", "uploaded", "era5")

    @pytest.mark.parametrize(
        "state, access, kinds, authority, expected",
        [
            (None, "public", (), None, "ethos-data catalog migrate era5"),
            ("draft", "public", (), None, "ethos-data catalog build era5"),
            ("built", "public", (), None, "ethos-data catalog upload era5"),
            ("built", "internal", (), None, "link it into the shared cache"),
            ("built", "restricted", (), None, "register its installation"),
            (
                "available",
                "public",
                ("uploaded",),
                None,
                "ethos-data catalog record era5",
            ),
            ("available", "internal", ("linked",), None, "materialize it before"),
            (
                "available",
                "restricted",
                ("linked",),
                None,
                "ethos-data catalog record era5",
            ),
            ("frozen", "internal", (), None, "record its authoritative copy"),
        ],
    )
    def test_the_next_step_follows_from_the_state_and_the_copies(
        self, state, access, kinds, authority, expected
    ):
        hint = lifecycle.next_step(
            "era5", state, access=access, kinds=kinds, authority=authority
        )

        assert expected in hint

    def test_a_frozen_dataset_with_its_authority_needs_nothing(self):
        assert lifecycle.next_step("era5", "frozen", authority="https://x/era5") == ""

    def test_unsettled_licensing_comes_before_any_copy(self):
        assert "licensing" in lifecycle.next_step("era5", "built", licensed=False)


class TestTheFile:
    @pytest.mark.parametrize(
        "document, message",
        [
            ({"state": "built"}, "a built dataset is built from its source_dir"),
            (
                {"state": "frozen", "source_dir": "/data"},
                "never rebuilt from local files",
            ),
            (
                {"state": "frozen", "authority": "https://x/a"},
                "not one of the recorded copies",
            ),
            (
                {"state": "shipped", "source_dir": "/d"},
                "'shipped', which is not one of",
            ),
            (
                {
                    "state": "available",
                    "source_dir": "/d",
                    "copies": [{"kind": "mailed", "location": "/x"}],
                },
                "'mailed', which is not one of",
            ),
        ],
    )
    def test_its_rules(self, document, message):
        with pytest.raises(DescriptorError, match=message):
            status_file.check(StatusFile.model_validate(document))

    def test_it_is_written_with_a_header_and_read_back_as_written(self, tmp_path):
        status = StatusFile(
            state="available",
            source_dir="/data/x",
            copies=[Copy(kind="linked", location="/cache/x", target="/data/x")],
            history=[dataset_status.event("link", "available", previous="built")],
        )

        path = dataset_status.write(tmp_path, status)

        raw = path.read_bytes()
        assert raw.startswith(b"# Written by the ethos-data catalog commands")
        assert b"\r\n" not in raw
        assert b"from: built" in raw and b"to: available" in raw
        assert dataset_status.read(tmp_path) == status

    def test_a_file_that_breaks_a_rule_is_refused_with_its_path(self, tmp_path):
        (tmp_path / "status.yaml").write_text("state: frozen\nsource_dir: /data\n")

        with pytest.raises(DescriptorError, match="status.yaml: a frozen dataset"):
            dataset_status.read(tmp_path)

    def test_keys_a_later_release_adds_are_kept(self, tmp_path):
        (tmp_path / "status.yaml").write_text(
            "state: draft\nsource_dir: /d\nrevision: 2\n"
        )

        dataset_status.write(tmp_path, dataset_status.read(tmp_path))

        assert yaml.safe_load((tmp_path / "status.yaml").read_text())["revision"] == 2


class TestTheBuild:
    def test_a_first_build_makes_a_draft_built_and_records_it(self, source):
        source.dataset("flat", {"a.csv": "1", "b.csv": "22"})

        assert source.build()[0] == 0

        status = source.status("flat")
        assert status["state"] == "built"
        (entry,) = status["history"]
        assert (entry["step"], entry["from"], entry["to"]) == (
            "build",
            "draft",
            "built",
        )
        assert (entry["files"], entry["bytes"]) == (2, 3)
        assert entry["at"].endswith("Z") and "by" in entry

    def test_a_rebuild_that_changes_no_file_records_nothing(self, source):
        directory = source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        before = (directory / "status.yaml").read_bytes()
        source.edit("flat", title="Renamed")

        assert source.build()[0] == 0

        assert (directory / "status.yaml").read_bytes() == before

    def test_changed_bytes_return_an_available_dataset_to_built(self, source):
        directory = source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        dataset_status.take(
            directory,
            dataset_status.read(directory),
            "link",
            dataset="flat",
            copy=Copy(kind="linked", location="/cache/flat", target="/data/flat"),
        )
        (source.bytes / "flat" / "a.csv").write_text("12")

        code, _, err = source.build()

        assert code == 0
        assert "its inventory changed since its bytes were made available" in err
        status = source.status("flat")
        assert status["state"] == "built"
        assert status["history"][-1]["step"] == "change"
        assert status["history"][-1]["from"] == "available"

    def test_a_frozen_dataset_rebuilds_its_metadata_and_keeps_its_inventory(
        self, source
    ):
        source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        inventory = source.package("flat")["resources"]
        source.freeze("flat")
        shutil.rmtree(source.bytes / "flat")
        source.edit("flat", title="Corrected")

        assert source.build()[0] == 0

        assert source.package("flat")["resources"] == inventory
        assert source.package("flat")["title"] == "Corrected"

    def test_dataset_yaml_may_not_say_what_status_yaml_records(self, source):
        source.dataset("flat", {"a.csv": "1"})
        source.edit("flat", source_dir="/somewhere/else")

        code, _, err = source.build()

        assert code == 1
        assert "flat: its dataset.yaml still states source_dir" in err
        assert "ethos-data catalog migrate flat" in err

    def test_a_dataset_without_one_still_builds_with_a_warning(self, source):
        source.dataset("old", {"a.csv": "1"}, legacy=True)

        code, _, err = source.build()

        assert code == 0
        assert "old keeps its build input in dataset.yaml" in err
        assert "`ethos-data catalog migrate` moves it across" in err
        assert not (source.directory("old") / "status.yaml").exists()

    def test_a_withdrawn_dataset_is_left_out_of_the_build(self, source):
        source.dataset("flat", {"a.csv": "1"})
        source.dataset("kept", {"a.csv": "1"})
        (source.directory("flat") / "status.yaml").write_text("state: withdrawn\n")

        code, out, _ = source.build()

        assert code == 0
        assert (
            "flat                               withdrawn, left out of the index" in out
        )
        assert [row["name"] for row in source.index()["datasets"]] == ["kept"]
        assert not (source.directory("flat") / "datapackage.json").exists()

    def test_a_status_file_is_never_published(self, source, tmp_path):
        source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        target = tmp_path / "public"
        target.mkdir()

        assert source.publish(target)[0] == 0

        assert not list(target.rglob("status.yaml"))
        published = "".join(p.read_text("utf-8") for p in target.rglob("*.json"))
        assert str(source.bytes / "flat").replace("\\", "\\\\") not in published


class TestUpload:
    def test_a_verified_upload_makes_a_built_dataset_available(self, uploading, store):
        catalogue, _ = uploading

        code, out, err = catalogue.catalog("upload", "flat")

        assert code == 0, err
        status = catalogue.status("flat")
        assert status["state"] == "available"
        (copy,) = status["copies"]
        assert (copy["kind"], copy["location"]) == (
            "uploaded",
            f"{store.url}/ethos-data/flat/",
        )
        assert copy["verified"].endswith("Z")
        assert status["source_dir"] == str(catalogue.bytes / "flat")
        assert status["history"][-1]["step"] == "upload"
        assert "recorded     flat is available" in out

    def test_an_upload_that_does_not_verify_records_nothing(self, uploading):
        catalogue, dcache = uploading
        dcache.put = None  # the transfer lands nowhere, so reading it back fails

        assert catalogue.catalog("upload", "flat")[0] == 1

        assert catalogue.status("flat")["state"] == "built"

    def test_a_dry_run_records_nothing(self, uploading):
        catalogue, _ = uploading

        assert catalogue.catalog("upload", "flat", "--dry-run")[0] == 0

        assert catalogue.status("flat")["state"] == "built"

    def test_a_frozen_dataset_is_only_rechecked(self, uploading):
        catalogue, _ = uploading
        assert catalogue.catalog("upload", "flat")[0] == 0
        assert catalogue.catalog("record", "flat")[0] == 0

        code, _, err = catalogue.catalog("upload", "flat")
        assert code == 1
        assert "nothing left to upload" in err

        code, _, err = catalogue.catalog(
            "upload", "flat", "--verify-only", "--no-chmod"
        )
        assert code == 0, err
        status = catalogue.status("flat")
        assert status["state"] == "frozen"
        assert status["history"][-1]["step"] == "verify"

    def test_a_withdrawn_dataset_is_refused_before_anything_moves(self, uploading):
        catalogue, dcache = uploading
        (catalogue.directory("flat") / "status.yaml").write_text(
            f"state: withdrawn\nsource_dir: '{catalogue.bytes / 'flat'}'\n"
        )

        code, _, err = catalogue.catalog("upload", "flat")

        assert code == 1
        assert "flat is withdrawn" in err
        assert dcache.copies == []

    def test_a_dataset_without_a_status_file_is_uploaded_and_not_recorded(
        self, tmp_path, store, monkeypatch
    ):
        catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
        catalogue.dataset("old", {"a.csv": "1\n"}, legacy=True)
        assert catalogue.build()[0] == 0
        monkeypatch.setattr(
            upload, "DcacheStore", lambda remote, frontend: FakeStore(put=store.put)
        )

        code, _, err = catalogue.catalog("upload", "old")

        assert code == 0
        assert "not recorded: old has no status.yaml" in err


class TestLinkAndMaterialize:
    def test_a_link_given_the_checkout_is_recorded_as_a_copy(self, linking):
        source, cache, cli = linking

        code, out, err = cli("link", "shared", "--catalog-root", str(source.root))

        assert code == 0, err
        status = source.status("shared")
        assert status["state"] == "available"
        assert status["copies"] == [
            {
                "kind": "linked",
                "location": str(cache / "shared"),
                "target": str(source.bytes / "shared"),
            }
        ]
        assert "recorded    shared is available" in out

    def test_without_the_checkout_nothing_is_recorded(self, linking):
        source, _, cli = linking

        assert cli("link", "shared", str(source.bytes / "shared"))[0] == 0

        assert source.status("shared")["state"] == "built"

    def test_a_draft_is_not_linked(self, linking, tmp_path):
        source, cache, cli = linking
        dataset_status.write(
            source.directory("shared"),
            StatusFile(state="draft", source_dir=str(source.bytes / "shared")),
        )

        code, _, err = cli("link", "shared", "--catalog-root", str(source.root))

        assert code == 1
        assert "shared is draft" in err and "Build it first" in err
        assert not (cache / "shared").exists()

    def test_link_all_records_each_link_once(self, linking):
        source, cache, _ = linking
        argv = [
            "link",
            "--all",
            "--catalog-root",
            str(source.root),
            "--root",
            str(cache),
        ]

        code, out, err = run_cli(argv)
        assert code == 0, err
        assert "recorded 1 link(s)" in out
        history = source.status("shared")["history"]

        assert run_cli(argv)[0] == 0
        assert source.status("shared")["history"] == history

    def test_a_copy_is_recorded_in_place_of_the_link_it_replaced(self, linking):
        source, cache, cli = linking
        assert cli("link", "shared", "--catalog-root", str(source.root))[0] == 0

        code, _, err = cli("materialize", "shared", "--catalog-root", str(source.root))

        assert code == 0, err
        status = source.status("shared")
        (copy,) = status["copies"]
        assert (copy["kind"], copy["location"]) == (
            "materialized",
            str(cache / "shared"),
        )
        assert status["history"][-1]["step"] == "materialize"


class TestRecord:
    def test_it_freezes_with_the_upload_as_the_authority(self, uploading, store):
        catalogue, _ = uploading
        assert catalogue.catalog("upload", "flat")[0] == 0

        code, _, err = catalogue.catalog("record", "flat")

        assert code == 0, err
        status = catalogue.status("flat")
        assert status["state"] == "frozen"
        assert status["authority"] == f"{store.url}/ethos-data/flat/"
        assert "source_dir" not in status
        assert status["history"][-1]["source_dir"] == str(catalogue.bytes / "flat")
        inventory = catalogue.package("flat")["resources"]
        shutil.rmtree(catalogue.bytes / "flat")
        assert catalogue.build()[0] == 0
        assert catalogue.package("flat")["resources"] == inventory

    def test_a_dry_run_checks_the_copy_and_writes_nothing(self, uploading):
        catalogue, _ = uploading
        assert catalogue.catalog("upload", "flat")[0] == 0
        before = catalogue.status("flat")

        code, out, _ = catalogue.catalog("record", "flat", "--dry-run")

        assert code == 0
        assert "ok    uploaded" in out and "freeze flat:" in out
        assert "Nothing was written." in out
        assert catalogue.status("flat") == before

    def test_a_built_dataset_has_no_copy_to_freeze_with(self, uploading):
        catalogue, _ = uploading

        code, _, err = catalogue.catalog("record", "flat")

        assert code == 1
        assert "flat is built" in err and "Make its bytes available first" in err

    def test_a_copy_that_no_longer_holds_the_files_is_refused(self, uploading, store):
        catalogue, _ = uploading
        assert catalogue.catalog("upload", "flat")[0] == 0
        (store.root / "ethos-data" / "flat" / "a.csv").unlink()

        code, out, _ = catalogue.catalog("record", "flat")

        assert code == 1
        assert "FAIL  uploaded" in out and "1 of 2 files not readable" in out
        assert catalogue.status("flat")["state"] == "available"

    def test_a_link_to_internal_data_is_the_authority_only_when_named(self, linking):
        source, cache, cli = linking
        assert cli("link", "shared", "--catalog-root", str(source.root))[0] == 0

        code, _, err = source.catalog("record", "shared")
        assert code == 1
        assert "A link borrows its source_dir" in err

        code, _, err = source.catalog(
            "record", "shared", "--copy", str(cache / "shared")
        )
        assert code == 0, err
        assert source.status("shared")["authority"] == str(cache / "shared")

    def test_a_registered_installation_is_the_authority_of_restricted_data(
        self, source, tmp_path, monkeypatch
    ):
        restricted = tmp_path / "restricted"
        monkeypatch.setenv("ETHOS_RESTRICTED_DIR", str(restricted))
        source.dataset(
            "licensed",
            {"a.tif": "x"},
            ethos_access="restricted",
            ethos_visibility="hidden",
            ethos_embargo=EMBARGO,
        )
        assert source.build()[0] == 0
        index = str(source.root / "datacatalog.json")
        installation = str(source.bytes / "licensed")

        code, _, err = run_cli(
            ["--catalog", index, "link", "licensed", installation,
             "--catalog-root", str(source.root)]
        )  # fmt: skip
        assert code == 0, err
        code, _, err = source.catalog("record", "licensed")

        assert code == 0, err
        assert source.status("licensed")["authority"] == str(restricted / "licensed")

    def test_a_dataset_without_a_status_file_is_migrated_first(self, source):
        source.dataset("old", {"a.csv": "1"}, legacy=True)
        assert source.build()[0] == 0

        code, _, err = source.catalog("record", "old")

        assert code == 1
        assert "ethos-data catalog migrate old" in err


class TestMigrate:
    def test_each_old_state_becomes_its_status(self, source):
        for name in ("drafted", "built", "uploaded", "frozen"):
            source.dataset(name, {"a.csv": "1"}, legacy=True)
        assert source.build("built", "uploaded", "frozen")[0] == 0
        source.edit("uploaded", source_dir=None, ethos_uploaded=True)
        source.edit("frozen", source_dir=None, ethos_frozen=True)

        code, _, err = source.catalog("migrate")

        assert code == 0, err
        assert source.status("drafted")["state"] == "draft"
        assert source.status("drafted")["source_dir"] == str(source.bytes / "drafted")
        assert source.status("built")["state"] == "built"
        location = "https://example.invalid/ethos-data/uploaded/"
        uploaded = source.status("uploaded")
        assert (uploaded["state"], uploaded["authority"]) == ("frozen", location)
        assert uploaded["copies"] == [{"kind": "uploaded", "location": location}]
        frozen = source.status("frozen")
        assert frozen["state"] == "frozen" and "authority" not in frozen
        assert frozen["history"][0]["note"] == "from ethos:frozen in dataset.yaml"
        for name in ("drafted", "built", "uploaded", "frozen"):
            text = (source.directory(name) / "dataset.yaml").read_text(encoding="utf-8")
            assert not {"source_dir", "ethos:uploaded", "ethos:frozen"} & set(
                yaml.safe_load(text)
            )
        assert source.build("built", "uploaded", "frozen", check=True)[0] == 0

    def test_every_other_line_and_comment_is_kept(self, source):
        path = source.dataset("flat", {"a.csv": "1"}, legacy=True) / "dataset.yaml"
        path.write_text(
            "# Reviewed by the custodian.\n"
            "title: Flat\n"
            "source_dir: '/data/flat'   # where the bytes are\n"
            "ethos:frozen: false\n"
            "licenses:\n"
            "  - name: CC0-1.0\n"
            "# the end\n",
            encoding="utf-8",
        )

        assert source.catalog("migrate")[0] == 0

        assert path.read_text(encoding="utf-8") == (
            "# Reviewed by the custodian.\n"
            "title: Flat\n"
            "licenses:\n"
            "  - name: CC0-1.0\n"
            "# the end\n"
        )
        assert source.status("flat")["source_dir"] == "/data/flat"

    def test_a_file_that_cannot_be_edited_line_by_line_is_left_alone(self, source):
        directory = source.dataset("flat", {"a.csv": "1"}, legacy=True)
        path = directory / "dataset.yaml"
        path.write_text("{title: Flat, source_dir: /data/flat}\n", encoding="utf-8")

        code, out, _ = source.catalog("migrate")

        assert code == 1
        assert "could not be removed from dataset.yaml line by line" in out
        assert (
            path.read_text(encoding="utf-8")
            == "{title: Flat, source_dir: /data/flat}\n"
        )
        assert not (directory / "status.yaml").exists()

    def test_keys_the_build_would_refuse_are_left_alone(self, source):
        directory = source.dataset("flat", {"a.csv": "1"}, legacy=True)
        source.edit("flat", ethos_frozen=True)

        code, out, _ = source.catalog("migrate")

        assert code == 1
        assert "declares ethos:frozen: true and still has source_dir" in out
        assert not (directory / "status.yaml").exists()

    def test_a_dry_run_writes_nothing(self, source):
        directory = source.dataset("flat", {"a.csv": "1"}, legacy=True)
        before = (directory / "dataset.yaml").read_bytes()

        code, out, _ = source.catalog("migrate", "--dry-run")

        assert code == 0
        assert "would migrate" in out
        assert (directory / "dataset.yaml").read_bytes() == before
        assert not (directory / "status.yaml").exists()

    def test_a_key_left_over_is_removed_when_it_agrees_and_refused_when_not(
        self, source
    ):
        directory = source.dataset("flat", {"a.csv": "1"})
        source.edit("flat", source_dir=source.status("flat")["source_dir"])

        assert source.catalog("migrate")[0] == 0
        text = (directory / "dataset.yaml").read_text(encoding="utf-8")
        assert "source_dir" not in yaml.safe_load(text)

        source.edit("flat", source_dir="/elsewhere")
        code, out, _ = source.catalog("migrate")
        assert code == 1
        assert "delete the one that is wrong" in out

    def test_a_migrated_dataset_is_left_unchanged(self, source):
        source.dataset("flat", {"a.csv": "1"})

        code, out, _ = source.catalog("migrate")

        assert code == 0
        assert "unchanged" in out

    def test_without_keys_removes_a_value_that_continues_on_the_next_lines(self):
        text = "title: T\nsource_dir: >-\n  /data/a\n  long\nlicenses: []\n"

        assert migrate.without_keys(text, ["source_dir"]) == "title: T\nlicenses: []\n"


class TestStatus:
    def test_it_lists_each_dataset_with_its_state_and_next_step(self, source):
        source.dataset("drafted", {"a.csv": "1"})
        source.dataset("ready", {"a.csv": "1"})
        source.dataset("old", {"a.csv": "1"}, legacy=True)
        assert source.build("ready")[0] == 0

        code, out, _ = source.catalog("status")

        assert code == 0
        rows = {line.split()[0]: line for line in out.splitlines()[1:] if line.strip()}
        assert rows["drafted"].split()[1:3] == ["draft", "public"]
        assert "ethos-data catalog build drafted" in rows["drafted"]
        assert "ethos-data catalog upload ready" in rows["ready"]
        assert rows["old"].split()[1] == "-"
        assert "ethos-data catalog migrate old" in rows["old"]

    def test_check_holds_for_a_record_that_matches(self, uploading):
        catalogue, _ = uploading
        assert catalogue.catalog("upload", "flat")[0] == 0

        code, out, err = catalogue.catalog("status", "--check")

        assert code == 0, out + err
        assert "ok    datapackage.json is current" in out
        assert "2 of 2 files readable" in out
        assert "Every record holds." in out

    def test_check_finds_what_no_longer_holds(self, linking):
        source, cache, cli = linking
        assert cli("link", "shared", "--catalog-root", str(source.root))[0] == 0
        (cache / "shared").unlink()
        (source.bytes / "shared" / "a.csv").write_text("changed")

        code, out, _ = source.catalog("status", "--check")

        assert code == 1
        assert "FAIL  datapackage.json is out of date" in out
        assert "the entry is missing" in out

    def test_check_flags_a_copy_on_dcache_of_data_that_became_restricted(
        self, uploading
    ):
        catalogue, _ = uploading
        assert catalogue.catalog("upload", "flat")[0] == 0
        catalogue.edit(
            "flat",
            ethos_access="restricted",
            ethos_visibility="hidden",
            ethos_embargo=EMBARGO,
        )

        code, out, _ = catalogue.catalog("status", "--check")

        assert code == 1
        assert "the dataset is restricted now, and a copy of it is on dCache" in out

    def test_a_status_file_that_cannot_be_read_is_one_row(self, source):
        source.dataset("broken", {"a.csv": "1"})
        source.dataset("fine", {"a.csv": "1"})
        (source.directory("broken") / "status.yaml").write_text(
            "state: frozen\nsource_dir: /data\n"
        )

        code, out, _ = source.catalog("status")

        assert code == 1
        rows = {line.split()[0]: line for line in out.splitlines()[1:] if line.strip()}
        assert rows["broken"].split()[1] == "?"
        assert "never rebuilt from local files" in rows["broken"]
        assert rows["fine"].split()[1] == "draft"

    def test_check_asks_where_a_migrated_frozen_dataset_is(self, source):
        source.dataset("frozen", {"a.csv": "1"}, legacy=True)
        assert source.build()[0] == 0
        source.edit("frozen", source_dir=None, ethos_frozen=True)
        assert source.catalog("migrate")[0] == 0

        code, out, _ = source.catalog("status", "--check")

        assert code == 1
        assert "where its authoritative copy is was never recorded" in out
