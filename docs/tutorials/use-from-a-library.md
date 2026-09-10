# Use it from your own package

You maintain a Python package that needs input data. This walks through wiring
it up to the shared catalogue, so that its data is deduplicated against every
other ICE-2 tool on a user's machine and a released version of your package
selects the same recorded inputs. RESKit is the worked example throughout.

If you only want to fetch data as an end user, [Your first
fetch](first-fetch.md) is the shorter road.

## Why not hand-roll it

A `collections.yaml` names *slices* of the shared catalogue through dataset
names and file patterns. It does not duplicate the catalogue inventory, sizes,
checksums, or download URLs.
Every tool resolves the same catalogue into the same cache layout,
`<cache>/<dataset>/<resource path>`, so when a second tool asks for a file the
first one already fetched, it is simply already there.

Keep the central catalogue authoritative. A generated snapshot for repository
test data is a deliberately pinned local copy of that catalogue, with a separate
update operation; it is not a second hand-maintained inventory.

## 1. Add the dependency

```toml
dependencies = [
  "ethos-data>=0.1.0",
]
```

## 2. Write `collections.yaml`

One file, next to the module that will expose it — for RESKit,
`reskit/data/collections.yaml`:

```yaml
# Pin a released tag so a given RESKit version always resolves to the same
# bytes. Override with $RESKIT_DATA_CATALOG (e.g. the internal catalogue, for
# developing against unpublished datasets).
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ethos-data-catalog/v2026.09/datacatalog.json

collections:
  test_suite:
    title: Data required by the pytest suite
    include:
      - dataset: reskit-test-data
        files: ["**"]

  landcover:
    title: Land cover for wind workflows
    include:
      - dataset: landcover
        files: ["*.tif"]

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

The URL above illustrates a release pin; select an available official release
or commit for your package. None of the selections requires the bytes to exist
on your machine, only the catalogue entries (or an active development overlay).
The full grammar is in
[Write a collections file](../how-to/write-a-collections-file.md).

## 3. Wrap it in a thin module

A small `reskit/data/__init__.py`-style wrapper resolves the collections file
relative to the module so callers can run from any working directory:

```python
import os
from pathlib import Path

import ethos_data

COLLECTIONS_FILE = Path(__file__).resolve().parent / "collections.yaml"
CATALOG_ENV = "RESKIT_DATA_CATALOG"     # use your own package's prefix


def fetch(collection: str, progressbar: bool = True):
    """Return {"<dataset>/<resource path>": Path} for one collection."""
    return ethos_data.fetch(
        collection,
        collections=COLLECTIONS_FILE,
        catalog=os.environ.get(CATALOG_ENV),
        progressbar=progressbar,
    )


def path(key: str) -> Path:
    """Return one input by its catalogue resource key."""
    loaded = ethos_data.load_collections(
        COLLECTIONS_FILE, catalog=os.environ.get(CATALOG_ENV),
    )
    return ethos_data.fetch_one(key, catalog=loaded.catalog)
```

The calling code then uses the package's interface:

```python
from reskit import data

files = data.fetch("onshore_wind")
turbines = files.one("turbinePlacements.shp")
```

The environment variable lets your package choose an internal catalogue while
another package in the same shell keeps its public pin. The ordinary fetch API
also applies the configured development overlay. Loading per request makes
newly staged files visible during development; persistent metadata caching still
avoids repeated retrieval of pinned remote descriptors.

Ship `collections.yaml` as package data and test the installed package from a
working directory outside the source checkout. A source-tree import alone does
not establish that the file was included in the wheel.

## 4. Read what comes back

`fetch` returns a [`DataFiles`][ethos_data.DataFiles] — an ordinary `dict` of
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
same recorded inventory, provided the catalogue version and published data
paths are retained. Prefer a commit URL or a release tag with an immutability
policy; a tag name alone does not prevent the publisher moving it.

For local development against a dataset that is not published yet, override it
with your own environment variable:

```bash
export RESKIT_DATA_CATALOG=/shared/ice2/catalogue/current/datacatalog.json
```

The path is an example supplied by the cluster administrator. For reproducible
runs choose a versioned directory instead of `current`. For test fixtures and
live integration jobs, see [Run package tests in CI](../how-to/run-in-ci.md).

## When your library needs a dataset that is not catalogued yet

Two options, depending on how far along the data is:

- **It is real and ready** — it belongs in the catalogue, which is a change to
  `ethos-data-catalog-internal`, *not* to your package. See
  [Propose a dataset](../how-to/propose-a-dataset.md). A catalogue maintainer
  accepts and publishes the proposal; you do not need upload credentials.
  Once accepted, the workflow selects it through `collections.yaml`. A small
  repository test-data snapshot can carry the selected files and generated
  metadata for offline tests, while dCache remains authoritative.
- **It is still changing shape** — use the
  [staging root](../how-to/stage-unpublished-data.md), which lets
  `fetch("my_collection")` work against a directory on your machine from day
  one, so there are no hard-coded paths to unpick later.

## Next

- [Write a collections file](../how-to/write-a-collections-file.md) — the full
  pattern grammar, `extends`, and sidecars.
- [Develop and propose a dataset](develop-and-propose-data.md).
- [Run package tests in CI](../how-to/run-in-ci.md).
- [API Reference](../reference/api/index.md).
