"""The handoffs between roles: drafted from templates by the commands that know the facts.

Tests for the decision "Handoffs between roles have templates": a proposal
from ``propose``, a problem report from ``report``, the release notice and
the answers from ``catalog release``, the removal notice from ``catalog
remove``, and the issue templates the public catalogue carries.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
from pathlib import Path

import pytest
from support import SourceCatalogue, run_cli

import ethos_data
from ethos_data import handoffs
from ethos_data.adapters.fakes import FakeGit, FakeStore
from ethos_data.bundles import create_bundle
from ethos_data.errors import DescriptorError
from ethos_data.maintain import release, upload

LICENCE = "licenses:\n  - name: CC-BY-4.0\n    path: https://creativecommons.org/licenses/by/4.0/\n"


def candidate(tmp_path, *, access="public", extra=""):
    directory = tmp_path / "candidate"
    directory.mkdir()
    (directory / "a.csv").write_bytes(b"1\n")
    (directory / "b.csv").write_bytes(b"22\n")
    (directory / "dataset.yaml").write_bytes(
        (
            f"name: new-data\ntitle: New data\nsource_dir: .\nethos:access: {access}\n"
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


class TestTemplates:
    def test_every_handoff_fills_in(self):
        assert handoffs.names() == [
            "answer",
            "proposal",
            "release-notice",
            "removal-notice",
            "report",
        ]
        text = handoffs.answer("new-data", "v2026.10.1")
        assert "`new-data` is in the catalogue as of release v2026.10.1" in text
        assert "catalog.min_version" in text

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


class TestPropose:
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

    def test_internal_data_goes_to_the_internal_tracker(self, tmp_path):
        proposal = handoffs.propose(candidate(tmp_path, access="internal"))

        assert handoffs.INTERNAL_TRACKER in proposal.text
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

    def test_an_unpublished_bundle_is_proposed_as_its_version(self, tmp_path):
        directory = tmp_path / "test_data"
        (directory / "data/fam/era5").mkdir(parents=True)
        (directory / "data/fam/era5/a.nc").write_bytes(b"1\n")
        create_bundle(directory, "fam")

        proposal = handoffs.propose(directory)

        assert "## Proposal: fam, version 1" in proposal.text
        assert "`fam/era5`" in proposal.text and "1 files" in proposal.text

    def test_from_the_package_command(self, tmp_path, reader):
        reader.dataset("other", {"x": "1"}, where="nowhere")
        collections = reader.collections(
            """
            uses_it:
              include:
                - dataset: new-data
            """
        )
        directory = candidate(tmp_path)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ethos_data.tool_main(
                collections, tool="pkg", argv=["propose", str(directory)]
            )

        assert code == 0
        assert "uses_it already name it" in out.getvalue()
        assert "still writable" in err.getvalue()


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
        assert "inputs" in out.getvalue()


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

        release_it(catalogue, public, "v2026.10.1", notices=notices)

        notice = (notices / "release-v2026.10.1.md").read_text("utf-8")
        assert "## Catalogue release v2026.10.1" in notice
        assert "New datasets:\n\n- `accepted`: Accepted data" in notice
        answer = (notices / "answer-accepted.md").read_text("utf-8")
        assert "release v2026.10.1" in answer
        assert "## Accepted: accepted" in capsys.readouterr().out

    def test_a_revision_and_a_removal_are_in_the_next_notice(self, releasing, tmp_path):
        catalogue, public = releasing
        catalogue.dataset("kept", {"a.csv": "1\n"})
        catalogue.dataset("gone", {"b.csv": "2\n"})
        assert catalogue.build()[0] == 0
        assert catalogue.catalog("upload", "kept")[0] == 0
        assert catalogue.catalog("upload", "gone")[0] == 0
        release_it(catalogue, public, "v2026.10.1")
        corrected = tmp_path / "corrected"
        corrected.mkdir()
        (corrected / "a.csv").write_bytes(b"11\n")
        assert (
            catalogue.catalog("build", "kept", "--revision", "--from", str(corrected))[
                0
            ]
            == 0
        )
        assert catalogue.catalog("upload", "kept")[0] == 0
        assert catalogue.catalog("remove", "gone", "--reason", "a mistake")[0] == 0
        notices = tmp_path / "notices"

        release_it(catalogue, public, "v2026.10.2", notices=notices)

        notice = (notices / "release-v2026.10.2.md").read_text("utf-8")
        assert "- `kept`, revision 2" in notice
        assert "Withdrawn:\n\n- `gone`: a mistake" in notice
        assert not list(notices.glob("answer-*"))

    def test_a_removal_drafts_its_notice(self, releasing):
        catalogue, public = releasing
        catalogue.dataset("old", {"a.csv": "1\n"})
        catalogue.dataset("new", {"x/a.csv": "1\n"}, ethos_supersedes="old")
        assert catalogue.build()[0] == 0
        for name in ("old", "new"):
            assert catalogue.catalog("upload", name)[0] == 0
        release_it(catalogue, public, "v2026.10.1")

        code, out, _ = catalogue.catalog("remove", "old", "--reason", "superseded")

        assert code == 0
        assert "## Removed: old" in out
        assert "withdrawn from the catalogue: superseded" in out
        assert "The last release that describes it is v2026.10.1" in out
        assert "read new instead" in out

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
