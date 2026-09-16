# Write a collections file

Declare all catalogue inputs relevant to your package or workflow, grouped by
task. You need dataset identifiers from a released catalogue. The names below
are examples; substitute entries and a revision that actually exist.

For the checks below, save this development wrapper beside the file as
`data_cli.py`. A shipped package should expose `tool_main` as its own console
script instead; see [Package integration](use-from-a-package.md).

```python
from pathlib import Path
from ethos_data import tool_main

if __name__ == "__main__":
    raise SystemExit(tool_main(
        Path(__file__).with_name("collections.yaml"), prog="python data_cli.py"
    ))
```

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

## 2. Name the inputs a workflow takes

If a workflow function takes its data as arguments, add `paths:` with one
handle per argument, mapped to a catalogue key:

```yaml
  onshore_wind:
    title: Inputs for onshore wind calculations
    extends: [landcover]
    include:
      - dataset: reskit-test-data/era5
        files: ["100m_*_component_of_wind.nc"]
      - dataset: reskit-test-data/global-wind-atlas
        files: ["gwa100-like.tif"]
    paths:
      era5: reskit-test-data/era5
      gwa_100m: reskit-test-data/global-wind-atlas/gwa100-like.tif
```

A key is a file (`<dataset>/<file>`), a folder (`<dataset>/<folder>`), a
dataset or a family. A file handle must be selected by `include`; a folder
handle needs at least one selected file under it and resolves to the directory
holding them. Handles are inherited through `extends`, and your own entry wins.
Name the handles after the workflow's arguments — `gwa_100m` for
`gwa_100m_path`; callers type `paths("onshore_wind")["gwa_100m"]` on the
handle built from your file.

Check:

```bash
python data_cli.py info onshore_wind
```

The output ends with a `named paths` section listing each handle and its key.
The handles are checked against the catalogue and the selection when the
collection is fetched, before any download starts: a handle naming a file the
collection does not include is refused, with the `include:` entry to add.

## 3. Pair a small test selection with the full data

When the same workflow has to run on small fixtures in examples and tests and
on the real inputs in production, write the collection twice, under `test:`
and `full:`:

```yaml
  onshore_wind:
    title: Inputs for onshore wind calculations
    test:
      extends: [landcover]
      include:
        - dataset: reskit-test-data/era5
          files: ["100m_*_component_of_wind.nc"]
        - dataset: reskit-test-data/global-wind-atlas
          files: ["gwa100-like.tif"]
      paths:
        era5: reskit-test-data/era5
        gwa_100m: reskit-test-data/global-wind-atlas/gwa100-like.tif
    full:
      extends: [landcover]
      include:
        - dataset: era5
        - dataset: global-wind-atlas-v3
          files: ["gwa3_250_wind-speed_100m.tif"]
      paths:
        era5: era5
        gwa_100m: global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif
```

Each variant holds its own `extends`, `include` and `paths`; `title` stays at
the top, and no selection key may sit beside the variants. Give both variants
the same handles: that is what lets
`ethos_data.collections("collections.yaml").paths("onshore_wind", test=True)`
and the same call without `test=True` feed the same code. A plain parent such
as `landcover` is the same for both variants; a parent with variants
contributes the matching one. The full data is the default, so a plain `all`
that extends `onshore_wind` selects its full variant, and `fetch all --test`
its test variant.

Check:

```bash
python data_cli.py list
python data_cli.py info onshore_wind --test
python data_cli.py paths onshore_wind --test
```

`list` prints one row per variant, `onshore_wind [test]` and
`onshore_wind [full]`. `info --test` shows the small selection and its handles;
without `--test`, the full one. `paths --test` fetches the test data and prints
one `handle<TAB>path` line per handle. If the two variants disagree about their
handles, `list` marks the collection `[unresolvable]` and every other command
refuses it, saying `only in test: ...; only in full: ...`. A collection that
merely extends it — the `all` above — is refused too: it would hand a workflow
different handles per variant.

## 4. Inspect the selection

```bash
python data_cli.py list
python data_cli.py info all
python data_cli.py plan all
```

Check the catalogue printed by `list`, expected paths, sidecars, size, and access
requirements. Resolve `[unresolvable]` entries and unexpectedly empty selections.
A configured catalogue override can replace the file's pin; inspect
`ethos-data config show` if the selected version differs.

## 5. Ship or use the file

For an application without a console wrapper:

```python
import ethos_data

data = ethos_data.collections("collections.yaml")
files = data.fetch("all")
```

For a package, [ship the file and wrapper](use-from-a-package.md). Users name
its collections through the package command; no file lookup is needed.

See [Collections format](../reference/schemas.md#collectionsyaml) for every key,
family selector and pattern rule.
