# `ethos-data`

Catalogue access, shared configuration, cache administration and catalogue
maintenance. Collection workflows, test bundles and staging use a
[package data command](package-data.md), such as `<your-tool>-data`.

```text
ethos-data [--catalog LOCATION] [--root DIR] COMMAND ...
```

## Global options

Put global options before the subcommand.

| Option | Behaviour |
| --- | --- |
| `--catalog LOCATION` | Select a local `datacatalog.json` or an HTTP(S) URL for this invocation. |
| `--root DIR` | Override the public cache for this invocation; for `link`, `unlink` and `materialize`, name the cache that holds the entry. |
| `-h`, `--help` | Show help without loading catalogue metadata. |

The catalogue is chosen from `--catalog`, `ETHOS_DATA_CATALOG`, configuration,
then the built-in public catalogue. `ethos-data` does not read a collections
file. A package command checks the catalogue against its file's release
bounds, and without a configured catalogue reads the public release they
select; see [catalogue resolution](../configuration.md#catalogue-resolution).

The global `--root` names the public cache for access by key, and for `link`,
`unlink` and `materialize` the cache that holds the entry: a public cache, or a
listed restricted cache. `link --all` builds the cache that `--root` after
`link` names, or else the global one; the one after `link` wins where both are
given. `catalog upload --root` is a third thing entirely — a publication folder
on the remote. Use `ethos-data COMMAND --help` for command options.

## `ls [key] [--meta]` {#ls-key}

```bash
ethos-data ls
ethos-data ls global-wind-atlas-v4
ethos-data ls reskit-test-data/era5
ethos-data ls reskit-test-data/gebco --meta
```

Without a key, list dataset names, access classes and titles from the catalogue
index without loading each dataset's inventory, and `(superseded by <name>)`
after a dataset a successor replaces. With a dataset, family, folder
or file key, list matching resource keys and sizes. A file includes its sidecars.
No data bytes are fetched; remote metadata can require network access.
With `--meta`, print instead the description of each dataset under the key:
title and version, description, access class and origin, homepage, sources,
licences, attribution, restriction, upstream status and contact, as far as
the catalogue records them.

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
catalogue hashes and reused when they match. Files resolved through cache links,
staging or an authorised restricted installation are read in place.
Restricted data is never downloaded.

The Python equivalent is [`Catalog.path`][ethos_data.catalogs.Catalog.path] on
[`ethos_data.catalog()`][ethos_data.catalog]. To use the catalogue a package
reads, point `--catalog` at the release its `show` names, or use its
collections handle's `.catalog`.

## `config`

`ethos-data config show` prints the settings file it read, the catalogue and
cache settings, their origins, one level of public-cache entries and the
[places a file is read from](../configuration.md#lookup-order) in order. It
numbers the restricted caches in reading order and says when the account lists
none, as a normal state. It works offline and marks unreachable cache paths with
the reason. It
reports the settings, not per-command overrides or the catalogue a package
reads within its release bounds.

Use `ethos-data ls` to see the catalogue selected for direct access, or
`<your-tool>-data show` for a package's selected catalogue and collections.

The setters and unsetters write to the settings file in effect, the file
`ETHOS_DATA_CONFIG` names or else the one in your account, and a setter creates
it if need be. `add-restricted-cache DIR` appends a restricted cache and refuses
one already listed; `remove-restricted-cache DIR` removes one. A cache setter
refuses a directory that is, contains or lies inside another root. `unset-publication-url` returns downloads to the door the
catalogue names. Settings affect package wrappers too. The
[configuration reference](../configuration.md) lists keys, commands, environment
variables and precedence. For setup steps, see
[Set up your machine](../../how-to/data-users/set-up-your-machine.md).

## `selftest` {#selftest}

Check that this machine can obtain data at all, with the small public
collections file that ships with ETHOS.Data
(`ethos_data.EXAMPLE_COLLECTIONS`, under 200 KB):

```bash
ethos-data selftest
ethos-data --root selftest-download selftest     # force a real download
```

It reports three steps and stops at the first that fails: the settings in
effect, with any cache this machine cannot reach marked; the catalogue they
choose and its version; and every file, `downloaded`, `already present` or
`read in place`, checked against the catalogue's checksums. It ends with
`selftest passed` and exit `0`, or names the failed step and exits `1`.
`--catalog` and `--root` apply as for every command.

## `report [key]` {#report}

Draft a problem report: run `selftest`, `config show` and, for a key,
`fetch <key> --plan`, and print their output in the report template, with
tokens, credentials in URLs, the home directory and the account name
removed. `--no-selftest` leaves out the self-test's download. A package's
data command has the same, with its collections.

## `verify <key>` {#verify}

Check the files under a dataset, folder or file against the catalogue, as a
package's `verify` checks a collection.

| Flag | |
|---|---|
| `--deep` | compare checksums, not just sizes |
| `--repair` | download damaged copies the public cache owns again; never a link |
| `--dry-run` | with `--repair`: say what would be re-fetched, change nothing |
| `-q`, `--quiet` | report only problems |

## `link [dataset] [directory]` {#link-dataset-directory}

Point cache entries at data already on this machine — one dataset by name, or
every dataset the source catalogue describes.

```bash
ethos-data link global-wind-atlas /data/GWA_4.0     # this directory
ethos-data link global-wind-atlas                   # its source_dir
ethos-data link global-wind-atlas --force           # repoint an existing link
ethos-data --root /shared/ethos/restricted/<group> link gadm-3.6 /data/gadm
ethos-data link --all --root /shared/ethos/cache    # every source_dir there is
ethos-data link --all --root /shared/ethos/cache --prune --dry-run
```

| Flag | | Mode |
|---|---|---|
| `--all` | link every dataset in the source catalogue that has a `source_dir` | selects catalogue mode |
| `--force` | repoint an entry that is already a link | dataset only |
| `--root DIR` | the public cache to build; required | `--all` only |
| `--prune` | the only flag that removes anything: links for names the catalogue no longer describes | `--all` only |
| `--dry-run` | print the plan, write nothing | with `--all`, and with `--catalog-root`; a link by name without it is made at once |
| `--catalog-root DIR` | catalogue checkout to read `source_dir` from (default: searched upward from the current directory); given, each link is recorded there | both |

A flag that belongs to the other mode is refused with exit `2` rather than
quietly ignored: `--root` or `--prune` beside a dataset name, `--force` beside
`--all`, and a dataset or directory beside `--all` each say which mode the
argument belongs to. Naming no dataset and passing no `--all` is an error for the
same reason — the two modes write to different places, so there is no safe
default to guess.

`--dry-run` is the one exception, and the one to know before relying on it:
beside a dataset name without `--catalog-root` it is accepted, has no effect,
and the link is made and reported as `linked`. That link is one entry and one
target, both named on the command line, and records nothing. With
`--catalog-root` the link is a step of the dataset, and `--dry-run` prints its
plan; with `--all` the plan covers a whole catalogue, and a mistaken `--root`
is worth catching before it is built.

The entry goes into the cache the global `--root` names. Without it, a public
dataset's entry goes into the public cache and a restricted dataset's into the
only listed restricted cache; with several listed, or none, the command refuses,
naming the caches or `config add-restricted-cache DIR`. A restricted dataset's
entry goes only into a listed restricted cache, and a public dataset's never into
one. The directory is recorded as given,
not resolved. A real directory in the cache is never replaced: that is data the
cache owns. If the catalogue's first listed file is not under the directory, the
link is still made and a warning names the file — the usual cause is naming a
level too high.

Without a directory, `source_dir` is read from the dataset's `status.yaml` in
the source checkout. It is never published. A frozen dataset has none left, and is refused with the
explicit form to use instead.

Given `--catalog-root`, linking is a step in the dataset's lifecycle: it is
refused before anything is linked when the dataset's state does not allow it,
a draft not built yet, and each link made is recorded in the dataset's
[`status.yaml`](../schemas.md#statusyaml) as a `linked` copy, which makes a
built dataset `available`. The command runs as a pipeline, each stage planned
before any acts: `check`, `link`, `record`. `--all` runs `plan`, `apply` and
`record`, skips such a dataset, and records each link once. Without
`--catalog-root` nothing is recorded, which is how a user registers an
installation of their own.

A dataset with **unresolved licensing is refused**, and skipped by `--all`: a
cache entry hands it to everyone reading that cache. Record the terms, or use
[a package's `staging add`](package-data.md#staging), which is deliberately not gated. See
[Licensing and immutability](../../explanation/licensing.md).

`--all` runs the same planner over a whole catalogue, and one difference from
naming a dataset is deliberate: it leaves **restricted datasets out of the
namespace it builds**. A namespace everybody sharing the machine reads must never
hand out licensed bytes to a reader who was never granted them. Naming a
restricted dataset explicitly does link it, into the restricted cache of its
access combination — that is how one authorised installation gets registered, by somebody who knows it is
authorised. The asymmetry is the design, not an oversight.

`--all` requires `--root`: the namespace goes only into a public cache somebody
names, in practice the cluster's public cache, and a forgotten `--root` cannot
build it in whatever cache the account happens to read. A listed restricted
cache is refused as its root, and a restricted dataset is skipped with "link it
by name into the restricted cache of its access combination". The run names
the root before it writes: its opening lines report the root and the catalogue
checkout, and `--dry-run` prints the same preamble while writing nothing.

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
either, `link` refuses and offers `ethos-data materialize NAME --from DIR`, a
verified copy. A junction (`mklink /J`) is **not** a substitute: it is reported
as an ordinary directory, so the cache would treat borrowed data as a copy it
owns and could write downloads into it.

## `unlink <dataset>`

Remove a cache entry that is a symbolic link, from the cache the global
`--root` names, or else from where `link` puts it. The data it points at is not
touched. A real directory is refused — it holds the cache's own copy. A public
dataset's entry in a restricted cache, which `verify` reports, is removed with
`ethos-data --root CACHE unlink NAME`.

## `materialize [datasets...]`

Replace symbolic-link cache entries with real, verified copies.

| Flag | |
|---|---|
| `--all` | every entry that is currently a link in the public cache, or in the public cache the global `--root` names |
| `--dry-run` | show the cost, copy nothing |
| `--no-verify` | skip checksum verification of each copied file (not advised) |
| `--from DIR` | copy from this directory instead of the entry's link target |
| `--catalog-root DIR` | catalogue checkout to read `source_dir` from, when there is no entry and no `--from`; given, each copy is recorded there |

Only files the catalogue describes are copied. Refuses if the copy would leave
less than 2% of the filesystem free. A named dataset's copy goes where `link`
puts its entry, a restricted dataset's into a listed restricted cache. A local
copy of licensed
files requires permission under that installation's terms and an appropriately
protected destination; see [Materialize linked data](../../how-to/catalogue-maintainers/materialize-linked-data.md#materialize-copies).
`--from` names one dataset (not `--all`) and also fills an entry that does not
exist yet, which is how a cache is seeded from bytes already on the machine
instead of an upload and a download back. With no entry and no `--from`, the
catalogue's `source_dir` is used. This also supports seeding an authorised
restricted installation. It will not write over a real directory the cache owns,
and `--all` walks a public cache only. Provenance is written to
`.ethos-data-materialized.json` in the new directory; `was_a_link_at` is null
when no link was replaced. Given `--catalog-root`, the command runs as a
pipeline: `check` leaves out a dataset whose state does not allow the step,
`copy` copies the rest, `verify` checks each copy in place against the sizes
in the inventory, and `record` records it in the dataset's `status.yaml` as
`materialized`, in place of the link it replaced. A dataset that fails does
not stop the others.

## `catalog`

Build, upload and publish catalogue metadata and dataset bytes, and probe storage
access. Cache links are `ethos-data link`, not a `catalog` subcommand. See
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
