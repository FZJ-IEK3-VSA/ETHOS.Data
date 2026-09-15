# Write a collections file

Declare all catalogue inputs relevant to your package or workflow, grouped by
task. You need dataset identifiers from a released catalogue. The names below
are examples; substitute entries and a revision that actually exist.

## 1. Select and pin the inputs

Create `collections.yaml`:

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/COMMIT/datacatalog.json
collections:
  test_suite:
    title: Inputs for regression tests
    include:
      - dataset: reskit-test-data
  landcover:
    title: Land cover used by the workflow
    include:
      - dataset: landcover
        files: ["**/*.tif"]
  onshore_wind:
    title: Inputs for onshore wind calculations
    extends: [landcover]
    include:
      - dataset: reskit-test-data/era5
        files: ["100m_*_component_of_wind.nc"]
  all:
    title: All catalogue inputs used by this package
    extends: [test_suite, onshore_wind]
```

Replace `COMMIT` with the accepted catalogue commit. For an internal workflow,
use a complete versioned internal `datacatalog.json` instead.

Omit `files` to select an entire dataset. Use `**` for all depths and
`**/*.tif` for TIFF files at any depth; `*.tif` selects only the top level.
Selecting a shapefile also selects declared companion files.

Add every workflow collection to `all.extends` directly or indirectly.
This `all` means all inputs used by **this package**, not every dataset in the
institute catalogue. Repeated resources are deduplicated.

## 2. Inspect the selection

```bash
ethos-data -c collections.yaml list
ethos-data -c collections.yaml info all
ethos-data -c collections.yaml plan all
```

Check the catalogue printed by `list`, expected paths, sidecars, size, and access
requirements. Resolve `[unresolvable]` entries and unexpectedly empty selections.
A configured catalogue override can replace the file's pin; inspect
`ethos-data config show` if the selected version differs.

## 3. Ship or use the file

For a standalone workflow:

```bash
ethos-data -c collections.yaml fetch all
```

For installed-package discovery, [register and ship the file](use-from-a-package.md).
Users can then run `ethos-data -p your_package fetch all`.

See [Collections format](../reference/schemas.md#collectionsyaml) for every key,
family selector, and pattern rule.
