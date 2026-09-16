# `ethos-data`

The consumer-side command: reading the catalogue, planning, fetching, verifying.
It never writes to a catalogue — that is [`ethos-data catalog`](catalog.md).

```
ethos-data [-c COLLECTIONS] [--catalog LOCATION] [--root DIR] [--skip-unavailable] [--test]
          <command> [--test] ...
```

An `AccessError` — restricted bytes, or a local root that is not set up — is
the catalogue working as designed, so it is printed as a message and exits `2`,
not as a traceback. So are an unknown collection, a collection whose definition
cannot be resolved, a catalogue copy whose index lists a dataset with no
descriptor behind it, and a catalogue index that cannot be read at all.

## A tool's own command { #tool-command }

A package that ships a collections file can bind these command groups to that
file through [`ethos_data.tool_main`][ethos_data.tool_main], giving it a
command of its own. Such a command offers the collection commands (`list`,
`info`, `plan`, `fetch`, `paths`, `verify`), the key commands (`path`, `ls`),
`bundle` and `config` described below, bound to the file the package ships, so
it takes no `-c`; the other global options are the same. The cache-maintenance
commands — `link`, `unlink`, `materialize`, `staging` and the maintainer's
`catalog` group — concern the shared cache rather than any one package's data
and stay with `ethos-data`. `ethos-data -c <the package's collections.yaml>`
runs the same commands on the same file. See
[Use ETHOS.Data in your package](../../how-to/use-from-a-package.md).

## Global options

Put these options before the subcommand, for example
`ethos-data --skip-unavailable -c collections.yaml fetch onshore_wind`.
`--root` here is a local public cache; `catalog upload --root` is a remote
publication folder. Use `ethos-data COMMAND --help` for command-specific options.

| Option | |
|---|---|
| `-c`, `--collections PATH` | path to a collections file — the one your project uses or the one a package ships. Default: `collections.yaml` in the current directory, or a configured default — see `config show`. |
| `--catalog LOCATION` | the catalogue to use for this run. A local path or an `http(s)` URL. |
| `--root DIR` | override the public cache directory for this run. |
| `--skip-unavailable` | carry on without data this machine cannot reach (licensed data you have no copy of), listing what was left out instead of stopping. |
| `--test` | the collection's small `test` variant instead of the full data. The one global option that is also accepted after the subcommand — see [`--test`](#test). |

The catalogue is the first of: `--catalog`, `$ETHOS_DATA_CATALOG`, a configured
catalogue (`config set-catalog`), the collections file's `catalog:` pin, and
the built-in public catalogue
`https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/main/datacatalog.json`.
The same order holds for `path` and `ls`, which take a key rather than a
collection: the pin they honour is that of the `-c` file, the configured
default collections file, or a `collections.yaml` in the current directory —
whichever `fetch` would read. A tool's command honours the pin of the tool's
own file.

## `--test` { #test }

`info`, `plan`, `fetch`, `paths` and `verify` take `--test` before or after the
subcommand: `ethos-data -c collections.yaml fetch onshore_wind --test` and
`ethos-data -c collections.yaml --test fetch onshore_wind` mean the same, and commands
without the flag ignore it. It selects the collection's `test` variant instead
of the default `full` one. A collection without variants is the same either way
unless a collection it extends has variants — the flag propagates through
`extends`, so a plain `all` extending `onshore_wind` selects `onshore_wind`'s
full variant by default and its test variant with `--test`. A collection that
defines only one of the two refuses a request for the other. Messages label the
variant, as in `onshore_wind [test]`. See
[`collections.yaml`](../schemas.md#collectionsyaml).

## `list`

```bash
ethos-data -c collections.yaml list
ethos-data -c probe-collections.yaml list
```

Every collection the file defines, with file count, total size and title. A
collection with `test:` and `full:` variants gets one row per variant, labelled
`name [test]` and `name [full]`, with the title on the first row only.

```title="Output"
catalogue: /path/to/datacatalog.json
cache:     /path/to/cache

  onshore_wind [test]             6 files     42.3 MB   Data for onshore wind workflows
  onshore_wind [full]          1835 files    311.7 GB
  test_suite                     14 files     97.5 MB   Data required by the pytest suite
```

Every row goes through the checks a fetch runs. A collection that cannot be
resolved — it names a dataset the catalogue does not describe, its definition
is faulty (not a mapping at all, selection keys beside its variants, variants
that disagree about their `paths`, a `paths` handle the collection cannot
honour, a cycle in `extends`), or the catalogue copy lacks the descriptor of a
dataset its index lists — is reported as `[unresolvable]` with the reason, and
the rest are still listed. Exit status is `1` if any row was unresolvable.

## `path <key>`

```bash
ethos-data path reskit-test-data/placements/turbine_placements.csv
ethos-data path reskit-test-data/era5
ethos-data -c collections.yaml path reskit-test-data/era5   # the version this file pins
```

Print the absolute local path of a file or folder, fetching it first if it is
not on this machine yet. `<key>` is `<dataset>/<file>`, `<dataset>/<folder>`,
a dataset name, or a dataset family name. A shapefile is fetched together with
its companion files. Needs no collections file, but honours the catalogue pin
of one when there is one — the `-c` file, the configured default, or a
`collections.yaml` in the current directory; for a tool's command, the tool's
own file — below `--catalog`, `$ETHOS_DATA_CATALOG` and a configured
catalogue, exactly as `fetch` chooses its catalogue. The Python equivalent is
[`Catalog.path`][ethos_data.catalogs.Catalog.path], on
[`ethos_data.catalog()`][ethos_data.catalog] or on a handle's `.catalog`.

## `ls <key>`

```bash
ethos-data ls global-wind-atlas-v4
ethos-data ls reskit-test-data/era5
ethos-data -c collections.yaml ls reskit-test-data   # a family, in the version this file pins
```

List the catalogue's files under a key, with sizes, fetching nothing. `<key>`
is a dataset name, a dataset family name, `<dataset>/<folder>`, or one file
(listed with its companion files). The catalogue is chosen as for `path`:
`--catalog`, `$ETHOS_DATA_CATALOG` or a configured catalogue first, then the
pin of the `-c` file (or of the configured default or `./collections.yaml`;
for a tool's command, its own file); resolving remote catalogue metadata can require network
access. Each line is the key `path` takes to return that one file. An unknown
dataset or folder exits `2`. The Python equivalent is
[`Catalog.resources`][ethos_data.catalogs.Catalog.resources].

```title="Output"
global-wind-atlas-v4: 3 files, 1.9 GB

  global-wind-atlas-v4/gwa4_250_wind-speed_100m.tif                  652.4 MB
  global-wind-atlas-v4/gwa4_250_wind-speed_150m.tif                  651.9 MB
  global-wind-atlas-v4/gwa4_250_wind-speed_50m.tif                   652.0 MB
```

## `info <collection> [--test]` { #info-collection }

Every file a collection selects, with its size, and — when the collection
declares `paths` — a `named paths` section listing each handle and the
catalogue key behind it. Resolves the catalogue but touches no data. The first
line labels the variant when the collection has them.

`info`, `plan`, `fetch` and `paths` check the collection's `paths` handles
against the catalogue and the selection before doing anything else, exactly as
[`ethos_data.fetch`][ethos_data.fetch] does: a handle naming a file the
collection does not include, a folder with no selected file under it, or a key
the catalogue lacks is a `CollectionError` — printed as `error: ...`, exit `2`
— and nothing is fetched. `list` runs the same check on every row.

```title="Output"
onshore_wind [test]: 6 files, 42.3 MB

  reskit-test-data/era5/100m_u_component_of_wind.nc                   16.2 MB
  reskit-test-data/era5/100m_v_component_of_wind.nc                   16.2 MB
  reskit-test-data/era5/forecast_surface_roughness.nc                  5.5 MB
  reskit-test-data/global-wind-atlas/gwa100-like.tif                   1.5 MB
  reskit-test-data/global-wind-atlas/gwa200-like.tif                   1.5 MB
  reskit-test-data/global-wind-atlas/gwa50-like.tif                    1.4 MB

named paths (the `paths` command resolves them to this machine):
  era5      ->  reskit-test-data/era5
  gwa_100m  ->  reskit-test-data/global-wind-atlas/gwa100-like.tif
  gwa_50m   ->  reskit-test-data/global-wind-atlas/gwa50-like.tif
  gwa_200m  ->  reskit-test-data/global-wind-atlas/gwa200-like.tif
```

## `plan <collection> [--test]` { #plan-collection }

What a fetch would do. No dataset bytes are downloaded, but resolving remote
catalogue metadata can require network access. With `--test`, what a fetch of
the test variant would do.

```title="Output"
public cache:    /path/to/cache
used in place:      3 files      1.2 GB  (namespace link, never copied)
already cached:     4 files      9.9 MB
to download:        2 files     32.4 MB
    + reskit-test-data/era5/100m_u_component_of_wind.nc
    + reskit-test-data/era5/100m_v_component_of_wind.nc
not available here:    4 files                  (licensed-example -- left out)
```

Presence is checked by size, which is cheap; `fetch` verifies the hash and
re-fetches anything that fails, so `plan`'s "already cached" is an estimate, not
a promise.

Files expected in place but missing are reported separately, under `MISSING
from where they were expected`.

## `fetch <collection> [--test]` { #fetch-collection }

Download whatever is missing and return. Files already present and matching
their recorded checksum are skipped — including files another tool fetched
earlier into the same cache. Datasets resolved in place are used where they lie
and never copied. A faulty `paths` handle is refused before any transfer (see
[`info`](#info-collection)). Progress messages label the variant:
`onshore_wind [test]: fetching 6 of 6 files (42.3 MB) into /path/to/cache`.
With `--skip-unavailable`, a collection none of whose files this machine can
reach reports `nothing to fetch` rather than pretending something was present.

## `paths <collection> [--test]` { #paths-collection }

```bash
ethos-data -c collections.yaml paths onshore_wind --test
ethos-data -c collections.yaml paths onshore_wind
```

Fetch the collection exactly as `fetch` does — on the collections file already
loaded, so the catalogue is read once — then print its `paths` handles resolved
to this machine: one `handle<TAB>absolute path` line per handle, tab-separated
so a shell can read it back (`while IFS=$'\t' read handle path`). A folder
handle prints the directory holding the collection's selected files under that
key. With `--skip-unavailable`, a handle whose data this machine cannot reach is
left out of the output and a warning names it — the same contract `fetch` gives
the files themselves; without the flag, unreachable data stops the command with
an `AccessError` before anything is downloaded. A collection that declares no
`paths` exits `2`. The Python equivalent is
[`Collections.paths`][ethos_data.selection.Collections.paths].

```title="Output"
era5	/home/me/.cache/ethos-data/reskit-test-data/era5
gwa_100m	/home/me/.cache/ethos-data/reskit-test-data/global-wind-atlas/gwa100-like.tif
gwa_50m	/home/me/.cache/ethos-data/reskit-test-data/global-wind-atlas/gwa50-like.tif
gwa_200m	/home/me/.cache/ethos-data/reskit-test-data/global-wind-atlas/gwa200-like.tif
```

## `verify [collection] [--test]` { #verify-collection }

Check file sizes, or SHA-256 hashes with `--deep`. Never writes anything
unless `--repair` is given.

| Flag | |
|---|---|
| `--all` | every collection in the file, in every variant (the default when no collection is named); one that cannot be resolved is reported as skipped |
| `--test` | the named collection's `test` variant |
| `--deep` | compare checksums, not just sizes — reads every byte |
| `--repair` | re-fetch whatever no longer matches, from dCache |
| `--dry-run` | with `--repair`: say what would be re-fetched, change nothing |
| `-q`, `--quiet` | only report problems |

Statuses, worst first: `dangling`, `wrong checksum`, `wrong size`, `missing`,
`unreadable`, `unavailable here`, `unverifiable`, `ok`.

`--all` prints `skipped <name> [<variant>]: <reason>` for every collection or
variant it cannot resolve — a dataset this catalogue does not describe, an
incomplete catalogue copy, a faulty definition — and verifies the rest. It
exits `1` if anything was skipped, even when every checked file matches: the
check was not complete, and a CI job must not read it as one.

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
network. A cache path this machine cannot reach -- a network drive that is not
connected, say -- is marked `NOT REACHABLE` with the reason, and the cache
contents are listed one level deep only, so the command finishes even when the
cache is a slow share. It does not resolve a collections file's pin or reflect
per-command `--catalog` and `--root` overrides; `list` prints the actual
catalogue selected for a collection.

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
| `1` | `list` reported an `[unresolvable]` row, `verify` found problems or skipped an unresolvable collection |
| `2` | an `AccessError`, an unknown dataset or collection, a collection whose definition cannot be resolved (`CollectionError`), a catalogue index that cannot be read (`CatalogUnavailable`), a catalogue copy whose index lists a dataset with no descriptor or shard behind it (`IncompleteCatalog`), an invalid bundle, or no collections file — printed as a message, not a traceback |

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
| `export TARGET COLLECTION...` | Export to a new directory; refuses an existing target. Canonical metadata is selected without staging; a collection with variants is exported in its `full` variant. |
| `export --source-root DATASET=PATH` | Use an existing local source and verify it against catalogue hashes; repeat for several datasets. |
| `export --source-revision REF` | Record the source commit/tag as provenance; this label does not change the catalogue URL or select a revision. |
| `verify DIRECTORY COLLECTION` | Report hash/presence findings; exits 1 for modified or missing fixtures. |
| `fetch DIRECTORY COLLECTION` | Check hashes and report local paths; no network or repair. |
| `fetch --allow-modified` | Explicit development override for changed bytes; warns and retains original metadata. Missing files still fail. |

Global cache, staging, and skip-unavailable settings do not redirect bundle reads.
`-c` (or a tool's own file) and `--catalog` select inputs for export only. Invalid bundle inputs exit 2.
See [Keep test data in a repository](../../how-to/keep-test-data-in-a-repository.md).
