"""The handoffs between roles: drafted from templates by the commands that know the facts.

Tests for the decision "Draft the handoffs between roles from templates": a
proposal from ``propose``, a problem report from ``report``, the release
notice and the answers from ``catalog release``, the removal notice from
``catalog remove``, and the issue templates the public catalogue carries.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
from pathlib import Path

import pytest
import yaml
from support import SourceCatalogue, run_cli

import ethos_data
from ethos_data import handoffs
from ethos_data.adapters.fakes import FakeGit, FakeStore
from ethos_data.bundles import create_bundle, update_bundle
from ethos_data.errors import BundleError, DescriptorError
from ethos_data.formats import registry
from ethos_data.maintain import release, upload

LICENCE = "licenses:\n  - name: CC-BY-4.0\n    path: https://creativecommons.org/licenses/by/4.0/\n"
LICENSED = {
    "licenses": [{"name": "CC-BY-4.0", "path": "https://example.invalid/cc-by"}]
}


def candidate(tmp_path, *, access="public", extra="", source_dir=True):
    directory = tmp_path / "candidate"
    directory.mkdir()
    (directory / "a.csv").write_bytes(b"1\n")
    (directory / "b.csv").write_bytes(b"22\n")
    (directory / "dataset.yaml").write_bytes(
        (
            "name: new-data\ntitle: New data\n"
            + ("source_dir: .\n" if source_dir else "")
            + f"ethos:access: {access}\n"
            + (
                "ethos:visibility: hidden\nethos:embargo:\n  until: unspecified\n  reason: paper\n"
                if access != "public"
                else ""
            )
            + LICENCE
            + extra
        ).encode()
    )
    return directory


def read_only(directory):
    for path in directory.iterdir():
        if path.name != "dataset.yaml":
            os.chmod(path, stat.S_IREAD)


def describe(root: Path, name: str, **meta: object) -> None:
    """Fill a bundled dataset's description in, with settled terms."""
    path = root / "datasets" / name / "dataset.yaml"
    path.write_text(
        yaml.safe_dump({"name": name, "title": f"The {name} data", **LICENSED, **meta}),
        encoding="utf-8",
    )


def bundle(root: Path, datasets: dict[str, dict[str, bytes]]) -> Path:
    """A bundle of ``datasets``, created, described and recorded."""
    for name, files in datasets.items():
        for relative, data in files.items():
            target = root / "data" / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    create_bundle(root)
    for name in datasets:
        describe(root, name)
    update_bundle(root)
    return root


def catalogued(reader, name: str, files: dict[str, bytes]):
    """A catalogue that holds ``name`` as a bundle describes it, and its handle."""
    reader.dataset(
        name,
        files,
        where="nowhere",
        descriptor={"title": f"The {name} data", **LICENSED},
    )
    return ethos_data.collections(
        reader.collections(f"{name}:\n  include:\n    - dataset: {name}\n")
    )


class TestTemplates:
    def test_every_handoff_has_a_template(self):
        assert registry.handoff_names() == [
            "answer",
            "proposal",
            "release-notice",
            "removal-notice",
            "report",
        ]

    def test_the_answer_names_staging_and_the_bundles_alignment(self):
        text = handoffs.answer("new-data", "v1.2.0")

        assert "`new-data` is in the catalogue as of release v1.2.0" in text
        assert "`catalog.min_version` in your collections file to `v1.2.0`" in text
        assert "staging entries" in text and "override" not in text
        assert "`bundle update`" in text and "alignment" in text

    def test_the_removal_notice_says_how_long_the_bytes_stay(self):
        text = handoffs.removal_notice("old", "a mistake", "v1.2.0", ["new"])

        assert "withdrawn from the catalogue: a mistake" in text
        assert "The last release that describes it is v1.2.0." in text
        assert "Read new instead, under its own keys." in text
        assert "until a major release is recorded after the\nremoval" in text
        assert "No release describes it." in handoffs.removal_notice(
            "old", "", None, []
        )

    def test_the_issue_templates_are_the_handoffs(self):
        for issue in handoffs.ISSUES:
            text = handoffs.issue_template(issue)
            assert text.startswith("---\nname: ")
            assert "${" not in text

    def test_a_report_is_scrubbed(self, monkeypatch):
        monkeypatch.setattr(handoffs.getpass, "getuser", lambda: "jdoe")
        home = str(Path.home())
        text = handoffs.scrub(
            f"cache {home}/cache, by jdoe; https://jdoe:secret@host/x; "
            "Authorization: Bearer abc.def; ?token=xyz"
        )

        assert home not in text and "~/cache" in text
        assert "jdoe" not in text and "<user>" in text
        assert "secret" not in text and "abc.def" not in text and "xyz" not in text


class TestTrackers:
    def test_restricted_data_goes_to_the_internal_tracker(self):
        assert handoffs.tracker("restricted") == (
            f"{handoffs.INTERNAL_TRACKER}: the data is restricted"
        )

    def test_public_data_goes_to_github_or_from_the_cluster_to_jugit(self):
        text = handoffs.tracker("public")

        assert text.startswith(handoffs.PUBLIC_TRACKER)
        assert f"{handoffs.INTERNAL_TRACKER} from a cluster installation" in text


class TestProposeADraft:
    def test_a_draft_becomes_the_text_of_its_proposal(self, tmp_path):
        directory = candidate(tmp_path)
        read_only(directory)

        proposal = handoffs.propose(directory)

        assert proposal.findings == []
        assert "## Proposal: new-data" in proposal.text
        assert "`new-data`; New data; a new dataset" in proposal.text
        assert "2 files, 5 B" in proposal.text
        assert "`include: [{dataset: new-data}]`" in proposal.text
        assert handoffs.PUBLIC_TRACKER in proposal.text

    def test_writable_bytes_are_named(self, tmp_path):
        proposal = handoffs.propose(candidate(tmp_path))

        assert any("still writable" in finding for finding in proposal.findings)
        assert "chmod -R a-w" in proposal.text

    def test_only_the_files_the_filters_keep_are_inventoried(self, tmp_path):
        directory = candidate(tmp_path, extra="ethos:exclude: [b.csv]\n")

        assert "1 files, 2 B" in handoffs.propose(directory).text

    def test_restricted_data_goes_to_the_internal_tracker(self, tmp_path):
        proposal = handoffs.propose(candidate(tmp_path, access="restricted"))

        assert f"{handoffs.INTERNAL_TRACKER}: the data is restricted" in proposal.text
        assert handoffs.PUBLIC_TRACKER not in proposal.text

    def test_a_successor_says_what_it_replaces(self, tmp_path):
        proposal = handoffs.propose(
            candidate(tmp_path, extra="ethos:supersedes: old-data\n")
        )

        assert "a successor of old-data" in proposal.text

    def test_a_draft_the_build_would_refuse_is_refused(self, tmp_path):
        directory = candidate(tmp_path, extra="ethos:origin: created\n")

        with pytest.raises(DescriptorError, match="claims this data was made here"):
            handoffs.propose(directory)

    def test_a_draft_without_source_dir_is_refused(self, tmp_path):
        directory = candidate(tmp_path, source_dir=False)

        with pytest.raises(DescriptorError, match="the draft names no source_dir"):
            handoffs.propose(directory)

    def test_from_the_package_command(self, tmp_path, reader):
        reader.dataset("other", {"x": "1"}, where="nowhere")
        collections = reader.collections(
            """
            uses_it:
              include:
                - dataset: new-data
            every_input:
              extends: [uses_it]
            unrelated:
              include:
                - dataset: other
            """
        )
        directory = candidate(tmp_path)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ethos_data.tool_main(
                collections, tool="pkg", argv=["propose", str(directory)]
            )

        assert code == 0
        assert "every_input, uses_it already name it" in out.getvalue()
        assert "a new dataset" in out.getvalue()
        assert "still writable" in err.getvalue()

    def test_a_catalogued_name_is_a_revision(self, tmp_path, reader):
        collections = catalogued(reader, "new-data", {"a.csv": b"1\n"})

        proposal = handoffs.propose(candidate(tmp_path), collections)

        assert "a revision of the catalogued new-data" in proposal.text
        assert "new-data already name it" in proposal.text


class TestProposeABundle:
    def test_its_ahead_datasets_are_proposed(self, tmp_path, reader):
        files = {"a.csv": b"1\n"}
        collections = catalogued(reader, "kept", files)
        root = bundle(tmp_path / "bundle", {"kept": files, "sites": {"b.csv": b"22\n"}})
        update_bundle(root, catalog=collections.base_catalog())

        proposal = handoffs.propose(root, collections)

        assert "## Proposal: sites" in proposal.text
        assert "`sites`, The sites data: a new dataset" in proposal.text
        assert "`kept`" not in proposal.text
        assert "1 files, 3 B, in the package's repository" in proposal.text
        assert "`include: [{dataset: sites}]`" in proposal.text
        assert handoffs.PUBLIC_TRACKER in proposal.text

    def test_a_changed_dataset_is_proposed_against_its_alignment(
        self, tmp_path, reader
    ):
        files = {"a.csv": b"1\n"}
        collections = catalogued(reader, "sites", files)
        root = bundle(tmp_path / "bundle", {"sites": files})
        update_bundle(root, catalog=collections.base_catalog())
        (root / "data" / "sites" / "a.csv").write_bytes(b"9\n")
        update_bundle(root)

        proposal = handoffs.propose(root, collections)

        assert (
            "`sites`, The sites data: 1 file changed since revision 1" in proposal.text
        )
        assert "sites already name it" in proposal.text

    def test_nothing_ahead_is_nothing_to_propose(self, tmp_path, reader):
        files = {"a.csv": b"1\n"}
        collections = catalogued(reader, "sites", files)
        root = bundle(tmp_path / "bundle", {"sites": files})
        update_bundle(root, catalog=collections.base_catalog())

        with pytest.raises(BundleError, match="there is nothing to propose"):
            handoffs.propose(root, collections)

    def test_a_change_nobody_recorded_is_refused(self, tmp_path):
        root = bundle(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
        (root / "data" / "sites" / "a.csv").write_bytes(b"9\n")

        with pytest.raises(
            BundleError, match="record the changes with `bundle update`"
        ):
            handoffs.propose(root)

    def test_data_a_bundle_may_not_hold_is_refused(self, tmp_path):
        root = bundle(tmp_path / "bundle", {"sites": {"a.csv": b"1\n"}})
        describe(root, "sites", **{"ethos:visibility": "hidden"})

        with pytest.raises(BundleError, match="sites is hidden"):
            handoffs.propose(root)


class TestReport:
    def test_the_report_holds_the_facts_without_personal_paths(self, reader):
        reader.dataset("flat", {"a.csv": "1\n"}, where="cache")
        index = str(reader.write())

        code, out, _ = run_cli(
            ["--catalog", index, "report", "flat/a.csv", "--no-selftest"]
        )

        assert code == 0
        assert "## Problem report" in out and "### Versions" in out
        assert f"ETHOS.Data {ethos_data.__version__}" in out
        assert "(left out)" in out
        assert "public cache" in out
        assert "already cached: 1 files" in out
        assert "### What verify finds, by size\n\n```text\n1 files: 1 ok" in out
        assert f"Post it at {handoffs.PUBLIC_TRACKER}" in out
        assert str(Path.home()) not in out

    def test_a_package_report_names_its_collections_and_plan(self, reader):
        reader.dataset("flat", {"a.csv": "1\n"}, where="cache")
        collections = reader.collections(
            """
            inputs:
              include:
                - dataset: flat
            """
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ethos_data.tool_main(
                collections, tool="pkg", argv=["report", "inputs", "--no-selftest"]
            )

        assert code == 0
        assert "### The package's collections" in out.getvalue()
        assert "inputs: 1 files, 2 B" in out.getvalue()
        assert "already cached: 1 files" in out.getvalue()

    def test_restricted_data_gives_every_restricted_cache_and_goes_to_jugit(
        self, tmp_path, reader, monkeypatch
    ):
        reader.dataset("closed", {"a.csv": "1\n"}, access="restricted", where="nowhere")
        index = str(reader.write())
        missing, listed = tmp_path / "gone", tmp_path / "group"
        (listed / "closed").mkdir(parents=True)
        (listed / "closed" / "a.csv").write_bytes(b"1\n")
        monkeypatch.setenv(
            "ETHOS_RESTRICTED_DIRS", os.pathsep.join([str(missing), str(listed)])
        )

        text = handoffs.report("closed", catalog=index, selftest=False)

        assert "restricted cache 1" in text and "[does not exist]" in text
        assert "restricted caches for closed: " in text
        assert ": cannot be reached; " in text and ": readable" in text
        assert "1 files: 1 note, 1 ok" in text
        assert f"Post it at {handoffs.INTERNAL_TRACKER}: the data is restricted" in text

    def test_a_failure_is_reported_in_its_place(self, reader):
        index = str(reader.write())

        text = handoffs.report("nothing/here", catalog=index, selftest=False)

        assert "### What a fetch would do\n\n```text\nerror: " in text
        assert "### What verify finds, by size\n\n```text\n(nothing to verify)" in text


@pytest.fixture
def releasing(tmp_path, store, monkeypatch):
    catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
    monkeypatch.setattr(
        upload, "DcacheStore", lambda remote, frontend: FakeStore(put=store.put)
    )
    public = tmp_path / "public"
    public.mkdir()
    return catalogue, public


def release_it(catalogue, public, version, **options):
    release.run(
        catalogue.root,
        version,
        public,
        source_git=FakeGit(),
        public_git=FakeGit(),
        **options,
    )


class TestNotices:
    def test_a_release_drafts_its_notice_and_the_answers(
        self, releasing, tmp_path, capsys
    ):
        catalogue, public = releasing
        draft = tmp_path / "draft"
        draft.mkdir()
        (draft / "a.csv").write_bytes(b"1\n")
        (draft / "dataset.yaml").write_bytes(
            ("name: accepted\ntitle: Accepted data\nsource_dir: .\n" + LICENCE).encode()
        )
        assert catalogue.catalog("add", str(draft))[0] == 0
        assert catalogue.catalog("upload", "accepted")[0] == 0
        notices = tmp_path / "notices"

        release_it(catalogue, public, "v1.0.0", notices=notices)

        notice = (notices / "release-v1.0.0.md").read_text("utf-8")
        assert "## Catalogue release v1.0.0" in notice
        assert "New datasets:\n\n- `accepted`: Accepted data" in notice
        answer = (notices / "answer-accepted.md").read_text("utf-8")
        assert "release v1.0.0" in answer
        assert "## Accepted: accepted" in capsys.readouterr().out

    def test_a_revision_and_a_removal_are_in_the_next_notice(self, releasing, tmp_path):
        catalogue, public = releasing
        catalogue.dataset("kept", {"a.csv": "1\n"})
        catalogue.dataset("gone", {"b.csv": "2\n"})
        assert catalogue.build()[0] == 0
        assert catalogue.catalog("upload", "kept")[0] == 0
        assert catalogue.catalog("upload", "gone")[0] == 0
        release_it(catalogue, public, "v1.0.0")
        corrected = tmp_path / "corrected"
        corrected.mkdir()
        (corrected / "a.csv").write_bytes(b"11\n")
        built = catalogue.catalog(
            "build", "kept", "--revision", "--from", str(corrected)
        )
        assert built[0] == 0
        assert catalogue.catalog("upload", "kept")[0] == 0
        assert catalogue.catalog("remove", "gone", "--reason", "a mistake")[0] == 0
        notices = tmp_path / "notices"

        release_it(catalogue, public, "v1.1.0", notices=notices)

        notice = (notices / "release-v1.1.0.md").read_text("utf-8")
        assert "- `kept`, revision 2" in notice
        assert "Withdrawn:\n\n- `gone`: a mistake" in notice
        assert not list(notices.glob("answer-*"))

    def test_a_removal_drafts_its_notice_in_its_own_stage(self, releasing, tmp_path):
        catalogue, public = releasing
        catalogue.dataset("old", {"a.csv": "1\n"})
        catalogue.dataset("new", {"x/a.csv": "1\n"}, ethos_supersedes="old")
        assert catalogue.build()[0] == 0
        for name in ("old", "new"):
            assert catalogue.catalog("upload", name)[0] == 0
        release_it(catalogue, public, "v1.0.0")
        notices = tmp_path / "notices"

        code, out, _ = catalogue.catalog(
            "remove", "old", "--reason", "superseded", "--notices", str(notices)
        )

        assert code == 0
        assert "notices      draft the removal notice of old, into" in out
        assert "## Removed: old" in out
        written = (notices / "removal-old.md").read_text("utf-8")
        assert "withdrawn from the catalogue: superseded" in written
        assert "The last release that describes it is v1.0.0." in written
        assert "Read new instead" in written

    def test_a_dry_run_drafts_no_notice(self, releasing):
        catalogue, _ = releasing
        catalogue.dataset("old", {"a.csv": "1\n"})
        assert catalogue.build()[0] == 0

        code, out, _ = catalogue.catalog("remove", "old", "--dry-run")

        assert code == 0
        assert "draft the removal notice of old" in out
        assert "## Removed: old" not in out

    def test_the_public_catalogue_carries_the_issue_templates(self, releasing):
        catalogue, public = releasing
        catalogue.dataset("flat", {"a.csv": "1\n"})
        assert catalogue.build()[0] == 0

        assert catalogue.publish(public)[0] == 0

        templates = public / ".github" / "ISSUE_TEMPLATE"
        assert sorted(p.name for p in templates.iterdir()) == [
            "propose-a-dataset.md",
            "report-a-problem.md",
        ]
        assert "## Proposal:" in (templates / "propose-a-dataset.md").read_text("utf-8")
        assert json.loads((public / "datacatalog.json").read_text("utf-8"))
