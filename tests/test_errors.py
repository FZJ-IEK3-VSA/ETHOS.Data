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
    "error, base",
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
def test_each_class_has_its_documented_base(error, base):
    assert issubclass(error, errors.EthosDataError)
    assert issubclass(error, base)


def test_the_facade_exports_every_error():
    for name in errors.__all__:
        assert getattr(ethos_data, name) is getattr(errors, name)


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

    settings = config.config_path()
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_bytes(b"public_cache: [unclosed\n")

    code, _, err = run_cli(["config", "show"])

    assert code == 2
    assert err.startswith("error: ")
    assert "is not valid YAML" in err
