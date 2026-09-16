"""``ethos-data config show`` stays cheap and says why a cache is out of reach.

It is the first command anybody runs when something is wrong, so it has to
finish -- with the cache on a network share holding hundreds of thousands of
files, and with that share not mounted at all -- and it has to print the
catalogue position whatever the cache looks like. Before this, the command
walked the whole cache looking for nested datasets; over SMB from Windows,
where the Linux-side links look like plain directories, that took minutes.
"""

import os
import string
from pathlib import Path

import pytest

from ethos_data import config
from ethos_data.cli import _unreachable, main


@pytest.fixture
def public(monkeypatch, tmp_path) -> Path:
    """An isolated configuration whose public cache is ``<tmp>/public``, not yet created."""
    monkeypatch.setattr(config, "load_config", lambda: ({}, {}))
    for variable in (
        config.RESTRICTED_ENV_VAR,
        config.STAGING_ENV_VAR,
        config.CATALOG_ENV_VAR,
        config.SKIP_UNAVAILABLE_ENV_VAR,
        "ETHOS_PUBLICATION_URL",
    ):
        monkeypatch.delenv(variable, raising=False)
    root = tmp_path / "public"
    monkeypatch.setenv(config.ENV_VAR, str(root))
    return root


def show(capsys) -> str:
    assert main(["config", "show"]) == 0
    return capsys.readouterr().out


class TestTheListingIsOneDirectoryRead:
    def test_a_dataset_without_top_level_files_is_not_walked(
        self, public, monkeypatch, capsys
    ):
        """A downloaded dataset laid out year/month has no file at its top level.

        The old walk took that for a namespace and descended into every one of
        its directories; a real dataset has thousands.
        """
        era5 = public / "era5"
        for year in range(2000, 2005):
            for month in range(1, 13):
                (era5 / str(year) / f"{month:02d}").mkdir(parents=True)
        (public / "flat").mkdir()
        (public / "flat" / "x.txt").write_text("x")

        listed: list[Path] = []
        original = Path.iterdir

        def counting(self):
            listed.append(self)
            return original(self)

        monkeypatch.setattr(Path, "iterdir", counting)
        out = show(capsys)

        assert (
            "public cache holds 0 link(s) and 2 director(ies) at the top level:" in out
        )
        assert "  era5" in out and "  flat" in out
        assert era5 not in listed and (era5 / "2000") not in listed

    def test_the_catalogue_position_comes_before_the_cache_contents(
        self, public, capsys
    ):
        public.mkdir()
        (public / "one").mkdir()
        out = show(capsys)
        assert out.index("catalogue:") < out.index("public cache holds")

    def test_links_are_listed_with_their_targets(self, public, tmp_path, capsys):
        public.mkdir()
        target = tmp_path / "elsewhere"
        target.mkdir()
        try:
            (public / "gwa").symlink_to(target)
        except OSError:
            pytest.skip("symbolic links need a privilege this account lacks")
        out = show(capsys)
        assert (
            "public cache holds 1 link(s) and 0 director(ies) at the top level:" in out
        )
        line = next(line for line in out.splitlines() if line.startswith("  gwa"))
        # Windows reports the target with a \\?\ prefix; the tail is what matters.
        assert line.split("->", 1)[1].strip().endswith(str(target))


class TestAnUnreachableCacheSaysWhy:
    def test_a_cache_nobody_created_yet_is_normal(self, public, capsys):
        out = show(capsys)
        assert "[not created yet -- the first download creates it]" in out
        assert "NOT REACHABLE" not in out
        assert "catalogue:" in out

    def test_a_missing_restricted_cache_is_flagged(
        self, public, monkeypatch, tmp_path, capsys
    ):
        """Restricted data is only ever read, so a missing root is never normal."""
        monkeypatch.setenv(config.RESTRICTED_ENV_VAR, str(tmp_path / "restricted"))
        out = show(capsys)
        assert "restricted cache" in out
        assert "[NOT REACHABLE -- does not exist]" in out

    def test_an_error_from_the_operating_system_is_repeated(
        self, public, monkeypatch, capsys
    ):
        """A share that dropped mid-session is not the same thing as an empty cache."""
        public.mkdir()
        real_stat = os.stat

        def failing(path, *args, **kwargs):
            if Path(path) == public:
                raise OSError(64, "The specified network name is no longer available")
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr(os, "stat", failing)
        out = show(capsys)
        assert (
            "[NOT REACHABLE -- cannot be reached "
            "(The specified network name is no longer available)]"
        ) in out
        assert "public cache contents: not listed -- cannot be reached" in out
        assert "catalogue:" in out

    def test_a_file_where_the_cache_should_be(self, public, capsys):
        public.write_text("not a directory")
        out = show(capsys)
        assert "[NOT REACHABLE -- is not a directory]" in out

    def test_a_per_dataset_root_that_is_gone(
        self, public, monkeypatch, tmp_path, capsys
    ):
        gone = tmp_path / "gone"
        monkeypatch.setattr(
            config,
            "load_config",
            lambda: (
                {"dataset_roots": {"era5": str(gone)}},
                {
                    "dataset_roots": "user config x",
                    "dataset_roots.era5": "user config x",
                },
            ),
        )
        out = show(capsys)
        assert f"  {'era5':<28} {gone}   [MISSING -- does not exist]" in out

    @pytest.mark.skipif(os.name != "nt", reason="drive letters are a Windows concept")
    def test_a_disconnected_drive_is_named(self):
        """The case that started this: a Samba drive that had dropped its connection."""
        free = next(
            f"{letter}:"
            for letter in reversed(string.ascii_uppercase)
            if not Path(f"{letter}:/").exists()
        )
        assert (
            _unreachable(Path(f"{free}/shared_data/public"))
            == f"drive {free} is not connected"
        )
