# Use ETHOS.Data in your package

Make your package's input data available to its users, examples and tests
without any configuration on their side. The package is called `your_tool`
below and its command `your-tool-data`; replace both with your names. Dataset
identifiers and the catalogue version are examples.

The package contributes configuration only: its one collections file, its
bundles, its name. Every behaviour, fetching, verifying, staging, bundles, the
command line, comes from ETHOS.Data, so a fix there reaches every package.

## 1. Add the dependency

```toml title="pyproject.toml"
[project]
dependencies = [
  "ethos-data>=0.2",
]
```

Before a package-index release, install ETHOS.Data from
[its repository](../../installation.md) into the same environment.

## 2. Ship the collections file

A package has exactly one collections file. Create
`your_tool/data/collections.yaml`, declare the catalogue versions the package
works with, and define its collections; see
[Write a collections file](write-a-collections-file.md). The examples below
assume it defines `my_workflow`.

## 3. Build the handle and the command

Create a small module beside the file, `your_tool/data/__init__.py`. It builds
one `ethos_data.Collections` handle on the file, once per process, and
forwards to it with explicit, typed parameters so that editors and linters
see what a caller may pass. The same module is the body of the package's data
command:

```python title="your_tool/data/__init__.py"
"""Access to the data your_tool needs: a thin configuration of ETHOS.Data."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ethos_data import Collections, DataFiles, NamedPaths

COLLECTIONS_FILE = Path(__file__).with_name("collections.yaml")
#: Bundles shipped in the repository, consulted before the catalogue.
BUNDLES = (
    Path(__file__).with_name("test_data"),
    Path(__file__).parents[1] / "wind" / "core" / "data",
)


@lru_cache(maxsize=1)
def handle() -> Collections:
    import ethos_data  # on first use, so `import your_tool` works without it

    return ethos_data.collections(COLLECTIONS_FILE, tool="your-tool", bundles=BUNDLES)


def paths(
    collection: str,
    *,
    test: bool = False,
    fetch: bool = True,
    progressbar: bool = True,
) -> NamedPaths:
    """The inputs of a workflow as {handle: Path}; see ethos_data.Collections.paths."""
    return handle().paths(collection, test=test, fetch=fetch, progressbar=progressbar)


def fetch(
    collection: str,
    *,
    test: bool = False,
    progressbar: bool = True,
) -> DataFiles:
    """Every file a collection selects, as {key: Path}."""
    return handle().fetch(collection, test=test, progressbar=progressbar)


def catalog_path(key: str, *, fetch: bool = True, progressbar: bool = False) -> Path:
    """One dataset, folder or file by catalogue key, in the catalogue this package reads."""
    return handle().catalog.path(key, fetch=fetch, progressbar=progressbar)


def main(argv: list[str] | None = None) -> int:
    import ethos_data

    return ethos_data.tool_main(COLLECTIONS_FILE, tool="your-tool", bundles=BUNDLES, argv=argv)
```

The two path functions answer two different questions. `paths(collection)`
takes the name of a collection from the package's file and returns every
input the workflow needs, by handle. `catalog_path(key)` takes a catalogue
key, `<dataset>/<path>`, and returns the location of that one dataset, folder
or file, whether or not any collection selects it; that is how a maintainer
tries a dataset before adding it to a collection.

Wire `main` up as a console script and ship the file and the bundles as
package data:

```toml title="pyproject.toml"
[project.scripts]
your-tool-data = "your_tool.data:main"

[tool.setuptools.package-data]
"your_tool.data" = ["collections.yaml", "test_data/**"]
```

Nothing is registered with ETHOS.Data: the module finds the file beside itself
and `your-tool-data` is an ordinary console script. A fresh checkout needs one
reinstall, `pip install -e . --no-deps`, for the script to appear. `tool_main`
builds the handle only for the commands that need it, so `your-tool-data
--help`, `config show` and `staging list` work without loading the catalogue.
`tool` names the package in messages and gives the command its default name.
`catalog=` on both calls is the place for a package-specific catalogue
override, applied below `--catalog` and above `$ETHOS_DATA_CATALOG`.

!!! warning "Gap: `bundles=` and `fetch=` do not exist yet"
    `ethos_data.collections`, `tool_main`, `Collections.paths` and
    `Catalog.path` take neither parameter. Until they do, drop `BUNDLES`,
    `bundles=` and `fetch=` from the module above; the rest works as shown.

## 4. Use the data in code, examples and tests

```python
from your_tool import data, simulate

inputs = data.paths("my_workflow", test=True)
result = simulate(era5_path=inputs["era5"], gwa_100m_path=inputs["gwa_100m"])
```

`paths()` fetches the collection and returns `{handle: absolute path}`, so an
example needs no resource key. `test=True` selects the small variant; drop it
and the same code runs on the full data. `fetch=False` returns the paths
without downloading, see
[Use data in a script](../data-users/use-data-in-a-script.md#fetch-or-path).

## 5. Check it

From a directory outside the source checkout:

```bash
your-tool-data --help
your-tool-data show
your-tool-data fetch my_workflow --test --paths
```

`--help` lists the commands without loading the catalogue. `show` lists
`my_workflow [test]` and `my_workflow [full]` as separate rows. `fetch --test
--paths` fetches the test variant and prints one `handle<TAB>path` line per
handle.

How users call `your-tool-data` day to day belongs in your package's own
documentation, which can point at the ETHOS.Data guides for everything that is
the same for every package. The command already includes `staging`, `bundle`
and `config`.

Two groups of commands stay with `ethos-data` and never appear in
`your-tool-data`. `link`, `unlink` and `materialize` act on the public cache
and the restricted caches, which serve every package on the machine.
`ethos-data catalog` acts on a maintainer's source-catalogue checkout, which
your users do not have.

## See also

- [Stage development data](stage-development-data.md)
- [Keep data in the repository](keep-data-in-the-repository.md)
- [Run tests and examples in CI](run-in-ci.md)
- [Package-command reference](../../reference/cli/package-data.md)
- [API reference](../../reference/api/index.md)
