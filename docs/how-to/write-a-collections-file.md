# Write a collections file

A `collections.yaml` names the parts of the catalogue a package needs, as
collections that users fetch by name.

## The shape

```yaml
# Optional: the catalogue version to use. Without it, the current public
# catalogue is used.
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/v2026.09/datacatalog.json

collections:
  test_suite:
    title: Data required by the pytest suite
    include:
      - dataset: reskit-test-data

  landcover:
    title: Land cover for wind workflows
    include:
      - dataset: landcover
        files: ["*.tif"]

  onshore_wind:
    title: Data for onshore wind workflows
    extends: [landcover]
    include:
      - dataset: reskit-test-data/era5
        files: ["100m_*_component_of_wind.nc"]
      - dataset: reskit-test-data/placements
        files: ["turbinePlacements.shp"]
```

| Key | |
|---|---|
| `catalog:` | the catalogue to use — a local path or an http(s) URL. Optional. |
| `collections:` | a mapping of collection name to definition. |
| `title:` | a one-line description, shown by `ethos-data list`. |
| `include:` | a list of `{dataset, files}` entries. |
| `extends:` | other collections in this file whose files are included too. |

`dataset:` takes a dataset name, a family name (all its members), or a glob
over dataset names such as `reskit-test-data/*`.

## Patterns

`files:` globs are matched against the file's path inside the dataset:

| Pattern | Matches | Does not match |
|---|---|---|
| `*.tif` | `wind.tif` | `sub/dir/wind.tif` |
| `**` | everything, at any depth | — |
| `**/*.tif` | `wind.tif`, `sub/dir/wind.tif` | — |
| `era5-like/*.nc` | `era5-like/temp.nc` | `era5-like/2020/temp.nc` |
| `era5-like/**` | everything under `era5-like/` | files elsewhere |

`*` matches within one folder level; `**` matches any number of levels.
Leaving out `files` takes the whole dataset. Selecting a `.shp` also selects its
`.shx`, `.dbf`, `.prj` and `.cpg`.

## Combine collections

```yaml
collections:
  all:
    title: All inputs used by this package
    extends: [test_suite, onshore_wind]
```

`extends` takes a list and can be nested. A file selected twice is listed once.

## Pin a catalogue version

Put a released tag or a commit in the URL:

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/v2026.09/datacatalog.json
```

URLs containing `main`, `master`, `HEAD`, `latest`, `dev` or `develop` are
fetched again on every use; other URLs are cached. A relative local path is
resolved relative to the collections file:

```yaml
catalog: ../ethos-data-catalog-internal/datacatalog.json
```

## Use another catalogue without editing the file

Strongest first:

```python
ethos_data.fetch("onshore_wind", package="reskit", catalog="/other/datacatalog.json")
```

```bash
ethos-data --catalog /other/datacatalog.json -p reskit list   # one command
export ETHOS_DATA_CATALOG=/other/datacatalog.json             # one shell or job
ethos-data config set-catalog /other/datacatalog.json         # all your work
```

See [Add the internal data catalogue](add-internal-catalogue.md).

## Check it

```bash
ethos-data -c collections.yaml list                # every collection, with sizes
ethos-data -c collections.yaml info onshore_wind   # exactly which files one selects
ethos-data -c collections.yaml plan onshore_wind   # what a fetch would download
```

Once the file is registered in your package, use `-p <package>` instead of `-c`;
see [Use ETHOS.Data in your package](use-from-a-package.md). A collection that
names a dataset the catalogue does not describe is listed as `[unresolvable]`.

## See also

- [File formats](../reference/schemas.md) — the complete key reference.
- [Propose a dataset](propose-a-dataset.md) — when a dataset is not catalogued yet.
