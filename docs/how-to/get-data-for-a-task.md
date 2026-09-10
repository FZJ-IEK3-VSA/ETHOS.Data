# Get data for a task

Use the collections shipped by your package to select its input data. You do
not need a checkout of the internal catalogue or credentials for public data.
The examples below run from an ETHOS.RESKit source checkout; replace the
collections path and names for another package.

## Discover and inspect collections

```bash
ethos-data -c reskit/data/collections.yaml list
ethos-data -c reskit/data/collections.yaml info onshore_wind
ethos-data -c reskit/data/collections.yaml plan onshore_wind
```

`list` shows the available collection names. `info` lists selected files,
including sidecars. `plan` estimates how many bytes need downloading and shows
files used in place or unavailable on this machine. These commands do not
download dataset bytes, but may retrieve catalogue metadata and inventory
shards if these are remote and not cached.

## Fetch the task's inputs

```bash
ethos-data -c reskit/data/collections.yaml fetch onshore_wind
```

From Python:

```python
from reskit import data

files = data.fetch("onshore_wind")
turbines = files.one("turbinePlacements.shp")
```

Downloaded files go into the configured cache. Existing valid cached files
are reused, including files another package fetched previously. Configured
local roots are read in place; see [Use data already on disk](use-data-already-on-disk.md).

## Fetch everything the package declares

RESKit declares an aggregate collection called `all`:

```bash
ethos-data -c reskit/data/collections.yaml plan all
ethos-data -c reskit/data/collections.yaml fetch all
```

`all` is a collection name defined by RESKit, not a special command to download
the entire institute catalogue. Another package may use a different name or
have no aggregate collection. Inspect `list` and the package documentation
before choosing. Package maintainers can define aggregates using
[`extends`](write-a-collections-file.md).

For a selection smaller than an existing collection, write a small personal
collections file with the same catalogue pin and narrower `files` patterns.
This changes what you request without editing the catalogue or package files.

## Use the cluster's internal catalogue

If your administrator provides a filesystem catalogue, point the consumer at
its generated `datacatalog.json`. For example:

```bash
ethos-data -c reskit/data/collections.yaml \
  --catalog /shared/ice2/catalogue/current/datacatalog.json list
```

The path is an example; use the one your cluster provides. For RESKit's Python
wrapper, the corresponding override is:

```bash
export RESKIT_DATA_CATALOG=/shared/ice2/catalogue/current/datacatalog.json
```

This chooses metadata. It does not grant access to restricted data or configure
the cache. Use [Configure the cache](configure-the-cache.md) and
[Work with restricted data](restricted-data.md) for those settings. A `current`
path may advance; use a versioned catalogue directory to reproduce a run.

## If a selection is unavailable

An unknown dataset can mean the wrong catalogue version, an internal dataset
absent from the public view, or a dataset not yet accepted. An access error can
mean a missing local root for licensed data. Use
[Troubleshoot catalogue access](troubleshoot-catalogue.md) to distinguish them.
Only use `--skip-unavailable` when your workflow can explicitly handle omitted
inputs; required data should cause the run to fail.
