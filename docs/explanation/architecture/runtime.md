# 6. Runtime View

This chapter answers how the building blocks of
[section 5](building-blocks.md) act together at runtime: how data users and
packages obtain and check their inputs (6.1–6.3), and how a dataset goes from
proposal to release, to a new version and to removal (6.4–6.8). Each step
names the command and the component that acts. Cluster examples use the layout
of [section 7.2](deployment.md#cluster), under `/shared/ethos/`; the ICE-2 wiki
holds the real paths.

## 6.1 Build a handle and fetch a collection

Which settings, which catalogue and which places decide where each file of a
collection is read.

<figure markdown="span">
  ![A handle reads the settings once and loads the collections file with its release bounds and the listed bundles, where a bundle ahead of the catalogue warns once when it is read; only when a dataset no bundle holds is first needed, or the download switch is on, does it choose the catalogue and check its release against the bounds (CatalogVersionError), and a fetch then selects files reading only the shards a pattern can match and asks the lookup chain's five locators where every file is read before any transfer. A refusal ends the call (AccessError for restricted data or a missing publication URL, BundleError for a missing file or an unrecorded change in a bundle), `fetch=False` raises NotFetched, and otherwise the Downloader fetches each revision folder anonymously from dCache into the public cache, never through a link, keeping only files whose hash matches.](../../assets/diagrams/architecture-fetch-light.svg#only-light){ .diagram }
  ![A handle reads the settings once and loads the collections file with its release bounds and the listed bundles, where a bundle ahead of the catalogue warns once when it is read; only when a dataset no bundle holds is first needed, or the download switch is on, does it choose the catalogue and check its release against the bounds (CatalogVersionError), and a fetch then selects files reading only the shards a pattern can match and asks the lookup chain's five locators where every file is read before any transfer. A refusal ends the call (AccessError for restricted data or a missing publication URL, BundleError for a missing file or an unrecorded change in a bundle), `fetch=False` raises NotFetched, and otherwise the Downloader fetches each revision folder anonymously from dCache into the public cache, never through a link, keeping only files whose hash matches.](../../assets/diagrams/architecture-fetch-dark.svg#only-dark){ .diagram }
</figure>

### Build the handle

A package calls `ethos_data.collections(COLLECTIONS_FILE, tool="your-tool",
bundles=BUNDLES)` once per process.

1. Settings (`config`) reads every setting once into a snapshot that records
   each value's source; `print(data.settings)` shows it.
2. The collections handle (`selection`) checks the collections file, and
   Bundles loads the listed bundles. A bundle that holds recorded changes, or
   a dataset the catalogue does not describe, is ahead of the catalogue:
   reading one of its datasets warns once per bundle, offline included,
   naming the datasets and how to realign them (6.3). Unless the download
   switch is on, a call that needs only bundled data reads no catalogue.
3. When a dataset no bundle holds is first needed, or the download switch is
   on, Settings chooses the catalogue; the first match wins: `--catalog` or `catalog=`; the package's
   `tool_main(catalog=)`; `ETHOS_DATA_CATALOG` or the `catalog` setting (on
   the cluster, the served checkout); the newest public release the bounds
   admit; without bounds, the public `main` index.
4. The catalogue reader (`catalogs`) reads only `datacatalog.json` and checks
   its version against the bounds (`CatalogVersionError`). The served
   checkout holds the latest release only, so the cluster refuses bounds that
   exclude it. The handle compares each bundled dataset's recorded revision
   with its index row: a later revision means the bundle is behind, which
   warns the same way. A bundled dataset with a recorded alignment that the
   index does not describe is withdrawn from the catalogue: the warning says
   to drop it from the bundle or switch to its successor.
5. The handle lays the bundles, then staging, over the catalogue view.

### Fetch

A workflow calls `data.paths("offshore_siting")` or `data.fetch(…)`;
`test=True` selects the small variant, which offers the same named paths.

1. The collections handle resolves the collection and checks its named paths;
   the inventory reader reads only the shards a pattern can match. A
   collection without the variant asked for, or with a named path that only
   one variant offers, raises `CollectionError` naming the collection and the
   variant or the named path. A dataset name the catalogue in use does not
   publish, mistyped or not, raises `UnknownDataset`: "the dataset 'era5-lnd'
   cannot be found. Maybe it was mistyped, or it is not published." No input
   is ever left out ([0013](decisions/0013-every-input-is-required.md)).
2. Retrieval (`retrieval`) asks the lookup chain (`access`) where each file is
   read. A refusal ends the call before any transfer: restricted data this
   account cannot read (`AccessError`, naming the dataset and how to obtain
   and register a copy), a bundled file that is missing or has a change
   `bundle update` has not recorded (`BundleError`), or a missing publication
   URL (`AccessError`). A file read in place must be present, or `AccessError`
   names it. With `fetch=False`, a file that would be downloaded raises
   `NotFetched`.
3. Retrieval downloads the rest through the Downloader port, per revision
   folder, into the public cache, never through a link; each file is
   hash-checked before it appears there. A failure raises `DownloadError`,
   naming the URL.
4. The call returns a `Path` for every key, or, from `paths()`, for every
   named path, or it raises.

### The lookup chain {#the-lookup-chain}

<figure markdown="span">
  ![Each file goes through five locators in order (staging, bundles, restricted caches, public cache, download), and the first that finds it decides where it is read: a staged entry or a listed bundle in place, restricted data in place from the first listed restricted cache with a readable entry, the public cache through a link in place or as a file of the recorded size, and otherwise a hash-checked download into the public cache, or NotFetched under `fetch=False`. A refusal ends the call before any transfer: BundleError for a bundled file that is missing or has an unrecorded change, and AccessError for restricted data without a readable entry (naming the dataset and how to obtain and register a copy) or for a missing publication URL. A file read in place must be there, so a broken link in the public cache refuses the read (AccessError) and verify reports it; plan and verify run the same chain in describe mode, where a refusal reads not available here, with its reason.](../../assets/diagrams/architecture-lookup-light.svg#only-light){ .diagram }
  ![Each file goes through five locators in order (staging, bundles, restricted caches, public cache, download), and the first that finds it decides where it is read: a staged entry or a listed bundle in place, restricted data in place from the first listed restricted cache with a readable entry, the public cache through a link in place or as a file of the recorded size, and otherwise a hash-checked download into the public cache, or NotFetched under `fetch=False`. A refusal ends the call before any transfer: BundleError for a bundled file that is missing or has an unrecorded change, and AccessError for restricted data without a readable entry (naming the dataset and how to obtain and register a copy) or for a missing publication URL. A file read in place must be there, so a broken link in the public cache refuses the read (AccessError) and verify reports it; plan and verify run the same chain in describe mode, where a refusal reads not available here, with its reason.](../../assets/diagrams/architecture-lookup-dark.svg#only-dark){ .diagram }
</figure>

The figure follows one file through the five locators (staging, bundles,
restricted caches, public cache, download);
[one lookup chain](decisions/0012-one-lookup-chain.md) gives what each
considers, where it finds a file and when it refuses. A cache entry is named
after the dataset, or `<name>@<r>` from revision 2 on.

On the cluster the public cache is shared: every cluster user sets it to one
directory on shared storage, for example `/shared/ethos/cache/`. Maintainers
link project storage into it and materialize copies there, and a fetch
downloads a missing public file into it once for everyone. A broken link in
it refuses the read until a maintainer repairs it (6.2).

`plan()`, `fetch --plan` and `verify` run the chain in describe mode, where a
refusal becomes "not available here", with its reason, and nothing is
downloaded; `verify` checks sizes, or SHA-256 with `--deep`, and reports a
broken link. `verify --repair` downloads a damaged copy again into the public
cache; it never removes or replaces a link, and never touches restricted or
staged data.

Decisions: [0010 Settings](decisions/0010-one-settings-file-per-account.md),
[0011 Access classes](decisions/0011-access-class-picks-the-root.md),
[0012 Lookup chain](decisions/0012-one-lookup-chain.md),
[0013 Required inputs](decisions/0013-every-input-is-required.md),
[0018 Releases](decisions/0018-numbered-catalogue-releases.md),
[0021 Bundles ahead of the catalogue](decisions/0021-bundles-ahead-of-the-catalogue.md),
[0028 Public cache on the cluster](decisions/0028-one-public-cache-on-the-cluster.md).

## 6.2 Self-test and problem report

How a user checks that a machine can obtain data, and hands a failure to the
maintainers with the facts attached.

`ethos-data selftest` (Self-test) runs the shipped example collection, public
data under 200 KB, through `settings`, `catalogue` and `files` (plan, fetch
and verify), stops at the first failure and exits 1 naming that step. On the
cluster the files are usually read in place from the cluster's public cache;
an empty `--root` forces a download.

A problem report:

1. `<tool>-data report <collection>` or `ethos-data report [key]`: Handoffs
   puts the self-test, `config show`, the package's collections and the plan
   into the report template, without tokens, credentials or personal paths.
2. The user posts it where it says: on JuGit for restricted data or from a
   cluster installation, on GitHub otherwise.
3. A catalogue maintainer reproduces it. The fix is a release, a revision
   (6.8), a repaired link in the cluster's public cache
   (`ethos-data link --force NAME DIR` or `ethos-data materialize NAME`, each
   with `--catalog-root <own clone>`), or `verify --repair`, which downloads a
   damaged copy again.

Decisions: [0017 Self-test](decisions/0017-self-test-collection.md),
[0025 Handoffs](decisions/0025-handoff-templates.md).

## 6.3 Package CI with bundles, and staging

How a package runs its tests without dCache, tests the download route, and
develops with data the catalogue does not describe yet. The handle lists the
package's bundles, and the collections file bounds the releases it accepts.

| CI job | Set-up | Inputs come from | It fails when |
|---|---|---|---|
| Required | network blocked; `pytest -m "not data_network"` | the bundles alone, hash-checked; no catalogue index is read | a bundled file is missing or has a change `bundle update` has not recorded, or an input is missing; an ahead bundle only warns |
| Live | `ETHOS_DATA_DIR` in the CI cache; optionally `ETHOS_DATA_CONFIG` | `ethos-data selftest`, then `fetch --plan`, `fetch` and `verify --deep` | the self-test, a download or a check fails |
| Download route | `ETHOS_DATA_DOWNLOAD=1 pytest -m data_network` | a bundled file whose SHA-256 the catalogue holds for the same key: the public cache or a download; every other bundled file: its bundle, with the warning | a download or a check fails; an ahead bundle only warns |

Restricted data needs a runner on the cluster computer whose settings list the
restricted caches it needs; its public cache is the cluster's or its own. A
bundle holds public data with settled licensing only, so licensed fixtures
belong in that restricted CI, not in a bundle.

A package's bundle is authoritative for that package, and may be ahead of the
catalogue: `<tool>-data bundle update DIR` records each change, and every
process that reads a dataset of an ahead bundle warns once per bundle, so the
required job shows it. The warning's category is exported from `ethos_data`,
so a package whose tests turn warnings into errors can keep it a warning. The
package maintainer realigns the bundle soon, in one of two ways:
`<tool>-data propose DIR` drafts the proposal for its ahead datasets (6.5), or
`bundle update DIR --from-catalog NAME` takes the catalogue's version of a
dataset.

To stage a dataset, `<tool>-data staging add NAME DIR [--copy]` (Staging)
links or copies it into the personal staging root, writing a missing
`dataset.yaml` as the start of a proposal. The staging locator reads it in
place, unchecked, with a warning, and never shadows restricted data. Data
whose licensing is unsettled is developed here, never in a bundle. Once the
proposal is accepted (6.5), `staging remove NAME`.

Decisions: [0020 Bundles](decisions/0020-repository-bundles.md),
[0021 Bundles ahead of the catalogue](decisions/0021-bundles-ahead-of-the-catalogue.md).

## 6.4 The dataset lifecycle {#dataset-lifecycle}

Which states a dataset of the source catalogue passes through, which command
moves it, and where each step is recorded.

<figure markdown="span">
  ![A dataset's lifecycle: add makes a draft; build makes it built; upload, verify, link or materialize make it available; record, with a verified freezable copy, freezes it; a change (of linked data only) or a revision returns it to built; remove withdraws it, and purge, only after a major release, deletes its bytes and keeps its status file. Each command checks its step against status.yaml and records it there; a release adds a step to every dataset that changed since the last release, and a major release also to every withdrawn dataset.](../../assets/diagrams/architecture-lifecycle-light.svg#only-light){ .diagram }
  ![A dataset's lifecycle: add makes a draft; build makes it built; upload, verify, link or materialize make it available; record, with a verified freezable copy, freezes it; a change (of linked data only) or a revision returns it to built; remove withdraws it, and purge, only after a major release, deletes its bytes and keeps its status file. Each command checks its step against status.yaml and records it there; a release adds a step to every dataset that changed since the last release, and a major release also to every withdrawn dataset.](../../assets/diagrams/architecture-lifecycle-dark.svg#only-dark){ .diagram }
</figure>

Each dataset's `status.yaml` holds its state, its build input `source_dir`
while there is one, its revision, its authority, the recorded copies and an
append-only history. Only commands write it, through the status recorder, in
the maintainer's own clone; it is never published. The states:

- `draft`: described, not built;
- `built`: inventory built from `source_dir`;
- `available`: the bytes are reachable for the access class: uploaded, linked
  or materialized;
- `frozen`: the inventory is final, backed by an authoritative copy, and
  `source_dir` is retired;
- `withdrawn`: out of the catalogue, with the bytes kept;
- `purged`: the bytes are deleted; `status.yaml` stays as a tombstone.

Every command checks its step with the lifecycle while it plans, and records
it after it acts; a step the state does not allow raises `TransitionError`,
naming what the dataset needs first. `link` and `materialize` take a step
only with `--catalog-root <own clone>`. A release changes no state; a major
release adds a release step to every withdrawn dataset, so the purge can see
it. The guards are part of the step: settled licensing
([0024](decisions/0024-licensing-gates-distribution.md)), the access class
([0011](decisions/0011-access-class-picks-the-root.md)), published bytes that
never change ([0019](decisions/0019-revisions-and-successors.md)), for a
release, a verified upload of each public dataset, and, for a purge, a major
release recorded after the removal. Each command is a
[pipeline](decisions/0023-maintenance-pipelines.md), and the maintainer
merges its records by merge request on JuGit.

Decisions: [0022 Status files](decisions/0022-dataset-status-files.md),
[0026 Internal catalogue](decisions/0026-internal-catalogue-on-the-cluster.md).

## 6.5 Accept and release a dataset

How a proposed dataset reaches its readers: who takes each step, where it
runs, and what it changes.

<figure markdown="span">
  ![From proposal to served release: the package maintainer runs propose and posts the proposal in an issue (on GitHub, or on JuGit for restricted data); the catalogue maintainer, in their own clone, adds the draft (or a bundle's ahead datasets with add-bundle), builds it, makes its bytes available by access class (public data: upload to dCache and, on the cluster, link or materialize into the cluster's public cache; restricted data: link the installation into a restricted cache), records it, and merges by merge request on JuGit. From the merged state, catalog release vX.Y.Z (the next patch, minor or major release) pushes both catalogues to GitHub and JuGit and syncs the public catalogue to dCache, catalog update-checkout fast-forwards the cluster's served checkout to that latest release, and after the answer in the issue the package maintainer raises catalog.min_version and realigns a bundle with bundle update.](../../assets/diagrams/architecture-accept-light.svg#only-light){ .diagram }
  ![From proposal to served release: the package maintainer runs propose and posts the proposal in an issue (on GitHub, or on JuGit for restricted data); the catalogue maintainer, in their own clone, adds the draft (or a bundle's ahead datasets with add-bundle), builds it, makes its bytes available by access class (public data: upload to dCache and, on the cluster, link or materialize into the cluster's public cache; restricted data: link the installation into a restricted cache), records it, and merges by merge request on JuGit. From the merged state, catalog release vX.Y.Z (the next patch, minor or major release) pushes both catalogues to GitHub and JuGit and syncs the public catalogue to dCache, catalog update-checkout fast-forwards the cluster's served checkout to that latest release, and after the answer in the issue the package maintainer raises catalog.min_version and realigns a bundle with bundle update.](../../assets/diagrams/architecture-accept-dark.svg#only-dark){ .diagram }
</figure>

The catalogue maintainer runs steps 2–5 and 7 in their own clone of the source
catalogue, in their own account on the cluster computer, where the build
inputs are readable, and runs each command first with `--dry-run`.

1. **Propose**, by the package maintainer: `<tool>-data propose DIR`
   (Handoffs) checks the draft, or a bundle's ahead datasets, as the build
   would, inventories the bytes and drafts the proposal for the tracker its
   access class names.
2. **Accept**, after review in the issue: `catalog add DRAFT` (Accept) checks
   the name, `source_dir` and the licence documents, writes `dataset.yaml` and
   `status.yaml`, and builds; a purged or existing name is refused. A bundle's
   ahead datasets go through `catalog add-bundle DIR [DATASET...]` (Bundle
   intake): it takes new datasets, revisions and changed descriptions, and
   copies the files into a build input the catalogue maintainers own, so the
   catalogue never reads a package checkout.
3. **Build.** `catalog build` (Inventory builder) hashes `source_dir` and
   writes `datapackage.json`, the shards and the index row.
4. **Make the bytes available**, by access class, each recording a copy:
    - public: `catalog upload NAME` (Uploader) checks the whole batch, copies
      without overwriting, makes the folder world-readable and reads every
      size back anonymously. On the cluster, `ethos-data link NAME DIR` or
      `ethos-data materialize NAME`, each with `--catalog-root <own clone>`,
      also puts the data into the cluster's public cache, where cluster users
      read it in place;
    - restricted: `ethos-data [--root <restricted cache>] link NAME DIR --catalog-root <own clone>`
      registers the installation by name in the restricted cache of its
      access combination; `catalog upload` refuses restricted data.

    The catalogue-wide form,
    `ethos-data link --all --root /shared/ethos/cache [--prune] --catalog-root <own clone>`,
    links public data only, and runs only from a clone at the merged state of
    the served release
    ([0028](decisions/0028-one-public-cache-on-the-cluster.md)).

5. **Record.** `catalog record NAME [--copy LOC]` (Freeze) checks the chosen
   copy file by file and makes it the authority: the dataset is `frozen`.
6. **Merge**, on JuGit: the maintainer reviews the diff, commits on a branch
   and merges by merge request.
7. **Release**, in the clone at the merged state, beside the public
   catalogue's checkout: `catalog release VERSION --public <checkout>`, then
   again with `--push --upload`. VERSION is the next patch, minor or major
   release at or above the level the changes since the last release require;
   `catalog status` and the dry run name the smallest admissible one.
   `--push` is the one direct push to the release branch; a merge that lands
   first makes it fail, and the release is rerun from the updated branch
   ([0026](decisions/0026-internal-catalogue-on-the-cluster.md)).
8. **Serve**, on the cluster computer while no jobs read the served checkout:
   `ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout`
   (Checkout updater) refuses local changes, fast-forwards to the newest
   release tag and runs `build --check`. The cluster then serves this release
   only.
9. **Answer.** The catalogue maintainer posts the drafted answers and announces
   the release on the ICE-2 wiki. The package maintainer raises
   `catalog.min_version` and runs `bundle update DIR` with the catalogue
   readable: it records the new alignment, and the ahead warning stops.

<figure markdown="span">
  ![catalog release VERSION plans every stage before any acts: its check computes the smallest level the changes since the last release require (patch for metadata only, minor for changed data) and refuses before any write unless VERSION is the next patch, minor or major release at or above that level, the release changes something, the build, publish and leak checks pass, every public dataset has a verified upload and both checkouts are clean; it then stamps the version and the release steps (in a major release also on every withdrawn dataset) into the maintainer's clone, commits and tags it, generates, commits and tags the public catalogue checkout, pushes both to GitHub and JuGit, syncs the public catalogue to dCache and drafts the notices, after which catalog update-checkout fast-forwards the cluster's served checkout, which holds the latest release only. Removal withdraws a dataset, a merge request and a later release leave it out, and once a major release is recorded after the removal, catalog remove --purge deletes its recorded entries in the cluster's public cache and the restricted caches and its dCache folders, and leaves a tombstone.](../../assets/diagrams/architecture-release-light.svg#only-light){ .diagram }
  ![catalog release VERSION plans every stage before any acts: its check computes the smallest level the changes since the last release require (patch for metadata only, minor for changed data) and refuses before any write unless VERSION is the next patch, minor or major release at or above that level, the release changes something, the build, publish and leak checks pass, every public dataset has a verified upload and both checkouts are clean; it then stamps the version and the release steps (in a major release also on every withdrawn dataset) into the maintainer's clone, commits and tags it, generates, commits and tags the public catalogue checkout, pushes both to GitHub and JuGit, syncs the public catalogue to dCache and drafts the notices, after which catalog update-checkout fast-forwards the cluster's served checkout, which holds the latest release only. Removal withdraws a dataset, a merge request and a later release leave it out, and once a major release is recorded after the removal, catalog remove --purge deletes its recorded entries in the cluster's public cache and the restricted caches and its dCache folders, and leaves a tombstone.](../../assets/diagrams/architecture-release-dark.svg#only-dark){ .diagram }
</figure>

The figure shows the release's stages, which
[maintenance pipelines](decisions/0023-maintenance-pipelines.md) lists. Its
`check` stage computes the smallest level the changes since the last release
require (a patch for metadata only, a minor release for changed data; no
change requires a major release), and refuses an unclean checkout, a version
that is not the next patch, minor or major release at or above that level, a
release that changes nothing, a stale build, a public dataset without a
verified upload, and a leak. It reads every non-frozen `source_dir`, so a
release runs on the cluster computer. A rerun does only what is left.

Decisions: [0018 Releases](decisions/0018-numbered-catalogue-releases.md),
[0027 Public catalogue](decisions/0027-public-catalogue-releases-on-github.md).

## 6.6 Remove and purge

How a dataset leaves the catalogues: metadata first, bytes last.

1. `catalog remove NAMES [--reason R]` (Removal), in the maintainer's own
   clone, withdraws the dataset from the index and drafts the removal notice.
   The description, the status file, the cache entries and the bytes stay.
2. Merge, then release (6.5, steps 6–8). Readers are served the dataset until
   that release. Older releases of the current major still describe it, so
   its bytes stay.
3. `catalog remove NAMES --purge`:
    - `check` requires a major release recorded after the removal, write
      access to every cache with a recorded entry of the dataset, and no
      other dataset's uploaded folder in or around this one;
    - `cache` deletes the recorded links and copies in the cluster's public
      cache and in the restricted caches. It refuses an entry that differs
      from its record, a recorded link that has become a real directory or a
      recorded copy that has become a link, so that a maintainer first finds
      out who made it. Unrecorded entries (downloads in the cluster's public
      cache, entries made without `--catalog-root`) are reported, not
      deleted. Public caches on other machines are not touched;
    - `store` purges every revision folder the store still holds, and reads
      back that it is gone;
    - `tombstone` deletes `datasets/<name>/` except `status.yaml` (`purged`).
4. Merge the tombstone. From then on, `catalog add` refuses the name.

Decisions: [0018 Releases](decisions/0018-numbered-catalogue-releases.md),
[0022 Status files](decisions/0022-dataset-status-files.md),
[0023 Pipelines](decisions/0023-maintenance-pipelines.md).

## 6.7 Check provenance

How a maintainer checks that a downloaded dataset still matches its source.

The catalogue maintainer downloads the originals again, or a sample, into the
validation folder, for example `/shared/ethos/validation/<dataset>/`. Then
`catalog check-source NAME DIR` (Provenance), in their own clone, hashes every
listed file under DIR, names those that differ or are not listed, records a
`check-source` step, and exits 1 on a difference. The maintainer merges the
step and acts on the outcome: a revision or a successor (6.8), a removal
(6.6), or a note that the source is gone.

## 6.8 Publish a new version: revision or successor

Published bytes never change. Changed bytes become a revision when the layout
stays, and a successor when it changes;
[revisions and successors](decisions/0019-revisions-and-successors.md)
compares the two and lists what each refuses.

- **Revision.** `catalog build NAME --revision [--from DIR] [--remove-missing]`
  (Revision) renders revision r+1 in memory, compares it with the clone's
  inventory and writes it. Bundled data changes in the package's bundle
  first: `bundle update` records the change, `<tool>-data propose` drafts it,
  and `catalog add-bundle` takes it in (6.5). The keys stay; changed and new
  files go under `<remote prefix>@<r+1>/` and into the entry
  `<dataset>@<r+1>/`. Then upload, record, merge and release, at least as a
  minor release. Each release describes the revision it was made with, so on
  a public installation a workflow bound to an older release of the current
  major reads that release's revision; the cluster serves the latest release
  only ([0026](decisions/0026-internal-catalogue-on-the-cluster.md)).
- **Successor.** A new dataset with `ethos:supersedes: <old>`, accepted as in
  6.5. The build marks the old dataset `ethos:superseded_by`, `ls` shows it
  superseded, and a collection that reads it warns. Collections move their
  named paths to the new keys.

Decisions:
[0019 Revisions and successors](decisions/0019-revisions-and-successors.md),
[0020 Bundles](decisions/0020-repository-bundles.md),
[0021 Bundles ahead of the catalogue](decisions/0021-bundles-ahead-of-the-catalogue.md).
