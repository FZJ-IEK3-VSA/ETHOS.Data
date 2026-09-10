"""The Python and CLI workflows must resolve the same development data."""
import json
import urllib.request

import pytest

import ethos_data
from ethos_data import config
from ethos_data.cli import main
from ethos_data.catalog import Catalog, Dataset, Resource


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'load_config', lambda: ({}, {}))
    monkeypatch.setenv('ETHOS_DATA_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('ETHOS_STAGING_DIR', str(tmp_path / 'staging'))
    monkeypatch.delenv('ETHOS_RESTRICTED_DIR', raising=False)
    monkeypatch.delenv('ETHOS_SKIP_UNAVAILABLE', raising=False)
    def no_network(*args, **kwargs):
        pytest.fail('Staged resource attempted network access')
    monkeypatch.setattr(urllib.request, 'urlopen', no_network)
    staged = tmp_path / 'staging' / 'example'
    staged.mkdir(parents=True)
    (staged / 'new.txt').write_text('development bytes')
    (tmp_path / 'datacatalog.json').write_text(json.dumps({'datasets': []}))
    collections = tmp_path / 'collections.yaml'
    collections.write_text('catalog: datacatalog.json\ncollections:\n  test:\n    include:\n      - dataset: example\n        files: ["**"]\n')
    return tmp_path, collections, staged


def test_new_dataset_matches_cli_and_python(workspace):
    root, collections, staged = workspace
    with pytest.warns(UserWarning):
        resolved = ethos_data.resolve('test', collections)
        files = ethos_data.fetch('test', collections, progressbar=False)
        assert main(['-c', str(collections), 'fetch', 'test']) == 0
        one = ethos_data.fetch_one('example/new.txt', str(root / 'datacatalog.json'))
    assert [r.key for r in resolved] == ['example/new.txt']
    assert files == {'example/new.txt': staged / 'new.txt'}
    assert one == staged / 'new.txt'
    assert not (root / 'cache' / 'example').exists()


def test_overlay_does_not_mutate_canonical_catalogue(workspace):
    _, collections, _ = workspace
    old = Resource('example', 'old', 'old.txt', 1, 'sha256:abc', 'text/plain')
    dataset = Dataset('example', 'Official', entry={'ethos:access': 'public'},
                      _descriptor={'resources': []}, _resources={'old.txt': old})
    catalog = Catalog('local', {}, {'example': dataset})
    with pytest.warns(UserWarning):
        overlaid = ethos_data.load_collections(collections, catalog=catalog)
    assert [r.path for r in overlaid.resolve('test')] == ['new.txt']
    canonical = ethos_data.load_collections(collections, catalog=catalog, include_staging=False)
    assert [r.path for r in canonical.resolve('test')] == ['old.txt']
    assert catalog.datasets['example'] is dataset


def test_restricted_catalogue_entry_is_not_shadowed(workspace):
    _, collections, _ = workspace
    dataset = Dataset('example', 'Licensed', entry={'ethos:access': 'restricted'},
                      _descriptor={'resources': []})
    catalog = Catalog('local', {}, {'example': dataset})
    with pytest.warns(UserWarning, match='IGNORED'):
        loaded = ethos_data.load_collections(collections, catalog=catalog)
    assert loaded.catalog.datasets['example'] is dataset


def test_explicit_roots_control_the_overlay(workspace, tmp_path):
    _, collections, _ = workspace
    roots = config.Roots(public=tmp_path / 'elsewhere')
    loaded = ethos_data.load_collections(collections, roots=roots)
    with pytest.raises(KeyError, match='unknown dataset'):
        loaded.resolve('test')


def test_broken_staging_link_fails_python_and_cli(workspace, capsys):
    root, collections, _ = workspace
    (root / 'staging' / 'broken').symlink_to(root / 'missing-input', target_is_directory=True)
    collections.write_text('catalog: datacatalog.json\ncollections:\n  test:\n    include:\n      - dataset: broken\n')
    for call in (lambda: ethos_data.fetch('test', collections, progressbar=False),
                 lambda: ethos_data.resolve('test', collections),
                 lambda: ethos_data.fetch_one('broken/input.txt', str(root / 'datacatalog.json'))):
        with pytest.raises(ethos_data.AccessError, match="staging entry 'broken'"):
            call()
    assert main(['-c', str(collections), 'fetch', 'test']) == 2
    assert "staging entry 'broken'" in capsys.readouterr().err
