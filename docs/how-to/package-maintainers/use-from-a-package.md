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
[its repository](../../installation.md) in the same environment first.

## 2. Ship a collections file

Create `reskit/data/collections.yaml` and pin a released catalogue revision.
Keep dataset selection, test/full variants and named inputs in that file,
following [Write a collections file](write-a-collections-file.md).
The examples below assume it defines `onshore_wind`.

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
commands that need it, so `reskit-data --help`, `reskit-data config show`
and `reskit-data staging list` work without loading the catalogue. `tool` names the package in messages and
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
reskit-data show
reskit-data fetch onshore_wind --test --paths
```

`--help` lists the commands without loading the catalogue. `show` lists
`onshore_wind [test]` and `onshore_wind [full]` as separate rows.
`fetch --test --paths` fetches the test variant and prints one
`handle<TAB>path` line per handle.

How users call `reskit-data` day to day — fetching inputs, configuring the
cache — belongs in your package's own documentation; ETHOS.Data's pages cover
`ethos-data` and `ethos_data`.

The wrapper already includes `staging add/list/remove` and bundle commands.
Keep this implementation shared; the consuming package only supplies its file,
name and optional catalogue override.

Two sets of commands stay with `ethos-data` and never appear in `reskit-data`,
and they are not the same job. `ethos-data materialize`, `ethos-data link` and
`ethos-data unlink` act on the shared cache itself: one cache serves every
package on the machine, so a command that repoints an entry in it cannot belong
to any one of them. `ethos-data catalog` — `build`, `publish`, `upload` and
`check-store` — acts instead on a maintainer's source-catalogue checkout, which
your users do not have. The two meet only at `ethos-data link --all`, which
fills a whole shared cache from such a checkout; it sits with `link` rather than
under `catalog` because it is `ethos-data link <dataset> <directory>` at the
scale of a whole catalogue.

Follow [Develop and propose a dataset](propose-a-dataset.md) for the development
workflow, and link users to the [package-command reference](../../reference/cli/package-data.md)
for all shared flags.

## See also

- [Keep test data in a repository](keep-test-data-in-a-repository.md)
- [Run package tests in CI](run-in-ci.md)
- [API reference](../../reference/api/index.md)
