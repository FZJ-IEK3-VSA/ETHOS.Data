"""``ethos-data link``: making one cache entry point at data already on disk.

The entry has to be a *symbolic link* specifically, because that is how the cache
records that the bytes are borrowed: retrieval reads them in place and refuses to
write through them. So the tests worth having are the ones about what an entry
is, not about whether a file appeared.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from ethos_data.access import ORIGIN_LINK, locate
from ethos_data.catalog import Catalog, Dataset, Resource, UnknownDataset
from ethos_data.cli import main
from ethos_data.config import Roots
from ethos_data.linking import LinkError, link, unlink

CONTENT = {'a.txt': b'first file', 'sub/b.txt': b'second file'}


def _catalog(access: str = 'public') -> Catalog:
    resources = {
        path: Resource('example', path.replace('/', '-'), path, len(payload),
                       'sha256:' + hashlib.sha256(payload).hexdigest(), 'text/plain')
        for path, payload in CONTENT.items()
    }
    dataset = Dataset('example', 'Example', entry={'ethos:access': access},
                      _descriptor={'resources': []}, _resources=resources)
    return Catalog('local', {}, {'example': dataset})


def _write(directory):
    for path, payload in CONTENT.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return directory


@pytest.fixture
def workspace(tmp_path):
    cache = tmp_path / 'cache'
    cache.mkdir()
    return cache, _write(tmp_path / 'data'), Roots(public=cache)


def test_creates_a_symbolic_link_in_the_cache(workspace):
    cache, data, roots = workspace
    report = link(_catalog(), 'example', data, roots)

    entry = cache / 'example'
    assert report.verb == 'linked'
    assert entry.is_symlink()
    assert (entry / 'a.txt').read_bytes() == CONTENT['a.txt']


def test_the_link_is_what_makes_retrieval_read_in_place(workspace):
    _, data, roots = workspace
    catalog = _catalog()
    link(catalog, 'example', data, roots)

    resources = list(catalog.dataset('example').resources.values())
    located = locate(catalog, resources, roots)

    assert all(location.in_place for location in located)
    assert {location.origin for location in located} == {ORIGIN_LINK}


def test_records_the_directory_it_was_given(workspace, tmp_path):
    """Not the resolved one: a curated path that itself goes through a link is
    the one that stays correct when the storage behind it moves."""
    cache, data, roots = workspace
    through = tmp_path / 'curated'
    through.symlink_to(data, target_is_directory=True)

    link(_catalog(), 'example', through, roots)

    # By final component: Windows records the link with a \\?\ extended-length
    # prefix, so the part that carries the meaning is which directory was named.
    recorded = (cache / 'example').readlink()
    assert recorded.name == through.name == 'curated'
    assert recorded.name != data.name


def test_a_relative_directory_is_made_absolute(workspace, monkeypatch, tmp_path):
    cache, data, roots = workspace
    monkeypatch.chdir(tmp_path)

    link(_catalog(), 'example', 'data', roots)

    # Resolved rather than compared literally: a link recorded relative to the
    # cache directory would point at nothing at all.
    assert (cache / 'example').resolve() == data.resolve()


def test_refuses_a_directory_that_is_not_there(workspace, tmp_path):
    cache, _, roots = workspace
    with pytest.raises(LinkError, match='not a directory'):
        link(_catalog(), 'example', tmp_path / 'nowhere', roots)
    assert not (cache / 'example').exists()


def test_will_not_replace_a_directory_the_cache_owns(workspace):
    cache, data, roots = workspace
    owned = cache / 'example'
    owned.mkdir()
    (owned / 'a.txt').write_bytes(b'downloaded earlier')

    with pytest.raises(LinkError, match='data the cache owns'):
        link(_catalog(), 'example', data, roots)
    assert (owned / 'a.txt').read_bytes() == b'downloaded earlier'


def test_repointing_needs_force(workspace, tmp_path):
    cache, data, roots = workspace
    other = _write(tmp_path / 'other')
    link(_catalog(), 'example', other, roots)

    with pytest.raises(LinkError, match='already points at'):
        link(_catalog(), 'example', data, roots)

    report = link(_catalog(), 'example', data, roots, force=True)
    assert report.verb == 'repointed'
    assert (cache / 'example').resolve() == data.resolve()


def test_restricted_data_is_linked_in_the_restricted_root(workspace, tmp_path):
    cache, data, _ = workspace
    restricted = tmp_path / 'restricted'
    roots = Roots(public=cache, restricted=restricted)

    link(_catalog('restricted'), 'example', data, roots)

    assert (restricted / 'example').is_symlink()
    assert not (cache / 'example').exists()


def test_restricted_data_without_a_restricted_cache_is_refused(workspace):
    cache, data, roots = workspace
    with pytest.raises(LinkError, match='no restricted cache is configured'):
        link(_catalog('restricted'), 'example', data, roots)
    # Never the public cache: that is the one place licensed bytes may not go.
    assert not (cache / 'example').exists()


def test_an_unknown_dataset_is_not_linked(workspace):
    _, data, roots = workspace
    with pytest.raises(UnknownDataset):
        link(_catalog(), 'mystery', data, roots)


def test_a_link_one_level_wrong_is_reported_but_still_made(workspace, tmp_path):
    cache, data, roots = workspace
    report = link(_catalog(), 'example', data.parent, roots)

    assert report.missing == 'a.txt'
    assert (cache / 'example').is_symlink()


def test_unlink_removes_the_entry_and_not_the_data(workspace):
    cache, data, roots = workspace
    link(_catalog(), 'example', data, roots)

    report = unlink(_catalog(), 'example', roots)

    assert report.verb == 'removed'
    assert not (cache / 'example').exists()
    assert (data / 'a.txt').read_bytes() == CONTENT['a.txt']


def test_unlink_refuses_a_real_directory(workspace):
    cache, _, roots = workspace
    owned = cache / 'example'
    owned.mkdir()
    (owned / 'a.txt').write_bytes(b'downloaded earlier')

    with pytest.raises(LinkError, match='real directory'):
        unlink(_catalog(), 'example', roots)
    assert (owned / 'a.txt').exists()


def _cli_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv('ETHOS_DATA_DIR', str(tmp_path / 'cache'))
    monkeypatch.delenv('ETHOS_RESTRICTED_DIR', raising=False)
    catalog = tmp_path / 'datacatalog.json'
    catalog.write_text(json.dumps({'datasets': [{
        'name': 'example', 'title': 'Example', 'path': 'example/datapackage.json',
        'ethos:access': 'public', 'ethos:file_count': 1, 'ethos:total_bytes': 10,
    }]}))
    package = tmp_path / 'example'
    package.mkdir()
    (package / 'datapackage.json').write_text(json.dumps({
        'name': 'example',
        'resources': [{'name': 'a', 'path': 'a.txt', 'bytes': 10, 'mediatype': 'text/plain',
                       'hash': 'sha256:' + hashlib.sha256(CONTENT['a.txt']).hexdigest()}],
    }))
    return catalog, _write(tmp_path / 'data')


def test_cli_links_and_unlinks(tmp_path, monkeypatch, capsys):
    catalog, data = _cli_workspace(tmp_path, monkeypatch)

    assert main(['--catalog', str(catalog), 'link', 'example', str(data)]) == 0
    assert (tmp_path / 'cache' / 'example').is_symlink()
    assert 'linked' in capsys.readouterr().out

    assert main(['--catalog', str(catalog), 'unlink', 'example']) == 0
    assert not (tmp_path / 'cache' / 'example').exists()
    assert (data / 'a.txt').exists()


def test_cli_reports_a_refusal_without_a_traceback(tmp_path, monkeypatch, capsys):
    catalog, _ = _cli_workspace(tmp_path, monkeypatch)

    code = main(['--catalog', str(catalog), 'link', 'example', str(tmp_path / 'nowhere')])

    assert code == 2
    assert 'error: not a directory' in capsys.readouterr().err
