"""Library code reports; only the command line prints.

Characterisation tests for the four-layer decision: the maintainer commands
send their progress and warnings to a reporter the caller chooses, so a test
or a script can record or silence them, and nothing below the command line
calls ``print``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import ethos_data
from ethos_data import report
from ethos_data.maintain import manifest, publish, upload


def test_a_build_reports_its_warnings_and_summary_to_the_reporter_given(source, capsys):
    source.dataset("flat", {"a.csv": "1"}, ethos_acess="restricted")
    recorded = report.RecordingReporter()

    assert manifest.run(source.root, [], reporter=recorded).ok

    assert capsys.readouterr() == ("", ""), "nothing reaches the console"
    assert recorded.warnings == [
        "warning: flat: ethos:acess is not a key of the dataset.yaml format; a typo?"
    ]
    assert any("datacatalog.json" in line for line in recorded.infos)


def test_a_null_reporter_silences_a_publish(source, tmp_path, capsys):
    source.dataset("open", {"a.csv": "1\n"})
    assert source.build()[0] == 0
    capsys.readouterr()
    target = tmp_path / "public"
    target.mkdir()

    assert publish.run(source.root, str(target), reporter=report.NullReporter()).ok

    assert capsys.readouterr() == ("", "")
    assert (target / "datacatalog.json").is_file()


def test_an_upload_takes_its_flags_as_options_not_a_command_line(source, monkeypatch):
    import subprocess

    source.dataset("flat", {"a.csv": "1\n"})
    assert source.build()[0] == 0
    commands = []
    monkeypatch.setattr(
        upload.subprocess,
        "run",
        lambda command, *a, **k: (
            commands.append(command) or subprocess.CompletedProcess(command, 0)
        ),
    )
    recorded = report.RecordingReporter()

    result = upload.run(
        source.root,
        ["flat"],
        upload.UploadOptions(dry_run=True, transfers=2),
        reporter=recorded,
    )

    assert result.ok and result.datasets == ["flat"]
    assert commands[0][commands[0].index("--transfers") + 1] == "2"
    assert "Dry run only; nothing was uploaded." in "\n".join(recorded.infos)


def test_reporting_restores_the_reporter_it_replaced():
    outer, inner = report.RecordingReporter(), report.RecordingReporter()

    with report.reporting(outer):
        with report.reporting(inner):
            report.info("inside")
        report.warning("after")
        with report.reporting(None):
            report.info("kept")

    assert inner.infos == ["inside"]
    assert outer.warnings == ["after"] and outer.infos == ["kept"]
    assert isinstance(report.current(), report.ConsoleReporter)


def test_outside_a_command_a_warning_is_a_python_warning_of_its_category():
    class Particular(UserWarning):
        pass

    with pytest.warns(Particular, match="look here") as caught:
        report.warning("look here", Particular)

    assert caught[0].filename == __file__, "it names the line that warned"


def test_nothing_below_the_report_issues_a_python_warning_itself():
    package = Path(ethos_data.__file__).parent
    offenders = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(package).as_posix()
        if relative == "report.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{relative}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "warn"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "warnings"
        ]
    assert offenders == [], "warn through ethos_data.report.warning instead"


#: Modules allowed to print: the presentation layer, and the console reporter.
PRINTERS = {"cli.py", "report.py", "formats/__main__.py"}


def test_nothing_below_the_command_line_prints():
    package = Path(ethos_data.__file__).parent
    offenders = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(package).as_posix()
        if relative in PRINTERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{relative}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ]
    assert offenders == [], "report through ethos_data.report instead"
