# Your first fetch

By the end of this page you will have downloaded a collection of files into a
shared cache, checked them against their checksums, and read them back from
Python. It takes about ten minutes and needs no credentials — published data is
served over plain HTTPS.

## 1. Install, and see where data would go

```bash
pip install git+https://jugit.fz-juelich.de/iek-3/shared-code/ice2-data.git
```

```bash
ice2-data config show
```

```title="Output (abridged)"
the two settings that matter:

  public cache      /home/you/.cache/ice2-data
                    from built-in default (per-user OS cache directory)
  restricted cache  (not set -- licensed datasets will refuse to resolve)
                    ice2-data config set-restricted-cache /path --scope environment
```

Nothing has been configured, and nothing needs to be: the **public cache**
falls back to your OS's per-user cache directory. That is the folder every
ICE-2 tool on this machine will share.

!!! tip "`config show` is the diagnostic"
    It prints not just the answer but the reasoning — every config file that
    was consulted, in precedence order, and which one won. When data turns up
    somewhere you did not expect, this is the first thing to run.

If `~/.cache` is on a small volume, put the cache somewhere with room now:

```bash
ice2-data config set-cache /data/ice2-data
```

## 2. Point at a catalogue

`ice2-data` reads two things: a **catalogue**, describing datasets, and a
**collections file**, naming which slices of them you want. A tool ships its
own collections file; the catalogue is pinned inside it.

If you are working inside a tool's repository — RESKit, say — there is one
already, and you can skip this step. Otherwise, point at one explicitly with
`-c`:

```bash
cd /path/to/ice2-data-catalog-internal
ice2-data -c probe-collections.yaml list
```

```title="Output"
catalogue: /projects2/.../ice2-data-catalog-internal/datacatalog.json
cache:     /projects2/.../ice2-data-cache-new

  probe                          25 files      8.5 MB   Everything synthetic -- the full upload/download round trip
  probe-refused                   2 files        58 B   Must FAIL with a useful message, never a mystery missing file
  probe-shards                    3 files     72.0 KB   One shard prefix only -- proves a sharded manifest resolves lazily
  probe-small                     7 files     14.7 KB   A handful of files, for a fast first check
```

Four collections, with file counts and sizes. Note what did **not** happen: no
dataset inventory was downloaded to produce this. The catalogue index carries
the totals, and a dataset's file list is fetched only when something actually
asks for it — which is what keeps `list` instant on a catalogue containing
170,000-file datasets.

!!! note "Getting tired of typing `-c`"
    `ice2-data config set-collections <path> --scope project` pins one for the
    directory you are working in. Careful: it applies everywhere the project
    config is found, not just in that one folder — see
    [Point the cache somewhere](../how-to/configure-the-cache.md).

## 3. Look before you leap

```bash
ice2-data -c probe-collections.yaml info probe-small
```

```title="Output"
probe-small: 7 files, 14.7 KB

  probe-basic/probe-notes.txt                                           114 B
  probe-basic/timeseries.csv                                           1.5 KB
  probe-basic/vectors/probe_sites.cpg                                     6 B
  probe-basic/vectors/probe_sites.dbf                                  4.0 KB
  probe-basic/vectors/probe_sites.prj                                    91 B
  probe-basic/vectors/probe_sites.shp                                  8.0 KB
  probe-basic/vectors/probe_sites.shx                                  1.0 KB
```

`info` says what a collection *contains*. Notice that the collections file asks
for `probe_sites.shp` and gets five files: a shapefile without its `.dbf` and
`.shx` is unreadable, so companions are pulled in automatically rather than
being something every collections file has to remember to spell out.

`plan` says what a fetch would *do*:

```bash
ice2-data -c probe-collections.yaml plan probe-small
```

```title="Output"
public cache:    /projects2/.../ice2-data-cache-new
already cached:     7 files     14.7 KB
to download:        0 files         0 B
```

`plan` touches no network. It is the command to run when you want to know what
a job is about to cost — or, as here, to discover that somebody else already
paid for it.

## 4. Fetch it

```bash
ice2-data -c probe-collections.yaml fetch probe-small
```

Files land at `<cache>/<dataset>/<resource path>` — here,
`.../probe-basic/vectors/probe_sites.shp`. Every downloaded file is verified
against the SHA-256 in the manifest as it arrives; a corrupt transfer is
retried, not silently kept.

**Run it a second time.** Nothing transfers. Files already present and matching
their recorded checksum are skipped — including files a *different* tool
fetched earlier into the same cache. That is the whole point of the design:
there is nothing to synchronise, because two tools resolving the same catalogue
compute the same path and the second one simply finds the file there.

## 5. Do it from Python

```python
from ice2_data import fetch

files = fetch("probe-small", collections="probe-collections.yaml")
```

`files` is a `DataFiles` — an ordinary `dict` mapping
`"<dataset>/<resource path>"` to a `pathlib.Path`, in catalogue order, with two
conveniences on top:

```python
files.paths                       # [Path, Path, ...] — hand the lot to a workflow
files.one("probe_sites.shp")      # one file, by the end of its name
```

`.one()` raises if the suffix is ambiguous or absent, so a typo fails loudly
instead of handing back the wrong raster.

```python
import geopandas as gpd

sites = gpd.read_file(files.one("probe_sites.shp"))
```

## 6. Check what is on disk

Downloads are verified as they arrive, but data can drift afterwards — most
often when a cache entry points into shared project storage that somebody else
reorganises.

```bash
ice2-data -c probe-collections.yaml verify probe-small
```

```title="Output"
verifying 7 files from probe-small (sizes)

ok: 7

7 file(s) match the catalogue.
```

That compared sizes, which is cheap enough to run often. Add `--deep` to
compare checksums — it reads every byte, so it is the check to run before you
publish a result rather than the one to run every morning. `--repair` re-fetches
whatever no longer matches.

## What you now know

| You ran | It answered |
|---|---|
| `ice2-data config show` | where data goes, and why |
| `ice2-data list` | what collections exist |
| `ice2-data info <name>` | which files one contains |
| `ice2-data plan <name>` | what a fetch would download |
| `ice2-data fetch <name>` | download it |
| `ice2-data verify <name>` | is what is on disk still what the catalogue describes |

## Next

- Your data should live somewhere other than `~/.cache`, or you are on a
  cluster: [Point the cache somewhere](../how-to/configure-the-cache.md).
- You maintain a package that needs input data:
  [Use it from your own package](use-from-a-library.md).
- You have data other people should be able to fetch:
  [Add a dataset to the catalogue](add-a-dataset.md).
- You want to know why the cache is shaped like this:
  [Why one catalogue](../explanation/deduplication.md).
