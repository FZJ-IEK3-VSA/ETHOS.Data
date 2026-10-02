# Write a collections file

Select the catalogue data your package's workflows use, grouped by task, and
name the inputs each workflow takes. A collections file holds no paths, sizes,
hashes or URLs, only references into the catalogue. A package has exactly one
such file, shipped beside its data module. You need dataset names from a
released catalogue; the names below are examples.

For the checks below, save this development wrapper beside the file as
`data_cli.py`. A shipped package exposes `tool_main` as its own console script
instead; see [Use ETHOS.Data in your package](use-from-a-package.md).

```python
from pathlib import Path
from ethos_data import tool_main

if __name__ == "__main__":
    raise SystemExit(tool_main(
        Path(__file__).with_name("collections.yaml"), prog="python data_cli.py"
    ))
```

## 1. Declare the catalogue versions {#catalog-version}

The file has two top-level keys: `catalog`, which says which versions of the
catalogue the package works with, and `collections`. Catalogue releases are
numbered `vYYYY.MM.N`, where `N` counts the releases within a month, so
`v2026.09.2` is the second release of September 2026 and versions compare
component by component.

```yaml
catalog:
  min_version: v2026.09.1     # the oldest release the package was tested with
  max_version: v2026.12.9     # optional: refuse anything newer
collections:
  ...
```

or, for a package that must resolve to the same bytes release after release:

```yaml
catalog:
  exact_version: v2026.09.2
collections:
  ...
```

Which catalogue is read stays a user setting: a cluster user's configured
internal catalogue, or the public catalogue for everyone else. The file only
bounds its version. A catalogue outside the bounds is refused with both
versions in the message, on the command line and in Python alike. With no
configured catalogue, `exact_version` selects that public release and
`min_version` the newest public release within the bounds.

## 2. Select the inputs

```yaml
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
  my_workflow:
    title: Inputs for the onshore wind workflow
    extends: [landcover]
    include:
      - dataset: reskit-test-data/era5
        files: ["100m_*_component_of_wind.nc"]
  all:
    title: All catalogue inputs used by this package
    extends: [test_suite, my_workflow]
```

Omit `files` to select an entire dataset. Use `**` for all depths and
`**/*.tif` for TIFF files at any depth; `*.tif` selects only the top level.
Selecting a shapefile also selects its companion files. Add every workflow
collection to `all.extends`, directly or indirectly. This `all` means every
input used by **this package**, not every dataset in the catalogue. Repeated
resources are deduplicated.

A collection that names an internal dataset resolves only on a cluster
installation; keep such collections separate from the ones public
installations need, so `show` marks only those as `[unresolvable]` elsewhere.

## 3. Name the inputs a workflow takes

If a workflow function takes its data as arguments, add `paths:` with one
handle per argument, mapped to a catalogue key:

```yaml
  my_workflow:
    title: Inputs for the onshore wind workflow
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
Name the handles after the workflow's arguments, `gwa_100m` for
`gwa_100m_path`, so a caller writes `paths("my_workflow")["gwa_100m"]`.

Check:

```bash
python data_cli.py show my_workflow
```

The output ends with a `named paths` section listing each handle and its key.
Handles are checked against the catalogue and the selection before any
download starts: a handle naming a file the collection does not include is
refused, with the `include:` entry to add.

## 4. Pair a small test selection with the full data

When the same workflow must run on small fixtures in examples and tests and on
the real inputs in production, write the collection twice, under `test:` and
`full:`:

```yaml
  my_workflow:
    title: Inputs for the onshore wind workflow
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
        - dataset: global-wind-atlas-v4
          files: ["wind_speed_cog_100m.tif"]
      paths:
        era5: era5
        gwa_100m: global-wind-atlas-v4/wind_speed_cog_100m.tif
```

Each variant holds its own `extends`, `include` and `paths`; `title` stays at
the top, and no selection key may sit beside the variants. Both variants must
offer the same handles: that is what lets `paths("my_workflow", test=True)`
and the same call without `test=True` feed the same code. A plain parent such
as `landcover` is the same for both variants; a parent with variants
contributes the matching one. The full data is the default, so a plain `all`
that extends `my_workflow` selects its full variant, and `fetch all --test`
its test variant.

Check:

```bash
python data_cli.py show
python data_cli.py show my_workflow --test
python data_cli.py fetch my_workflow --test --paths
```

`show` prints one row per variant. If the two variants disagree about their
handles, `show` marks the collection `[unresolvable]` and every other command
refuses it, saying `only in test: ...; only in full: ...`. A collection that
merely extends it is refused too.

## 5. Inspect the selection

```bash
python data_cli.py show all
python data_cli.py fetch all --plan
```

Check the catalogue printed by `show`, the expected paths, sidecars, size and
access classes. Resolve `[unresolvable]` entries and unexpectedly empty
selections. A configured catalogue replaces the public one; inspect
`ethos-data config show` if the selected version differs.

## 6. Ship or use the file

For an application without a console wrapper:

```python
import ethos_data

data = ethos_data.collections("collections.yaml")
files = data.fetch("all")
```

For a package, [ship the file and wrapper](use-from-a-package.md). Users name
its collections through the package command; no file lookup is needed.

See [Collections format](../../reference/schemas.md#collectionsyaml) for every
key, family selector and pattern rule.
