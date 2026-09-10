# Your first fetch

You use ETHOS.RESKit and want to obtain the data needed by a workflow. This
lesson discovers its collections, fetches a selected input, and reads the
returned paths in Python. It assumes `ethos-data` and RESKit are installed in
your active environment and that you are in a RESKit source checkout containing
`reskit/data/collections.yaml`. For another package, use its shipped collections
file and collection names.

Publicly downloadable data needs no storage credentials. You do not need
access to the internal catalogue repository. If your cluster provides a local
catalogue instead, use the override in
[Get data for a task](../how-to/get-data-for-a-task.md#use-the-clusters-internal-catalogue).

## 1. See where data will go

```bash
ethos-data config show
```

The output shows the public cache, configured local roots, any staging root,
and the configuration source for each setting. With no configuration, the
public cache uses your operating system's per-user cache directory. If that
volume is too small, choose a location with enough space before fetching:

```bash
ethos-data config set-cache /data/ethos-data
```

Replace the example path with a writable directory on your machine. The cache
can be shared by several consuming packages.

## 2. Discover the package's collections

```bash
ethos-data -c reskit/data/collections.yaml list
```

The collections file declares the package's selections and pins its catalogue.
RESKit includes collections such as `test_suite`, `onshore_wind`, `solar`, and
`all`. This lesson uses `onshore_wind`; inspect its size before proceeding.

Catalogue metadata may be retrieved from the configured host. This step does
not download the selected dataset bytes.

## 3. Inspect the selection and transfer estimate

```bash
ethos-data -c reskit/data/collections.yaml info onshore_wind
ethos-data -c reskit/data/collections.yaml plan onshore_wind
```

`info` lists the files. Selecting `turbinePlacements.shp` also selects the
recorded shapefile companions, such as `.dbf` and `.shx`, needed to read it.

`plan` shows the cache location, files already present, files used in place,
and estimated downloads. Planning can load remote descriptors and shards; it
does not fetch dataset bytes. Its size checks are a quick estimate rather than
a checksum verification.

## 4. Fetch the collection

```bash
ethos-data -c reskit/data/collections.yaml fetch onshore_wind
```

A downloaded file is stored under `<cache>/<dataset>/<resource path>` and
checked against its recorded checksum. A dataset configured for local access
is read in place. Run the same fetch again: valid cached downloads are reused.
This also works when another package originally fetched the same resources.

## 5. Obtain the paths from Python

```python
from reskit import data

files = data.fetch("onshore_wind")
turbines = files.one("turbinePlacements.shp")
```

`files` maps resource keys such as `reskit-test-data/turbinePlacements.shp` to
`pathlib.Path` objects. Its `.paths` property returns all paths, while
`.one("suffix")` returns one unambiguous match and raises for an absent or
ambiguous suffix. The result can be passed to the corresponding workflow or
reader:

```python
import geopandas as gpd

sites = gpd.read_file(turbines)
```

If a package does not provide a wrapper, the underlying call is:

```python
from ethos_data import fetch

files = fetch("onshore_wind", collections="reskit/data/collections.yaml")
```

## 6. Check the stored files

```bash
ethos-data -c reskit/data/collections.yaml verify onshore_wind --deep
```

This compares checksums, including for catalogued files read in place. Without
`--deep`, verification compares sizes. Inspect failures before choosing a
[repair operation](../how-to/verify-and-repair.md).

You have now followed selection, transfer, reuse, and verification. Continue
with [Get data for a task](../how-to/get-data-for-a-task.md) for smaller subsets
and the package's `all` collection, or
[Troubleshoot catalogue access](../how-to/troubleshoot-catalogue.md) if your
configuration or available data differs from the lesson.
