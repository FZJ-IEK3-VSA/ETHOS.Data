"""Generating the public catalogue from the source catalogue.

Characterisation tests for [Release the catalogue]: what ``publish`` strips,
what it carries along, what it must never mention, and what ``--check``
compares. Two known defects are recorded as strict expected failures, so the
pull request that fixes them has to say so by removing the marker.
"""

from __future__ import annotations

import json

import pytest

NOTE = "Checked against the provider's page; see the proposal issue."
EMBARGO = {"until": "2027-06-30", "reason": "Pending the paper.", "becomes": "public"}
TERMS = b"The bespoke terms, archived.\n"


def everything_in(target):
    return {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(target).parts
    }


@pytest.fixture
def target(tmp_path):
    """An existing public checkout with a .git directory and a stray file."""
    public = tmp_path / "public"
    (public / ".git").mkdir(parents=True)
    (public / ".git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    (public / "stale.txt").write_bytes(b"left over from an earlier publish\n")
    return public


@pytest.fixture
def built(source):
    source.dataset(
        "open", {"a.csv": "1\n"}, ethos_license_note=NOTE, ethos_embargo=EMBARGO
    )
    source.dataset(
        "secret-plan",
        {"b.csv": "2\n"},
        ethos_access="internal",
        ethos_visibility="hidden",
        ethos_embargo=EMBARGO,
    )
    source.dataset("done", {"c.csv": "3\n"})
    code, _, err = source.build()
    assert code == 0, err
    source.edit("done", ethos_uploaded=True, source_dir=None)
    code, _, err = source.build()
    assert code == 0, err
    return source


class TestWhatIsPublished:
    def test_maintainer_bookkeeping_is_stripped(self, built, target):
        code, _, err = built.publish(target)
        assert code == 0, err

        for name in ("open", "done"):
            package = json.loads(
                (target / "datasets" / name / "datapackage.json").read_text("utf-8")
            )
            for key in (
                "source_dir",
                "ethos:embargo",
                "ethos:license_note",
                "ethos:uploaded",
                "ethos:frozen",
            ):
                assert key not in package, f"{name} still carries {key}"
        assert NOTE.encode() not in b"".join(everything_in(target).values())

    def test_the_index_is_stamped_as_published(self, built, target):
        built.publish(target)
        index = json.loads((target / "datacatalog.json").read_text("utf-8"))
        assert index["ethos:catalog_role"] == "published"

    def test_a_hidden_dataset_is_never_named(self, built, target):
        built.publish(target)
        for relative, content in everything_in(target).items():
            assert b"secret-plan" not in content, f"{relative} names the hidden dataset"

    def test_everything_but_git_is_replaced(self, built, target):
        built.publish(target)
        assert not (target / "stale.txt").exists()
        assert (target / ".git" / "HEAD").read_bytes() == b"ref: refs/heads/main\n"

    def test_licence_documents_travel_verbatim(self, source, target):
        source.dataset(
            "with-terms",
            {"c.csv": "3\n"},
            documents={"licenses/terms.txt": TERMS},
            licenses=[
                {
                    "title": "Bespoke terms",
                    "path": "https://example.org/terms",
                    "ethos:document": "licenses/terms.txt",
                }
            ],
        )
        assert source.build()[0] == 0
        assert source.publish(target)[0] == 0
        published = target / "datasets" / "with-terms" / "licenses" / "terms.txt"
        assert published.read_bytes() == TERMS


class TestCheck:
    def test_check_passes_after_publishing_and_fails_after_a_change(
        self, built, target
    ):
        assert built.publish(target)[0] == 0
        assert built.publish(target, check=True)[0] == 0

        built.edit("open", title="A new title")
        assert built.build()[0] == 0
        code, _, err = built.publish(target, check=True)

        assert code == 1
        assert "datasets/open/datapackage.json" in err.replace("\\", "/")
        assert (
            b"A new title"
            not in (target / "datasets" / "open" / "datapackage.json").read_bytes()
        )

    @pytest.mark.xfail(
        strict=True,
        reason="publish --check compares the bytes of a licence document with "
        "read_text and reports it stale; fixed with the format specifications",
    )
    def test_check_passes_for_licence_documents(self, source, target):
        source.dataset(
            "with-terms",
            {"c.csv": "3\n"},
            documents={"licenses/terms.txt": TERMS},
            licenses=[
                {
                    "title": "Bespoke terms",
                    "path": "https://example.org/terms",
                    "ethos:document": "licenses/terms.txt",
                }
            ],
        )
        assert source.build()[0] == 0
        assert source.publish(target)[0] == 0
        assert source.publish(target, check=True)[0] == 0


@pytest.mark.xfail(
    strict=True,
    reason="the published index row is built separately from the source row and "
    "lacks visibility, remote prefix, licence status, version and ethos:namespace; "
    "fixed with the format specifications",
)
def test_a_published_index_row_says_what_the_source_row_says(source, target):
    source.namespace("family")
    source.dataset("family/member", {"a.csv": "1\n"}, version="2.0")
    assert source.build()[0] == 0
    assert source.publish(target)[0] == 0

    published = {
        row["name"]: row
        for row in json.loads((target / "datacatalog.json").read_text("utf-8"))[
            "datasets"
        ]
    }
    for row in source.index()["datasets"]:
        assert published[row["name"]] == row
