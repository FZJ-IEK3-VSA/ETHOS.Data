"""Which value of a setting wins, and the commands that write one.

Characterisation tests for [Set up your machine]: an explicit argument beats
the environment, which beats the settings file, which beats the built-in
default; the restricted caches are a list with no default, which the
environment replaces; a setting written by ``config set-*`` or
``add-restricted-cache`` is shown by ``config show`` and removed by
``unset-*`` or ``remove-restricted-cache``; and no root contains another.
Where the settings file lives is for ``test_settings_file.py``, so these
tests never name it.
"""

from __future__ import annotations

import os

import pytest
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


def test_the_restricted_caches_and_the_staging_root_have_no_default():
    roots = ethos_data.read_settings().roots
    assert roots.restricted == ()
    assert roots.staging is None


def test_a_setting_is_written_shown_and_removed(tmp_path):
    cache = tmp_path / "staging"

    code, _, _ = run_cli(["config", "set-staging-cache", str(cache)])
    assert code == 0
    _, shown, _ = run_cli(["config", "show"])
    assert str(cache) in shown

    code, _, _ = run_cli(["config", "unset-staging-cache"])
    assert code == 0
    _, shown, _ = run_cli(["config", "show"])
    assert str(cache) not in shown
    assert ethos_data.read_settings().roots.staging is None


def test_restricted_caches_are_listed_in_order_and_removed_one_by_one(tmp_path):
    first, second = tmp_path / "group-a", tmp_path / "group-b"

    assert run_cli(["config", "add-restricted-cache", str(first)])[0] == 0
    assert run_cli(["config", "add-restricted-cache", str(second)])[0] == 0
    assert ethos_data.read_settings().roots.restricted == (first, second)

    code, _, err = run_cli(["config", "add-restricted-cache", str(first)])
    assert code == 2
    assert "already a restricted cache" in err

    assert run_cli(["config", "remove-restricted-cache", str(first)])[0] == 0
    assert ethos_data.read_settings().roots.restricted == (second,)

    code, _, err = run_cli(["config", "remove-restricted-cache", str(first)])
    assert code == 2
    assert "is not a restricted cache" in err


def test_the_environment_replaces_the_list_of_restricted_caches(tmp_path, monkeypatch):
    run_cli(["config", "add-restricted-cache", str(tmp_path / "file")])
    listed = [tmp_path / "env-a", tmp_path / "env-b"]
    monkeypatch.setenv("ETHOS_RESTRICTED_DIRS", os.pathsep.join(map(str, listed)))

    roots = ethos_data.read_settings().roots

    assert roots.restricted == tuple(listed), "nothing is merged"
    assert roots.restricted_source == "$ETHOS_RESTRICTED_DIRS"


def test_the_environment_wins_over_the_settings_file_for_the_staging_root(
    tmp_path, monkeypatch
):
    run_cli(["config", "set-staging-cache", str(tmp_path / "file")])
    monkeypatch.setenv("ETHOS_STAGING_DIR", str(tmp_path / "env"))

    roots = ethos_data.read_settings().roots

    assert roots.staging == tmp_path / "env"
    assert roots.staging_source == "$ETHOS_STAGING_DIR"


@pytest.mark.parametrize(
    "first, second",
    [
        (["set-public-cache", "cache"], ["add-restricted-cache", "cache/restricted"]),
        (["add-restricted-cache", "restricted"], ["set-staging-cache", "restricted"]),
        (["set-staging-cache", "work/staging"], ["set-public-cache", "work"]),
        (["add-restricted-cache", "a/inner"], ["add-restricted-cache", "a"]),
    ],
    ids=["inside", "the same", "containing", "one restricted cache in another"],
)
def test_no_root_is_contains_or_lies_inside_another(tmp_path, first, second):
    command, directory = first
    assert run_cli(["config", command, str(tmp_path / directory)])[0] == 0
    command, directory = second

    code, _, err = run_cli(["config", command, str(tmp_path / directory)])

    assert code == 2
    assert "is, contains or lies inside" in err


def test_the_public_cache_has_one_setter(tmp_path):
    code, _, err = run_cli(["config", "set-cache", str(tmp_path)])

    assert code == 2
    assert "invalid choice: 'set-cache'" in err
