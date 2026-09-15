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

inputs = ethos_data.paths("onshore_wind", package="reskit", test=True)  # {"era5": Path, "gwa_100m": Path, ...}
files = ethos_data.fetch("onshore_wind", package="reskit")              # {"<dataset>/<file>": Path}
placements = ethos_data.path("reskit-test-data/placements/turbine_placements.csv")
```

`paths()` returns the inputs a collection names, fetched, as
`{name: absolute path}`; `test=True` selects the package's small test
selection, and the same call without it the full data.

```bash
ethos-data -p reskit list                         # what is on offer, one row per variant
ethos-data -p reskit info onshore_wind --test     # what is in a collection's test variant
ethos-data -p reskit plan onshore_wind            # what a fetch of the full data would download
ethos-data -p reskit fetch onshore_wind           # download it
ethos-data -p reskit paths onshore_wind --test    # fetch the test data, print name<TAB>path
ethos-data path reskit-test-data/era5             # the local path of a file or folder
ethos-data ls global-wind-atlas-v4                # what a dataset contains, fetching nothing
```

The public catalogue is built in. A package makes its collections available
under `-p` / `package=` with one entry point:

```toml
[project.entry-points."ethos_data.collections"]
reskit = "reskit.data"      # the module whose directory holds collections.yaml
```

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
| [Your first fetch](docs/tutorials/first-fetch.md) | find a package's collections, fetch one, use the paths from Python |
| [Get data for a task](docs/how-to/get-data-for-a-task.md) | `ethos_data.paths()` and `path()` in scripts, and the command line |
| [Use ETHOS.Data in your package](docs/how-to/use-from-a-package.md) | ship and register a `collections.yaml` |
| [Add a dataset to the catalogue](docs/tutorials/add-a-dataset.md) | the maintainer round trip, on a practice catalogue |
| [How-to guides](docs/how-to/index.md) | cache configuration, internal catalogue, restricted data, verify/repair, CI, uploading, publishing |
| [Explanation](docs/explanation/index.md) | why one catalogue; caches, classes and roots; the catalogue format; licensing |
| [Reference](docs/reference/cli/ethos-data.md) | both CLIs, configuration keys, file formats, glossary, API |

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
