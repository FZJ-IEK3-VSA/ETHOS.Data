"""ethos_data.path, collections files registered by packages, and the default catalogue."""
import hashlib
import json
import sys
from importlib import metadata
from pathlib import Path

import pytest

import ethos_data
from ethos_data import config, selection
from ethos_data.cli import main


def _write(path: Path, text: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    data = path.read_bytes()
    return {"bytes": len(data), "hash": "sha256:" + hashlib.sha256(data).hexdigest()}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A catalogue whose every file is already in the cache, so nothing downloads."""
    monkeypatch.setattr(config, "load_config", lambda: ({}, {}))
    for variable in ("ETHOS_DATA_CATALOG", "ETHOS_STAGING_DIR", "ETHOS_RESTRICTED_DIR",
                     "ETHOS_SKIP_UNAVAILABLE"):
        monkeypatch.delenv(variable, raising=False)
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))

    layout = {
        "family/alpha": {"era5/x.nc": "x", "era5/y.nc": "y", "sites.shp": "shp", "sites.dbf": "dbf"},
        "flat": {"one.csv": "1", "sub/two.csv": "2", "sub.csv": "s"},
    }
    catalogue = tmp_path / "catalogue"
    entries = [{"name": "family", "ethos:namespace": True}]
    for name, files in layout.items():
        resources = []
        for relative, text in files.items():
            resource = {"name": relative, "path": relative, **_write(cache / name / relative, text)}
            if relative == "sites.shp":
                resource["ethos:sidecars"] = ["sites.dbf"]
            resources.append(resource)
        package = catalogue / "datasets" / name / "datapackage.json"
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_text(json.dumps({"name": name, "resources": resources}))
        entries.append({"name": name, "path": f"datasets/{name}/datapackage.json",
                        "ethos:license_status": "resolved"})
    index = catalogue / "datacatalog.json"
    index.write_text(json.dumps({"name": "test", "ethos:publication_url": "https://example.invalid",
                                 "datasets": entries}))
    return tmp_path, cache, index


def test_a_file_inside_a_family_member(world):
    _, cache, index = world
    found = ethos_data.path("family/alpha/era5/x.nc", catalog=str(index))
    assert found == cache / "family/alpha/era5/x.nc"
    assert found.is_absolute()


def test_a_shapefile_brings_its_sidecars(world, monkeypatch):
    _, cache, index = world
    asked = []
    real = ethos_data.download

    def spy(catalog, resources, **kwargs):
        asked.extend(r.key for r in resources)
        return real(catalog, resources, **kwargs)

    monkeypatch.setattr(ethos_data, "download", spy)
    assert ethos_data.path("family/alpha/sites.shp", catalog=str(index)) == cache / "family/alpha/sites.shp"
    assert asked == ["family/alpha/sites.shp", "family/alpha/sites.dbf"]


@pytest.mark.parametrize("key, expected", [
    ("family/alpha/era5", "family/alpha/era5"),
    ("family/alpha/era5/", "family/alpha/era5"),
    ("flat/sub", "flat/sub"),          # the folder, not the sibling file sub.csv
    ("flat", "flat"),
    ("family/alpha", "family/alpha"),
    ("family", "family"),
])
def test_a_folder_a_dataset_or_a_family(world, key, expected):
    _, cache, index = world
    assert ethos_data.path(key, catalog=str(index)) == cache / expected


def test_an_unknown_key_says_so(world):
    _, _, index = world
    with pytest.raises(KeyError, match="no file or folder 'nope'"):
        ethos_data.path("flat/nope", catalog=str(index))
    with pytest.raises(ethos_data.UnknownDataset, match="missing"):
        ethos_data.path("missing/file.csv", catalog=str(index))
    with pytest.raises(ethos_data.UnknownDataset, match="family"):
        ethos_data.path("family/beta/x.nc", catalog=str(index))


def test_fetch_one_accepts_a_family_member_key(world):
    _, cache, index = world
    assert ethos_data.fetch_one("family/alpha/era5/y.nc", str(index)) == cache / "family/alpha/era5/y.nc"


def test_without_a_catalogue_the_public_one_is_used(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: ({}, {}))
    monkeypatch.delenv("ETHOS_DATA_CATALOG", raising=False)
    asked = []

    def stop(location):
        asked.append(location)
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(ethos_data, "load_catalog", stop)
    with pytest.raises(RuntimeError):
        ethos_data.path("some-dataset/file.csv")
    assert asked == [config.DEFAULT_CATALOG]


def test_a_collections_file_without_a_pin_uses_the_public_catalogue(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: ({}, {}))
    monkeypatch.delenv("ETHOS_STAGING_DIR", raising=False)
    asked = []
    monkeypatch.setattr(selection, "load_catalog",
                        lambda location: asked.append(location) or ethos_data.Catalog(location, {}, {}))
    collections = tmp_path / "collections.yaml"
    collections.write_text("collections: {}\n")
    ethos_data.load_collections(collections)
    assert asked == [config.DEFAULT_CATALOG]


def test_the_catalogue_variable_beats_a_config_file(monkeypatch):
    monkeypatch.setattr(config, "load_config",
                        lambda: ({"catalog": "/from/config.json"}, {"catalog": "user config"}))
    monkeypatch.setenv("ETHOS_DATA_CATALOG", "https://example.invalid/datacatalog.json")
    assert config.resolve_catalog() == ("https://example.invalid/datacatalog.json", "$ETHOS_DATA_CATALOG")
    assert config.resolve_catalog("explicit.json")[0] == "explicit.json"


@pytest.fixture
def registered(world, monkeypatch):
    """An installed package, fakepkg, that registers its collections file."""
    tmp_path, _, index = world
    package = tmp_path / "site" / "fakepkg"
    (package / "data").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "data" / "__init__.py").write_text("")
    (package / "data" / "collections.yaml").write_text(
        f"catalog: {index.as_posix()}\n"
        "collections:\n  wind:\n    include:\n      - dataset: family/alpha\n        files: ['era5/*.nc']\n")
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    for name in ("fakepkg", "fakepkg.data"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    entry = metadata.EntryPoint(name="fakepkg", value="fakepkg.data", group=selection.ENTRY_POINT_GROUP)
    monkeypatch.setattr(metadata, "entry_points", lambda: metadata.EntryPoints([entry]))
    return world


def test_a_package_registers_its_collections_file(registered):
    tmp_path = registered[0]
    assert selection.registered_packages() == {"fakepkg": "fakepkg.data"}
    assert ethos_data.package_collections("fakepkg") == tmp_path / "site/fakepkg/data/collections.yaml"


def test_fetch_and_path_by_package_name(registered):
    _, cache, _ = registered
    files = ethos_data.fetch("wind", package="fakepkg", progressbar=False)
    assert sorted(files) == ["family/alpha/era5/x.nc", "family/alpha/era5/y.nc"]
    # path() resolves against the catalogue the package pins.
    assert ethos_data.path("family/alpha/era5", package="fakepkg") == cache / "family/alpha/era5"


def test_collections_and_package_are_alternatives(registered):
    with pytest.raises(TypeError):
        ethos_data.fetch("wind", collections="collections.yaml", package="fakepkg")
    with pytest.raises(TypeError):
        ethos_data.fetch("wind")


def test_the_cli_takes_a_package_name(registered, capsys):
    _, cache, _ = registered
    assert main(["-p", "fakepkg", "fetch", "wind"]) == 0
    capsys.readouterr()
    assert main(["-p", "fakepkg", "path", "family/alpha/sites.shp"]) == 0
    assert capsys.readouterr().out.strip() == str(cache / "family/alpha/sites.shp")
    assert main(["-p", "nosuch", "list"]) == 2
    assert "nosuch" in capsys.readouterr().err
