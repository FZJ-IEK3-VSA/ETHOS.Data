"""The two handles: ``ethos_data.catalog`` for keys, ``ethos_data.collections`` for a
tool's file -- and the command a tool builds on the latter."""
import hashlib
import json
from pathlib import Path

import pytest

import ethos_data
from ethos_data import config, retrieval, selection
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


# -- the catalogue handle: keys ------------------------------------------------------------


def test_a_file_inside_a_family_member(world):
    _, cache, index = world
    found = ethos_data.catalog(str(index)).path("family/alpha/era5/x.nc")
    assert found == cache / "family/alpha/era5/x.nc"
    assert found.is_absolute()


def test_a_shapefile_brings_its_sidecars(world, monkeypatch):
    _, cache, index = world
    asked = []
    real = retrieval.download

    def spy(catalog, resources, **kwargs):
        asked.extend(r.key for r in resources)
        return real(catalog, resources, **kwargs)

    monkeypatch.setattr(retrieval, "download", spy)
    found = ethos_data.catalog(str(index)).path("family/alpha/sites.shp")
    assert found == cache / "family/alpha/sites.shp"
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
    assert ethos_data.catalog(str(index)).path(key) == cache / expected


def test_an_unknown_key_says_so(world):
    _, _, index = world
    catalog = ethos_data.catalog(str(index))
    with pytest.raises(KeyError, match="no file or folder 'nope'"):
        catalog.path("flat/nope")
    with pytest.raises(ethos_data.UnknownDataset, match="missing"):
        catalog.path("missing/file.csv")
    with pytest.raises(ethos_data.UnknownDataset, match="family"):
        catalog.path("family/beta/x.nc")


def test_resources_lists_without_fetching(world, monkeypatch):
    _, _, index = world
    monkeypatch.setattr(retrieval, "download", lambda *a, **k: pytest.fail("listing must not fetch"))
    listed = ethos_data.catalog(str(index)).resources("family/alpha/era5")
    assert [r.key for r in listed] == ["family/alpha/era5/x.nc", "family/alpha/era5/y.nc"]


def test_a_handle_is_built_once_and_reused(world, monkeypatch):
    """The catalogue is loaded when the handle is built, not on every call."""
    _, cache, index = world
    catalog = ethos_data.catalog(str(index))
    loads = []
    monkeypatch.setattr(ethos_data, "load_catalog", lambda location: loads.append(location))
    assert catalog.path("family/alpha/era5/y.nc") == cache / "family/alpha/era5/y.nc"
    assert catalog.path("flat/one.csv") == cache / "flat/one.csv"
    assert loads == []


def test_without_a_catalogue_the_public_one_is_used(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: ({}, {}))
    monkeypatch.delenv("ETHOS_DATA_CATALOG", raising=False)
    asked = []

    def stop(location):
        asked.append(location)
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(ethos_data, "load_catalog", stop)
    with pytest.raises(RuntimeError):
        ethos_data.catalog()
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


# -- the collections handle: a tool's file -------------------------------------------------


@pytest.fixture
def shipped(world):
    """A tool, faketool, with a collections file beside its data module -- and
    nothing registered anywhere. Returns the file."""
    tmp_path, _, index = world
    package = tmp_path / "site" / "faketool" / "data"
    package.mkdir(parents=True)
    file = package / "collections.yaml"
    file.write_text(
        f"catalog: {index.as_posix()}\n"
        "collections:\n  wind:\n    include:\n      - dataset: family/alpha\n        files: ['era5/*.nc']\n")
    return file


def test_a_tool_builds_its_handle_from_the_file_beside_its_code(shipped, world):
    _, cache, _ = world
    data = ethos_data.collections(shipped, tool="faketool")
    assert data.tool == "faketool"
    assert data.names() == ["wind"]
    files = data.fetch("wind", progressbar=False)
    assert sorted(files) == ["family/alpha/era5/x.nc", "family/alpha/era5/y.nc"]
    # .catalog is the catalogue the file pins, for keys.
    assert data.catalog.path("family/alpha/era5") == cache / "family/alpha/era5"
    assert data.catalog.staged, "the overlay is applied once, when the handle is built"


def test_an_unknown_collection_names_the_tool(shipped):
    data = ethos_data.collections(shipped, tool="faketool")
    with pytest.raises(ethos_data.UnknownCollection, match="faketool defines: wind"):
        data.fetch("nosuch", progressbar=False)
    with pytest.raises(ethos_data.UnknownCollection, match="this file defines: wind"):
        ethos_data.collections(shipped).resolve("nosuch")


def test_the_one_call_forms_take_the_file(shipped):
    files = ethos_data.fetch("wind", shipped, progressbar=False)
    assert sorted(files) == ["family/alpha/era5/x.nc", "family/alpha/era5/y.nc"]
    assert [r.key for r in ethos_data.resolve("wind", shipped)] == sorted(files)
    with pytest.raises(TypeError):
        ethos_data.fetch("wind")  # there is no default file; say which one


def test_the_tool_command_runs_the_collection_commands_on_its_file(shipped, world, capsys):
    _, cache, _ = world
    data = ethos_data.collections(shipped, tool="faketool")
    assert data.main(["list"]) == 0
    assert "wind" in capsys.readouterr().out
    assert data.main(["fetch", "wind"]) == 0
    capsys.readouterr()
    # Keys resolve against the catalogue the file pins.
    assert data.main(["path", "family/alpha/sites.shp"]) == 0
    assert capsys.readouterr().out.strip() == str(cache / "family/alpha/sites.shp")
    assert data.main(["ls", "family/alpha/era5"]) == 0
    assert "family/alpha/era5/x.nc" in capsys.readouterr().out
    # A refusal is a message naming the tool, not a traceback.
    assert data.main(["fetch", "nosuch"]) == 2
    assert "faketool defines: wind" in capsys.readouterr().err


def test_the_tool_command_is_named_after_the_tool_and_has_no_c_flag(shipped, capsys):
    data = ethos_data.collections(shipped, tool="faketool")
    with pytest.raises(SystemExit) as stop:
        data.main(["--help"])
    assert stop.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: faketool-data")
    assert "--collections" not in out, "the file is fixed; there is nothing to name"
    assert "materialize" not in out, "cache maintenance stays with ethos-data"
    with pytest.raises(SystemExit) as refused:
        data.main(["-c", "elsewhere.yaml", "list"])
    assert refused.value.code == 2
    with pytest.raises(SystemExit) as stop:
        data.main(["--help"], prog="fake-data")
    assert capsys.readouterr().out.startswith("usage: fake-data")


def test_the_tool_command_takes_catalog_for_one_run(shipped, world, tmp_path, capsys):
    """The handle already chose its catalogue; only an explicit --catalog changes it."""
    other = tmp_path / "other" / "datacatalog.json"
    other.parent.mkdir()
    other.write_text(json.dumps({"name": "other", "datasets": []}))
    data = ethos_data.collections(shipped, tool="faketool")
    assert data.main(["--catalog", str(other), "list"]) == 1
    assert "unresolvable" in capsys.readouterr().out
    assert data.main(["list"]) == 0, "the handle itself is untouched"


def test_ethos_data_without_a_file_points_at_the_tool_command(world, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["list"]) == 2
    err = capsys.readouterr().err
    assert "no collections file" in err and "-c" in err


def test_tool_main_builds_the_handle_only_when_a_command_needs_it(shipped, world, monkeypatch, capsys):
    """``--help`` and ``config show`` must work offline: no catalogue is loaded for them."""
    monkeypatch.setattr(selection, "load_catalog",
                        lambda location: pytest.fail(f"loaded the catalogue at {location}"))
    monkeypatch.setattr(ethos_data, "load_catalog",
                        lambda location: pytest.fail(f"loaded the catalogue at {location}"))
    with pytest.raises(SystemExit) as stop:
        ethos_data.tool_main(shipped, tool="faketool", argv=["--help"])
    assert stop.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: faketool-data")
    assert "wind" in out, "the example collection is read from the file, not the catalogue"
    assert ethos_data.tool_main(shipped, tool="faketool", argv=["config", "show"]) == 0


def test_tool_main_runs_the_commands_and_reuses_one_handle(shipped, monkeypatch, capsys):
    loads = []
    real = selection.load_catalog
    monkeypatch.setattr(selection, "load_catalog", lambda location: loads.append(location) or real(location))
    assert ethos_data.tool_main(shipped, tool="faketool", argv=["fetch", "wind"]) == 0
    assert len(loads) == 1
    assert ethos_data.tool_main(shipped, tool="faketool", prog="fake-data", argv=["fetch", "nosuch"]) == 2
    assert "faketool defines: wind" in capsys.readouterr().err


def test_an_unreachable_pin_can_still_be_overridden_with_catalog(shipped, world, tmp_path, capsys):
    """The point of --catalog: a tag nobody has cut yet must not block the command."""
    _, _, index = world
    broken = shipped.with_name("broken.yaml")
    broken.write_text("catalog: https://example.invalid/nowhere/datacatalog.json\n"
                      "collections:\n  wind:\n    include:\n      - dataset: family/alpha\n")
    assert ethos_data.tool_main(broken, tool="faketool", argv=["list"]) == 2
    assert "cannot read the catalogue" in capsys.readouterr().err
    assert ethos_data.tool_main(broken, tool="faketool", argv=["--catalog", str(index), "list"]) == 0
    assert "wind" in capsys.readouterr().out


def test_the_tools_own_override_sits_below_catalog_and_above_the_environment(shipped, world, tmp_path, monkeypatch, capsys):
    _, _, index = world
    other = tmp_path / "other" / "datacatalog.json"
    other.parent.mkdir()
    other.write_text(json.dumps({"name": "other", "datasets": []}))
    # The tool's override beats the environment ...
    monkeypatch.setenv("ETHOS_DATA_CATALOG", str(other))
    assert ethos_data.tool_main(shipped, tool="faketool", catalog=str(index), argv=["list"]) == 0
    capsys.readouterr()
    # ... and --catalog beats the tool's override.
    assert ethos_data.tool_main(shipped, tool="faketool", catalog=str(index),
                                argv=["--catalog", str(other), "list"]) == 1
    assert "unresolvable" in capsys.readouterr().out
