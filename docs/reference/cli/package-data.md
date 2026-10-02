# Package data commands

[`ethos_data.tool_main`][ethos_data.tool_main] and
[`Collections.main`][ethos_data.selection.Collections.main] provide the shared
CLI used by consuming packages. Replace `<tool>-data` below with the installed
command, for example `<your-tool>-data`.

```text
<tool>-data [--catalog LOCATION] [--root DIR] [--test] COMMAND ...
```

The package ships and selects its own collections file. There is no CLI option
to substitute another file. See [Use ETHOS.Data in your package](../../how-to/package-maintainers/use-from-a-package.md)
to expose the wrapper.

## Global options

| Option | Behaviour |
| --- | --- |
| `--catalog LOCATION` | Override the catalogue for this invocation. |
| `--root DIR` | Override the public cache for this invocation. |
| `--test` | Select the collection's test variant; also accepted after collection subcommands. |
| `-h`, `--help` | Show help without loading the catalogue. |

Every input a collection names is required: restricted data this account
cannot read stops `fetch`, before anything is downloaded, with an error that
names the dataset, says how to obtain it as far as the catalogue records that,
and gives the two commands that register a copy. `fetch --plan`, `show` and
`verify` only describe, and list it as not available here, with the state of
every listed restricted cache.

Place global options before the subcommand, except `--test`, which works in
either position. A package may supply an environment override such as
`<YOUR_TOOL>_DATA_CATALOG`; it ranks below `--catalog` and above shared settings.
See [catalogue resolution](../configuration.md#catalogue-resolution).

`--help`, `config show`, staging management, and bundle reads do not load the
catalogue. Collection commands need readable metadata.

## Collections, not keys { #scope }

This command works in the collections its package ships: `show` answers
questions about them and never transfers a byte, `fetch` is the one that moves
data, and `verify` checks what is already on disk. A single catalogue key — one
dataset, folder or file — belongs to [`ethos-data ls` and
`ethos-data fetch`](ethos-data.md), which read the same catalogue.

`list`, `info`, `plan`, `paths`, `path` and `ls` were retired, not aliased.
Each answers with the line to type instead:

```text
$ <your-tool>-data plan onshore_wind
error: `<your-tool>-data plan` is gone -- use `<your-tool>-data fetch <collection> --plan`.
Run `<your-tool>-data --help` for the commands this version has.
```

## `--test` { #test }

`show`, `fetch` and `verify` take `--test` before or after the
subcommand: `<tool>-data fetch onshore_wind --test` and
`<tool>-data --test fetch onshore_wind` mean the same, and commands
without the flag ignore it. It selects the collection's `test` variant instead
of the default `full` one. A collection without variants is the same either way
unless a collection it extends has variants — the flag propagates through
`extends`, so a plain `all` extending `onshore_wind` selects `onshore_wind`'s
full variant by default and its test variant with `--test`. A collection that
defines only one of the two refuses a request for the other. Messages label the
variant, as in `onshore_wind [test]`. See
[`collections.yaml`](../schemas.md#collectionsyaml).

## `show [collection] [--test] [--files] [--meta]` { #show }

Reads catalogue metadata and nothing else: no form of `show` downloads
anything.

```bash
<tool>-data show                         # every collection in the file
<tool>-data show onshore_wind --test     # one collection
<tool>-data show onshore_wind --files    # ... and every file it selects
<tool>-data show onshore_wind --meta     # ... and every dataset's description
```

Without a collection: every collection the file defines, with file count, total
size and title. A collection with `test:` and `full:` variants gets one row per
variant, labelled `name [test]` and `name [full]`, with the title on the first
row only.

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

With a collection: its size, its title, and — when the collection declares
`paths` — a `named paths` section listing each handle and the catalogue key
behind it. The first line labels the variant when the collection has them. The
file list is opt-in under `--files`: a workflow is wired up from the handles,
and a collection large enough to be worth asking about is large enough that its
file list buries them.

```title="Output"
onshore_wind [test]: 6 files, 42.3 MB
  Data for onshore wind workflows

named paths (`<your-tool>-data fetch onshore_wind --test --paths` resolves them to this machine):
  era5      ->  reskit-test-data/era5
  gwa_100m  ->  reskit-test-data/global-wind-atlas/gwa100-like.tif
  gwa_50m   ->  reskit-test-data/global-wind-atlas/gwa50-like.tif
  gwa_200m  ->  reskit-test-data/global-wind-atlas/gwa200-like.tif

(6 files; --files lists them)
```

`show`, `fetch` and `fetch --plan` check the collection's `paths` handles
against the catalogue and the selection before doing anything else, exactly as
[`ethos_data.fetch`][ethos_data.fetch] does: a handle naming a file the
collection does not include, a folder with no selected file under it, or a key
the catalogue lacks is a `CollectionError` — printed as `error: ...`, exit `2`
— and nothing is fetched. A bare `show` runs the same check on every row.

## `fetch <collection> [--test] [--plan | --paths]` { #fetch-collection }

Download whatever the collection selects and this machine does not already
have. Files already present and matching their recorded checksum are skipped —
including files another tool fetched earlier into the same cache. Datasets
resolved in place are used where they lie and never copied. A faulty `paths`
handle is refused before any transfer (see [above](#show)). Progress messages
label the variant:
`onshore_wind [test]: fetching 6 of 6 files (42.3 MB) into /path/to/cache`.

`--plan` and `--paths` choose what to report about the transfer and cannot be
combined.

### `--plan` { #plan }

What the fetch would do, without doing it. No dataset bytes are downloaded, but
resolving remote catalogue metadata can require network access. It shares its
parser and its resolution with the fetch it previews, so the two cannot drift.

```title="Output"
public cache:    /path/to/cache
used in place:      3 files      1.2 GB  (namespace link, never copied)
already cached:     4 files      9.9 MB
to download:        2 files     32.4 MB
    + reskit-test-data/era5/100m_u_component_of_wind.nc
    + reskit-test-data/era5/100m_v_component_of_wind.nc
not available here:    4 files                  (licensed-example -- a fetch stops here)
```

Presence is checked by size, which is cheap; a real fetch verifies the hash and
re-fetches anything that fails, so `--plan`'s "already cached" is an estimate,
not a promise.

Files expected in place but missing are reported separately, under `MISSING
from where they were expected`.

### `--paths` { #paths }

```bash
<tool>-data fetch onshore_wind --test --paths
<tool>-data fetch onshore_wind --paths
```

Fetch the collection as usual — on the collections file already
loaded, so the catalogue is read once — then print its `paths` handles resolved
to this machine: one `handle<TAB>absolute path` line per handle, tab-separated
so a shell can read it back (`while IFS=$'\t' read handle path`). A folder
handle prints the directory holding the collection's selected files under that
key. Data this machine cannot reach stops the command with an `AccessError`
before anything is downloaded. A collection that declares
no `paths` exits `2`. The Python equivalent is
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
| `--repair` | download again, into the public cache, the copies it owns that no longer match; never a link |
| `--dry-run` | with `--repair`: say what would be re-fetched, change nothing |
| `-q`, `--quiet` | only report problems |

Statuses, worst first: `dangling`, `wrong checksum`, `wrong size`, `missing`,
`unreadable`, `unavailable here`, `unverifiable`, `note`, `ok`.
`unverifiable` fails the check for a catalogue file whose record holds no
SHA-256, and only reports a staged file; `--repair` skips both. A `note` is
about a cache rather than a file and never fails the check: an entry the lookup
passed over in a restricted cache listed before the one it read, or a public
dataset's entry in a restricted cache. A broken link names its cache.

`--repair` never removes or replaces a link: a broken link, and a file read
through a link that does not match, are reported for whoever maintains the
link. It never touches restricted or staged data.

`--all` prints `skipped <name> [<variant>]: <reason>` for every collection or
variant it cannot resolve — a dataset this catalogue does not describe, an
incomplete catalogue copy, a faulty definition — and verifies the rest. It
exits `1` if anything was skipped, even when every checked file matches: the
check was not complete, and a CI job must not read it as one.

See [Check and repair the cache](../../how-to/data-users/verify-and-repair.md).

## Reaching past the collections {#keys}

A dataset, folder or file the package's collections do not name is
`ethos-data`'s to hand out — given the catalogue the package reads, the
answer is the same and lands in the same cache.

```bash
ethos-data ls
ethos-data ls reskit-test-data/era5
ethos-data fetch reskit-test-data/era5
```

## `staging`

Data that is not in the catalogue yet. See
[Stage uncatalogued data](../../how-to/package-maintainers/stage-development-data.md#stage-development-data).

```bash
<tool>-data staging add <name> <directory> [--note TEXT] [--copy]
<tool>-data staging list [--new-only]
<tool>-data staging remove <name> [--force]
```

| Flag | |
|---|---|
| `--note TEXT` | what this is, for the next person |
| `--copy` | copy the data instead of linking to it |
| `--new-only` | only datasets with no entry in the public or restricted cache |
| `--force` | on `remove`: required if the entry is a real directory, not a link |

Staging registrations use your configured staging root; they are not private to
the package that created them. They add to or shadow non-restricted datasets.
Registration/listing/removal works offline; fetching a collection with staged
data still needs a readable catalogue index. `staging list --new-only` compares
with local official caches, not with the remote catalogue.

Removing a link preserves its source. Removing a copied entry requires
`--force` and deletes that staged copy. Verification reports staged resources
as `unverifiable`; restricted datasets are never shadowed.

`add` writes a minimal `dataset.yaml` into the directory, with the name, `source_dir: .`
and the `--note` as its description, unless the directory has one already.
It is the start of the dataset's [proposal](../../how-to/package-maintainers/propose-a-dataset.md);
staging never reads it, and it is not one of the staged dataset's files.

A family member is staged under its full name, such as
`reskit-test-data/era5`, and shadows that member only. Its entry sits in a
folder named after the family, which `remove` deletes once it is empty. A
family and one of its members are never staged at the same time, and a name
with an empty, `.` or `..` segment is refused.

## `bundle`

A bundle is data a package keeps in its repository: the files of a selection
of catalogue datasets under `data/<dataset>/<path>`, each dataset's
description and licence documents under `datasets/<dataset>/`, and
`bundle.json`, which records each dataset's alignment with the catalogue,
whether it holds every file or a selection, the changes recorded since the
alignment, and every file's size and SHA-256. A bundle holds public, visible
data with settled licensing only; anything else is refused with `BundleError`.

```bash
<tool>-data bundle create tests/data-bundle --family your-tool-test-data
<tool>-data bundle update tests/data-bundle
<tool>-data bundle verify tests/data-bundle
<tool>-data bundle export ../other-tool/test_data test_suite --test
```

| Command/option | Behaviour |
|---|---|
| `create DIRECTORY [--family NAME]` | Start a bundle from the directories under `DIRECTORY/data/`, each a dataset; `--family NAME` makes the subdirectories of `data/NAME/` the members of a family. Hashes every file, drafts each dataset's `dataset.yaml`, and writes `bundle.json`. Refuses a bundle that exists. |
| `update DIRECTORY` | Record every changed, added and removed file, the descriptions and licence documents included, against each dataset's alignment, and every new dataset. With the catalogue readable, record the alignment of each dataset whose files, description and licence documents the catalogue holds as the bundle does. |
| `update --from-catalog DATASET...` | Take the catalogue's files of the bundled selection, with the description and licence documents, and record the alignment. |
| `export TARGET COLLECTION...` | Write a new bundle of what the package reads for the collections, through its handle: its bundles first, then the caches and the download, never staging. Each dataset keeps its description, licence documents and alignment; every file is checked as it is copied. Refuses an existing target. |
| `export --test` | The collections' test variants. |
| `verify DIRECTORY [DATASET_OR_KEY...]` | Report each file as `ok`, `modified`, `missing` or `unrecorded`, the descriptions and licence documents included, each dataset's alignment and state, and, with the catalogue readable, an aligned dataset the catalogue holds otherwise; exits 1 for any of these. |
| `fetch DIRECTORY [DATASET_OR_KEY...]` | Check hashes and report local paths; no network and no repair. |
| `fetch --allow-modified` | Read files changed without `bundle update`, with a warning naming them; the recorded hashes stay. A missing file fails all the same. |

A package's handle lists its bundles with `bundles=`, and reads go to them
first, after staging: see [Keep data in the repository](../../how-to/package-maintainers/keep-data-in-the-repository.md#use-a-bundle).
A bundle ahead of the catalogue is read with a `BundleAlignmentWarning`, once
per bundle and process. Invalid bundle inputs exit 2.

## `propose <directory>` {#propose}

Check a candidate dataset, the directory holding its draft `dataset.yaml`, or
a bundle, and print the proposal to submit.

```bash
<tool>-data propose /projects/shared/candidates/my-dataset
<tool>-data propose your_tool/data/test_data
```

A draft is checked as the catalogue's build would check it, and refused
where the build would refuse it; its bytes are inventoried and every file
still writable is named. For a bundle, the proposal covers the datasets that
are ahead of the catalogue, and a bundle that holds data it may not hold is
refused. The proposal names the dataset, its kind (new, a revision of a
catalogued dataset, or a successor), the bytes, the package's collections
that already name it, and the tracker to submit it to, by access class.

## `report [collection]` {#report}

Draft a problem report: run `ethos-data selftest`, `config show`, `show` and,
for a collection, `fetch <collection> --plan`, and print their output in the
report template, with tokens, credentials in URLs, the home directory and
the account name removed.

| Flag | |
|---|---|
| `--test` | the collection's test variant |
| `--no-selftest` | leave out the self-test's download |

## `config`

The wrapper exposes the same shared [configuration commands](../configuration.md)
as `ethos-data`. Settings apply across packages. `config show` reports shared
settings and origins; `show` prints the actual catalogue chosen by this wrapper.

## Exit status

`0` means success. `show` and `verify` return `1` for unresolved selections or
failed checks, and bundle verification returns `1` for modified/missing files.
Unknown collections/keys, inaccessible data and invalid collection or bundle
definitions return `2` with an error message. Staging refusals return `2`
without changing the refused entry.

Direct access outside a package uses [`ethos-data ls` and `fetch`](ethos-data.md).
