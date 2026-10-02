# `ethos-data catalog`

The catalogue-maintenance group of [`ethos-data`](ethos-data.md). It builds
metadata, generates the public view, uploads bytes, and keeps each dataset's
[`status.yaml`](../schemas.md#statusyaml). Check modes can be read-only;
`check-store` creates temporary remote objects.

Shared cache links are not in this group: one dataset or a whole catalogue,
they are [`ethos-data link`](ethos-data.md#link-dataset-directory). Building a
namespace is site administration on the machine that holds the data, not
catalogue maintenance, and having had it in both places only ever raised the
question of which one you were supposed to type.

```
ethos-data catalog [--catalog-root DIR] <command> ...
```

The catalogue to act on is found by searching **upward** from the current
directory for `catalog.yaml`, so these commands work from anywhere inside a
checkout. `--catalog-root` overrides that.

A catalogue is identified by its hand-written `catalog.yaml`. The generated
`datacatalog.json` is *not* a marker — a published catalogue has one too, and
must never be mistaken for a source one. Running these inside a published
catalogue gets an explicit refusal naming the source catalogue to use instead.

## `add <source>` {#add-source}

Take a reviewed draft into the catalogue and build it.

```bash
ethos-data catalog add /projects/shared/candidates/my-dataset --dry-run
ethos-data catalog add /projects/shared/candidates/my-dataset
ethos-data catalog add drafts/dataset.yaml --name my-dataset
```

`<source>` is the draft `dataset.yaml`, or the directory holding it. Three
stages, each planned before any acts, so `--dry-run` shows the whole plan and
a refusal comes before anything is written:

| Stage | |
|---|---|
| `intake` | read the draft and check it as the build would: a name, a `source_dir` that is a directory, licence documents that exist; a draft that says `ethos:uploaded` or `ethos:frozen` is refused |
| `place` | write `datasets/<name>/dataset.yaml`, the draft line by line without `source_dir`; copy its licence documents beside it; write its `status.yaml`: a draft built from `source_dir` |
| `build` | build it, which makes it `built` |

A relative `source_dir` is relative to the draft, and is recorded as the
absolute path it names, symbolic links left as they are. A dataset already in
the catalogue is refused, unless an earlier run placed this same draft and did
not build it: then only the build is left.

| Flag | |
|---|---|
| `--name NAME` | the dataset's name, for a draft that states none |
| `--dry-run` | check and plan; write nothing |

## `add-bundle <directory>` {#add-bundle}

Bring the catalogue's family up to a package's repository bundle.

```bash
ethos-data catalog add-bundle /checkout/your_tool/data/test_data --dry-run
ethos-data catalog add-bundle /checkout/your_tool/data/test_data
```

Compares the bundle with what the catalogue holds of its family and plans
one step for each difference, each planned before any is taken: the family's
description where it is new or changed; a member the catalogue lacks, added
and built from the bundle's draft as [`add`](#add-source) does; a changed
description, taken; a member not published yet whose files changed, rebuilt
from the bundle; a published member whose files changed, made its next
[revision](#build-datasets). The bundle's files are the build input. A
published file the bundle no longer has is refused unless `--remove-missing`
says it is meant; a member the bundle lacks is left as it is.

| Flag | |
|---|---|
| `--remove-missing` | let published files the bundle no longer has go, keys and all |
| `--dry-run` | compare and plan; write nothing |

## `build [datasets...]` {#build-datasets}

Regenerate `datapackage.json` (and `shards/*.json` for a sharded dataset)
from each `dataset.yaml`, plus the catalogue-wide `datacatalog.json`.

```bash
ethos-data catalog build my-dataset      # one
ethos-data catalog build                 # all
ethos-data catalog build --check         # CI: fail if any manifest is out of date
```

Walks `source_dir`, computes a SHA-256 per file, applies
`ethos:include`/`ethos:exclude`, pulls in shapefile companions, and excludes VCS
plumbing, `__pycache__` and root `README*`/`LICENSE*`/`CHANGELOG*`.

An `ethos:include` pattern matching nothing **fails**; an `ethos:exclude` pattern
matching nothing only warns. See
[Add a dataset](../../how-to/catalogue-maintainers/add-a-dataset.md#select-the-files).

The build reads `source_dir` from the dataset's `status.yaml` and records
there what it changed: a draft's first build makes it `built`, and an
inventory that differs from the one before is recorded as a change, which
returns an `available` dataset to `built` with a warning. A frozen dataset
keeps its inventory and re-derives the rest. A dataset without a status file
is built from `source_dir`, `ethos:uploaded` and `ethos:frozen` in its
`dataset.yaml`, with a warning naming [`migrate`](#migrate-datasets).

A sharded dataset built before the shard directory was renamed still has
`manifests/`. The build moves its shards to `shards/` and deletes the old
directory, and `--check` fails until that has happened.

A plain build refuses other bytes for a dataset whose bytes were uploaded or
materialized: published objects never change. `--revision` makes the next
revision of one such dataset from the corrected files, `--from DIR` or its
`source_dir`: it compares them with the recorded inventory, names what
changed, is new or is gone, and writes the inventory as the next revision,
each changed and new file published under `<remote_prefix>@<revision>/` and
each unchanged one kept where it is. A file that is gone is refused unless
`--remove-missing` says so. See
[Publish a new version](../../how-to/catalogue-maintainers/publish-a-new-version.md).

| Flag | |
|---|---|
| `--check` | report staleness and exit non-zero; write nothing |
| `--revision` | make the next revision of one dataset |
| `--from DIR` | with `--revision`: the corrected files (default: its `source_dir`) |
| `--remove-missing` | with `--revision`: let files that are gone go, keys and all |
| `--dry-run` | with `--revision`: compare and plan; write nothing |

## `publish <target>`

Generate the public catalogue from this source one, into a checkout of the
public repository.

```bash
ethos-data catalog publish ../ETHOS.Data-Catalogue
ethos-data catalog publish ../ETHOS.Data-Catalogue --check
```

Emits `datacatalog.json`, each public `datasets/<name>/datapackage.json` with
the keys the dataset.yaml format marks unpublished stripped (`source_dir`,
`ethos:embargo`, `ethos:license_note`, `ethos:uploaded`, `ethos:frozen`), and
the README table — for every dataset marked `ethos:visibility: public`.
Anything it no longer generates is deleted from the target.

Before it compares or writes anything, it checks the generated tree for a
leak: an unpublished key that is still there, or a withheld dataset named in
a descriptor, the index or the README. A leak exits non-zero with nothing
written, in both modes. Licence documents are copied verbatim and not searched.

!!! danger "It wipes everything in its target except `.git`"
    Point it only at the public repository. See
    [Release the catalogue](../../how-to/catalogue-maintainers/release-the-catalogue.md).

| Flag | |
|---|---|
| `--check` | fail if the target is out of date or the tree would leak; write nothing |

## `upload <dataset> [<dataset> ...]`

Put datasets' bytes on dCache, then verify them anonymously. Needs `rclone`
and `oidc-agent` on `PATH`.

```bash
ethos-data catalog upload my-dataset --dry-run
ethos-data catalog upload my-dataset
ethos-data catalog upload my-dataset --verify-only
```

Name one dataset, or any subset of the catalogue. A family name stands for every
member beneath it, since the family itself has no files. Each dataset is uploaded
and verified in turn, in the order given, and a run ends with a per-dataset summary:

```bash
ethos-data catalog upload global-wind-atlas-v4 global-solar-atlas
ethos-data catalog upload datasets/global-wind-atlas-v4   # a path works too
ethos-data catalog upload reskit-test-data                # a family: all 15 members
```

Every dataset named is loaded and checked **before any of them is uploaded**, so
a restricted dataset, an unbuilt manifest or a mistyped name stops the run while
nothing has been published yet. That is the difference from a shell loop, which
would upload the first dataset and only then discover the problem with the
second.

| Flag | Default | |
|---|---|---|
| `--dry-run` | | preview rclone transfers; may contact storage; do not combine with `--verify-only` |
| `--verify-only` | | skip transfer; public chmod still runs unless `--no-chmod` is supplied |
| `--allow-internal` | | permit internal data without public chmod; verification remains anonymous |
| `--no-chmod` | | do not set `0755` on the dataset prefix |
| `--transfers N` | `8` | parallel transfers |
| `--remote NAME` | `catalog.yaml`'s `ethos:store`, else `HIFIS` | rclone remote name |
| `--oidc-profile NAME` | `catalog.yaml`'s `ethos:store`, else `HIFIS` | oidc-agent profile |
| `--vo-path PATH` | `catalog.yaml`'s `ethos:store`, else `Helmholtz/FZJ-ICE2` | namespace path of the VO |
| `--root NAME` | last segment of `catalog.yaml`'s `ethos:publication_url` | publication root under the VO |

A dataset may be named by directory name or by path — a path must point into
the source catalogue's `datasets/`, so naming one in the *published* catalogue
is refused with the name to use instead.

The bytes go to `<root>/<ethos:remote_prefix>/` on the remote. A dataset that
declares no `ethos:remote_prefix` goes to the folder named after it, which is
where readers download it from.

Refuses `restricted` datasets outright and unresolved licensing for transfers
(`--verify-only` is allowed). It passes `rclone --immutable` to refuse detected
changes at existing paths. Keep published paths immutable regardless of what
the remote backend can compare. After
transferring it HEADs every file in the manifest with **no credentials** and
reports anything unreadable or the wrong size, plus the storage locality
(`ONLINE` / `ONLINE_AND_NEARLINE` / `NEARLINE`).

HEAD checks establish readability and size, not remote SHA-256 identity.
An internal upload can succeed in transfer yet fail anonymous verification.
`--allow-internal` does not establish private storage permissions or configure
authenticated consumer downloads.

The dataset's state must allow the step: a built dataset is uploaded, a frozen
one is refused and only rechecked with `--verify-only`. A verified upload, and
a recheck that passes, is recorded in the dataset's `status.yaml` as its copy
on dCache, which makes a built dataset `available`; [`record`](#record-dataset)
freezes it afterwards. A dataset without a status file is uploaded as before,
and a warning says nothing was recorded.

Use `--verify-only --no-chmod` to recheck without changing permissions.

With a single dataset the exit code is rclone's own on a transfer failure, or
`1` on a verification miss. With several it is `1` if any dataset failed, and
the summary says which.

Full runbook: [Upload a dataset](../../how-to/catalogue-maintainers/upload-a-dataset.md).

## `status [datasets...]` {#status-datasets}

Each dataset's state, access class and next step, from its `status.yaml`.

```bash
ethos-data catalog status                  # every dataset
ethos-data catalog status my-dataset       # one; a family lists its members
ethos-data catalog status --check          # and whether each record still holds
```

```text
  dataset          state      access      next
  era5             built      public      ethos-data catalog upload era5
  climate-inputs   available  internal    none while its source_dir stays; materialize it before that goes
  gadm-3.6         frozen     restricted  -
  old-dataset      -          public      ethos-data catalog migrate old-dataset
```

A dataset without a status file shows `-`, and one whose status file cannot be
read shows `?` with the reason. `--check` compares each record with the
evidence, one line per comparison:

- the `datapackage.json` the build would write, against the one there;
- a draft's `source_dir`;
- every recorded copy, file by file: an upload over anonymous HTTP, a cache
  entry on this machine, a link against the target it was recorded with;
- a copy on dCache of a dataset that is restricted now, an available dataset
  with no copy, and a frozen one whose authoritative copy was never recorded.

| Flag | |
|---|---|
| `--check` | compare each record with the evidence; exit `1` if one does not hold |

Exit `1` also when a status file cannot be read.

## `record <dataset>` {#record-dataset}

Freeze a dataset whose bytes are available: check a recorded copy file by file,
make it the authoritative copy, and retire `source_dir`. A rebuild afterwards
keeps the inventory as it is and re-derives only the metadata.

```bash
ethos-data catalog record my-dataset --dry-run
ethos-data catalog record my-dataset
ethos-data catalog record gadm-3.6 --copy /shared/ethos/restricted/gadm-3.6
```

Which copy, unless `--copy` names one: the upload, else the copy a cache owns,
else, for restricted data, the registered installation. A link to public or
internal data borrows the build input, which a rebuild still reads, and is the
authoritative copy only when named. A dataset that is not `available` is
refused, and one already frozen may have its authoritative copy changed to
another recorded copy.

| Flag | |
|---|---|
| `--copy LOCATION` | the recorded copy to make authoritative |
| `--dry-run` | check the copy; write nothing |

## `remove <datasets...>` {#remove-datasets}

Take datasets out of the catalogue, metadata first.

```bash
ethos-data catalog remove old-dataset --reason "accepted by mistake" --dry-run
ethos-data catalog remove old-dataset --reason "accepted by mistake"
```

Two stages: `withdraw` records every dataset named as `withdrawn`, with the
reason, and a family name stands for its members; `index` rebuilds the index,
and the families above them, without them. From then on the build, `publish`
and `link --all` leave a withdrawn dataset out, and a family whose members are
all withdrawn. Its description, inventory and status file stay in the
checkout, and its cache entries and bytes where they are, until a release
without it is out. Removing a withdrawn dataset again does nothing.

`--purge` is the second half, once a [release](#release-version) since the
removal is recorded in the dataset's status file:

| Stage | |
|---|---|
| `check` | every dataset named is withdrawn, a release since says it is gone, and no other dataset's copy on the store lies in its folder or around it |
| `cache` | unlink every link the status file records; delete every copy a cache owns |
| `store` | purge the dataset's folder on the store, which has no trash area, and check that it is no longer served |
| `tombstone` | delete the dataset's directory but its `status.yaml`, which records it `purged`, and a family left with no members; rebuild the index |

The tombstone keeps the name: `catalog add` refuses to give it to other bytes.

| Flag | |
|---|---|
| `--reason TEXT` | why, for the record in `status.yaml` |
| `--purge` | delete the cache entries, bytes and directory of datasets a release dropped |
| `--dry-run` | check and plan; write nothing |

## `check-source <dataset> <directory>` {#check-source}

Compare a fresh download from a downloaded dataset's source with its
recorded inventory, and record the result.

```bash
ethos-data catalog check-source global-wind-atlas-v4 /validation/gwa-v4 --dry-run
ethos-data catalog check-source global-wind-atlas-v4 /validation/gwa-v4 \
    --note "against the 2026-09 release on the provider's site"
```

Two stages: `compare` hashes every file under `<directory>` whose path the
inventory lists and compares its size and SHA-256 with the recorded ones;
`record` adds the result to the dataset's `status.yaml`, as a `check-source`
step: how many of the inventory's files were compared, how many match and
differ, and the note. A file the inventory does not list is named and not
compared, and a folder with nothing to compare is refused. Created and derived
datasets have no source and are refused.

| Flag | |
|---|---|
| `--note TEXT` | what was compared against, such as the source's release |
| `--dry-run` | compare; record nothing |

Exit `1` if a file differs.

## `release <version>` {#release-version}

Make a release of the checked source catalogue, the internal and the public
catalogue alike.

```bash
ethos-data catalog release v2026.10.1 --public ../ETHOS.Data-Catalogue --dry-run
ethos-data catalog release v2026.10.1 --public ../ETHOS.Data-Catalogue
ethos-data catalog release v2026.10.1 --public ../ETHOS.Data-Catalogue --push --upload
```

| Stage | |
|---|---|
| `check` | the version, `vYYYY.MM.N`, follows the catalogue's last release and has no tag; both checkouts are clean, and the public one is not a source catalogue; every manifest is current; every public dataset the public catalogue lists has a verified upload recorded; the public tree does not leak |
| `stamp` | write `version:` into `catalog.yaml` and the index; add a `release` step to the history of every dataset with steps since its last release |
| `commit` | commit the source checkout, `Release <version>`, and tag it |
| `public` | generate the public catalogue in its checkout, commit and tag it |
| `push` | with `--push`: push both checkouts and the tag to `--remote` |
| `store` | with `--upload`: put the public catalogue on the store under `<publication root>/catalogue/`, replacing the previous one, make it world-readable, and check that it is served |

Run again with the same version, it does only what is left: a stamp or a tag
that is there is not made again. A release made without `--push` and
`--upload` is finished by running it again with them, and so is one that was
interrupted.

| Flag | |
|---|---|
| `--public DIR` | the checkout of the public catalogue repository; required |
| `--push` | push both checkouts and the tag |
| `--upload` | put the public catalogue on the store |
| `--remote NAME` | the git remote to push to (default: `origin`) |
| `--dry-run` | check and plan; write nothing |

## `update-checkout` {#update-checkout}

Move the checkout readers are served, on the machine that serves it, to a
release.

```bash
ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout --dry-run
ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout
```

Three stages: `fetch` the remote's branches and tags, refusing a checkout
with changes nobody committed; `advance` to the latest release tag, or to
`--to`, by fast-forward only, checking that `catalog.yaml` then says that
release; `check` every manifest against its files, writing nothing. Nothing is
rebuilt in a served checkout.

| Flag | |
|---|---|
| `--to VERSION` | the release to move to (default: the latest tag) |
| `--remote NAME` | the git remote to fetch (default: `origin`) |
| `--dry-run` | plan; fetch and move nothing |

## `migrate [datasets...]` {#migrate-datasets}

Write each dataset's `status.yaml` from the keys its `dataset.yaml` held
before status files, and remove those keys.

```bash
ethos-data catalog migrate --dry-run
ethos-data catalog migrate
ethos-data catalog migrate my-dataset
```

| `dataset.yaml` says | `status.yaml` says |
|---|---|
| `source_dir`, never built | `draft`, with the `source_dir` |
| `source_dir`, built | `built`, with the `source_dir` |
| `ethos:uploaded: true` | `frozen`, its copy on dCache the authoritative one |
| `ethos:frozen: true` | `frozen`, where its authoritative copy is not recorded |

The keys are removed line by line, so every other line of `dataset.yaml`,
comments included, stays as it was; the result is read back and compared, and
a file that cannot be edited that way is left alone and reported, as is a
dataset whose keys the build would refuse. Nothing is checked against the
bytes: run `status --check` afterwards. A key left in `dataset.yaml` beside a
status file is removed when the two agree and reported when they do not.

| Flag | |
|---|---|
| `--dry-run` | show what would change; write nothing |

Exit `1` if a dataset was left alone.

## `check-store [vo]`

Probe what this account can do on dCache InfiniteSpace. Default VO:
`FZJ-ICE2`.

```bash
ethos-data catalog check-store FZJ-ICE2
```

Creates temporary remote files/directories and cleans up after itself. It
reports whether you can chmod at all (self-managed vs. root-owned "Simple"
model — the latter needs a HIFIS ticket) and whether permissions inherit to new
files.

It is a shell script by necessity: it reproduces exactly what a maintainer would
type against `curl` and `rclone`, so the commands it prints on failure are the
ones it actually ran. This is the one subcommand that does not need a catalogue
checkout.

## See also

- [Set up dCache access](../../how-to/catalogue-maintainers/set-up-dcache-access.md)
- [Create, rename, and delete folders](../../how-to/catalogue-maintainers/manage-dcache-folders.md) — uses
  rclone directly; there are no equivalent ETHOS.Data subcommands.

- [`ethos-data link --all`](ethos-data.md#link-dataset-directory) — build the shared
  cache as links to data already on this machine. It reads `source_dir` from the
  same source checkout these commands do.
- [Add a dataset](../../how-to/catalogue-maintainers/add-a-dataset.md)
- [Release the catalogue](../../how-to/catalogue-maintainers/release-the-catalogue.md)
- [Bootstrap a new catalogue](../../how-to/catalogue-maintainers/bootstrap-a-catalogue.md)
- [API: maintainer tooling](../api/maintain.md)


For the complete cluster migration, see [Link existing data into the cache](../../how-to/catalogue-maintainers/link-existing-data.md), which covers overrides, cache links and
[materialized copies](../../how-to/catalogue-maintainers/materialize-linked-data.md#materialize-copies) in one guide. Restricted entries are registered through [Add a dataset, restricted datasets](../../how-to/catalogue-maintainers/add-a-dataset.md#restricted-installations).
