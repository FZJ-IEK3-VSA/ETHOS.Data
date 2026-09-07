# Use it from your own package

You maintain a Python package that needs input data. This walks through wiring
it up to the shared catalogue, so that its data is deduplicated against every
other ICE-2 tool on a user's machine and a released version of your package
always resolves to the same bytes. RESKit is the worked example throughout.

If you only want to fetch data as an end user, [Your first
fetch](first-fetch.md) is the shorter road.

## Why not hand-roll it

A `collections.yaml` names *slices* of the shared catalogue. It holds **no file
paths, sizes, checksums or URLs** — and that omission is the entire mechanism.
Every tool resolves the same catalogue into the same cache layout,
`<cache>/<dataset>/<resource path>`, so when a second tool asks for a file the
first one already fetched, it is simply already there. If each library carried
its own copy of the inventory instead, the two would drift the first time a
dataset was revised, and the sharing would stop silently.

## 1. Add the dependency

```toml
dependencies = [
  "ice2-data>=0.1.0",
]
```

## 2. Write `collections.yaml`

One file, next to the module that will expose it — for RESKit,
`reskit/data/collections.yaml`:

```yaml
# Pin a released tag so a given RESKit version always resolves to the same
# bytes. Override with $RESKIT_DATA_CATALOG (e.g. the internal catalogue, for
# developing against unpublished datasets).
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ice2-data-catalog/v2026.09/datacatalog.json

collections:
  test_suite:
    title: Data required by the pytest suite
    include:
      - dataset: reskit-test-data
        files: ["**"]

  onshore_wind:
    title: Data for onshore wind workflows
    extends: [landcover]              # pulls in another collection's files too
    include:
      - dataset: reskit-test-data
        files:
          - "era5-like/100m_*_component_of_wind.nc"
          - "gwa*-like.tif"
          - "turbinePlacements.shp"   # pulls .shx/.dbf/.prj/.cpg in automatically
```

Each `include` entry names one catalogued dataset and, optionally, `files`
globs against its resource paths: `*` matches within one path segment, `**`
across any depth, and omitting `files` takes everything. `extends` composes
collections without repeating their contents.

None of this requires the datasets to exist on your machine — only their
catalogue entries. The full grammar is in
[Write a collections file](../how-to/write-a-collections-file.md).

## 3. Wrap it in a thin module

RESKit's `reskit/data/__init__.py` is the pattern to copy. A handful of
functions over `ice2_data`, with the collections file resolved **relative to
the module** so it works regardless of the caller's working directory:

```python
import os
from functools import lru_cache
from pathlib import Path

import ice2_data

COLLECTIONS_FILE = Path(__file__).resolve().parent / "collections.yaml"
CATALOG_ENV = "RESKIT_DATA_CATALOG"     # name it after your own package


@lru_cache(maxsize=1)
def _loaded():
    return ice2_data.load_collections(COLLECTIONS_FILE, catalog=os.environ.get(CATALOG_ENV))


def fetch(collection: str, progressbar: bool = True):
    """Make a collection available locally; returns {"<dataset>/<path>": Path}."""
    return ice2_data.fetch(
        collection, collections=COLLECTIONS_FILE,
        catalog=os.environ.get(CATALOG_ENV), progressbar=progressbar,
    )


def path(key: str) -> Path:
    """One named file, e.g. 'reskit-test-data/era5-like/2m_temperature.nc'."""
    return ice2_data.fetch_one(key, catalog=_loaded().catalog)


def directory(key_prefix: str) -> Path:
    """The folder holding every file under a prefix, for readers that want a
    directory rather than a file list."""
    loaded = _loaded()
    dataset_name, _, sub = key_prefix.partition("/")
    dataset = loaded.catalog.dataset(dataset_name)
    resources = [r for p, r in dataset.resources.items() if p.startswith(sub)]
    files = ice2_data.download(loaded.catalog, resources)
    directories = files.directories
    if len(directories) > 1:
        raise ValueError(f"{key_prefix!r} spans {len(directories)} directories")
    return directories[0]
```

Then the rest of the package never touches `ice2_data` directly:

```python
from reskit import data

files = data.fetch("onshore_wind")     # everything that workflow needs
clc   = data.path("landcover/C3S-LC-L4-LCCS-Map-300m-P1Y-2018-v2.1.1.tif")
era5  = data.directory("reskit-test-data/era5-like")
```

Three reasons the wrapper earns its place:

- **The environment-variable name is yours.** `RESKIT_DATA_CATALOG`, not a
  shared one, so two ICE-2 tools in one shell can be pointed at different
  catalogues.
- **`lru_cache` means the catalogue index is parsed once** per process, not
  once per call.
- **Your callers get your vocabulary.** `data.path("landcover/…")` reads like
  your package; `ice2_data.fetch_one(…, catalog=…)` reads like plumbing.

## 4. Read what comes back

`fetch` returns a [`DataFiles`][ice2_data.DataFiles] — an ordinary `dict` of
`"<dataset>/<path>" -> Path` in catalogue order, plus:

| | |
|---|---|
| `.paths` | every file, as a list — for handing the lot to a workflow |
| `.directories` | the distinct parent directories, for path-based readers |
| `.one("suffix")` | one file by the end of its name, raising if that is ambiguous or absent |

`.one()` raising rather than guessing is deliberate: silently returning the
wrong raster is a bug you find weeks later, in results.

## 5. Pin a catalogue for releases, override it for development

The `catalog:` key takes a versioned URL rather than a moving branch for one
reason: **reproducibility**. A released version of your package resolves to the
same bytes every time somebody installs it, forever.

For local development against a dataset that is not published yet, override it
with your own environment variable:

```bash
export RESKIT_DATA_CATALOG=/path/to/ice2-data-catalog-internal/datacatalog.json
```

For CI, see [Run it in CI](../how-to/run-in-ci.md), which covers caching the
downloaded data between runs.

## When your library needs a dataset that is not catalogued yet

Two options, depending on how far along the data is:

- **It is real and ready** — it belongs in the catalogue, which is a change to
  `ice2-data-catalog-internal`, *not* to your package. See
  [Add a dataset](add-a-dataset.md). Once it is catalogued, your library only
  ever needs an `include:` entry in `collections.yaml`; the dataset's files,
  checksums and licence stay out of your repository entirely.
- **It is still changing shape** — use the
  [staging root](../how-to/stage-unpublished-data.md), which lets
  `fetch("my_collection")` work against a directory on your machine from day
  one, so there are no hard-coded paths to unpick later.

## Next

- [Write a collections file](../how-to/write-a-collections-file.md) — the full
  pattern grammar, `extends`, and sidecars.
- [Run it in CI](../how-to/run-in-ci.md).
- [API Reference](../reference/api/index.md).
