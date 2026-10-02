"""Refusals are typed exceptions, and the command line turns them into one line.

Library code never exits the process: a script, a test and the command line
receive the same exception. The command line prints ``error: <message>`` and
exits ``2`` when a request could not be served, ``1`` when a maintenance
command refused its input, the statuses the CLI references document.
"""

from __future__ import annotations

import pytest
from support import run_cli

import ethos_data
from ethos_data import errors


@pytest.mark.parametrize(
    "error, legacy",
    [
        (errors.UnknownDataset, KeyError),
        (errors.UnknownKey, KeyError),
        (errors.UnknownCollection, KeyError),
        (errors.CatalogUnavailable, OSError),
        (errors.IncompleteCatalog, FileNotFoundError),
        (errors.CollectionError, ValueError),
        (errors.BundleError, ValueError),
        (errors.ConfigurationError, ValueError),
        (errors.AccessError, RuntimeError),
        (errors.LinkError, RuntimeError),
        (errors.DescriptorError, ValueError),
    ],
)
def test_every_refusal_is_still_the_exception_it_used_to_be(error, legacy):
    assert issubclass(error, errors.EthosDataError)
    assert issubclass(error, legacy), "an `except` written for an older release"


def test_the_old_import_paths_still_work():
    from ethos_data.access import AccessError
    from ethos_data.bundles import BundleError
    from ethos_data.catalogs import UnknownDataset
    from ethos_data.linking import LinkError
    from ethos_data.selection import CollectionError

    assert AccessError is ethos_data.AccessError is errors.AccessError
    assert BundleError is errors.BundleError
    assert UnknownDataset is errors.UnknownDataset
    assert LinkError is errors.LinkError
    assert CollectionError is errors.CollectionError


def test_a_refused_descriptor_exits_1_with_one_line(source):
    source.dataset("draft", {"a.csv": "1"}, ethos_access="secret")

    code, _, err = source.build()

    assert code == 1
    assert err.startswith("error: draft: ethos:access must be one of")
    assert "Traceback" not in err


def test_a_refusal_is_raised_by_the_library_rather_than_exiting(source):
    from ethos_data.maintain.manifest import run

    source.dataset("draft", {"a.csv": "1"}, ethos_access="secret")
    with pytest.raises(errors.DescriptorError, match="ethos:access"):
        run(source.root, [])


def test_a_settings_file_that_is_not_yaml_is_an_error_not_a_traceback(
    _isolated_settings,
):
    from ethos_data import config

    settings = config.config_path("user")
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_bytes(b"public_cache: [unclosed\n")

    code, _, err = run_cli(["config", "show"])

    assert code == 2
    assert err.startswith("error: ")
    assert "is not valid YAML" in err
