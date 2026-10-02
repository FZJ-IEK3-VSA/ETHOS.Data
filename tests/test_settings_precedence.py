"""Which value of a setting wins, and the commands that write one.

Characterisation tests for [Set up your machine]: an explicit argument beats
the environment, which beats the settings file, which beats the built-in
default; the restricted cache has no default; and a setting written by
``config set-*`` is shown by ``config show`` and removed by ``unset-*``.
The order stays when the settings move to one file per account; where the
file lives does not, so these tests never name it.
"""

from __future__ import annotations

from support import run_cli

import ethos_data


def test_the_public_cache_comes_from_the_first_place_that_names_it(
    tmp_path, monkeypatch
):
    assert ethos_data.resolve_public_cache().source.startswith("built-in default")

    run_cli(["config", "set-public-cache", str(tmp_path / "from-file")])
    from_file = ethos_data.resolve_public_cache()
    assert from_file.value == tmp_path / "from-file"
    assert from_file.source.startswith("settings file")

    monkeypatch.setenv("ETHOS_DATA_DIR", str(tmp_path / "from-env"))
    assert ethos_data.resolve_public_cache().value == tmp_path / "from-env"

    explicit = ethos_data.resolve_public_cache(tmp_path / "explicit")
    assert explicit.value == tmp_path / "explicit"
    assert explicit.source == "explicit argument"


def test_the_restricted_and_staging_caches_have_no_default():
    assert ethos_data.resolve_restricted_cache() is None
    assert ethos_data.resolve_staging_cache() is None


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
    assert ethos_data.resolve_restricted_cache() is None


def test_the_environment_wins_over_the_settings_file_for_every_cache(
    tmp_path, monkeypatch
):
    for setter, variable, resolve in (
        (
            "set-restricted-cache",
            "ETHOS_RESTRICTED_DIR",
            ethos_data.resolve_restricted_cache,
        ),
        ("set-staging-cache", "ETHOS_STAGING_DIR", ethos_data.resolve_staging_cache),
    ):
        run_cli(["config", setter, str(tmp_path / "file")])
        monkeypatch.setenv(variable, str(tmp_path / "env"))
        resolved = resolve()
        assert resolved.value == tmp_path / "env"
        assert resolved.source == f"${variable}"


def test_a_dataset_root_is_written_and_removed(tmp_path):
    code, _, _ = run_cli(["config", "set-root", "flat", str(tmp_path / "flat")])
    assert code == 0
    assert ethos_data.dataset_roots() == {"flat": str(tmp_path / "flat")}

    code, _, _ = run_cli(["config", "unset-root", "flat"])
    assert code == 0
    assert ethos_data.dataset_roots() == {}
