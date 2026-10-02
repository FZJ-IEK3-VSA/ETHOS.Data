"""Every input a collection names is required.

Characterisation tests for the decision of that name and for [Use data in a
script]: licensed data this machine cannot read stops a fetch before anything
is downloaded, with an error that describes the dataset and how to register a
copy; the commands that only describe list it as not available here; and no
setting, variable or argument leaves an input out any more.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from support import run_cli

import ethos_data
from ethos_data import access, config
from ethos_data.errors import AccessError
from ethos_data.formats import dataset as dataset_format
from ethos_data.formats.derived import reader_description

DESCRIBED = {
    "title": "GADM administrative areas",
    "version": "3.6",
    "description": "Boundaries of every country and its subdivisions.",
    "homepage": "https://gadm.org",
    "sources": [{"title": "GADM download", "path": "https://gadm.org/download"}],
    "licenses": [{"name": "GADM-licence", "path": "https://gadm.org/license"}],
    "ethos:attribution": "GADM, version 3.6.",
    "ethos:restriction": "Licensed for academic use; ask the custodian for a copy.",
    "ethos:upstream": {"status": "available", "note": "Version 4.1 is current."},
    "ethos:contact": "data-custodian@example.org",
}

BOTH = """
    both:
      include:
        - dataset: open
        - dataset: gadm
"""


@pytest.fixture
def both(reader):
    """A collection of one public and one licensed dataset; returns the handle."""
    reader.dataset("open", {"a.csv": "1\n"}, where="store")
    reader.dataset(
        "gadm",
        {"gadm.gpkg": "g"},
        access="restricted",
        where="nowhere",
        descriptor=DESCRIBED,
    )
    return ethos_data.collections(reader.collections(BOTH))


class TestTheRefusal:
    def test_it_describes_the_dataset_and_how_to_register_a_copy(self, both, store):
        with pytest.raises(AccessError) as refused:
            both.fetch("both", progressbar=False)

        message = refused.value.message
        assert message.startswith(
            "dataset 'gadm' is restricted, and this machine cannot read it: "
            "no restricted cache is configured on this machine."
        )
        for line in (
            "GADM administrative areas  (version 3.6)",
            "Boundaries of every country and its subdivisions.",
            "homepage     https://gadm.org",
            "source       GADM download (https://gadm.org/download)",
            "licence      GADM-licence (https://gadm.org/license)",
            "attribution  GADM, version 3.6.",
            "restricted   Licensed for academic use; ask the custodian for a copy.",
            "upstream     available: Version 4.1 is current.",
            "contact      data-custodian@example.org",
            "ethos-data config set-restricted-cache /path/to/ethos_data_restricted",
            "ethos-data link gadm /path/to/gadm",
        ):
            assert line in message, line
        assert store.downloads() == [], (
            "nothing is downloaded, not even the public file"
        )

    def test_a_restricted_cache_without_an_entry_for_it_refuses_too(
        self, both, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("ETHOS_RESTRICTED_DIR", str(tmp_path / "restricted"))
        (tmp_path / "restricted").mkdir()

        with pytest.raises(AccessError, match="has no entry for it") as refused:
            ethos_data.collections(both.path).fetch("both", progressbar=False)

        assert "GADM administrative areas" in refused.value.message

    def test_an_entry_this_account_may_not_read_refuses_too(
        self, both, tmp_path, monkeypatch
    ):
        entry = tmp_path / "restricted" / "gadm"
        entry.mkdir(parents=True)
        monkeypatch.setenv("ETHOS_RESTRICTED_DIR", str(tmp_path / "restricted"))
        monkeypatch.setattr(access.os, "access", lambda path, mode: Path(path) != entry)

        with pytest.raises(AccessError, match="you may not read its entry"):
            ethos_data.collections(both.path).fetch("both", progressbar=False)

    def test_a_link_to_an_installation_that_is_gone_refuses_too(
        self, both, tmp_path, monkeypatch
    ):
        entry = tmp_path / "restricted" / "gadm"
        entry.parent.mkdir()
        try:
            entry.symlink_to(tmp_path / "moved", target_is_directory=True)
        except OSError:
            pytest.skip("symbolic links need a privilege this account lacks")
        monkeypatch.setenv("ETHOS_RESTRICTED_DIR", str(tmp_path / "restricted"))

        with pytest.raises(AccessError, match="which is not there"):
            ethos_data.collections(both.path).fetch("both", progressbar=False)

    def test_the_command_stops_with_it_too(self, both, store):
        code, out, err = run_cli_tool(both)

        assert code == 2
        assert "dataset 'gadm' is restricted" in err
        assert "GADM administrative areas" in err
        assert out == ""
        assert store.downloads() == []


def run_cli_tool(handle, *args: str) -> tuple[int, str, str]:
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = ethos_data.tool_main(
                handle.path, tool="faketool", argv=["fetch", "both", *args]
            )
        except SystemExit as stop:  # argparse refusing an argument
            code = stop.code
    return code, out.getvalue(), err.getvalue()


class TestWhatOnlyDescribes:
    def test_a_plan_lists_it_as_not_available_here(self, both, store):
        code, out, _ = run_cli_tool(both, "--plan")

        assert code == 0
        assert "not available here:    1 files" in out
        assert "(gadm -- a fetch stops here)" in out
        assert store.downloads() == []

    def test_verify_reports_it_and_why(self, both, reader):
        files = ethos_data.collections(reader.collections(BOTH)).catalog
        resources = both.resolve("both")

        findings = ethos_data.verify(files, resources)

        unavailable = [f for f in findings if f.status == "unavailable here"]
        assert [f.resource.key for f in unavailable] == ["gadm/gadm.gpkg"]
        assert unavailable[0].detail.startswith(
            "no restricted cache is configured on this machine"
        )


class TestNothingLeavesAnInputOut:
    def test_the_old_setting_and_variable_are_ignored_and_named(
        self, both, monkeypatch
    ):
        settings_file = config.config_path()
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_bytes(yaml.safe_dump({"skip_unavailable": True}).encode())
        monkeypatch.setenv("ETHOS_SKIP_UNAVAILABLE", "1")

        with pytest.raises(AccessError):
            ethos_data.collections(both.path).fetch("both", progressbar=False)
        code, out, _ = run_cli(["config", "show"])

        assert code == 0
        assert "skip_unavailable  (no longer read: every input is required)" in out
        assert (
            "$ETHOS_SKIP_UNAVAILABLE  (no longer read: every input is required)" in out
        )

    def test_the_arguments_are_gone(self, both):
        with pytest.raises(TypeError):
            both.fetch("both", skip_unavailable=True)
        assert not hasattr(ethos_data, "resolve_skip_unavailable")
        assert not hasattr(ethos_data.NamedPaths(), "omitted")

    @pytest.mark.parametrize(
        "argv",
        [
            ["config", "set-skip-unavailable", "true"],
            ["config", "unset-skip-unavailable"],
        ],
    )
    def test_the_commands_are_gone(self, argv):
        assert run_cli(argv)[0] == 2

    def test_the_package_command_takes_no_flag(self, both):
        code, _, err = run_cli_tool(both, "--skip-unavailable")

        assert code == 2
        assert "unrecognized arguments: --skip-unavailable" in err


def test_the_description_covers_every_user_facing_key():
    """The format marks the keys a reader without a copy sees; each is printed."""
    printed = "\n".join(reader_description(DESCRIBED))

    for key in dataset_format.USER_FACING:
        if key == "ethos:access":
            continue  # the refusal says it is restricted
        value = DESCRIBED[key]
        if isinstance(value, list):
            value = value[0].get("title") or value[0]["name"]
        elif isinstance(value, dict):
            value = value["status"]
        assert str(value) in printed, key
