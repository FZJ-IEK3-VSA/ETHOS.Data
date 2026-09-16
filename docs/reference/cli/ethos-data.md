# `ethos-data`

Catalogue access, shared configuration, cache administration and catalogue
maintenance. Collection workflows, test bundles and staging use a
[package data command](package-data.md), such as `reskit-data`.

```text
ethos-data [--catalog LOCATION] [--root DIR] COMMAND ...
```

## Global options

Put global options before the subcommand.

| Option | Behaviour |
| --- | --- |
| `--catalog LOCATION` | Select a local `datacatalog.json` or an HTTP(S) URL for this invocation. |
| `--root DIR` | Override the local public cache directory for this invocation. |
| `-h`, `--help` | Show help without loading catalogue metadata. |

The catalogue is chosen from `--catalog`, `ETHOS_DATA_CATALOG`, configuration,
then the built-in public catalogue. `ethos-data` does not read a collections
file. A package command instead uses its own file's pin when no override is
set; see [catalogue resolution](../configuration.md#catalogue-resolution).

`--root` here names a local cache. `catalog upload --root` names a remote
publication folder. Use `ethos-data COMMAND --help` for command options.

## `ls [key]` {#ls-key}

```bash
ethos-data ls
ethos-data ls global-wind-atlas-v4
ethos-data ls reskit-test-data/era5
```

Without a key, list dataset names, access classes and titles from the catalogue
index without loading each dataset's inventory. With a dataset, family, folder
or file key, list matching resource keys and sizes. A file includes its sidecars.
No data bytes are fetched; remote metadata can require network access.

The Python equivalent for files under a key is
[`Catalog.resources`][ethos_data.catalogs.Catalog.resources].
Dataset entries are available through `catalog.datasets`.

## `fetch <key>` {#fetch-key}

```bash
ethos-data fetch reskit-test-data/placements/turbine_placements.csv
ethos-data fetch reskit-test-data/era5
```

Fetch a file, folder, dataset or dataset family and print its absolute local
path. A shapefile brings its sidecars. Downloaded files are checked against
catalogue hashes and reused when they match. Files resolved through local roots,
cache links, staging or an authorised restricted installation are read in place.
Restricted data is never downloaded.

The Python equivalent is [`Catalog.path`][ethos_data.catalogs.Catalog.path] on
[`ethos_data.catalog()`][ethos_data.catalog]. To use the catalogue a package
pins, use its wrapper's `path` command or its collections handle's `.catalog`.

## `config`

`ethos-data config show` prints configured catalogue and cache settings, their
origins, local dataset overrides and one level of public-cache entries. It works
offline and marks unreachable cache paths with the reason. It reports shared
settings, not per-command overrides or a package's resolved catalogue pin.

Use `ethos-data ls` to see the catalogue selected for direct access, or
`reskit-data list` for RESKit's selected catalogue and collections.

All setters/unsetters accept `--scope project|user|environment|site`, defaulting
to `user`. Settings affect package wrappers too. The
[configuration reference](../configuration.md) lists keys, commands, environment
variables, scopes and precedence. For setup steps, see
[Set up your machine](../../how-to/set-up-your-machine.md).

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
[a package's `staging add`](package-data.md#staging), which is deliberately not gated. See
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
protected destination; see [Move linked data into the cache](../../how-to/link-cluster-data.md#materialize-copies).
`--from` names one dataset (not `--all`) and also fills an entry that does not
exist yet, which is how a cache is seeded from bytes already on the machine
instead of an upload and a download back. With no entry and no `--from`, the
catalogue's `source_dir` is used. This also supports seeding an authorised
restricted installation. It will not write over a real directory the cache owns,
and `--all` still walks the public cache only. Provenance is written to
`.ethos-data-materialized.json` in the new directory; `was_a_link_at` is null
when no link was replaced.

## `catalog`

Build, upload and publish catalogue metadata and dataset bytes, create shared
cache links, and probe storage access. See the
[`ethos-data catalog` reference](catalog.md).

## Exit status

Successful operations return `0`. Unknown keys, unreadable/incomplete catalogues
and unavailable data produce an error message and return `2`. Maintenance
commands can return `1` for failed checks or partial results; their reference
pages describe the individual contracts.

## Migrating earlier commands {#tool-command}

| Earlier invocation | Current invocation |
| --- | --- |
| `ethos-data path KEY` | `ethos-data fetch KEY` |
| `ethos-data -c reskit/data/collections.yaml fetch COLLECTION` | `reskit-data fetch COLLECTION` |
| Collection `list`, `info`, `plan`, `paths`, `verify` | The corresponding package command |
| `ethos-data staging ...` or `ethos-data bundle ...` | The package's `staging ...` or `bundle ...` command |

`-c` / `--collections`, default collections-file discovery, and
`config set-collections` / `unset-collections` have been removed from the CLI.
`--test` and `--skip-unavailable` are package-wrapper options.
Applications without a wrapper can still pass an explicit file to
[`ethos_data.collections`][ethos_data.collections] in Python.
