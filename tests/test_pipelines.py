"""The maintainer pipelines: catalog add, remove and check-source, and what they share.

Tests for the decision "Catalogue maintenance runs as pipelines": every stage
plans before any acts, so a refusal comes before the first write and a dry
run is the plan; and each pipeline records its steps in the datasets'
status files, so a second run does only what is left.
"""

from __future__ import annotations

import json

import pytest
import yaml
from support import DEFAULT_LICENSES, digest

from ethos_data import report
from ethos_data.errors import MaintenanceError
from ethos_data.maintain import accept, manifest
from ethos_data.maintain.pipeline import Action, Pipeline

TERMS = "licenses:\n  - name: CC-BY-4.0\n    path: https://creativecommons.org/licenses/by/4.0/\n"
#: A licence narrowed to files the dataset lacks: the build refuses it once
#: the dataset's files are hashed.
NARROWED = [{**DEFAULT_LICENSES[0], "ethos:applies_to": ["missing/*"]}]


@pytest.fixture
def candidate(tmp_path):
    """A proposal: data with a draft dataset.yaml beside it, as `staging add` writes."""
    directory = tmp_path / "candidates" / "new-data"
    (directory / "sub").mkdir(parents=True)
    (directory / "a.csv").write_bytes(b"1\n")
    (directory / "sub" / "b.csv").write_bytes(b"22\n")
    (directory / "dataset.yaml").write_bytes(
        (
            "# Proposed by the wind team.\n"
            "name: new-data\n"
            "title: New data\n"
            "source_dir: .\n"
            "ethos:retrieved: '2026-09-01'\n" + TERMS
        ).encode()
    )
    return directory


class TestPipeline:
    def test_every_stage_plans_before_any_acts(self):
        done = []

        class Writes:
            name = "writes"

            def plan(self, context):
                return [Action("write", lambda: done.append("written"))]

        class Refuses:
            name = "refuses"

            def plan(self, context):
                raise MaintenanceError("not allowed")

        with pytest.raises(MaintenanceError, match="not allowed"):
            Pipeline("p", [Writes(), Refuses()]).run(None)

        assert done == []

    def test_a_dry_run_is_the_plan(self, capsys):
        done = []

        class Writes:
            name = "writes"

            def plan(self, context):
                return [Action("write the file", lambda: done.append("written"))]

        assert Pipeline("p", [Writes()]).run(None, dry_run=True).planned == 1

        assert done == []
        out = capsys.readouterr().out
        assert "writes       write the file" in out
        assert "Nothing was written." in out

    def test_an_action_whose_result_is_wrong_stops_the_pipeline(self):
        done = []

        class Checked:
            name = "checked"

            def plan(self, context):
                return [
                    Action(
                        "first", lambda: done.append(1), lambda: "it came out wrong"
                    ),
                    Action("second", lambda: done.append(2)),
                ]

        with pytest.raises(MaintenanceError, match="p, checked: it came out wrong"):
            Pipeline("p", [Checked()]).run(None)

        assert done == [1]

    def test_a_failed_dataset_of_a_batch_stops_only_its_own_actions(self):
        done = []

        def fails():
            raise MaintenanceError("rclone exited 7")

        class Transfer:
            name = "transfer"

            def plan(self, context):
                return [
                    Action("copy a", fails, subject="a"),
                    Action("copy b", lambda: done.append("copy b"), subject="b"),
                ]

        class Record:
            name = "record"

            def plan(self, context):
                return [
                    Action("record a", lambda: done.append("record a"), subject="a"),
                    Action("record b", lambda: done.append("record b"), subject="b"),
                ]

        with report.reporting(recorded := report.RecordingReporter()):
            run = Pipeline("p", [Transfer(), Record()]).run(None)

        assert done == ["copy b", "record b"]
        assert not run.ok
        assert run.failed == {"a": "rclone exited 7"}
        assert recorded.warnings == ["p, transfer, a: rclone exited 7"]


class TestAdd:
    def test_a_draft_is_placed_and_built(self, source, candidate):
        code, out, err = source.catalog("add", str(candidate))

        assert code == 0, err
        directory = source.directory("new-data")
        description = (directory / "dataset.yaml").read_text(encoding="utf-8")
        assert description.startswith("# Proposed by the wind team.\nname: new-data\n")
        assert "source_dir" not in description
        status = source.status("new-data")
        assert status["state"] == "built"
        assert status["source_dir"] == str(candidate)
        assert [entry["step"] for entry in status["history"]] == ["add", "build"]
        assert [r["path"] for r in source.package("new-data")["resources"]] == [
            "a.csv",
            "sub/b.csv",
        ]
        assert [row["name"] for row in source.index()["datasets"]] == ["new-data"]
        assert "new-data is built" in out

    def test_its_licence_documents_come_with_it(self, source, candidate):
        (candidate / "terms.txt").write_bytes(b"the terms\n")
        text = (candidate / "dataset.yaml").read_text(encoding="utf-8")
        (candidate / "dataset.yaml").write_bytes(
            text.replace(
                "    path: https://creativecommons.org/licenses/by/4.0/\n",
                "    path: https://creativecommons.org/licenses/by/4.0/\n"
                "    ethos:document: terms.txt\n",
            ).encode()
        )

        assert source.catalog("add", str(candidate))[0] == 0

        assert (
            source.directory("new-data") / "terms.txt"
        ).read_bytes() == b"the terms\n"

    def test_a_relative_source_dir_is_relative_to_the_draft(self, source, tmp_path):
        data = tmp_path / "elsewhere" / "data"
        data.mkdir(parents=True)
        (data / "a.csv").write_bytes(b"1\n")
        draft = tmp_path / "elsewhere" / "draft.yaml"
        draft.write_bytes(
            ("name: moved\ntitle: Moved\nsource_dir: data\n" + TERMS).encode()
        )

        assert source.catalog("add", str(draft))[0] == 0

        assert source.status("moved")["source_dir"] == str(data)

    def test_a_dry_run_checks_and_writes_nothing(self, source, candidate):
        code, out, _ = source.catalog("add", str(candidate), "--dry-run")

        assert code == 0
        assert "place        write datasets/new-data/dataset.yaml" in out
        assert "build        build new-data" in out
        assert not source.directory("new-data").exists()

    @pytest.mark.parametrize(
        "change, message",
        [
            ({"name": None}, "names no dataset: add `name:` to it, or pass --name"),
            ({"name": "../outside"}, "unsafe dataset name"),
            ({"source_dir": None}, "names no source_dir"),
            ({"source_dir": "missing"}, "is not a directory"),
            ({"ethos:origin": "created"}, "claims this data was made here"),
        ],
    )
    def test_a_draft_the_catalogue_cannot_take_is_refused_before_anything_is_written(
        self, source, candidate, change, message
    ):
        meta = yaml.safe_load((candidate / "dataset.yaml").read_text(encoding="utf-8"))
        for key, value in change.items():
            if value is None:
                meta.pop(key)
            else:
                meta[key] = value
        (candidate / "dataset.yaml").write_bytes(yaml.safe_dump(meta).encode())

        code, _, err = source.catalog("add", str(candidate))

        assert code == 1
        assert message in err
        assert not list((source.root / "datasets").iterdir())

    def test_a_name_on_the_command_line_must_agree_with_the_draft(
        self, source, candidate
    ):
        code, _, err = source.catalog("add", str(candidate), "--name", "other")

        assert code == 1
        assert "drop --name or fix the draft" in err

    def test_a_dataset_already_in_the_catalogue_is_refused(self, source, candidate):
        assert source.catalog("add", str(candidate))[0] == 0

        code, _, err = source.catalog("add", str(candidate))

        assert code == 1
        assert "new-data is in the catalogue already (built)" in err
        assert "ethos-data catalog build new-data" in err

    def test_a_run_that_was_interrupted_is_finished(self, source, candidate):
        placed = accept.Draft(source.root, candidate)
        Pipeline("add", [accept.Intake(), accept.Place()]).run(placed)
        assert source.status("new-data")["state"] == "draft"

        code, out, err = source.catalog("add", str(candidate))

        assert code == 0, err
        assert "place" not in out
        assert source.status("new-data")["state"] == "built"

    def test_a_run_interrupted_inside_place_is_finished(self, source, candidate):
        """The status file is written last: without one, the draft is placed again."""
        draft = accept.Draft(source.root, candidate)
        accept.Intake().plan(draft)
        describe, *_ = accept.Place().plan(draft)
        describe.perform()
        assert not (source.directory("new-data") / "status.yaml").exists()

        code, out, err = source.catalog("add", str(candidate))

        assert code == 0, err
        assert "place        write datasets/new-data/status.yaml" in out
        assert source.status("new-data")["state"] == "built"


class TestRemove:
    def test_a_withdrawn_dataset_leaves_the_index_and_the_public_catalogue(
        self, source, tmp_path
    ):
        source.dataset("gone", {"a.csv": "1"})
        source.dataset("kept", {"b.csv": "2"})
        assert source.build()[0] == 0

        code, out, err = source.catalog(
            "remove", "gone", "--reason", "accepted by mistake"
        )

        assert code == 0, err
        status = source.status("gone")
        assert status["state"] == "withdrawn"
        assert status["history"][-1]["note"] == "accepted by mistake"
        assert [row["name"] for row in source.index()["datasets"]] == ["kept"]
        assert (source.directory("gone") / "datapackage.json").is_file()
        target = tmp_path / "public"
        target.mkdir()
        assert source.publish(target)[0] == 0
        assert not (target / "datasets" / "gone").exists()
        assert "gone" not in (target / "datacatalog.json").read_text("utf-8")
        assert "a withdrawal needs a minor release" in out
        assert "until a major release is recorded after the removal" in out
        assert source.build()[0] == 0
        assert [row["name"] for row in source.index()["datasets"]] == ["kept"]

    def test_a_family_stands_for_its_members(self, source):
        source.namespace("fam")
        source.dataset("fam/one", {"a.csv": "1"})
        source.dataset("fam/two", {"b.csv": "2"})
        source.dataset("other", {"c.csv": "3"})
        assert source.build()[0] == 0

        code, _, err = source.catalog("remove", "fam")

        assert code == 0, err
        assert source.status("fam/one")["state"] == "withdrawn"
        assert source.status("fam/two")["state"] == "withdrawn"
        assert [row["name"] for row in source.index()["datasets"]] == ["other"]

    def test_the_family_counts_only_the_members_left(self, source):
        source.namespace("fam")
        source.dataset("fam/one", {"a.csv": "1"})
        source.dataset("fam/two", {"b.csv": "22"})
        assert source.build()[0] == 0

        assert source.catalog("remove", "fam/one")[0] == 0

        assert source.package("fam")["ethos:total_bytes"] == 2
        assert sorted(row["name"] for row in source.index()["datasets"]) == [
            "fam",
            "fam/two",
        ]

    def test_removing_again_withdraws_nothing_new(self, source):
        source.dataset("gone", {"a.csv": "1"})
        assert source.build()[0] == 0
        assert source.catalog("remove", "gone")[0] == 0
        history = source.status("gone")["history"]

        code, out, _ = source.catalog("remove", "gone")

        assert code == 0
        assert "withdraw     " not in out
        assert source.status("gone")["history"] == history

    def test_a_dry_run_writes_nothing(self, source):
        source.dataset("gone", {"a.csv": "1"})
        assert source.build()[0] == 0
        index = (source.root / "datacatalog.json").read_bytes()

        code, out, _ = source.catalog("remove", "gone", "--dry-run")

        assert code == 0
        assert "withdraw     withdraw gone, built" in out
        assert source.status("gone")["state"] == "built"
        assert (source.root / "datacatalog.json").read_bytes() == index

    def test_link_all_leaves_a_withdrawn_dataset_out(self, source, tmp_path):
        from support import run_cli

        source.dataset("gone", {"a.csv": "1"})
        assert source.build()[0] == 0
        assert source.catalog("remove", "gone")[0] == 0
        cache = tmp_path / "public"

        code, out, _ = run_cli(
            ["link", "--all", "--catalog-root", str(source.root), "--root", str(cache)]
        )

        assert code == 0
        assert "withdrawn: out of the catalogue" in out
        assert not (cache / "gone").exists()

    def test_a_dataset_without_a_status_file_is_migrated_first(self, source):
        source.dataset("old", {"a.csv": "1"})
        assert source.build()[0] == 0
        (source.directory("old") / "status.yaml").unlink()

        code, _, err = source.catalog("remove", "old")

        assert code == 1
        assert "ethos-data catalog migrate old" in err

    def test_the_purge_of_a_withdrawn_dataset_waits_for_a_major_release(self, source):
        source.dataset("gone", {"a.csv": "1"})
        assert source.build()[0] == 0
        assert source.catalog("remove", "gone")[0] == 0

        _, out, _ = source.catalog("status", "gone")

        assert "withdrawn" in out
        assert "once a major release is recorded after its removal" in out


class TestCheckSource:
    @pytest.fixture
    def downloaded(self, source, tmp_path):
        source.dataset(
            "mirror", {"a.csv": "1\n", "sub/b.csv": "22\n", "c.csv": "333\n"}
        )
        assert source.build()[0] == 0
        folder = tmp_path / "validation" / "mirror"
        (folder / "sub").mkdir(parents=True)
        return source, folder

    def test_a_sample_that_matches_is_recorded(self, downloaded):
        source, folder = downloaded
        (folder / "a.csv").write_bytes(b"1\n")
        (folder / "sub" / "b.csv").write_bytes(b"22\n")

        code, out, err = source.catalog(
            "check-source", "mirror", str(folder), "--note", "2026-09 release"
        )

        assert code == 0, err
        entry = source.status("mirror")["history"][-1]
        assert entry["step"] == "check-source" and entry["to"] == "built"
        assert entry["files"] == 2
        assert entry["note"] == (
            f"2 of 3 files compared with {folder}: 2 match, 0 differ; 2026-09 release"
        )
        assert "record       record: 2 of 3 files compared" in out

    def test_a_file_that_differs_fails_and_is_recorded(self, downloaded):
        source, folder = downloaded
        (folder / "a.csv").write_bytes(b"9\n")
        (folder / "extra.csv").write_bytes(b"x\n")

        code, out, _ = source.catalog("check-source", "mirror", str(folder))

        assert code == 1
        assert "differs      a.csv" in out
        assert "not listed   extra.csv" in out
        assert "0 match, 1 differ" in source.status("mirror")["history"][-1]["note"]

    def test_a_dry_run_compares_and_records_nothing(self, downloaded):
        source, folder = downloaded
        (folder / "a.csv").write_bytes(b"1\n")
        history = source.status("mirror")["history"]

        code, out, _ = source.catalog(
            "check-source", "mirror", str(folder), "--dry-run"
        )

        assert code == 0
        assert "Nothing was written." in out
        assert source.status("mirror")["history"] == history

    def test_a_folder_with_nothing_to_compare_is_refused(self, downloaded):
        source, folder = downloaded
        (folder / "unrelated.csv").write_bytes(b"x\n")

        code, _, err = source.catalog("check-source", "mirror", str(folder))

        assert code == 1
        assert "no file under" in err

    def test_created_data_has_no_source_to_check(self, source, tmp_path):
        source.dataset(
            "ours",
            {"a.csv": "1"},
            ethos_origin="created",
            contributors=[{"title": "A. Person", "roles": ["author"]}],
        )
        assert source.build()[0] == 0

        code, _, err = source.catalog("check-source", "ours", str(tmp_path))

        assert code == 1
        assert "ours is created, so it has no source" in err

    def test_a_draft_has_no_inventory_to_compare_with(self, source, tmp_path):
        source.dataset("drafted", {"a.csv": "1"})

        code, _, err = source.catalog("check-source", "drafted", str(tmp_path))

        assert code == 1
        assert "drafted is draft" in err

    def test_the_comparison_reads_hashes_not_only_sizes(self, downloaded):
        source, folder = downloaded
        (folder / "a.csv").write_bytes(b"7\n")  # the same size as the original
        recorded = {r["path"]: r["hash"] for r in source.package("mirror")["resources"]}
        assert recorded["a.csv"] == digest(b"1\n")

        assert source.catalog("check-source", "mirror", str(folder))[0] == 1

        index = json.loads((source.root / "datacatalog.json").read_text("utf-8"))
        assert [row["name"] for row in index["datasets"]] == ["mirror"]


class TestBuild:
    def test_a_dry_run_lists_what_would_change_and_writes_nothing(self, source):
        directory = source.dataset("flat", {"a.csv": "1"})

        code, out, err = source.catalog("build", "--dry-run")

        assert code == 0, err
        assert "write        write datasets/flat/: datapackage.json" in out
        assert "write        write datacatalog.json: 1 datasets" in out
        assert "record       flat becomes built" in out
        assert not (directory / "datapackage.json").exists()
        assert not (directory / ".ethos-data-hash-cache.json").exists()
        assert source.status("flat")["state"] == "draft"

    def test_a_build_that_changes_nothing_writes_nothing(self, source):
        directory = source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        written = (directory / "datapackage.json").stat().st_mtime_ns

        code, out, _ = source.build()

        assert code == 0
        assert "nothing to do." in out
        assert (directory / "datapackage.json").stat().st_mtime_ns == written

    def test_a_dataset_the_build_refuses_stops_it_before_anything_is_written(
        self, source
    ):
        source.dataset("ok", {"a.csv": "1"})
        source.dataset("zz", {"b.csv": "2"})
        assert source.build()[0] == 0
        source.edit("ok", title="Renamed")
        source.edit("zz", source_dir="/somewhere")

        code, _, err = source.build()

        assert code == 1
        assert "ethos-data catalog migrate zz" in err
        assert source.package("ok")["title"] != "Renamed"

    def test_a_refused_dataset_keeps_the_hashes_the_build_computed(
        self, source, monkeypatch
    ):
        first = source.dataset("first", {"a.csv": "1"})
        second = source.dataset("second", {"b.csv": "2"}, licenses=NARROWED)

        code, _, err = source.build()

        assert code == 1
        assert "second: licenses entry 'CC-BY-4.0' has ethos:applies_to" in err
        for directory in (first, second):
            assert (directory / ".ethos-data-hash-cache.json").is_file()
            assert not (directory / "datapackage.json").exists()
        assert not (source.root / "datacatalog.json").exists()

        hashed = []
        monkeypatch.setattr(
            manifest, "of_file", lambda path, *args: hashed.append(path) or ""
        )
        source.edit("second", licenses=DEFAULT_LICENSES)

        assert source.build()[0] == 0
        assert hashed == [], "the build after the fix hashes nothing again"

    def test_every_refused_dataset_is_named_and_nothing_is_written(self, source):
        source.dataset("first", {"a.csv": "1"})
        source.dataset("second", {"b.csv": "2"}, licenses=NARROWED)
        source.dataset("third", {"c.csv": "3"}, licenses=NARROWED)

        code, _, err = source.build()

        assert code == 1
        assert (
            "2 datasets cannot be built, so no descriptor, shard or index was written"
            in err
        )
        assert "\n  second: licenses entry" in err
        assert "\n  third: licenses entry" in err
        assert not (source.directory("first") / "datapackage.json").exists()
        assert not (source.root / "datacatalog.json").exists()

    def test_check_keeps_the_hashes_in_memory(self, source):
        directory = source.dataset("flat", {"a.csv": "1"})

        assert source.build(check=True)[0] == 1

        assert not (directory / ".ethos-data-hash-cache.json").exists()


class TestPublish:
    def test_a_dry_run_is_the_plan(self, source, tmp_path):
        source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        target = tmp_path / "public"
        target.mkdir()
        (target / "stray.txt").write_text("left over", encoding="utf-8")

        code, out, err = source.catalog("publish", str(target), "--dry-run")

        assert code == 0, err
        assert "write        remove stray.txt" in out
        assert "write        write datacatalog.json" in out
        assert [p.name for p in target.iterdir()] == ["stray.txt"]

    def test_publishing_again_changes_nothing(self, source, tmp_path):
        source.dataset("flat", {"a.csv": "1"})
        assert source.build()[0] == 0
        target = tmp_path / "public"
        target.mkdir()
        assert source.publish(target)[0] == 0

        code, out, _ = source.publish(target)

        assert code == 0
        assert "nothing to do." in out
