# Your first fetch

You use ETHOS.RESKit and want the data one of its workflows needs. In this
lesson you find the collections RESKit declares, fetch one, and use the files
from Python. It assumes `ethos-data` and RESKit are installed in your active
environment; nothing else needs to be set up. For another package, replace
`reskit` and the names below with that package's.

## 1. See where data will go

```bash
ethos-data config show
```

The first lines name the public cache and where that setting came from. With
nothing configured, it is your operating system's per-user cache directory. If
that disk is too small, choose another directory before fetching:

```bash
ethos-data config set-public-cache /data/ethos-data
```

## 2. Find the package's collections

```bash
ethos-data -p reskit list
```

`-p reskit` reads the collections file that RESKit ships. The list includes
`test_suite`, `onshore_wind`, `solar` and `all`, each with its size. This
lesson uses `onshore_wind`.

## 3. Look before you download

```bash
ethos-data -p reskit info onshore_wind
ethos-data -p reskit plan onshore_wind
```

`info` lists the files in the collection. `plan` shows how many of them are
already on this machine and how much would be downloaded. Neither downloads the
data itself.

## 4. Fetch the collection

```bash
ethos-data -p reskit fetch onshore_wind
```

Run the same command again: it reports that every file is already present and
downloads nothing. Another package asking for the same files later finds them
too.

## 5. Use the files from Python

Get the path of one file, and of one folder:

```python
import ethos_data

placements = ethos_data.path("reskit-test-data/placements/turbine_placements.csv")
era5_folder = ethos_data.path("reskit-test-data/era5")
print(placements)
print(era5_folder)
```

Both are absolute paths into the cache. Hand them to RESKit as you would any
other path:

```python
import pandas as pd

sites = pd.read_csv(placements)
```

Now get the whole collection at once:

```python
files = ethos_data.fetch("onshore_wind", package="reskit")
print(len(files), "files")
```

`files` maps each key, such as `reskit-test-data/era5/…`, to its path.

## 6. Check the stored files

```bash
ethos-data -p reskit verify onshore_wind --deep
```

Every file is compared with the checksum recorded in the catalogue, and the
command ends with the number of files that match.

## What you did

You found a package's collections, looked at one before downloading it,
fetched it, got file and folder paths from Python, and verified the result —
without configuring a catalogue or a collections file.

## Next

- [Get data for a task](../how-to/get-data-for-a-task.md) — the same calls for
  your own scripts and notebooks.
- [Configure the cache](../how-to/configure-the-cache.md) — put the cache
  somewhere specific.
- [Troubleshoot catalogue access](../how-to/troubleshoot-catalogue.md) — when
  something differs from this lesson.
