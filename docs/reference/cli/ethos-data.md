# `ethos-data`

The consumer-side command: reading the catalogue, planning, fetching, verifying.
It never writes to a catalogue — that is [`ethos-data catalog`](catalog.md).

```
ethos-data [-c COLLECTIONS] [--catalog LOCATION] [--root DIR] [--skip-unavailable]
          <command> ...
```

An `AccessError` — restricted bytes, or a local root that is not set up — is
the catalogue working as designed, so it is printed as a message and exits `2`,
not as a traceback.

## Global options

| Option | |
|---|---|
| `-c`, `--collections PATH` | path to a collections file. Default: `collections.yaml` in the current directory, or a configured default — see `config show`. |
| `--catalog LOCATION` | override the catalogue the collections file pins. A local path or an `http(s)` URL. |
| `--root DIR` | override the public cache directory for this run. |
| `--skip-unavailable` | carry on without data this machine cannot reach (licensed datasets away from the institute cluster), listing what was left out instead of stopping. |

## `list`

```bash
ethos-data list
ethos-data -c probe-collections.yaml list
```

Every collection the file defines, with file count, total size and title.

```title="Output"
catalogue: /path/to/datacatalog.json
cache:     /path/to/cache

  probe                          25 files      8.5 MB   Everything synthetic -- the full upload/download round trip
  probe-small                     7 files     14.7 KB   A handful of files, for a fast first check
```

A collection naming a dataset the catalogue does not describe is reported as
`[unresolvable]` with the reason, and the rest are still listed. Exit status is
`1` if any collection was unresolvable.

## `info <collection>`

Every file a collection selects, with its size. Resolves the catalogue but
touches no data.

```title="Output"
probe-small: 7 files, 14.7 KB

  probe-basic/probe-notes.txt                                           114 B
  probe-basic/vectors/probe_sites.shp                                  8.0 KB
```

## `plan <collection>`

What a fetch would do. No dataset bytes are downloaded, but resolving remote
catalogue metadata can require network access.

```title="Output"
public cache:    /path/to/cache
used in place:      3 files      1.2 GB  (namespace link, never copied)
already cached:     7 files     14.7 KB
to download:        2 files    140.6 MB
    + reskit-test-data/era5-like/100m_u_component_of_wind.nc
not available here:  4 files                  (licensed-example -- left out)
```

Presence is checked by size, which is cheap; `fetch` verifies the hash and
re-fetches anything that fails, so `plan`'s "already cached" is an estimate, not
a promise.

Files expected in place but missing are reported separately, under `MISSING
from where they were expected`.

## `fetch <collection>`

Download whatever is missing and return. Files already present and matching
their recorded checksum are skipped — including files another tool fetched
earlier into the same cache. Datasets resolved in place are used where they lie
and never copied.

## `verify [collection]`

Check the data on disk against the catalogue's checksums. Never writes anything
unless `--repair` is given.

| Flag | |
|---|---|
| `--all` | every collection in the file (the default when no collection is named) |
| `--deep` | compare checksums, not just sizes — reads every byte |
| `--repair` | re-fetch whatever no longer matches, from dCache |
| `--dry-run` | with `--repair`: say what would be re-fetched, change nothing |
| `-q`, `--quiet` | only report problems |

Statuses, worst first: `dangling`, `wrong checksum`, `wrong size`, `missing`,
`unreadable`, `unavailable here`, `unverifiable`, `ok`.

See [Check and repair the cache](../../how-to/verify-and-repair.md).

## `materialize [datasets...]`

Replace symbolic-link cache entries with real, verified copies.

| Flag | |
|---|---|
| `--all` | every entry in the public cache that is currently a link |
| `--dry-run` | show the cost, copy nothing |
| `--force` | do not stop at entries that are already real directories |
| `--no-verify` | skip checksum verification of each copied file (not advised) |

Only files the catalogue describes are copied. Refuses if the copy would leave
less than 2% of the filesystem free. Explicit dataset names use the root for
their access class, including the restricted root. A local copy of licensed
files requires permission under that installation's terms and an appropriately
protected destination; see [Migrate cluster data](../../how-to/migrate-cluster-data.md#restricted-data).
Provenance is written to `.ethos-data-materialized.json` in the new directory.

## `staging`

Data that is not in the catalogue yet. See
[Stage uncatalogued data](../../how-to/stage-unpublished-data.md).

```bash
ethos-data staging add <name> <directory> [--note TEXT] [--copy]
ethos-data staging list [--new-only]
ethos-data staging remove <name> [--force]
```

| Flag | |
|---|---|
| `--note TEXT` | what this is, for the next person |
| `--copy` | copy the data instead of linking to it |
| `--new-only` | only datasets with no entry in the public or restricted cache |
| `--force` | on `remove`: required if the entry is a real directory, not a link |

## `config`

### `config show`

The resolved cache directories, why each was chosen, every config file
consulted with an exists flag, the datasets read from a local root, and any
pinned catalogue or collections file. Needs no catalogue and no network.

### Setting a cache root

```bash
ethos-data config set-cache             <directory> [--scope SCOPE]   # alias of set-public-cache
ethos-data config set-public-cache      <directory> [--scope SCOPE]
ethos-data config set-restricted-cache  <directory> [--scope SCOPE]
ethos-data config set-staging-cache     <directory> [--scope SCOPE]
```

Each has a matching `unset-…`. `--scope` is one of `project`, `user` (default),
`environment`, `site`.

### Other settings

| Command | |
|---|---|
| `config set-root <dataset> <directory>` | escape hatch: use one dataset from a local directory |
| `config unset-root <dataset>` | stop using a local directory for it |
| `config set-skip-unavailable true\|false` | carry on without licensed data this machine cannot reach |
| `config unset-skip-unavailable` | remove the setting |
| `config set-catalog <location>` | permanently point at a catalogue, so `--catalog` is not needed every time |
| `config unset-catalog` | remove it |
| `config set-collections <path>` | permanently point at a collections file, so `-c` is not needed every time |
| `config unset-collections` | remove it |
| `config set-publication-url <url>` | fetch bytes from a different door (the high-throughput one, for CI) |

All take `--scope`. See [Configuration](../configuration.md) for precedence and
file locations.

## Environment variables

| Variable | |
|---|---|
| `ETHOS_DATA_DIR` | the public cache directory |
| `ETHOS_RESTRICTED_DIR` | the restricted cache directory |
| `ETHOS_STAGING_DIR` | the staging directory |
| `ETHOS_SKIP_UNAVAILABLE` | carry on without unreachable data |
| `ETHOS_CATALOG_NO_CACHE` | never cache a fetched catalogue descriptor on disk |

## Exit status

| | |
|---|---|
| `0` | success |
| `1` | a collection could not be resolved, or `verify` found problems |
| `2` | an `AccessError` or an unknown dataset — printed as a message, not a traceback |

## `bundle`

A bundle is a repository copy of selected catalogue resources plus generated
metadata. dCache remains authoritative. Bundle reads use only local files and
never overwrite fixtures or fall back to downloads.

```bash
ethos-data -c collections.yaml bundle export tests/data-bundle test_suite --source-revision v2026.09
ethos-data bundle verify tests/data-bundle test_suite
ethos-data bundle fetch tests/data-bundle test_suite
ethos-data bundle fetch tests/data-bundle test_suite --allow-modified
```

| Command/option | Behaviour |
|---|---|
| `export TARGET COLLECTION...` | Export to a new directory; refuses an existing target. Canonical metadata is selected without staging. |
| `export --source-root DATASET=PATH` | Use an existing local source and verify it against catalogue hashes; repeat for several datasets. |
| `export --source-revision REF` | Record the source commit/tag as provenance; this label does not change the catalogue URL or select a revision. |
| `verify DIRECTORY COLLECTION` | Report hash/presence findings; exits 1 for modified or missing fixtures. |
| `fetch DIRECTORY COLLECTION` | Check hashes and report local paths; no network or repair. |
| `fetch --allow-modified` | Explicit development override for changed bytes; warns and retains original metadata. Missing files still fail. |

Global cache, staging, and skip-unavailable settings do not redirect bundle reads.
`-c` and `--catalog` select inputs for export only. Invalid bundle inputs exit 2.
See [Keep test data in a repository](../../how-to/keep-test-data-in-a-repository.md).
