"""Every input a collection names is required.

Characterisation tests for the decision of that name and for [Use data in a
script]: restricted data this account cannot read stops a fetch before anything
is downloaded, with a short error that says how to obtain the dataset and how
to register a copy; the commands that only describe list it as not available
here, with the state of every listed restricted cache; and no setting,
variable or argument leaves an input out.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from support import run_cli

import ethos_data
from ethos_data import access
from ethos_data.errors import AccessError

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
    """A collection of one public and one restricted dataset; returns the handle."""
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
    def test_it_is_short_and_says_how_to_obtain_and_register_a_copy(self, both, store):
        with pytest.raises(AccessError) as refused:
            both.fetch("both", progressbar=False)

        assert refused.value.message.splitlines() == [
            "the dataset 'gadm' is restricted.",
            "  Obtain it: Licensed for academic use; ask the custodian for a copy.",
            "  Homepage: https://gadm.org",
            "  Contact: data-custodian@example.org",
            "  This account lists no restricted cache.",
            "  Once you have a copy you may use, register it:",
            "    ethos-data config add-restricted-cache DIR",
            "    ethos-data link gadm DIR",
        ]
        assert store.downloads() == [], (
            "nothing is downloaded, not even the public file"
        )

    def test_it_prints_only_what_the_catalogue_records(self, reader, store):
        reader.dataset("gadm", {"gadm.gpkg": "g"}, access="restricted", where="nowhere")
        handle = ethos_data.collections(
            reader.collections(BOTH.replace("open", "gadm"))
        )

        with pytest.raises(AccessError) as refused:
            handle.fetch("both", progressbar=False)

        message = refused.value.message
        for absent in ("Obtain it", "Homepage", "Contact", "GADM administrative"):
            assert absent not in message, absent

    def test_a_cache_without_an_entry_for_it_gives_no_reason(
        self, both, tmp_path, monkeypatch
    ):
        (tmp_path / "restricted").mkdir()
        monkeypatch.setenv("ETHOS_RESTRICTED_DIRS", str(tmp_path / "restricted"))

        with pytest.raises(AccessError) as refused:
            ethos_data.collections(both.path).fetch("both", progressbar=False)

        message = refused.value.message
        assert "the dataset 'gadm' is restricted." in message
        assert str(tmp_path / "restricted") not in message
        assert "This account lists no restricted cache" not in message

    def test_an_entry_this_account_may_not_read_is_named(
        self, both, tmp_path, monkeypatch
    ):
        entry = tmp_path / "restricted" / "gadm"
        entry.mkdir(parents=True)
        monkeypatch.setenv("ETHOS_RESTRICTED_DIRS", str(tmp_path / "restricted"))
        monkeypatch.setattr(access.os, "access", lambda path, mode: Path(path) != entry)

        with pytest.raises(AccessError) as refused:
            ethos_data.collections(both.path).fetch("both", progressbar=False)

        assert (
            f"The entry in {tmp_path / 'restricted'} cannot be read."
            in refused.value.message
        )

    def test_a_link_to_an_installation_that_is_gone_is_named(
        self, both, tmp_path, monkeypatch
    ):
        entry = tmp_path / "restricted" / "gadm"
        entry.parent.mkdir()
        try:
            entry.symlink_to(tmp_path / "moved", target_is_directory=True)
        except OSError:
            pytest.skip("symbolic links need a privilege this account lacks")
        monkeypatch.setenv("ETHOS_RESTRICTED_DIRS", str(tmp_path / "restricted"))

        with pytest.raises(AccessError) as refused:
            ethos_data.collections(both.path).fetch("both", progressbar=False)

        assert f"The entry in {tmp_path / 'restricted'} is dangling" in (
            refused.value.message
        )

    def test_the_command_stops_with_it_too(self, both, store):
        code, out, err = run_cli_tool(both)

        assert code == 2
        assert "error: the dataset 'gadm' is restricted." in err
        assert "GADM administrative areas" not in err
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
    def test_a_plan_lists_it_with_the_state_of_every_restricted_cache(
        self, both, store, tmp_path, monkeypatch
    ):
        first, second = tmp_path / "group-a", tmp_path / "group-b"
        first.mkdir()
        monkeypatch.setenv(
            "ETHOS_RESTRICTED_DIRS", os.pathsep.join([str(first), str(second)])
        )
        handle = ethos_data.collections(both.path)

        code, out, _ = run_cli_tool(handle, "--plan")

        assert code == 0
        assert "not available here:    1 files" in out
        assert "(gadm -- a fetch stops here)" in out
        assert f"{first}: no entry" in out
        assert f"{second}: cannot be reached" in out
        assert store.downloads() == []

    def test_verify_reports_it_and_why(self, both, reader):
        files = ethos_data.collections(reader.collections(BOTH)).catalog
        resources = both.resolve("both")

        findings = ethos_data.verify(files, resources)

        unavailable = [f for f in findings if f.status == "unavailable here"]
        assert [f.resource.key for f in unavailable] == ["gadm/gadm.gpkg"]
        assert unavailable[0].detail.startswith(
            "restricted; this account lists no restricted cache"
        )

    def test_a_missing_publication_url_is_described_not_raised(self, reader):
        reader.publication_url = ""
        reader.dataset("open", {"a.csv": "1\n"}, where="nowhere")
        catalog = ethos_data.catalog(str(reader.write()))
        resources = catalog.resources("open")

        report = ethos_data.plan(catalog, resources)
        findings = ethos_data.verify(catalog, resources)

        assert [r.key for r in report["unavailable"]] == ["open/a.csv"]
        assert "no publication URL" in report["unavailable_reasons"]["open"]
        assert [f.status for f in findings] == ["unavailable here"]
        with pytest.raises(AccessError, match="no publication URL"):
            ethos_data.download(catalog, resources)


class TestNothingLeavesAnInputOut:
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
