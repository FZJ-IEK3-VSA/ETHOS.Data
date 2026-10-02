"""Releasing the catalogue, updating the served checkout, and purging a removed dataset.

Tests for the release pipeline of "Catalogue maintenance runs as pipelines",
and for the history a release leaves: a release step in every dataset that
changed, which ``catalog status`` shows and which purging a withdrawn dataset
waits for. git is a :class:`FakeGit` unless a test says otherwise; dCache is a
:class:`FakeStore` that puts what it is sent on the loopback store.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request

import pytest
import yaml
from support import SourceCatalogue, run_cli

from ethos_data.adapters.fakes import FakeGit, FakeStore
from ethos_data.errors import MaintenanceError
from ethos_data.formats.status_file import StatusFile
from ethos_data.maintain import checkout, release, remove, upload
from ethos_data.maintain import status as dataset_status

EMBARGO = {"until": "unspecified", "reason": "paper", "becomes": "public"}


@pytest.fixture
def released(tmp_path, store, monkeypatch):
    """A source catalogue with one uploaded public dataset, and a public checkout."""
    catalogue = SourceCatalogue(tmp_path, publication_url=f"{store.url}/ethos-data")
    catalogue.dataset("flat", {"a.csv": "1\n", "b.csv": "22\n"})
    assert catalogue.build()[0] == 0
    dcache = FakeStore(put=store.put, remove=store.remove)
    monkeypatch.setattr(upload, "DcacheStore", lambda remote, frontend: dcache)
    assert catalogue.catalog("upload", "flat")[0] == 0
    public = tmp_path / "public"
    public.mkdir()
    return catalogue, public, dcache


def release_it(catalogue, public, version="v2026.10.1", **options):
    gits = options.pop("gits", None) or (FakeGit(), FakeGit())
    release.run(
        catalogue.root,
        version,
        public,
        source_git=gits[0],
        public_git=gits[1],
        **options,
    )
    return gits


def history(catalogue, name):
    return [entry["step"] for entry in catalogue.status(name)["history"]]


class TestRelease:
    def test_it_stamps_records_commits_tags_and_publishes(self, released):
        catalogue, public, _ = released

        source_git, public_git = release_it(catalogue, public)

        assert (
            yaml.safe_load((catalogue.root / "catalog.yaml").read_text())["version"]
            == "v2026.10.1"
        )
        assert catalogue.index()["version"] == "v2026.10.1"
        last = catalogue.status("flat")["history"][-1]
        assert (last["step"], last["release"]) == ("release", "v2026.10.1")
        assert source_git.commits == ["Release v2026.10.1"]
        assert source_git.tag_names() == ["v2026.10.1"]
        published = json.loads((public / "datacatalog.json").read_text("utf-8"))
        assert published["version"] == "v2026.10.1"
        assert published["ethos:catalog_role"] == "published"
        assert public_git.tag_names() == ["v2026.10.1"]
        assert source_git.pushes == [] and public_git.pushes == []

    def test_push_and_upload_reach_past_the_machine(self, released, store):
        catalogue, public, dcache = released

        source_git, public_git = release_it(
            catalogue, public, push=True, upload=True, store=dcache
        )

        assert source_git.pushes == [("origin", ("HEAD", "v2026.10.1"))]
        assert public_git.pushes == [("origin", ("HEAD", "v2026.10.1"))]
        (sync,) = dcache.syncs
        assert sync["destination"] == "ethos-data/catalogue"
        assert "datacatalog.json" in sync["paths"]
        assert ("Helmholtz/FZJ-ICE2/ethos-data/catalogue", 493) in dcache.chmods
        url = f"{store.url}/ethos-data/catalogue/datacatalog.json"
        with urllib.request.urlopen(url) as response:
            assert json.load(response)["version"] == "v2026.10.1"

    def test_running_it_again_finishes_what_is_left(self, released):
        catalogue, public, dcache = released
        gits = release_it(catalogue, public)

        release_it(catalogue, public, gits=gits, push=True, upload=True, store=dcache)

        source_git, public_git = gits
        assert source_git.commits == ["Release v2026.10.1"], "no second commit"
        assert len(source_git.pushes) == 1 and len(public_git.pushes) == 1
        assert len(dcache.syncs) == 1
        assert history(catalogue, "flat").count("release") == 1

    def test_a_dry_run_writes_nothing(self, released, capsys):
        catalogue, public, _ = released
        before = (catalogue.root / "catalog.yaml").read_bytes()

        source_git, _ = release_it(catalogue, public, dry_run=True)

        assert (catalogue.root / "catalog.yaml").read_bytes() == before
        assert source_git.commits == []
        assert not (public / "datacatalog.json").exists()
        out = capsys.readouterr().out
        assert "stamp        write version: v2026.10.1 into catalog.yaml" in out
        assert "commit       commit the source checkout and tag it v2026.10.1" in out

    def test_only_datasets_that_changed_record_the_release(self, released):
        catalogue, public, _ = released
        catalogue.dataset("other", {"c.csv": "3\n"}, ethos_access="internal")
        assert catalogue.build()[0] == 0
        gits = release_it(catalogue, public)
        (catalogue.bytes / "other" / "c.csv").write_bytes(b"33\n")
        assert catalogue.build()[0] == 0

        release_it(catalogue, public, "v2026.10.2", gits=(FakeGit(), FakeGit()))

        assert history(catalogue, "flat").count("release") == 1
        assert history(catalogue, "other")[-2:] == ["change", "release"]
        assert gits[0].tag_names() == ["v2026.10.1"]

    def test_status_names_the_release_and_what_came_after(self, released):
        catalogue, public, _ = released
        release_it(catalogue, public)

        _, out, _ = catalogue.catalog("status")
        assert "v2026.10.1 " in out

        assert (
            catalogue.catalog("upload", "flat", "--verify-only", "--no-chmod")[0] == 0
        )
        _, out, _ = catalogue.catalog("status")
        assert "v2026.10.1 +1" in out

    @pytest.mark.parametrize(
        "case, message",
        [
            ("older", "does not follow the catalogue's release v2026.11.1"),
            ("tagged", "has a tag v2026.10.1 already"),
            ("dirty", "has changes nobody committed"),
            ("source", "is a source catalogue"),
            ("stale", "the manifests are not current"),
            ("not uploaded", "with no verified upload recorded: fresh"),
            ("leak", "names the withheld dataset secret-plan"),
            ("version", "is not a catalogue release"),
        ],
    )
    def test_what_is_not_ready_is_refused_before_anything_is_written(
        self, released, case, message
    ):
        catalogue, public, _ = released
        source_git, public_git = FakeGit(), FakeGit()
        version = "v2026.10.1"
        if case == "older":
            text = (catalogue.root / "catalog.yaml").read_text(encoding="utf-8")
            (catalogue.root / "catalog.yaml").write_bytes(
                (text + "version: v2026.11.1\n").encode()
            )
            assert catalogue.build()[0] == 0
        elif case == "tagged":
            source_git.tags.append(("v2026.10.1", ""))
        elif case == "dirty":
            source_git.clean = False
        elif case == "source":
            public = catalogue.root
        elif case == "stale":
            catalogue.edit("flat", title="Renamed, not rebuilt")
        elif case == "not uploaded":
            catalogue.dataset("fresh", {"c.csv": "3\n"})
            assert catalogue.build()[0] == 0
        elif case == "leak":
            catalogue.dataset(
                "secret-plan",
                {"s.csv": "1\n"},
                ethos_access="internal",
                ethos_visibility="hidden",
                ethos_embargo=EMBARGO,
            )
            catalogue.edit("flat", description="Built from secret-plan.")
            assert catalogue.build()[0] == 0
        elif case == "version":
            version = "2026-10"
        before = (catalogue.root / "catalog.yaml").read_bytes()

        with pytest.raises(MaintenanceError, match=message):
            release_it(catalogue, public, version, gits=(source_git, public_git))

        assert (catalogue.root / "catalog.yaml").read_bytes() == before
        assert source_git.commits == [] and public_git.commits == []

    def test_on_the_command_line(self, released, monkeypatch):
        catalogue, public, _ = released
        made = []
        real = release.run

        def recording(*args, **kwargs):
            made.append(kwargs)
            return real(*args, **kwargs, source_git=FakeGit(), public_git=FakeGit())

        monkeypatch.setattr(release, "run", recording)

        code, out, err = catalogue.catalog(
            "release", "v2026.10.1", "--public", str(public)
        )

        assert code == 0, err
        assert made[0]["push"] is False and made[0]["upload"] is False
        assert "run this again with --push and --upload to finish it" in out


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
class TestWithGit:
    @staticmethod
    def git(*arguments, cwd):
        return subprocess.run(
            [
                "git",
                "-c",
                "user.email=t@example.invalid",
                "-c",
                "user.name=T",
                *arguments,
            ],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def repository(self, directory, remote):
        self.git("init", "--bare", str(remote), cwd=directory.parent)
        self.git("init", cwd=directory)
        self.git("config", "user.email", "t@example.invalid", cwd=directory)
        self.git("config", "user.name", "T", cwd=directory)
        self.git("remote", "add", "origin", str(remote), cwd=directory)

    def test_a_release_pushes_both_tags_and_the_server_follows(
        self, released, tmp_path
    ):
        catalogue, public, _ = released
        self.repository(catalogue.root, tmp_path / "source.git")
        self.git("add", "--all", cwd=catalogue.root)
        self.git("commit", "-m", "Add flat", cwd=catalogue.root)
        self.git("push", "origin", "HEAD:refs/heads/main", cwd=catalogue.root)
        self.repository(public, tmp_path / "public.git")
        (public / "README.md").write_bytes(b"public\n")
        self.git("add", "--all", cwd=public)
        self.git("commit", "-m", "Start", cwd=public)
        self.git("push", "origin", "HEAD:refs/heads/main", cwd=public)
        served = tmp_path / "served"
        self.git("clone", str(tmp_path / "source.git"), str(served), cwd=tmp_path)

        release.run(catalogue.root, "v2026.10.1", public, push=True)

        for remote in ("source.git", "public.git"):
            assert self.git("tag", cwd=tmp_path / remote).split() == ["v2026.10.1"]
        checkout.run(served)
        assert (
            yaml.safe_load((served / "catalog.yaml").read_text())["version"]
            == "v2026.10.1"
        )
        assert self.git("status", "--porcelain", cwd=catalogue.root) == ""


class TestUpdateCheckout:
    def test_it_fetches_and_moves_to_the_latest_release(self, released):
        catalogue, public, _ = released
        release_it(catalogue, public, "v2026.10.2")
        git = FakeGit(remote_tags=["v2026.10.1", "v2026.10.2", "not-a-release"])

        checkout.run(catalogue.root, git=git)

        assert git.fetches == ["origin"]
        assert git.forwards == ["v2026.10.2"]

    def test_a_checkout_that_does_not_say_the_release_is_refused(self, released):
        catalogue, public, _ = released
        release_it(catalogue, public, "v2026.10.2")
        git = FakeGit(remote_tags=["v2026.10.1", "v2026.10.2"])

        with pytest.raises(MaintenanceError, match="its catalog.yaml says v2026.10.2"):
            checkout.run(catalogue.root, to="v2026.10.1", git=git)

    def test_a_served_checkout_with_changes_is_left_alone(self, released):
        catalogue, _, _ = released
        git = FakeGit(clean=False)

        with pytest.raises(MaintenanceError, match="has changes nobody committed"):
            checkout.run(catalogue.root, git=git)

        assert git.fetches == []


class TestPurge:
    @pytest.fixture
    def withdrawn(self, released, tmp_path):
        """flat uploaded and linked into a cache, then withdrawn."""
        catalogue, public, dcache = released
        cache = tmp_path / "cache"
        index = str(catalogue.root / "datacatalog.json")
        code, _, err = run_cli(
            ["--catalog", index, "--root", str(cache), "link", "flat",
             "--catalog-root", str(catalogue.root)]
        )  # fmt: skip
        assert code == 0, err
        assert catalogue.catalog("remove", "flat", "--reason", "a mistake")[0] == 0
        return catalogue, public, dcache, cache

    def test_it_waits_for_a_release_without_the_dataset(self, withdrawn):
        catalogue, _, dcache, cache = withdrawn

        with pytest.raises(MaintenanceError, match="no release without it is recorded"):
            remove.run(catalogue.root, ["flat"], purge=True, store=dcache)

        assert (cache / "flat").is_symlink()
        assert dcache.purges == []

    def test_after_the_release_everything_goes_but_the_record(self, withdrawn, store):
        catalogue, public, dcache, cache = withdrawn
        release_it(catalogue, public)
        assert (store.root / "ethos-data" / "flat" / "a.csv").is_file()

        remove.run(catalogue.root, ["flat"], purge=True, store=dcache)

        assert not (cache / "flat").exists()
        assert dcache.purges == ["ethos-data/flat"]
        assert not (store.root / "ethos-data" / "flat").exists()
        directory = catalogue.directory("flat")
        assert sorted(p.name for p in directory.iterdir()) == ["status.yaml"]
        assert catalogue.status("flat")["state"] == "purged"
        assert "flat" not in [row["name"] for row in catalogue.index()["datasets"]]
        _, out, _ = catalogue.catalog("status")
        assert any(line.split()[:2] == ["flat", "purged"] for line in out.splitlines())

    def test_a_purged_name_is_not_given_to_other_bytes(self, withdrawn, tmp_path):
        catalogue, public, dcache, _ = withdrawn
        release_it(catalogue, public)
        remove.run(catalogue.root, ["flat"], purge=True, store=dcache)
        draft = tmp_path / "draft"
        draft.mkdir()
        (draft / "x.csv").write_bytes(b"1\n")
        (draft / "dataset.yaml").write_bytes(
            b"name: flat\ntitle: Flat\nsource_dir: .\nlicenses:\n  - name: CC0-1.0\n"
        )

        code, _, err = catalogue.catalog("add", str(draft))

        assert code == 1
        assert "flat was a dataset of this catalogue and was purged" in err

    def test_a_folder_another_dataset_lies_in_is_refused(self, withdrawn, store):
        catalogue, public, dcache, _ = withdrawn
        catalogue.dataset("inner", {"i.csv": "1\n"})
        assert catalogue.build()[0] == 0
        dataset_status.write(
            catalogue.directory("inner"),
            StatusFile.model_validate(
                {
                    "state": "available",
                    "source_dir": str(catalogue.bytes / "inner"),
                    "copies": [
                        {
                            "kind": "uploaded",
                            "location": f"{store.url}/ethos-data/flat/inner/",
                        }
                    ],
                }
            ),
        )
        release_it(catalogue, public)

        with pytest.raises(MaintenanceError, match="holds or lies in inner's"):
            remove.run(catalogue.root, ["flat"], purge=True, store=dcache)

        assert dcache.purges == []

    def test_a_family_left_with_no_members_goes_too(self, released, tmp_path):
        catalogue, public, dcache = released
        catalogue.namespace("fam")
        catalogue.dataset("fam/one", {"a.csv": "1\n"}, ethos_access="internal")
        assert catalogue.build()[0] == 0
        assert catalogue.catalog("remove", "fam")[0] == 0
        release_it(catalogue, public)

        remove.run(catalogue.root, ["fam/one"], purge=True, store=dcache)

        assert not (catalogue.directory("fam") / "dataset.yaml").exists()
        assert catalogue.status("fam/one")["state"] == "purged"
        assert catalogue.build()[0] == 0
        assert [row["name"] for row in catalogue.index()["datasets"]] == ["flat"]

    def test_a_dry_run_deletes_nothing(self, withdrawn, capsys):
        catalogue, public, dcache, cache = withdrawn
        release_it(catalogue, public)
        capsys.readouterr()

        remove.run(catalogue.root, ["flat"], purge=True, store=dcache, dry_run=True)

        out = capsys.readouterr().out
        assert f"cache        unlink {cache / 'flat'}" in out
        assert "store        purge HIFIS:ethos-data/flat on the store" in out
        assert (cache / "flat").is_symlink() and dcache.purges == []
        assert catalogue.status("flat")["state"] == "withdrawn"
