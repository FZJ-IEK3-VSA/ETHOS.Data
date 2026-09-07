# ice2-data

Shared data access for ICE-2 scientific software.

One institute-wide input data catalogue ([ice2-data-catalog](../ice2-data-catalog-internal))
describes the datasets: file paths, sizes, SHA-256 checksums, original sources
and licences, as [Frictionless Data Packages](https://datapackage.org/).
Each software project declares only which *slices* of those datasets it needs,
in its own `collections.yaml`.

## Why this shape

A tool's collections file contains **no file paths, hashes or URLs** — only
references into the catalogue. That is what makes deduplication work: every tool
resolves the same catalogue into the same cache layout,

    $ICE2_DATA_DIR/<dataset>/<resource path>

so when a second tool asks for ERA5 data that RESKit already downloaded, it
finds the file already there. Nothing to synchronise, no symlink farm, and no
per-tool copy. If each tool carried its own inventory instead, the two would
drift and the sharing would silently stop.

## Usage

```python
from ice2_data import fetch

paths = fetch("test_suite", collections="collections.yaml")
```

```bash
ice2-data -c collections.yaml list                # what is on offer
ice2-data -c collections.yaml info test_suite     # what is in a collection
ice2-data -c collections.yaml plan test_suite     # what a fetch would download
ice2-data -c collections.yaml fetch test_suite    # download it
```

## Documentation

Full documentation lives in [`docs/`](docs/) — tutorials, how-to guides,
explanation and reference, organised by what you came for:

```bash
mkdocs serve      # live preview on http://localhost:8000
mkdocs build      # static site into ./site
```

| | |
|---|---|
| [Your first fetch](docs/tutorials/first-fetch.md) | install, point at a catalogue, download a collection |
| [Use it from your own package](docs/tutorials/use-from-a-library.md) | `collections.yaml` and the thin wrapper module pattern |
| [Add a dataset to the catalogue](docs/tutorials/add-a-dataset.md) | the maintainer round trip, end to end |
| [How-to guides](docs/how-to/index.md) | cache configuration, local data, restricted data, verify/repair, CI, uploading, publishing |
| [Explanation](docs/explanation/index.md) | why one catalogue; caches, classes and roots; the catalogue format; licensing |
| [Reference](docs/reference/cli/ice2-data.md) | both CLIs, configuration keys, file formats, glossary, API |

## Maintaining a catalogue

The `ice2-data catalog` command, installed alongside `ice2-data`, is the writing
half of the same format. A catalogue repository holds metadata only; the code
that generates and publishes it lives here, so that the descriptors written and
the descriptors read can never drift apart.

```bash
ice2-data catalog build                        # regenerate manifests from dataset.yaml
ice2-data catalog publish ../ice2-data-catalog # emit the public subset
ice2-data catalog upload <dataset>             # put the bytes on dCache, then verify
ice2-data catalog check-store                 # probe dCache permissions
```

`upload` and `check-store` need `rclone` and `oidc-agent` on PATH. Nothing
else here has dependencies beyond the package's own.

## Licensing

Datasets whose redistribution terms have not been confirmed carry
`ice2:license_status: unresolved` in the catalogue, and `fetch()` emits a
`UserWarning` on download. An absent licence is a question, not a default.
