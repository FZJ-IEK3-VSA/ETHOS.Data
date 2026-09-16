# Use ETHOS.Data in your package

Make your package's input data available to its users, examples and tests
without any configuration on their side. ETHOS.RESKit is the example; replace
`reskit` with your package's name. Dataset identifiers and the catalogue tag
below are examples; replace them with a revision released by the maintainer.

## 1. Add the dependency

```toml title="pyproject.toml"
[project]
dependencies = [
  "ethos-data>=0.1.0",
]
```

During development before a package-index release, install ETHOS.Data from
[its repository](../installation.md) in the same environment first.

## 2. Write the collections file

Create `collections.yaml` in a module of your package — for RESKit,
`reskit/data/collections.yaml`:

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/v2026.09/datacatalog.json

collections:
  test_suite:
    title: Data required by the pytest suite
    include:
      - dataset: reskit-test-data

  onshore_wind:
    title: Data for onshore wind workflows
    test:
      include:
        - dataset: reskit-test-data/era5
          files: ["100m_*_component_of_wind.nc", "forecast_surface_roughness.nc"]
        - dataset: reskit-test-data/global-wind-atlas
          files: ["gwa*-like.tif"]
      paths:
        era5: reskit-test-data/era5
        gwa_100m: reskit-test-data/global-wind-atlas/gwa100-like.tif
        gwa_50m: reskit-test-data/global-wind-atlas/gwa50-like.tif
        gwa_200m: reskit-test-data/global-wind-atlas/gwa200-like.tif
    full:
      include:
        - dataset: era5
        - dataset: global-wind-atlas-v3
          files: ["gwa3_250_wind-speed_*.tif"]
      paths:
        era5: era5
        gwa_100m: global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif
        gwa_50m: global-wind-atlas-v3/gwa3_250_wind-speed_50m.tif
        gwa_200m: global-wind-atlas-v3/gwa3_250_wind-speed_200m.tif
```

`paths:` names the inputs a workflow takes, so its callers never see a resource
key. `test:` and `full:` pair a small selection for examples and tests with the
real inputs; both must name the same handles, so the same code runs on either.
`catalog:` pins the catalogue version a release of your package uses; leave it
out to use the current public catalogue. The pin must name a revision that
exists and describes the datasets you select — a tag nobody has released yet,
or a repository that has moved, makes every call raise `CatalogUnavailable`
naming the URL; a user can still override the pin with `$ETHOS_DATA_CATALOG`
or `ethos-data config set-catalog`. See
[Write a collections file](write-a-collections-file.md) for all keys and
patterns.

## 3. Build the handle and the command

Create a small module beside the file — for RESKit, `reskit/data/__init__.py`.
It builds one `ethos_data.Collections` handle on the file, once per process,
and forwards to it; the same module is the body of the package's own data
command:

```python title="reskit/data/__init__.py"
from functools import lru_cache
from pathlib import Path

COLLECTIONS_FILE = Path(__file__).with_name("collections.yaml")


@lru_cache(maxsize=1)
def handle():
    import ethos_data  # on first use, so `import reskit` works without it

    return ethos_data.collections(COLLECTIONS_FILE, tool="reskit")


def paths(collection, test=False):
    return handle().paths(collection, test=test)


def fetch(collection, test=False):
    return handle().fetch(collection, test=test)


def main(argv=None):
    import ethos_data

    return ethos_data.tool_main(COLLECTIONS_FILE, tool="reskit", argv=argv)
```

Wire `main` up as a console script and ship the file as package data, for
example with setuptools:

```toml title="pyproject.toml"
[project.scripts]
reskit-data = "reskit.data:main"

[tool.setuptools.package-data]
"reskit.data" = ["collections.yaml"]
```

Nothing is registered with ETHOS.Data: the module finds the file beside
itself, and `reskit-data` is an ordinary console script. A fresh checkout
needs one reinstall for the script to appear, for example with
`pip install -e . --no-deps`. `tool_main` builds the handle only for the
commands that need it, so `reskit-data --help` and `reskit-data config show`
work without loading the catalogue. `tool` names the package in messages and
gives the command its default name; `catalog=` on both calls is the place for
a package-specific catalogue override, applied below `--catalog` and above
`$ETHOS_DATA_CATALOG`.

## 4. Use the data in code, examples and tests

```python
import reskit as rk
from reskit import data

inputs = data.paths("onshore_wind", test=True)
result = rk.wind.wind_era5_PenaSanchezDunkelWinklerEtAl2025(
    placements=placements,
    era5_path=inputs["era5"],
    gwa_100m_path=inputs["gwa_100m"],
    height_scaling_data={50: inputs["gwa_50m"], 200: inputs["gwa_200m"]},
)
```

`paths()` fetches the collection and returns its handles as
`{handle: absolute path}`, so the example needs no resource key. `test=True`
selects the `test` variant; drop it and the same code runs on the full data.
The whole collection by resource key, and a single file or folder in the
catalogue version the file pins, remain available through the handle:

```python
files = data.handle().fetch("onshore_wind")
era5_folder = data.handle().catalog.path("reskit-test-data/era5")
```

## 5. Check it

From a directory outside the source checkout:

```bash
reskit-data --help
reskit-data list
reskit-data paths onshore_wind --test
```

`--help` lists the commands without loading the catalogue. `list` shows
`onshore_wind [test]` and `onshore_wind [full]` as separate rows. `paths
--test` fetches the test variant and prints one `handle<TAB>path` line per
handle. From the checkout root, the same `list` runs on the file through
`ethos-data`, with no console script involved:

```bash
ethos-data -c reskit/data/collections.yaml list
```

How users call `reskit-data` day to day — fetching inputs, configuring the
cache — belongs in your package's own documentation; ETHOS.Data's pages cover
`ethos-data` and `ethos_data`.

## If the package needs data that is not catalogued yet

- To work with it now: [Stage uncatalogued data](stage-unpublished-data.md).
- To add it to the catalogue: [Propose a dataset](propose-a-dataset.md).

## See also

- [Keep test data in a repository](keep-test-data-in-a-repository.md)
- [Run package tests in CI](run-in-ci.md)
- [API reference](../reference/api/index.md)
