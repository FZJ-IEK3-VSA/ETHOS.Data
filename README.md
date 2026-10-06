# ETHOS.Data

Shared data access for ETHOS tools and workflows.

One institute-wide input data catalogue,
[ETHOS.Data-Catalogue](https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue),
describes the datasets: file paths, sizes, SHA-256 checksums, original sources
and licences, as [Frictionless Data Packages](https://datapackage.org/).
Each software package declares only which *slices* of those datasets it needs,
in a `collections.yaml` it ships with itself.

## Why this shape

A tool's collections file contains **no file paths, hashes or URLs** — only
references into the catalogue. That is what makes deduplication work: every tool
resolves the same catalogue into the same cache layout,

    $ETHOS_DATA_DIR/<dataset>/<resource path>

so when a second tool asks for ERA5 data that RESKit already downloaded, it
finds the file already there. Nothing to synchronise, no symlink farm, and no
per-tool copy. If each tool carried its own inventory instead, the two would
drift and the sharing would silently stop.

## Usage

For direct catalogue access:

```bash
ethos-data config show
ethos-data ls
ethos-data ls global-wind-atlas-v4
ethos-data fetch reskit-test-data/era5
```

`fetch` takes a dataset, family, folder or file key and prints its local path.
Use `--catalog LOCATION` before the subcommand to select a particular index.

For a package workflow, use its Python API or thin wrapper. For example, with
a package built on ETHOS.Data installed, written here as `your_tool` and `<your-tool>-data`:

```python
from your_tool import data

inputs = data.paths("onshore_wind", test=True)
```

```bash
<your-tool>-data show
<your-tool>-data fetch onshore_wind --test --paths
<your-tool>-data staging list
```

Packages expose collections, named inputs, test variants, bundles and staging
through `ethos_data.tool_main`. The shared CLI owns configuration, direct
catalogue access and `link`, `unlink`, `materialize` and `catalog` maintenance.
Staging uses a shared development root even though package wrappers manage it.

Applications can also use `ethos_data.catalog().path(KEY)` for keys or
`ethos_data.collections("collections.yaml").paths(COLLECTION)` for an explicit
collections file. See [Package integration](docs/how-to/package-maintainers/use-from-a-package.md)
and the [package-command reference](docs/reference/cli/package-data.md).

## Documentation

Full documentation is published at <https://ethos-data.readthedocs.io/> and
lives in [`docs/`](docs/) — tutorials, how-to guides, explanation and
reference, organised by what you came for:

```bash
pip install -e ".[docs]"
mkdocs serve      # live preview on http://localhost:8000
mkdocs build      # static site into ./site
```

| | |
|---|---|
| [Your first fetch](docs/tutorials/first-fetch.md) | fetch a file from a practice catalogue, use the path from Python, repair a damaged cache copy |
| [Use data in a script](docs/how-to/data-users/use-data-in-a-script.md) | get a workflow's inputs in Python, fetching them or only resolving their paths; single keys with the CLI |
| [Use ETHOS.Data in your package](docs/how-to/package-maintainers/use-from-a-package.md) | ship a `collections.yaml`, a handle on it and a console script of your own via `ethos_data.tool_main` |
| [Add a dataset to the catalogue](docs/tutorials/add-a-dataset.md) | the maintainer round trip, on a practice catalogue |
| [How-to guides](docs/how-to/index.md) | cache configuration, internal catalogue, restricted data, verify/repair, CI, uploading, publishing |
| [Explanation](docs/explanation/index.md) | why one catalogue; caches, classes and roots; the catalogue format; licensing |
| [Reference](docs/reference/cli/ethos-data.md) | the `ethos-data` and `ethos-data catalog` commands, configuration keys, file formats, glossary, API |

## Maintaining a catalogue

The `ethos-data catalog` subcommand is the writing
half of the same format. A catalogue repository holds metadata only; the code
that generates and publishes it lives here, so that the descriptors written and
the descriptors read can never drift apart.

```bash
ethos-data catalog add <draft>                      # take a reviewed draft in and build it
ethos-data catalog build                            # regenerate manifests from dataset.yaml
ethos-data catalog publish ../ETHOS.Data-Catalogue  # emit the public subset
ethos-data catalog upload <dataset>                 # put the bytes on dCache, then verify
ethos-data catalog remove <dataset> --reason "..."  # withdraw a dataset from the catalogue
ethos-data catalog check-source <dataset> <dir>     # compare a re-download with the inventory
ethos-data catalog check-store                      # probe dCache permissions
```

`upload` and `check-store` need `rclone` and `oidc-agent` on PATH. Nothing
else here has dependencies beyond the package's own.

## Licensing

`ethos-data` — the software in this repository — is under the
[MIT License](LICENSE).

**The licence of the software is not the licence of the data.**
