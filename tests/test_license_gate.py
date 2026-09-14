"""Unresolved licensing stops distribution, not development.

An absent licence is a question, not a permission. The two operations that hand
a dataset to other people -- putting it in a shared cache, and publishing it to
dCache -- refuse until somebody has answered it. Staging does not: a staged
dataset is one person's, on one machine, and is unverifiable by construction.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from ethos_data.catalog import Catalog, Dataset, Resource, license_settled
from ethos_data.config import Roots
from ethos_data.linking import LinkError, link
from ethos_data.maintain import namespace
from ethos_data.maintain.manifest import render_dataset, write_dataset
from ethos_data.maintain.upload import preflight

PAYLOAD = b'first file'
RESOLVED = {'licenses': [{'name': 'CC-BY-4.0'}]}


class TestTheRule:
    """What counts as settled, asked of a plain descriptor."""

    def test_a_named_licence_settles_it(self):
        assert license_settled({'licenses': [{'name': 'CC-BY-4.0'}]})

    def test_so_does_an_explicit_resolved(self):
        assert license_settled({'ethos:license_status': 'resolved'})

    @pytest.mark.parametrize('meta', [
        {},                                          # nobody has looked
        {'licenses': []},                            # an empty list says nothing
        {'ethos:license_status': 'unresolved'},      # somebody looked and could not say
        {'ethos:license_status': 'unknown'},
    ])
    def test_everything_else_is_unanswered(self, meta):
        assert not license_settled(meta)


def _catalog(status: str | None) -> Catalog:
    entry = {'ethos:access': 'public'}
    if status is not None:
        entry['ethos:license_status'] = status
    resource = Resource('example', 'a', 'a.txt', len(PAYLOAD),
                        'sha256:' + hashlib.sha256(PAYLOAD).hexdigest(), 'text/plain')
    dataset = Dataset('example', 'Example', entry=entry,
                      _descriptor={'resources': []}, _resources={'a.txt': resource})
    return Catalog('local', {}, {'example': dataset})


@pytest.fixture
def workspace(tmp_path):
    cache = tmp_path / 'cache'
    cache.mkdir()
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'a.txt').write_bytes(PAYLOAD)
    return cache, data, Roots(public=cache)


@pytest.mark.parametrize('status', [None, 'unresolved', 'unknown'])
def test_link_refuses_a_dataset_nobody_has_licensed(workspace, status):
    cache, data, roots = workspace
    with pytest.raises(LinkError, match='unresolved licensing'):
        link(_catalog(status), 'example', data, roots)
    assert not (cache / 'example').exists()


def test_link_says_to_stage_it_instead(workspace):
    _, data, roots = workspace
    with pytest.raises(LinkError, match='staging add'):
        link(_catalog('unresolved'), 'example', data, roots)


def test_link_allows_a_settled_licence(workspace):
    cache, data, roots = workspace
    link(_catalog('resolved'), 'example', data, roots)
    assert (cache / 'example').is_symlink()


def _checkout(root: Path, extra: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / 'catalog.yaml').write_text('name: t\nethos:catalog_role: source\n')
    source = root / 'src'
    source.mkdir(parents=True)
    (source / 'a.txt').write_bytes(PAYLOAD)
    dataset_dir = root / 'datasets' / 'example'
    dataset_dir.mkdir(parents=True)
    meta = {'name': 'example', 'title': 'Example', 'source_dir': str(source),
            'ethos:remote_prefix': 'example', **extra}
    (dataset_dir / 'dataset.yaml').write_text(yaml.safe_dump(meta))
    write_dataset(dataset_dir, render_dataset(dataset_dir))
    return root


def test_link_cache_skips_it_rather_than_linking_it(tmp_path):
    checkout = _checkout(tmp_path / 'catalogue', {'ethos:license_status': 'unresolved'})
    cache = tmp_path / 'cache'

    actions = namespace.plan(checkout, cache)

    assert [(a.verb, a.dataset) for a in actions] == [('skip', 'example')]
    assert 'unresolved licensing' in actions[0].detail
    namespace.apply([a for a in actions if a.changes_anything])
    assert not (cache / 'example').exists()


def test_link_cache_links_it_once_the_terms_are_recorded(tmp_path):
    checkout = _checkout(tmp_path / 'catalogue', RESOLVED)
    cache = tmp_path / 'cache'

    actions = namespace.plan(checkout, cache)

    assert [(a.verb, a.dataset) for a in actions] == [('link', 'example')]


def _package(extra: dict) -> dict:
    return {'name': 'example', 'ethos:access': 'public', 'ethos:remote_prefix': 'example',
            **extra}


def test_upload_refuses_it(tmp_path):
    source = tmp_path / 'src'
    source.mkdir()
    with pytest.raises(SystemExit, match='unresolved licensing'):
        preflight('example', _package({'ethos:license_status': 'unresolved'}), source,
                  allow_internal=False, verify_only=False)


def test_upload_refuses_a_descriptor_that_says_nothing_at_all(tmp_path):
    """The default has to be "nobody has looked", not "nothing applies"."""
    source = tmp_path / 'src'
    source.mkdir()
    with pytest.raises(SystemExit, match='unresolved licensing'):
        preflight('example', _package({}), source, allow_internal=False, verify_only=False)


def test_verify_only_still_works(tmp_path):
    """Rechecking what is already published copies nothing."""
    source = tmp_path / 'src'
    source.mkdir()
    assert preflight('example', _package({'ethos:license_status': 'unresolved'}), source,
                     allow_internal=False, verify_only=True) == 'example'


def test_upload_allows_a_settled_licence(tmp_path):
    source = tmp_path / 'src'
    source.mkdir()
    assert preflight('example', _package(RESOLVED), source,
                     allow_internal=False, verify_only=False) == 'example'


def test_staging_is_not_gated(tmp_path, monkeypatch):
    """The escape hatch the refusals point at has to actually be open."""
    from ethos_data import staging

    monkeypatch.setenv('ETHOS_STAGING_DIR', str(tmp_path / 'staging'))
    data = tmp_path / 'data'
    data.mkdir()
    (data / 'a.txt').write_bytes(PAYLOAD)

    staged = staging.add('example', data, note='terms not settled yet')

    assert staged.entry.is_symlink()
    assert staged.files == 1


def test_the_whole_command_line_refuses(tmp_path, monkeypatch, capsys):
    from ethos_data.cli import main

    monkeypatch.setenv('ETHOS_DATA_DIR', str(tmp_path / 'cache'))
    catalog = tmp_path / 'datacatalog.json'
    catalog.write_text(json.dumps({'datasets': [{
        'name': 'example', 'title': 'Example', 'path': 'example/datapackage.json',
        'ethos:access': 'public', 'ethos:license_status': 'unresolved',
    }]}))
    data = tmp_path / 'data'
    data.mkdir()

    code = main(['--catalog', str(catalog), 'link', 'example', str(data)])

    assert code == 2
    assert 'unresolved licensing' in capsys.readouterr().err
    assert not (tmp_path / 'cache' / 'example').exists()
