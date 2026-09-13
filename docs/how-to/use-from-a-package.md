# Use ETHOS.Data in your package

Make your package's input data available to its users, examples and tests
without any configuration on their side. ETHOS.RESKit is the example; replace
`reskit` with your package's name.

## 1. Add the dependency

```toml title="pyproject.toml"
[project]
dependencies = [
  "ethos-data>=0.1.0",
]
```

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
    include:
      - dataset: reskit-test-data/era5
        files: ["100m_*_component_of_wind.nc"]
      - dataset: landcover
        files: ["*.tif"]
```

`catalog:` pins the catalogue version a release of your package uses. Leave it
out to use the current public catalogue. See
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

files = ethos_data.fetch("onshore_wind", package="reskit")
era5_folder = ethos_data.path("reskit-test-data/era5", package="reskit")
```

With `package="reskit"`, `path()` uses the catalogue version pinned in step 2.

## 5. Check it

From a directory outside the source checkout:

```bash
ethos-data -p reskit list
ethos-data -p reskit plan test_suite
```

## If the package needs data that is not catalogued yet

- To work with it now: [Stage uncatalogued data](stage-unpublished-data.md).
- To add it to the catalogue: [Propose a dataset](propose-a-dataset.md).

## See also

- [Keep test data in a repository](keep-test-data-in-a-repository.md)
- [Run package tests in CI](run-in-ci.md)
- [API reference](../reference/api/index.md)
