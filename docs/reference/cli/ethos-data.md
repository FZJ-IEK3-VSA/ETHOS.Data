# `ethos-data`

The consumer-side command: reading the catalogue, planning, fetching, verifying.
It never writes to a catalogue — that is [`ethos-data catalog`](catalog.md).

```
ethos-data [-c COLLECTIONS | -p PACKAGE] [--catalog LOCATION] [--root DIR] [--skip-unavailable]
          <command> ...
```

An `AccessError` — restricted bytes, or a local root that is not set up — is
the catalogue working as designed, so it is printed as a message and exits `2`,
not as a traceback.

## Global options

Put these options before the subcommand, for example
`ethos-data --skip-unavailable -p reskit fetch onshore_wind`.
`--root` here is a local public cache; `catalog upload --root` is a remote
publication folder. Use `ethos-data COMMAND --help` for command-specific options.

| Option | |
|---|---|
| `-c`, `--collections PATH` | path to a collections file. Default: `collections.yaml` in the current directory, or a configured default — see `config show`. |
| `-p`, `--package NAME` | the collections file an installed package registers under `NAME`, e.g. `-p reskit`. Not combined with `-c`. |
| `--catalog LOCATION` | the catalogue to use for this run. A local path or an `http(s)` URL. |
| `--root DIR` | override the public cache directory for this run. |
| `--skip-unavailable` | carry on without data this machine cannot reach (licensed data you have no copy of), listing what was left out instead of stopping. |

The catalogue is the first of: `--catalog`, `$ETHOS_DATA_CATALOG`, a configured
catalogue (`config set-catalog`), the collections file's `catalog:` pin, and
the built-in public catalogue
`https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/main/datacatalog.json`.

## `list`

```bash
ethos-data -p reskit list
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

## `path <key>`

```bash
ethos-data path reskit-test-data/placements/turbine_placements.csv
ethos-data path reskit-test-data/era5
ethos-data -p reskit path reskit-test-data/era5     # the catalogue version RESKit pins
```

Print the absolute local path of a file or folder, fetching it first if it is
not on this machine yet. `<key>` is `<dataset>/<file>`, `<dataset>/<folder>`,
a dataset name, or a dataset family name. A shapefile is fetched together with
its companion files. Needs no collections file. The Python equivalent is
[`ethos_data.path`][ethos_data.path].

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

Check file sizes, or SHA-256 hashes with `--deep`. Never writes anything
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

## `link [dataset] [directory]`

Point cache entries at data already on this machine.

```bash
ethos-data link global-wind-atlas /data/GWA_4.0   # this directory
ethos-data link global-wind-atlas                 # its source_dir
ethos-data link --all                             # every source_dir there is
```

| Flag | |
|---|---|
| `--all` | link every dataset in the source catalogue that has a `source_dir` |
| `--force` | repoint an entry that is already a link |
| `--dry-run` | honoured only with `--all`; a single-dataset link is applied immediately |
| `--catalog-root DIR` | catalogue checkout to read `source_dir` from (default: searched upward from the current directory) |

Entries go in the root for each dataset's access class, so a restricted dataset
lands in the restricted cache or is refused. The directory is recorded as given,
not resolved. A real directory in the cache is never replaced: that is data the
cache owns. If the catalogue's first listed file is not under the directory, the
link is still made and a warning names the file — the usual cause is naming a
level too high.

Without a directory, `source_dir` is read from the hand-written
`datasets/<name>/dataset.yaml`, which is the only place it exists: it is popped
out of the descriptor when the manifest is built. An uploaded dataset has none
by design, and is refused with the explicit form to use instead.

A dataset with **unresolved licensing is refused**, and skipped by `--all`: a
cache entry hands it to everyone reading that cache. Record the terms, or use
[`staging add`](#staging), which is deliberately not gated. See
[Licensing and immutability](../../explanation/licensing.md).

`--all` is [`catalog link-cache`](catalog.md) pointed at the cache this machine
reads, and skips restricted datasets for the same reason. Naming a restricted
dataset explicitly does link it, in the restricted root — that is how an
authorised installation is registered.

On Windows a symbolic link needs Developer Mode or an elevated shell. Without
either, use `config set-root` instead. A junction (`mklink /J`) is **not** a
substitute: it is reported as an ordinary directory, so the cache would treat
borrowed data as a copy it owns and could write downloads into it.

## `unlink <dataset>`

Remove a cache entry that is a symbolic link. The data it points at is not
touched. A real directory is refused — it holds the cache's own copy.

## `materialize [datasets...]`

Replace symbolic-link cache entries with real, verified copies.

| Flag | |
|---|---|
| `--all` | every entry in the public cache that is currently a link |
| `--dry-run` | show the cost, copy nothing |
| `--force` | compatibility option; existing real directories are still skipped |
| `--no-verify` | skip checksum verification of each copied file (not advised) |
| `--from DIR` | copy from this directory instead of the entry's link target |
| `--catalog-root DIR` | catalogue checkout to read `source_dir` from, when there is no entry and no `--from` |

Only files the catalogue describes are copied. Refuses if the copy would leave
less than 2% of the filesystem free. Explicit dataset names use the root for
their access class, including the restricted root. A local copy of licensed
files requires permission under that installation's terms and an appropriately
protected destination; see [Move linked data into the cache](../../how-to/move-linked-data-into-the-cache.md#restricted-data).
`--from` names one dataset (not `--all`) and also fills an entry that does not
exist yet, which is how a cache is seeded from bytes already on the machine
instead of an upload and a download back. With no entry and no `--from`, the
catalogue's `source_dir` is used. This also supports seeding an authorised
restricted installation. It will not write over a real directory the cache owns,
and `--all` still walks the public cache only. Provenance is written to
`.ethos-data-materialized.json` in the new directory; `was_a_link_at` is null
when no link was replaced.

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
consulted with an exists flag, the datasets read from a local root, and the
configured catalogue and default collections file. Needs no catalogue and no
network. It does not resolve a package's pin or reflect per-command `--catalog`
and `--root` overrides; `list` prints the actual catalogue selected for a collection.

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
| `config set-root <dataset> <directory>` | read one dataset from a local directory |
| `config unset-root <dataset>` | stop using a local directory for it |
| `config set-skip-unavailable true\|false` | carry on without licensed data this machine cannot reach |
| `config unset-skip-unavailable` | remove the setting |
| `config set-catalog <location>` | use this catalogue instead of the one a collections file pins, or the built-in public one |
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
| `ETHOS_DATA_CATALOG` | the catalogue, for every tool in this shell or job |
| `ETHOS_SKIP_UNAVAILABLE` | carry on without unreachable data |
| `ETHOS_CATALOG_NO_CACHE` | never cache a fetched catalogue descriptor on disk |
| `ETHOS_PUBLICATION_URL` | override the dataset download base URL |

## Exit status

| | |
|---|---|
| `0` | success |
| `1` | a collection could not be resolved, or `verify` found problems |
| `2` | an `AccessError`, an unknown dataset or package, or no collections file — printed as a message, not a traceback |

## `bundle`

A bundle is a repository copy of selected catalogue resources plus generated
metadata. dCache remains authoritative. Bundle reads use only local files and
never overwrite fixtures or fall back to downloads.

```bash
ethos-data -p reskit bundle export tests/data-bundle test_suite --source-revision v2026.09
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
`-c`, `-p` and `--catalog` select inputs for export only. Invalid bundle inputs exit 2.
See [Keep test data in a repository](../../how-to/keep-test-data-in-a-repository.md).
