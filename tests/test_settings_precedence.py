"""Which value of a setting wins, and the commands that write one.

Characterisation tests for [Set up your machine]: an explicit argument beats
the environment, which beats the settings file, which beats the built-in
default; the restricted cache has no default; and a setting written by
``config set-*`` is shown by ``config show`` and removed by ``unset-*``.
Where the settings file lives is for ``test_settings_file.py``, so these
tests never name it.
"""

from __future__ import annotations

from support import run_cli

import ethos_data


def test_the_public_cache_comes_from_the_first_place_that_names_it(
    tmp_path, monkeypatch
):
    roots = ethos_data.read_settings().roots
    assert roots.public_source.startswith("built-in default")

    run_cli(["config", "set-public-cache", str(tmp_path / "from-file")])
    roots = ethos_data.read_settings().roots
    assert roots.public == tmp_path / "from-file"
    assert roots.public_source.startswith("settings file")

    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "from-env"))
    assert ethos_data.read_settings().roots.public == tmp_path / "from-env"

    roots = ethos_data.read_settings(root=tmp_path / "explicit").roots
    assert roots.public == tmp_path / "explicit"
    assert roots.public_source == "explicit argument"


def test_the_restricted_and_staging_caches_have_no_default():
    roots = ethos_data.read_settings().roots
    assert roots.restricted is None
    assert roots.staging is None


def test_a_setting_is_written_shown_and_removed(tmp_path):
    cache = tmp_path / "restricted"

    code, _, _ = run_cli(["config", "set-restricted-cache", str(cache)])
    assert code == 0
    _, shown, _ = run_cli(["config", "show"])
    assert str(cache) in shown

    code, _, _ = run_cli(["config", "unset-restricted-cache"])
    assert code == 0
    _, shown, _ = run_cli(["config", "show"])
    assert str(cache) not in shown
    assert ethos_data.read_settings().roots.restricted is None


def test_the_environment_wins_over_the_settings_file_for_every_cache(
    tmp_path, monkeypatch
):
    for setter, variable, root in (
        ("set-restricted-cache", "ETHOS_RESTRICTED_DIR", "restricted"),
        ("set-staging-cache", "ETHOS_STAGING_DIR", "staging"),
    ):
        run_cli(["config", setter, str(tmp_path / "file")])
        monkeypatch.setenv(variable, str(tmp_path / "env"))
        roots = ethos_data.read_settings().roots
        assert getattr(roots, root) == tmp_path / "env"
        assert getattr(roots, f"{root}_source") == f"${variable}"


def test_the_public_cache_has_one_setter(tmp_path):
    code, _, err = run_cli(["config", "set-cache", str(tmp_path)])

    assert code == 2
    assert "invalid choice: 'set-cache'" in err
