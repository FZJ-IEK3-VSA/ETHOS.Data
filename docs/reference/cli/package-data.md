# Package data commands

[`ethos_data.tool_main`][ethos_data.tool_main] and
[`Collections.main`][ethos_data.selection.Collections.main] provide the shared
CLI used by consuming packages. Replace `<tool>-data` below with the installed
command, for example `reskit-data`.

```text
<tool>-data [--catalog LOCATION] [--root DIR] [--skip-unavailable] [--test] COMMAND ...
```

The package ships and selects its own collections file. There is no CLI option
to substitute another file. See [Use ETHOS.Data in your package](../../how-to/use-from-a-package.md)
to expose the wrapper.

## Global options

| Option | Behaviour |
| --- | --- |
| `--catalog LOCATION` | Override the catalogue for this invocation. |
| `--root DIR` | Override the public cache for this invocation. |
| `--skip-unavailable` | Omit data this machine cannot access, with a warning; omitted inputs have no returned path. |
| `--test` | Select the collection's test variant; also accepted after collection subcommands. |
| `-h`, `--help` | Show help without loading the catalogue. |

Place global options before the subcommand, except `--test`, which works in
either position. A package may supply an environment override such as
`RESKIT_DATA_CATALOG`; it ranks below `--catalog` and above shared settings.
See [catalogue resolution](../configuration.md#catalogue-resolution).

`--help`, `config show`, staging management, and bundle reads do not load the
catalogue. Collection commands and catalogue-key commands need readable metadata.

## `--test` { #test }

`info`, `plan`, `fetch`, `paths` and `verify` take `--test` before or after the
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

## `list`

```bash
<tool>-data list
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
<tool>-data paths onshore_wind --test
<tool>-data paths onshore_wind
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

## `ls [key]` and `path <key>` {#keys}

`ls` lists catalogue datasets, or resources under an optional key, without
fetching data bytes. `path` fetches a file, folder, dataset or family and prints
its absolute local path. Both use the same catalogue as the package's collections.

```bash
reskit-data ls
reskit-data ls reskit-test-data/era5
reskit-data path reskit-test-data/era5
```

## `staging`

Data that is not in the catalogue yet. See
[Stage uncatalogued data](../../how-to/propose-a-dataset.md#stage-development-data).

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

Staging registrations use the shared staging root; they are not private to
the package that created them. They add to or shadow non-restricted datasets.
Registration/listing/removal works offline; fetching a collection with staged
data still needs a readable catalogue index. `staging list --new-only` compares
with local official caches, not with the remote catalogue.

Removing a link preserves its source. Removing a copied entry requires
`--force` and deletes that staged copy. Verification reports staged resources
as `unverifiable`; restricted datasets are never shadowed.

## `bundle`

A bundle is a repository copy of selected catalogue resources plus generated
metadata. dCache remains authoritative. Bundle reads use only local files and
never overwrite fixtures or fall back to downloads.

```bash
<tool>-data bundle export tests/data-bundle test_suite --source-revision v2026.09
<tool>-data bundle verify tests/data-bundle test_suite
<tool>-data bundle fetch tests/data-bundle test_suite
<tool>-data bundle fetch tests/data-bundle test_suite --allow-modified
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
The package's collections file and `--catalog` select inputs for export only. Invalid bundle inputs exit 2.
See [Keep test data in a repository](../../how-to/keep-test-data-in-a-repository.md).
## `config`

The wrapper exposes the same shared [configuration commands](../configuration.md)
as `ethos-data`. Settings apply across packages. `config show` reports shared
settings and origins; `list` prints the actual catalogue chosen by this wrapper.

## Exit status

`0` means success. `list` and `verify` return `1` for unresolved selections or
failed checks, and bundle verification returns `1` for modified/missing files.
Unknown collections/keys, inaccessible data and invalid collection or bundle
definitions return `2` with an error message. Staging refusals return a nonzero
status without changing the refused entry.

Direct access outside a package uses [`ethos-data ls` and `fetch`](ethos-data.md).
