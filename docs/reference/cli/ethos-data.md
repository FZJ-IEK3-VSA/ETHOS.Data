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
builds, and it wins where both are given. They also differ in what they *claim*:
the global one says the directory is this invocation's public cache, while the
one after `link` only says where to build — which is why only the first lets
`--prune` retract a restricted link. See
[Removing an exposure depends on what the root is](#namespace-authority).
`catalog upload --root` is a third thing entirely — a publication folder on the
remote. Use `ethos-data COMMAND --help` for command options.

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
| `--prune` | the only flag that removes anything: links for names the catalogue no longer lists, links for datasets it has reclassified, and an empty directory standing where an entry belongs | `--all` only |
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
cache owns, and an entry whose path runs *through* a symbolic link is refused
from the other side of the same rule — the directory it would go in is borrowed,
so the entry would be written into somebody else's tree and would disappear the
day its owner removed that one link. If the catalogue's first listed file is not
under the directory, the link is still made and a warning names the file — the
usual cause is naming a level too high.

Without a directory, `source_dir` is read from the hand-written
`datasets/<name>/dataset.yaml`, which is the only place it exists: it is popped
out of the descriptor when the manifest is built. An uploaded dataset has none
by design, and is refused with the explicit form to use instead.

`--force` has no atomic repoint behind it: the old link is removed before the new
one is attempted. If the new link then cannot be made, the error says so, names
the target the old entry pointed at, and prints the `ethos-data link` line that
puts it back — that target is the only thing the removal destroyed, and the only
thing needed to undo it.

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

Leaving it out of the plan is the whole answer only while the cache holds nothing
for that dataset. Access classes and licences are edited **after** a namespace was
built — that is what a reclassification is — so the first run that reads
`ethos:access: restricted` is often looking at a live link it made itself last
week. Such an entry is reported as `exposed`, not `skip`, and the run returns
`1`: the link is still handing those bytes to everybody who reads this cache, and
a line saying `skip` above an exit code of `0` is how that lasts for months. A
licence withdrawn to `ethos:license_status: unresolved` is reported the same way.
A dataset the cache does not hold at all still prints the plain `skip` line and
affects no exit code.

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

### Removing an exposure depends on what the root is {#namespace-authority}

`--prune` turns that finding into a `retract` and removes the link, leaving the
data behind it untouched — but for a **restricted** dataset only where this
installation can say the directory is its own public cache. The same link means
opposite things in two places. In a public cache it is an exposure. In another
machine's restricted cache it is one authorised installation, put there
deliberately by `ethos-data link <dataset> <directory>`, and removing it destroys
exactly what that command exists to create. Building a namespace for a machine
other than your own is a supported workflow here, so the command is *told* which
case it is by the root it was given rather than guessing:

| The directory `--all` builds | A restricted dataset already linked in it |
| --- | --- |
| this machine's own public cache — the default, or a directory named by the **top-level** `--root` | `exposed`; with `--prune`, `retract`, and the link is removed |
| a directory this installation cannot identify — typically `link --all --root DIR` aimed at another machine's cache | `exposed`, and never removed, whatever `--prune` says |
| this machine's restricted cache | the run is refused before the checkout is read; exit `2` |

`--root` *after* `link` names a destination and claims nothing about what it is,
which is why it does not authorise a removal. The top-level `--root` does claim it:
it sets the public cache for the whole invocation, so `ethos-data --root
/shared/ethos/public link --all --prune` is the spelling that rebuilds another
machine's public cache *and* retracts what such a cache must not hold. When the
root cannot be identified, the closing paragraph gives both readings and prints
that spelling for whoever knows which one applies. The reasoning, the
alternatives and what this costs are in
[a namespace root says what it is](../../explanation/architecture/decisions.md#a-namespace-root-says-what-it-is-2026-09-17).

An **unresolved licence** needs none of this, and is retracted under `--prune`
wherever the run happens at all. There is no namespace in which "nobody has read
the terms" is acceptable, so that removal is justified without knowing which
namespace this is.

Refusing this machine's restricted cache is the one case with no plan and no
report. `link --all` builds a shared namespace from a catalogue checkout, and
there is nothing it could legitimately do there: `source_dir` is a statement about
the maintainer's own machine, so authorised installations may not be created in
bulk from a checkout, and a public entry written there would sit where lookups
never go. The refusal names the commands that do belong there — `link
<dataset>`, `materialize <dataset> --from`, `unlink <dataset>` — and says that
nothing was read and nothing was changed. It also fires, with a different opening
sentence, when the public and restricted caches are configured to the *same*
directory, because that configuration is why a namespace build would serve
licensed bytes to everybody.

An excluded dataset the cache holds as a **real directory** is reported `skip`,
and is never removed — not even by `--prune`. That directory may be the only copy
of those bytes, and no command deletes it on the strength of an edit to a
`dataset.yaml`; the line says so rather than printing what it would print for a
dataset the cache has never held. Licensed bytes downloaded or materialized into
a public cache before the reclassification are a worse exposure than a link, and
clearing them is a deliberate decision somebody makes rather than something this
command does on its own.

An excluded dataset reached **through a borrowed link** is reported and never
retracted either, in any root. The entry sits inside a tree this cache does not
own, so what stands at that path may be the other project's own entry; the line
names the borrowed link to remove instead, which is the one move that is
certainly this cache's to make.

### What `--prune` removes {#namespace-prune}

`--prune` is the only flag that removes anything, and it removes three kinds of
entry under three different lines. `prune` is a link for a name the catalogue no
longer describes. `retract` is a link for a name the catalogue still describes
but this namespace must not hold — the reclassification above. `replace` is an
empty directory standing where an entry belongs, taken away so the dataset can be
linked there.

`prune` and `retract` only ever unlink a symbolic link: a link is a pointer, so
removing it costs nothing but the name, while a real directory is the bytes
themselves, and a catalogue that has stopped naming them says something about the
catalogue rather than about the data. A real directory the catalogue no longer
names is therefore left alone **silently** — the prune pass skips it before it
becomes anything to report, so it gets no line in the output at all. Read the
plan as the changes that are planned, not as an inventory of the cache: where the
catalogue would otherwise have linked a dataset, its real directory is listed as
`keep`; where the catalogue has dropped the dataset, its directory is not listed
at all.

`replace` is the one removal that is not a link, and it is narrow by
construction. The directory has to hold no file of its own at any depth — nothing
this cache ever downloaded or materialized — and has to be empty once this run's
own removals are done. Only `rmdir` is used, never a recursive delete, so a
planner that got this wrong costs an entry reported `failed` rather than a byte.
The shape it exists for is a family collapsed back into one flat dataset: the
members are pruned, and `<cache>/family` is then a husk standing exactly where
the flat dataset's entry belongs. Without `--prune` that husk is reported
`obstructed` and the dataset gets no entry at all.

A name that is a **namespace prefix** of a dataset the catalogue does describe is
never pruned. With `family/member` in the catalogue, `<cache>/family` is the
directory that member lives in, not a stale entry, and removing it would take
every member entry under it while the run reported success. Only a family the
catalogue has left entirely is pruned.

The other half of that reorganisation is the stale link itself. If
`<cache>/family` is a **symbolic link** left over from when `family` was a single
dataset, `family/member` is not written at all: creating its parent directory
would succeed straight through the link, put this cache's entry inside somebody
else's tree, and report it as made. The entry is reported `blocked`, the rest of
the namespace is still built, and the run returns `1`. Remove the stale link —
which discards nothing, because nothing under it belongs to the cache — and run
again. Naming that dataset instead of using `--all` refuses for the same reason
with exit `2`, and refuses before `--force` removes anything.

One finding switches the prune pass off entirely. If any entry is `collides` —
spelled differently in the cache from the name the catalogue uses — no `prune`
line is planned in that run at all, for any name, because the flag that deletes
must not run against a namespace whose entries it cannot name reliably. `retract`
is deliberately not gated that way: a spelling difference somewhere else must
never be the reason licensed bytes go on being served.

### The report {#namespace-report}

Every dataset in the plan gets one line, and the verb is the whole vocabulary:

| Line | What it reports |
| --- | --- |
| `link`, `repoint` | the entry is created, or pointed at where `source_dir` now says |
| `replace` | an empty directory standing where the entry belongs is removed, and the dataset linked there |
| `unchanged` | the link is already correct |
| `keep` | a real directory the cache owns; never replaced with a link |
| `skip` | nothing to do and nothing wrong: no `source_dir`, or a dataset this namespace must not hold and does not hold as a link |
| `missing` | the dataset's `source_dir` is not on this machine |
| `exposed` | a link this namespace must not hold is still in the cache, and nothing removed it |
| `retract` | that link is being removed; the data behind it is untouched |
| `prune` | a link for a name the catalogue no longer describes is being removed |
| `blocked` | the entry would be created inside borrowed data, so it was not written |
| `conflict` | the checkout gives this name files of its own *and* datasets below it; neither shape gets an entry, and the datasets below it are linked as usual |
| `obstructed` | something else stands where the entry belongs: a file, or a directory left behind when the family below the name was withdrawn |
| `collides` | the cache spells this entry differently from the catalogue name — one path to this filesystem, two to the machines reading the cache over a share |
| `failed` | this one entry could not be written or removed; the rest of the namespace was built |

`retract`, `prune` and `replace` appear only with `--prune`. `failed` is the one
verb that is not in the plan: it is discovered while carrying the plan out, so it
is printed after the listing as its own block, naming the entry and the reason,
and the entry's planned line is still above. It no longer means only "the
filesystem refused this": a parent that turned into a symbolic link between the
plan and the write, and a path that could not be created, both arrive under the
same verb, so read the reason rather than assuming a permission problem.

`missing`, `exposed`, `blocked`, `conflict`, `obstructed`, `collides` and
`failed` are the seven that make the run return `1`. Each is counted in a closing
paragraph that says what to do about it; `exposed` can produce up to three of
them, because a link that `--prune` would remove, a link in a root nobody has
identified, and a link reached through borrowed data need three different
answers.

Preview with `--dry-run` first, which prints exactly this plan and writes nothing
at all. The one thing it does not preview is the exit code: a dry run returns `1`
while an `exposed` finding is outstanding, **including** a `retract` it planned
under `--prune`, because a preview removed nothing and the link is still serving
those bytes when the process exits. So `link --all --prune --dry-run` can return
`1` where the identical run without `--dry-run` returns `0`. The asymmetry is
deliberate and confined to exposures: an exposure a run did not clear is a
standing wrong, while a `link` or a `replace` a dry run did not carry out is
merely work left undone, and those do not set the code.

On Windows a symbolic link needs Developer Mode or an elevated shell. Without
either, use `config set-root` instead. A junction (`mklink /J`) is **not** a
substitute: it is reported as an ordinary directory, so the cache would treat
borrowed data as a copy it owns and could write downloads into it — and for the
same reason a junction standing where a namespace prefix belongs is not caught as
`blocked`. In catalogue mode a refused link costs one entry rather than the run:
it is reported as `failed` with that same advice, the remaining entries are still
attempted, and `N change(s) applied.` counts what actually happened, so it can be
lower than the number of changes that were planned.

## `unlink <dataset>`

Remove a cache entry that is a symbolic link. The data it points at is not
touched. A real directory is refused — it holds the cache's own copy.

The entry is looked up in the root for the dataset's **current** access class,
which is why `unlink` cannot clear what a reclassification left behind: once the
catalogue says `restricted`, it looks in the restricted cache and reports no
entry, while the public-cache link is still there. That one is `--prune`'s job.
Unlike `link`, `unlink` is deliberately not refused by a borrowed parent, so an
entry an earlier version wrote inside one can still be taken away — removing a
link discards nothing.

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
its name says, or was deliberately skipped. `1` means the namespace was built as
far as this machine allowed and something is left for a maintainer to fix here:

- a dataset's `source_dir` does not exist on this machine (`missing`);
- a link this namespace must not hold is still in the cache (`exposed`) — clear
  it with `--prune` in a root named as a public cache, or by removing the
  borrowed link the line names;
- an entry was not written because a link stands where a namespace prefix belongs
  (`blocked`);
- the checkout gives one name files of its own and datasets below it (`conflict`);
- something else stands where an entry belongs (`obstructed`);
- an entry is spelled differently in the cache from the catalogue name
  (`collides`);
- an entry could not be written or removed (`failed`).

Each is named on its own line and counted in a closing paragraph, because a
directory that has moved is a fact about this machine worth reporting, not a
reason to abandon the other twenty entries. `--dry-run` reports the same findings
and writes nothing; it returns `1` for a finding it only previewed, a planned
`retract` included, which is why a `--prune --dry-run` preview can return `1`
where the real run returns `0`.

`2` is separate and means the run did not happen. Beside the argument refusals
above, `--all` returns `2` when the directory it was asked to build is this
machine's **restricted cache**: nothing is read and nothing is planned, because
`link --all` builds a shared namespace from a catalogue and an authorised
installation of licensed data is registered one dataset at a time instead. See
[Removing an exposure depends on what the root is](#namespace-authority).

A run that used to exit `0` can now exit `1` with nothing having changed on the
filesystem: a cache holding a dataset the catalogue has since reclassified used
to report it as `skip`. A nightly `ethos-data link --all` under `set -e` will
start failing on such a cache. That is the alarm working — add `--prune` to the
invocation so the run removes the link instead of only naming it.

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
