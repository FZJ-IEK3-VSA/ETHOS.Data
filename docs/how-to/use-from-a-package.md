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

## 3. Register the collections file

```toml title="pyproject.toml"
[project.entry-points."ethos_data.collections"]
reskit = "reskit.data"
```

The name (`reskit`) is what users pass as `package="reskit"` or `-p reskit`.
The value is the module whose directory contains `collections.yaml`.

Ship the file as package data, for example with setuptools:

```toml title="pyproject.toml"
[tool.setuptools.package-data]
"reskit.data" = ["collections.yaml"]
```

Reinstall the package, for example with `pip install -e . --no-deps`, so that
the entry point is registered.

## 4. Use the data in code, examples and tests

```python
import ethos_data
import reskit as rk

inputs = ethos_data.paths("onshore_wind", package="reskit", test=True)
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
The whole collection by resource key, and a single file or folder, remain
available:

```python
files = ethos_data.fetch("onshore_wind", package="reskit")
era5_folder = ethos_data.path("reskit-test-data/era5", package="reskit")
```

With `package="reskit"`, all three use the catalogue version pinned in step 2.

## 5. Check it

From a directory outside the source checkout:

```bash
ethos-data -p reskit list
ethos-data -p reskit info onshore_wind --test
ethos-data -p reskit plan test_suite
ethos-data -p reskit paths onshore_wind --test
```

`list` shows `onshore_wind [test]` and `onshore_wind [full]` as separate rows.
`paths --test` fetches the test variant and prints one `handle<TAB>path` line
per handle.

## If the package needs data that is not catalogued yet

- To work with it now: [Stage uncatalogued data](stage-unpublished-data.md).
- To add it to the catalogue: [Propose a dataset](propose-a-dataset.md).

## See also

- [Keep test data in a repository](keep-test-data-in-a-repository.md)
- [Run package tests in CI](run-in-ci.md)
- [API reference](../reference/api/index.md)
