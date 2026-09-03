# Using the catalogue from a library

How a Python package — RESKit is the working example — declares which
datasets it needs and gets them onto a user's machine, deduplicated against
every other ICE-2 tool that also uses `ice2-data`. If you just want to fetch
data as an end user, see [GETTING-DATA.md](GETTING-DATA.md) instead; if you
maintain the catalogue itself, see [ADDING-DATA.md](ADDING-DATA.md).

## Why a library shouldn't hand-roll this

A `collections.yaml` names *slices* of the shared catalogue — it holds no
file paths, sizes, checksums or URLs. That's what makes deduplication work:
every tool resolves the same catalogue into the same cache layout,
`$ICE2_DATA_DIR/<dataset>/<resource path>`, so when a second tool asks for a
file the first one already fetched, it's simply already there. If each
library carried its own copy of the inventory instead, the two would drift
and the sharing would silently stop.

## 1. Add `ice2-data` as a dependency

```
dependencies = [
  "ice2-data>=0.1.0",
]
```

## 2. Write `collections.yaml`

One file, next to the module that will expose it — for RESKit,
`reskit/data/collections.yaml`:

```yaml
# Pin a released tag so a given RESKit version always resolves to the same
# bytes. Override with $RESKIT_DATA_CATALOG (e.g. the internal catalogue,
# for developing against unpublished datasets).
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

Each `include` entry names one cataloged dataset and, optionally, `files`
globs against its resource paths (`*` within one path segment, `**` across
any depth; omit `files` for everything). `extends` composes collections
without repeating their contents. None of this needs the datasets to exist
locally yet — only their catalogue entries.

## 3. Wrap it in a thin module

RESKit's `reskit/data/__init__.py` is the pattern to copy — a handful of
functions over `ice2_data`, with the collections file resolved relative to
the module so it works regardless of the caller's working directory:

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

`fetch` returns a `DataFiles` — an ordinary `dict` of `"<dataset>/<path>" ->
Path`, in catalogue order, plus `.paths` (just the paths) and
`.one("suffix")` (one file by the end of its name, raising if that's
ambiguous or absent rather than silently returning the wrong file).

## 4. Point tests and CI at a reproducible catalogue

Pin a tag in `collections.yaml` so a released version of your package always
resolves to the same bytes — that's the whole reason `catalog:` takes a
versioned URL rather than a moving branch. For local development against a
dataset that isn't published yet, override with your env var:

```bash
export RESKIT_DATA_CATALOG=/path/to/ice2-data-catalog-internal/datacatalog.json
```

For CI, see the caching example in [GETTING-DATA.md](GETTING-DATA.md#in-ci).

## Adding a dataset your library needs

If the dataset isn't in the catalogue yet, that's a change to
`ice2-data-catalog-internal`, not to your package — see [ADDING-DATA.md](ADDING-DATA.md).
Once it's cataloged, your library only ever needs an `include:` entry in
`collections.yaml` (step 2); the dataset's files, checksums and licence stay
out of your repository entirely.
