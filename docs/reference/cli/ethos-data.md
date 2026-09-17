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

`--root` here names a local cache, and so does `--root` after `link --all`. They
differ in reach: the global one changes the cache every command in this
invocation uses, the one after `link` changes only the namespace that single run
builds, and it wins where both are given. `catalog upload --root` is a third
thing entirely — a publication folder on the remote. Use
`ethos-data COMMAND --help` for command options.

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

## `link [dataset] [directory]` {#link-dataset-directory}

Point cache entries at data already on this machine — one dataset by name, or
every dataset the source catalogue describes.

```bash
ethos-data link global-wind-atlas /data/GWA_4.0     # this directory
ethos-data link global-wind-atlas                   # its source_dir
ethos-data link global-wind-atlas --force           # repoint an existing link
ethos-data link --all                               # every source_dir there is
ethos-data link --all --root /shared/ethos/public   # into a cache named here
ethos-data link --all --prune --dry-run             # review a full rebuild first
```

| Flag | | Mode |
|---|---|---|
| `--all` | link every dataset in the source catalogue that has a `source_dir` | selects catalogue mode |
| `--force` | repoint an entry that is already a link | dataset only |
| `--root DIR` | build the namespace in this directory instead of the public cache this machine reads | `--all` only |
| `--prune` | the only flag that removes anything: links for names the catalogue no longer describes | `--all` only |
| `--dry-run` | show what would change, write nothing | honoured only with `--all`; a single-dataset link is applied immediately |
| `--catalog-root DIR` | catalogue checkout to read `source_dir` from (default: searched upward from the current directory) | both |

A flag that belongs to the other mode is refused with exit `2` rather than
quietly ignored: `--root` or `--prune` beside a dataset name, `--force` beside
`--all`, and a dataset or directory beside `--all` each say which mode the
argument belongs to. Naming no dataset and passing no `--all` is an error for the
same reason — the two modes write to different places, so there is no safe
default to guess.

`--dry-run` is the one exception, and the one to know before relying on it:
beside a dataset name it is accepted, has no effect, and the link is made and
reported as `linked`. Dataset mode has no plan to show — one entry, one target,
both of them named on the command line — but a flag that reads as a rehearsal and
is not one is how a link gets created by somebody who meant to look first.
Previewing belongs to `--all`, where the plan covers a whole catalogue and a
mistaken `--root` is worth catching before it is built.

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

`--all` runs the same planner over a whole catalogue, and one difference from
naming a dataset is deliberate: it leaves **restricted datasets out of the
namespace it builds**. A namespace everybody sharing the machine reads must never
hand out licensed bytes to a reader who was never granted them. Naming a
restricted dataset explicitly does link it, into the restricted root — that is
how one authorised installation gets registered, by somebody who knows it is
authorised. The asymmetry is the design, not an oversight.

Without `--root`, `--all` builds the namespace in the public cache the rest of
this invocation is already using — the configured public cache, or the global
`--root` when one was given — so the cache you inspect afterwards is the cache
you just wrote to. The run names it before it writes: its opening lines report
the root and the catalogue checkout, and `--dry-run` prints the same preamble
while writing nothing. Read the destination there rather than from
`ethos-data config show`, which reports the shared settings this machine is
configured with and never sees a global `--root`. A namespace built in a
directory nobody meant still reads as success from the terminal, so the line
naming the root is the one worth checking. `--root` after `link` overrides all
of this for this run alone, which is how a maintainer populates a shared cache
from a machine configured to read its own.

### What `--prune` removes {#namespace-prune}

`--prune` is the only flag that removes anything, and it removes one kind of
entry: a link for a name the catalogue no longer describes.

It only ever unlinks a symbolic link: a link is a pointer, so removing it costs
nothing but the name, while a real directory is the bytes themselves, and a
catalogue that has stopped naming them says something about the catalogue rather
than about the data. A real directory the catalogue no longer names is therefore
left alone **silently** — the prune pass skips it before it becomes anything to
report, so it gets no line in the output at all. Read the plan as the changes
that are planned, not as an inventory of the cache: where the catalogue would
otherwise have linked a dataset, its real directory is listed as `keep`; where
the catalogue has dropped the dataset, its directory is not listed at all.

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

Build, upload and publish catalogue metadata and dataset bytes, and probe storage
access. Shared cache links are `ethos-data link`, not a `catalog` subcommand. See
the [`ethos-data catalog` reference](catalog.md).

## Exit status

Successful operations return `0`. Unknown keys, unreadable/incomplete catalogues
and unavailable data produce an error message and return `2`. Maintenance
commands can return `1` for failed checks or partial results; their reference
pages describe the individual contracts.

`link --all` is the one access command with a partial-success code, and it has a
single rule. `0` means every dataset the catalogue names now has an entry where
its name says, or was deliberately skipped — a restricted dataset, one whose
licensing is unresolved, one with no `source_dir`, or a real directory the cache
owns. `1` means one or more datasets have a `source_dir` that does not exist on
this machine (`missing`). Each is named on its own line, and a run that applied
changes closes by counting them, because a directory that has moved is a fact
about this machine worth reporting, not a reason to abandon the other twenty
entries. `--dry-run` prints the same lines and returns the same code, and writes
nothing.

`2` is separate and means the run did not happen: a flag that belongs to the
other mode — `--root` or `--prune` beside a dataset name, `--force` beside
`--all` — a dataset or directory named beside `--all`, or neither a dataset nor
`--all`.

## Migrating earlier commands {#tool-command}

| Earlier invocation | Current invocation |
| --- | --- |
| `ethos-data path KEY` | `ethos-data fetch KEY` |
| `ethos-data -c reskit/data/collections.yaml fetch COLLECTION` | `reskit-data fetch COLLECTION` |
| Collection `list`, `info`, `plan`, `paths`, `verify` | The corresponding package command |
| `ethos-data staging ...` or `ethos-data bundle ...` | The package's `staging ...` or `bundle ...` command |
| `ethos-data catalog link-cache --root DIR` | `ethos-data link --all --root DIR` |

`-c` / `--collections`, default collections-file discovery, and
`config set-collections` / `unset-collections` have been removed from the CLI.
`--test` and `--skip-unavailable` are package-wrapper options.
Applications without a wrapper can still pass an explicit file to
[`ethos_data.collections`][ethos_data.collections] in Python.

`catalog link-cache` was a second name for the planner behind `link --all`, and
two entrances to one mechanism is how a maintainer ends up wondering which of
them prunes. `--root`, `--prune` and `--dry-run` mean on `link --all` exactly what
they meant there.
