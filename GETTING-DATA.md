# Setting up a cache and getting data

`ice2-data` downloads the datasets an ICE-2 tool needs into one folder shared
by every ICE-2 tool on the machine — verified against a checksum, and
downloaded once no matter how many tools ask for it. This is the consumer
side: where that folder lives, how to point it somewhere specific, and how to
pull data into it. Writing to the catalogue itself is covered in
[ADDING-DATA.md](ADDING-DATA.md) and [UPLOAD.md](UPLOAD.md); wiring a
Python package up to use this is [USING-IN-A-LIBRARY.md](USING-IN-A-LIBRARY.md).

## The cache needs no setup by default

Data goes to your OS's per-user cache directory unless told otherwise — same
mechanism on Linux, macOS and Windows.

```bash
ice2-data config show
```

prints the folder in use, **why** it was chosen, and every place that was
checked along the way.

## Pointing it somewhere specific

Six ways to set the cache directory, strongest first — the first one that
applies wins:

| | How | Good for |
|---|---|---|
| 1 | `--root /path` on the command line, or `root=` in Python | one-off runs |
| 2 | the `ICE2_DATA_DIR` environment variable | CI, batch jobs, SLURM |
| 3 | a file called `ice2-data.yaml` in your project folder | a setting you want to see and commit |
| 4 | your personal setting | all your work, every project |
| 5 | a setting inside the conda environment | a shared install someone else manages |
| 6 | a machine-wide setting | a cluster, set by an admin |

**Most people want option 3** — an ordinary file, in the folder you work in,
that you can open, read, edit and commit. Run this from the folder you want
it to appear in:

```bash
ice2-data config set-cache /data/my-analysis/ice2-data --scope project
```

```yaml
# ice2-data.yaml
cache_dir: /data/my-analysis/ice2-data
```

It's found from anywhere *inside* the project — the same way `git` finds a
repository from a subfolder — and setting it again from a subfolder updates
that one file instead of creating a second.

For a personal setting that follows you across projects, drop `--scope`:

```bash
ice2-data config set-cache /data/ice2-data
```

`ice2-data config unset-cache` goes back to the default.

### On a cluster

An admin sets the cache and any locally-held datasets once, site-wide:

```bash
ice2-data config set-cache /projects2/shared/ice2-data --scope site
ice2-data config set-root submarine-cables /benchtop/shared_data/SubmarineCables --scope site
```

Everyone else gets it with no setup. A batch job needing node-local scratch
can still override for one run with `ICE2_DATA_DIR`.

### In CI

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/ice2-data
    key: ice2-data-${{ hashFiles('**/collections.yaml') }}

- run: ice2-data -c reskit/data/collections.yaml fetch test_suite
  env:
    ICE2_DATA_DIR: ~/.cache/ice2-data
```

No credentials needed: published data is served over plain HTTPS.

## Using data that's already on disk

Point a dataset at an existing copy instead of downloading it — a cluster
share, or data not yet published:

```bash
ice2-data config set-root submarine-cables /benchtop/shared_data/SubmarineCables
```

Those files are then read **where they lie**; nothing is copied and nothing
written into the cache. This is also how licensed data is handled — it must
never be duplicated into a shared cache. `--scope project`/`--scope site`
work here too, and roots from different scopes combine (an admin's
site-wide roots and your own don't clobber each other).

`ice2-data config unset-root <dataset>` reverses it.

### Until dCache is ready

> **Temporary**, until `/Helmholtz/FZJ-ICE2` is uploaded and world-readable —
> see [UPLOAD.md](UPLOAD.md).

Nothing is on dCache yet, so real datasets are read from copies already on
this cluster, using exactly the local-root mechanism above:

```bash
ice2-data config set-root landcover        /projects2/2026-j-belina-ResKit-Update/landcover
ice2-data config set-root reskit-test-data /projects2/2026-j-belina-ResKit-Update/reskit_test_data
ice2-data config set-root submarine-cables /benchtop/shared_data/SubmarineCables

export RESKIT_DATA_CATALOG=/projects2/2026-j-belina-ResKit-Update/ice2-data-catalog-internal/datacatalog.json
```

`ice2-data config show` should list each under *"datasets read from a local
root"*, and `ice2-data plan <collection>` should report `to download: 0
files`. Once a dataset is actually uploaded, `ice2-data config unset-root
<dataset>` switches it back to downloading — nothing else changes.

## Fetching data

```bash
ice2-data list                  # what collections exist
ice2-data info onshore_wind     # which files are in one
ice2-data plan onshore_wind     # what a fetch would download, without downloading
ice2-data fetch onshore_wind    # do it
```

Run these from a directory containing a `collections.yaml`, or point at one
with `-c /path/to/collections.yaml`. `-c` selects which *collections* file to
read — the tool-specific list of what to fetch; a repo that isn't itself a
tool (like `ice2-data-catalog-internal`) has no `collections.yaml` of its
own, only demo files such as `probe-collections.yaml`, so pass those
explicitly with `-c`.

To stop passing `-c` every time — e.g. while working inside
`ice2-data-catalog-internal`, which will never grow its own
`collections.yaml` — pin one the same way as the cache directory:

```bash
ice2-data config set-collections /path/to/probe-collections.yaml --scope project
```

**This applies everywhere the project config is found**, not just in that
one directory — the same "found by walking up, like git" rule as
`cache_dir`. If you later run bare `ice2-data list` somewhere that has its
own real `collections.yaml` (RESKit's, say), you'd still get the pinned one
unless you pass `-c` explicitly. `ice2-data config unset-collections`
removes it; `ice2-data config show` always says which file is in effect and
why.

### Pinning a default catalogue

A collections file pins its own catalogue (`catalog:` at the top of the
YAML), which is enough for most use. To work against a *different* one every
time without editing that file or exporting an environment variable in every
shell — e.g. developing against the internal catalogue instead of a
published tag — set it once:

```bash
ice2-data config set-catalog /path/to/ice2-data-catalog-internal/datacatalog.json --scope project
```

Same scopes and precedence as the cache directory (`ice2-data config show`
prints it once set). It takes a local path or an `http(s)` URL, and is
overridden by `--catalog`/`catalog=` for a single run.
`ice2-data config unset-catalog` removes it.

From Python:

```python
from ice2_data import fetch

files = fetch("onshore_wind", collections="collections.yaml")   # {key: Path}
```

Nothing is re-downloaded if it's already present and its checksum matches —
including a file a *different* tool fetched earlier into the same cache.
`fetch`/`plan` only ever transfer what's missing or hash-mismatched; running
the same fetch twice in a row transfers nothing the second time.

### If a dataset can't be downloaded

Some cataloged datasets are licensed or institute-internal and are never
served publicly. Asking for one tells you so, and what to do:

```
dataset 'licensed-example' is restricted and is never downloaded.
  Licensed from <vendor> under contract <ref>. Redistribution prohibited.
Point ice2-data at the copy on this machine:
    ice2-data config set-root licensed-example /path/to/licensed-example
```

That's deliberate — a clear message up front, rather than a workflow failing
deep inside on a missing file.

## Getting unstuck

```bash
ice2-data config show      # where data goes, why, and which datasets are local
ice2-data plan <name>      # what would be downloaded, without downloading
ice2-data info <name>      # exactly which files a collection contains
```

`config show` answers most "why is my data going there / coming from there?"
questions on its own — including naming the exact config file that decided
it, if something looks wrong.
