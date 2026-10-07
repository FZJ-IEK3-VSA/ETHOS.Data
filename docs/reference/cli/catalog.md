# `ethos-data catalog`

The catalogue-maintenance group of [`ethos-data`](ethos-data.md). It builds
metadata, generates the public view, uploads bytes, and keeps each dataset's
[`status.yaml`](../schemas.md#statusyaml). Check modes can be read-only;
`check-store` creates temporary remote objects.

Cache links are not in this group: one dataset or a whole catalogue,
they are [`ethos-data link`](ethos-data.md#link-dataset-directory). Building a
namespace fills a public cache, in practice the cluster's public cache, which is
cache administration on the machine that holds the data, not catalogue
maintenance.

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
| `intake` | read the draft and check it as the build would: a name, a `source_dir` that is a directory, licence documents that exist |
| `place` | write `datasets/<name>/dataset.yaml`, the draft line by line without `source_dir`; copy its licence documents beside it; write its `status.yaml`: a draft built from `source_dir` |
| `build` | build it, which makes it `built` |

A relative `source_dir` is relative to the draft, and is recorded as the
absolute path it names, symbolic links left as they are. A dataset already in
the catalogue is refused, unless an earlier run with this same draft was
interrupted: the status file is written last, so a run that stopped inside
`place` places the draft again, and one that stopped before the build only
builds.

| Flag | |
|---|---|
| `--name NAME` | the dataset's name, for a draft that states none |
| `--dry-run` | check and plan; write nothing |

## `add-bundle <directory> [datasets...]` {#add-bundle}

Take a package's bundle's datasets that are ahead of the catalogue, or the
ones named, into your own clone.

```bash
ethos-data catalog add-bundle /checkout/your_tool/test_data --dry-run
ethos-data catalog add-bundle /checkout/your_tool/test_data
```

One stage, `update`, plans a step per dataset, each planned before any is
taken: a dataset the catalogue does not describe, added and built as
[`add`](#add-source) does from the bundle's description; a published dataset
whose files changed, made its next [revision](#build-datasets), only while the
catalogue is at the revision the bundle is aligned with; a dataset not
published yet whose files changed, built again; a changed description or
licence document, taken. The files are first copied into a build input the
catalogue maintainers own, `<into>/<dataset>` or
`<into>/<dataset>@<revision>`, each checked against `bundle.json`, so the
catalogue never reads a package checkout. `<into>` is `build-inputs/` in the
clone unless `--into` names another directory. That folder ignores itself in
git, and [`record`](#record-dataset) deletes a build input there once the
upload is the authoritative copy. `source_dir` is recorded as an absolute
path, so run `add-bundle` on the machine that uploads.

A bundled dataset is ahead only when `bundle.json` records a change for it,
or the catalogue does not describe it. A dataset the bundle records as aligned
is not taken, even when it is named. A change of access or visibility
that comes from a bundle is refused, as is a file gone from the bundle,
unless `--remove-missing` says it is meant. The families above the datasets
are built again last.

| Flag | |
|---|---|
| `--into DIR` | the directory of build inputs the catalogue maintainers own (default: `build-inputs/` in the clone) |
| `--remove-missing` | let files gone from the bundle go, keys and all |
| `--dry-run` | compare and plan; write nothing |

## `build [datasets...]` {#build-datasets}

Regenerate `datapackage.json` (and `shards/*.json` for a sharded dataset)
from each `dataset.yaml`, plus the catalogue-wide `datacatalog.json`.

```bash
ethos-data catalog build my-dataset      # one
ethos-data catalog build                 # all
ethos-data catalog build --dry-run       # what a build would write and record
ethos-data catalog build --check         # CI: fail if any manifest is out of date
```

Four stages, each planned before any acts: `check` reads `catalog.yaml` and
the state of every dataset named before anything is hashed; `render` renders
every generated file in memory; `write` writes the files that differ from the
ones on disk, and the index; `record` records what the build changed. A build
that changes nothing writes nothing.

`render` keeps each dataset's hashes in `.ethos-data-hash-cache.json` beside
its `dataset.yaml` as soon as they are computed, whether the dataset is then
rendered or refused. A dataset `render` refuses does not stop the others: the
build renders every one, then names each refused dataset and why, and writes
no descriptor, shard or index. The build after the fix hashes only the files
that changed since. `--check` and `--dry-run` keep the hashes in memory.

Walks `source_dir`, computes a SHA-256 per file, applies
`ethos:include`/`ethos:exclude`, pulls in shapefile companions, and excludes VCS
plumbing, `__pycache__` and root `README*`/`LICENSE*`/`CHANGELOG*`. A
`dataset.yaml` at the top of `source_dir` is never one of the dataset's files.

An `ethos:include` pattern matching nothing **fails**; an `ethos:exclude` pattern
matching nothing only warns. See
[Add a dataset](../../how-to/catalogue-maintainers/add-a-dataset.md#select-the-files).

The build reads `source_dir` from the dataset's `status.yaml` and records
there what it changed: a draft's first build makes it `built`, and an
inventory that differs from the one before is recorded as a change, which
returns an `available` dataset to `built` with a warning. A frozen dataset
keeps its inventory and re-derives the rest. A dataset without a status file,
or whose `dataset.yaml` states `source_dir` beside one, is refused, naming
[`migrate`](#migrate-datasets). Shards are read from and written to `shards/`
only.

A plain build refuses other bytes for a dataset whose bytes were uploaded or
materialized: published objects never change. `--revision` makes the next
revision of one such dataset from the corrected files, `--from DIR` or its
`source_dir`: it compares them with the recorded inventory, names what
changed, is new or is gone, and writes the inventory as the next revision,
each changed and new file published under `<remote_prefix>@<revision>/` and
each unchanged one kept where it is, in two stages, `compare` and `revise`.
A file that is gone is refused unless `--remove-missing` says so. The
revision has no authoritative copy until a copy of its bytes is recorded, and
a run interrupted after writing it records it when run again. A successor
built by name rebuilds the dataset it replaces too, which records
`ethos:superseded_by`. See
[Publish a new version](../../how-to/catalogue-maintainers/publish-a-new-version.md).

| Flag | |
|---|---|
| `--dry-run` | print the plan; write nothing |
| `--check` | report staleness and exit non-zero; write nothing |
| `--revision` | make the next revision of one dataset |
| `--from DIR` | with `--revision`: the corrected files (default: its `source_dir`) |
| `--remove-missing` | with `--revision`: let files that are gone go, keys and all |

## `publish <target>`

Generate the public catalogue from this source one, into a checkout of the
public repository.

```bash
ethos-data catalog publish ../ETHOS.Data-Catalogue --dry-run
ethos-data catalog publish ../ETHOS.Data-Catalogue
ethos-data catalog publish ../ETHOS.Data-Catalogue --check
```

Three stages: `render` renders the public tree in memory, `check` runs the
leak check below, and `write` writes the files that differ and removes the
files the target holds that are not generated.

Emits `datacatalog.json`, each public `datasets/<name>/datapackage.json` with
the keys the dataset.yaml format marks unpublished stripped (`source_dir`,
`ethos:embargo`, `ethos:license_note`), and
the README table — for every dataset marked `ethos:visibility: public`.
Anything in the target that it does not generate is deleted, so `publish` refuses a target that holds a `catalog.yaml`, a source checkout.

Before it compares or writes anything, it checks the generated tree for a
leak: an unpublished key that is still there, or a withheld dataset named in
a descriptor, the index or the README. A leak exits non-zero with nothing
written, in both modes. Licence documents are copied verbatim and not searched.

!!! danger "It wipes everything in its target except `.git`"
    Point it only at the public repository. See
    [Release the catalogue](../../how-to/catalogue-maintainers/release-the-catalogue.md).

| Flag | |
|---|---|
| `--dry-run` | print the plan: the files it would write and remove; write nothing |
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
member beneath it, since the family itself has no files, so naming a bundle's
family uploads what `add-bundle` took in: a member frozen or withdrawn already
is passed over with a line saying so, and with `--verify-only` only a
withdrawn one. A dataset named itself is checked all the same. Five stages, each
planned before any acts, handle the datasets in the order given: `check`,
`transfer`, `permissions`, `verify` and `record`. A run of several ends with a
per-dataset summary:

```bash
ethos-data catalog upload global-wind-atlas-v4 global-solar-atlas
ethos-data catalog upload datasets/global-wind-atlas-v4   # a path works too
ethos-data catalog upload reskit-test-data                # a family: all 15 members
```

Every dataset named is loaded and checked **before any of them is uploaded**, so
a restricted dataset, an unbuilt manifest or a mistyped name stops the run while
nothing has been published yet. That is the difference from a shell loop, which
would upload the first dataset and only then discover the problem with the
second. A dataset that fails later, in its transfer or its read-back, does not
stop the others, and what was uploaded stays. A dataset whose upload of its
current inventory is verified and recorded is not uploaded again, so running
the command again finishes the batch.

| Flag | Default | |
|---|---|---|
| `--dry-run` | | print the plan; contact no store |
| `--verify-only` | | skip the transfer; the chmod runs unless `--no-chmod` is given too |
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

The dataset's state must allow the step: a built dataset is uploaded, a frozen
one is refused and only rechecked with `--verify-only`. A verified upload, and
a recheck that passes, is recorded in the dataset's `status.yaml` as its copy
on dCache, which makes a built dataset `available`; [`record`](#record-dataset)
freezes it afterwards. A dataset without a status file is refused, naming
[`migrate`](#migrate-datasets). The guards of the step refuse restricted data
and unresolved licensing with `TransitionError`.

Use `--verify-only --no-chmod` to recheck without changing permissions.

The exit code is `1` if any dataset failed; with several, the summary says
which.

Full runbook: [Upload a dataset](../../how-to/catalogue-maintainers/upload-a-dataset.md).

## `status [datasets...]` {#status-datasets}

Each dataset's state, access class and next step, from its `status.yaml`.

```bash
ethos-data catalog status                  # every dataset
ethos-data catalog status my-dataset       # one; a family lists its members
ethos-data catalog status --check          # and whether each record still holds
```

```text
  dataset          state      access      release          next
  era5             built      public      -                ethos-data catalog upload era5
  climate-inputs   available  public      v1.2.0           none while its source_dir stays; materialize it before that goes
  gadm-3.6         frozen     restricted  v1.2.0           -
  old-dataset      -          public      -                ethos-data catalog migrate old-dataset
```

The name column is at most 40 characters wide; a longer name pushes the rest
of its own row to the right. A dataset without a status file shows `-` and
names [`migrate`](#migrate-datasets), and one whose status file cannot be read
shows `?` with the reason; either fails the command.

`--check` adds a `check` column: `ok` when every comparison holds, `FAIL` when
one does not. Under the row it lists each comparison that does not hold, and
each warning the comparison raised:

```text
  dataset          state      access      release          check next
  era5             built      public      -                ok    ethos-data catalog upload era5
  gebco-2025       built      public      -                ok    ethos-data catalog upload gebco-2025
      warning: gebco-2025: ethos:exclude pattern '**/__init__.py' matches nothing under /data/gebco-2025 -- already cleaned up, or a typo?
  trep-db          built      public      -                FAIL  ethos-data catalog upload trep-db
      FAIL  datapackage.json is out of date: ethos-data catalog build trep-db
```

It compares the record with the evidence:

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

## `record <datasets...>` {#record-dataset}

Freeze datasets whose bytes are available: check a recorded copy of each file
by file, make it the authoritative copy, and retire `source_dir`. Every
dataset named is checked before any is frozen. A family name stands for its
members, those frozen or withdrawn already passed over. A rebuild afterwards
keeps the inventory as it is and re-derives only the metadata. A retired
`source_dir` in the clone's `build-inputs/`, where
[`add-bundle`](#add-bundle) copies a bundle's files, is deleted, and the
folders it leaves empty with it, unless a cache link still points into it.

```bash
ethos-data catalog record my-dataset --dry-run
ethos-data catalog record my-dataset
ethos-data catalog record reskit-test-data
ethos-data catalog record gadm-3.6 --copy /shared/ethos/restricted/gadm-3.6
```

Which copy, unless `--copy` names one: the upload, else the copy a cache owns,
else, for restricted data, the registered installation, a link in a
restricted cache. A link to public data borrows the build input, which every
rebuild reads, and is the authoritative copy only when named with `--copy`. A
dataset that is not `available` is refused, and one already frozen may have
its authoritative copy changed to another recorded copy.

| Flag | |
|---|---|
| `--copy LOCATION` | the recorded copy to make authoritative, of one dataset |
| `--dry-run` | check the copy; write nothing |

## `remove <datasets...>` {#remove-datasets}

Take datasets out of the catalogue, metadata first.

```bash
ethos-data catalog remove old-dataset --reason "accepted by mistake" --dry-run
ethos-data catalog remove old-dataset --reason "accepted by mistake"
```

Three stages: `withdraw` records every dataset named as `withdrawn`, with
the reason, and a family name stands for its members; `index` rebuilds the
index, and the families above them, without them; `notices` drafts the
removal notice of each dataset withdrawn, for the packages that read it: the
reason, the last release that describes it, its replacement, and that its
bytes stay until a major release is recorded after the removal. From then on the build, `publish`
and `link --all` leave a withdrawn dataset out, and a family whose members are
all withdrawn. Its description, inventory and status file stay in the
checkout, and its cache entries and bytes where they are, until a major
release is recorded after the removal. Removing a withdrawn dataset again does
nothing.

`--purge` is the second half, once a major [release](#release-version) is
recorded after the removal in the dataset's status file:

| Stage | |
|---|---|
| `check` | every dataset named is withdrawn; a major release is recorded after its removal; no other dataset's copy on the store lies in its folder or around it; this account can write every cache that holds a recorded entry, else the cache is named and nothing is deleted. Entries in the account's public cache and restricted caches that no copy records are reported, not deleted |
| `cache` | unlink every link the status file records; delete every copy a cache owns |
| `store` | purge the dataset's folder on the store, which has no trash area, unless it holds nothing any more, and check that it is not served afterwards |
| `tombstone` | delete the dataset's directory but its `status.yaml`, which records it `purged`, and a family left with no members; rebuild the index |

The tombstone keeps the name: `catalog add` refuses to give it to other bytes.
A purge interrupted half-way finishes when it is run again.

| Flag | |
|---|---|
| `--reason TEXT` | why, for the record in `status.yaml` |
| `--purge` | delete the cache entries, bytes and directory of withdrawn datasets, after a major release |
| `--notices DIR` | also write the removal notices into this directory, `removal-<dataset>.md` each |
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
ethos-data catalog release v1.3.0 --public ../ETHOS.Data-Catalogue --dry-run
ethos-data catalog release v1.3.0 --public ../ETHOS.Data-Catalogue
ethos-data catalog release v1.3.0 --public ../ETHOS.Data-Catalogue --push --upload
```

| Stage | |
|---|---|
| `check` | the version is admissible and has no tag; both checkouts are clean, and the public one is not a source catalogue; every manifest is current; every public dataset the public catalogue lists has an upload verified after its last inventory change; the public tree does not leak |
| `stamp` | write `version:` into `catalog.yaml` and the index; add a `release` step to the history of every dataset with steps since its last release, and, in a major release, of every withdrawn dataset |
| `commit` | commit the source checkout, `Release <version>`, and tag it |
| `public` | generate the public catalogue in its checkout, commit and tag it |
| `push` | with `--push`: push both checkouts and the tag to `--remote` |
| `store` | with `--upload`: put the public catalogue on the store under `<publication root>/catalogue/`, replacing the previous one, make it world-readable, and check that it is served |
| `notices` | draft the release notice, the datasets added, revised, superseded and withdrawn, and the answer to every proposal the release accepts; printed, and written into `--notices DIR` |

The version is `vMAJOR.MINOR.PATCH`. The first release is `v1.0.0`; every
later one is the next patch, minor or major of the last release, at or above
the smallest level the changes since need. The `check` stage works that level
out and names the smallest admissible version, `catalog status` too:

| Changes since the last release | Level |
|---|---|
| A step recorded in a status file that adds, builds, changes or withdraws a dataset | minor |
| A dataset that enters or leaves the internal or the public catalogue, or whose row changes its access class, visibility, size, file count or remote prefix | minor |
| Any other change of an index row, and any file of the clone that differs from the last release's tag, status files aside | patch |

A patch or minor release that changes nothing is refused. A major release is
a retention epoch: it needs no change, and the purge of a withdrawn dataset
waits for one.

Run again with the same version, it does only what is left: a stamp, a
release step or a tag that is there is not made again. A release made without `--push` and
`--upload` is finished by running it again with them, and so is one that was
interrupted.

| Flag | |
|---|---|
| `--public DIR` | the checkout of the public catalogue repository; required |
| `--push` | push both checkouts and the tag |
| `--upload` | put the public catalogue on the store |
| `--remote NAME` | the git remote to push to (default: `origin`) |
| `--notices DIR` | also write the notice and the answers into this directory |
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
rebuilt in a served checkout. The check hashes the files of every dataset that
is not frozen, so freezing datasets with [`record`](#record-dataset) keeps it
short.

| Flag | |
|---|---|
| `--to VERSION` | the release to move to, `v1.2.0` (default: the latest release tag) |
| `--remote NAME` | the git remote to fetch (default: `origin`) |
| `--dry-run` | plan; fetch and move nothing |

## `migrate [datasets...]` {#migrate-datasets}

The one converter of the clean break: write each dataset's `status.yaml`
from `source_dir`, `ethos:uploaded` and `ethos:frozen` in its `dataset.yaml`,
remove those keys, and move a dataset's shards from `manifests/` to `shards/`.

```bash
ethos-data catalog migrate --dry-run
ethos-data catalog migrate
ethos-data catalog migrate my-dataset
```

| `dataset.yaml` says | `status.yaml` says |
|---|---|
| `source_dir`, never built | `draft`, with the `source_dir` as an absolute path |
| `source_dir`, built | `built`, with the `source_dir` as an absolute path |
| `ethos:uploaded: true` | `frozen`, its copy on dCache the authoritative one |
| `ethos:frozen: true` | `frozen`, where its authoritative copy is not recorded |

The keys are removed line by line, so every other line of `dataset.yaml`,
comments included, stays as it was; the result is read back and compared, and
a file that cannot be edited that way is left alone and reported, as is a
dataset whose keys contradict each other. Nothing is checked against the
bytes: run `status --check` afterwards. A key left in `dataset.yaml` beside a
status file is removed when the two agree and reported when they do not.

| Flag | |
|---|---|
| `--dry-run` | show what would change; write nothing |

Exit `1` if a dataset was left alone.

## `check-store [vo]`

Probe what this account can do on dCache InfiniteSpace. Inside a catalogue
checkout it probes the store `catalog.yaml` names under
[`ethos:store`](../schemas.md#catalogyaml); elsewhere, or for another VO
named, the VO `FZJ-ICE2` by default.

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

- [`ethos-data link --all`](ethos-data.md#link-dataset-directory) — build a public
  cache as links to data already on this machine. It reads `source_dir` from the
  same source checkout these commands do.
- [Add a dataset](../../how-to/catalogue-maintainers/add-a-dataset.md)
- [Release the catalogue](../../how-to/catalogue-maintainers/release-the-catalogue.md)
- [Bootstrap a new catalogue](../../how-to/catalogue-maintainers/bootstrap-a-catalogue.md)
- [API: maintainer tooling](../api/maintain.md)


To make data already on the cluster computer available through its caches, see [Link existing data into the cache](../../how-to/catalogue-maintainers/link-existing-data.md), which covers cache links and
[materialized copies](../../how-to/catalogue-maintainers/materialize-linked-data.md#materialize-copies) in one guide. Restricted entries are registered through [Add a dataset, restricted datasets](../../how-to/catalogue-maintainers/add-a-dataset.md#restricted-installations).
