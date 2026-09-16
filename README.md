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

```python
import ethos_data

data = ethos_data.collections("collections.yaml")
inputs = data.paths("onshore_wind", test=True)     # {"era5": Path, "gwa_100m": Path, ...}
files = data.fetch("onshore_wind")                 # {"<dataset>/<file>": Path}
placements = data.catalog.path("reskit-test-data/placements/turbine_placements.csv")
```

`paths()` returns the inputs a collection names, fetched, as
`{name: absolute path}`; `test=True` selects the collection's small test
variant, and the same call without it the full data. The collections file is
the one your project uses or the one a package ships. `ethos_data.catalog()`
answers for a dataset, folder or file by key in the configured catalogue; a
handle's `.catalog` does the same in the version the file pins.

```bash
ethos-data -c collections.yaml list                       # the collections in the file, one row per variant
ethos-data -c collections.yaml info onshore_wind --test   # what is in a collection's test variant
ethos-data -c collections.yaml plan onshore_wind          # what a fetch of the full data would download
ethos-data -c collections.yaml fetch onshore_wind         # download it
ethos-data -c collections.yaml paths onshore_wind --test  # fetch the test data, print name<TAB>path
ethos-data path reskit-test-data/era5                     # the local path of a file or folder
ethos-data ls global-wind-atlas-v4                        # what a dataset contains, fetching nothing
```

The public catalogue is built in. A package that ships a collections file can
bind the same commands to its own console script with `ethos_data.tool_main` —
see the maintainer how-to [Use ETHOS.Data in your package](docs/how-to/use-from-a-package.md).
How to use such a command is documented by that package.

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
| [Your first fetch](docs/tutorials/first-fetch.md) | fetch a collection from a practice catalogue, use the path from Python, repair a damaged cache copy |
| [Get data for a task](docs/how-to/get-data-for-a-task.md) | the `ethos-data` command, and the `ethos_data` handles in scripts — a collection's `paths()`, the catalogue's `path()` |
| [Use ETHOS.Data in your package](docs/how-to/use-from-a-package.md) | ship a `collections.yaml`, a handle on it and a console script of your own via `ethos_data.tool_main` |
| [Add a dataset to the catalogue](docs/tutorials/add-a-dataset.md) | the maintainer round trip, on a practice catalogue |
| [How-to guides](docs/how-to/index.md) | cache configuration, internal catalogue, restricted data, verify/repair, CI, uploading, publishing |
| [Explanation](docs/explanation/index.md) | why one catalogue; caches, classes and roots; the catalogue format; licensing |
| [Reference](docs/reference/cli/ethos-data.md) | the `ethos-data` and `ethos-data catalog` commands, configuration keys, file formats, glossary, API |

## Maintaining a catalogue

The `ethos-data catalog` command, installed alongside `ethos-data`, is the writing
half of the same format. A catalogue repository holds metadata only; the code
that generates and publishes it lives here, so that the descriptors written and
the descriptors read can never drift apart.

```bash
ethos-data catalog build                            # regenerate manifests from dataset.yaml
ethos-data catalog publish ../ETHOS.Data-Catalogue  # emit the public subset
ethos-data catalog upload <dataset>                 # put the bytes on dCache, then verify
ethos-data catalog check-store                      # probe dCache permissions
```

`upload` and `check-store` need `rclone` and `oidc-agent` on PATH. Nothing
else here has dependencies beyond the package's own.

## Licensing

`ethos-data` — the software in this repository — is under the
[MIT License](LICENSE).

**The licence of the software is not the licence of the data.** 
