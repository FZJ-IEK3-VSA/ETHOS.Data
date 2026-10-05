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
  ![A handle reads the settings once and chooses the catalogue within the release bounds; selection reads only the shards it needs; every file goes through the lookup chain before any download; a refusal stops the call.](../../assets/diagrams/architecture-fetch-light.svg#only-light){ .diagram }
  ![A handle reads the settings once and chooses the catalogue within the release bounds; selection reads only the shards it needs; every file goes through the lookup chain before any download; a refusal stops the call.](../../assets/diagrams/architecture-fetch-dark.svg#only-dark){ .diagram }
</figure>

### Build the handle

A package calls `ethos_data.collections(COLLECTIONS_FILE, tool="your-tool",
bundles=BUNDLES)` once per process.

1. Settings (`config`) reads every setting once into a snapshot that records
   each value's source; `print(data.settings)` shows it.
2. The collections handle (`selection`) checks the collections file, and
   Bundles loads the listed bundles. Unless the download switch is on, a call
   that needs only bundled data reads no catalogue.
3. When a dataset no bundle holds is first needed, Settings chooses the
   catalogue; the first match wins: `--catalog` or `catalog=`; the package's
   `tool_main(catalog=)`; `ETHOS_DATA_CATALOG` or the `catalog` setting (on
   the cluster, the served checkout); the newest public release the bounds
   admit; without bounds, the public `main` index.
4. The catalogue reader (`catalogs`) reads only `datacatalog.json` and checks
   its version, and each bundle's release, against the bounds
   (`CatalogVersionError`). The served checkout holds the latest internal
   release only, so the cluster refuses bounds that exclude it.
5. The handle lays the bundles, then staging, over the catalogue view.

### Fetch

A workflow calls `data.paths("offshore_siting")` or `data.fetch(…)`;
`test=True` selects the small variant, which offers the same named paths.

1. The collections handle resolves the collection and checks its named paths;
   the inventory reader reads only the shards a pattern can match.
2. Retrieval (`retrieval`) asks the lookup chain (`access`) where each file is
   read. A refusal ends the call before any transfer; a file read in place
   must be present, or `AccessError` lists it. With `fetch=False`, a file that
   would be downloaded raises `NotFetched`.
3. Retrieval downloads the rest through the Downloader port, per revision
   folder, into the user's own public cache, never through a link or into the
   shared cache. A failure raises `DownloadError`, naming the URL.
4. The call returns a `Path` for every key, or, from `paths()`, for every
   named path, or it raises.

### The lookup chain {#the-lookup-chain}

<figure markdown="span">
  ![Where one file is read: dataset root, staging, bundles, restricted cache, shared cache, public-cache link, public-cache copy, download.](../../assets/diagrams/architecture-lookup-light.svg#only-light){ .diagram }
  ![Where one file is read: dataset root, staging, bundles, restricted cache, shared cache, public-cache link, public-cache copy, download.](../../assets/diagrams/architecture-lookup-dark.svg#only-dark){ .diagram }
</figure>

The figure follows one file through the eight locators;
[one lookup chain](decisions/0012-one-lookup-chain.md) gives what each
considers, where it finds a file and when it refuses. A cache entry is named
after the dataset, or `<name>@<r>` from revision 2 on.

On the cluster, the shared cache serves what maintainers put there, and only
the public files it lacks reach the user's own cache. A broken shared entry
passes, so its public files are downloaded and its internal files refused
until a maintainer repairs it.

`plan()`, `fetch --plan` and `verify` run the chain in describe mode, where a
refusal becomes "not available here" and nothing is downloaded; `verify`
checks sizes, or SHA-256 with `--deep`, and reports a shared-cache entry that
lacks a file. `verify --repair` downloads public data again into the user's
own public cache only, replacing a link there with an owned copy
(`--dry-run` lists the links).

Decisions: [0010 Settings](decisions/0010-one-settings-file-per-account.md),
[0011 Access classes](decisions/0011-access-class-picks-the-root.md),
[0012 Lookup chain](decisions/0012-one-lookup-chain.md),
[0013 Required inputs](decisions/0013-every-input-is-required.md),
[0018 Releases](decisions/0018-numbered-catalogue-releases.md),
[0028 Shared cache](decisions/0028-read-only-shared-cache.md).

## 6.2 Self-test and problem report

How a user checks that a machine can obtain data, and hands a failure to the
maintainers with the facts attached.

`ethos-data selftest` (Self-test) runs the shipped example collection, public
data under 200 KB, through `settings`, `catalogue` and `files` (plan, fetch
and verify), stops at the first failure and exits 1 naming that step. On the
cluster the files are usually read from the shared cache; an empty `--root`
forces a download.

A problem report:

1. `<tool>-data report <collection>` or `ethos-data report [key]`: Handoffs
   puts the self-test, `config show`, the package's collections and the plan
   into the report template, without tokens, credentials or personal paths.
2. The user posts it where it says: JuGit for internal or restricted data, a
   cluster installation or a broken shared-cache entry; GitHub otherwise.
3. A catalogue maintainer reproduces it. The fix is a release, a revision
   (6.8), a repaired shared entry
   (`ethos-data --root <shared cache> link --force NAME DIR` or
   `ethos-data --root <shared cache> materialize NAME`, each with
   `--catalog-root <own clone>`), or `verify --repair` in the reporter's own
   cache.

Decisions: [0017 Self-test](decisions/0017-self-test-collection.md),
[0025 Handoffs](decisions/0025-handoff-templates.md).

## 6.3 Package CI with repository bundles, and staging

How a package runs its tests without dCache, tests the download route, and
develops with data the catalogue does not describe yet. The handle lists the
package's bundles, and the collections file bounds the releases it accepts.

| CI job | Set-up | Inputs come from | It fails when |
|---|---|---|---|
| Required | network blocked; `pytest -m "not data_network"` | the bundles alone, hash-checked; no catalogue index is read | a bundled file is missing or changed, or an input is missing |
| Live | `ETHOS_DATA_DIR` in the CI cache; optionally `ETHOS_DATA_CONFIG` | `ethos-data selftest`, then `fetch --plan`, `fetch` and `verify --deep` | the self-test, a download or a check fails |
| Download route | `ETHOS_DATA_DOWNLOAD=1 pytest -m data_network` | the catalogue's copies; the bundles are loaded, not laid over | a collection reaches a bundle version no release holds (`BundleError`) |

Internal and restricted data need a runner on the cluster computer with the
shared cache and the restricted cache configured.

A repository bundle is the source of truth for its next, unpublished version:
`bundle update` records each change, and reading a version no release holds
warns.

To stage a dataset, `<tool>-data staging add NAME DIR [--copy]` (Staging)
links or copies it into the personal staging root, writing a missing
`dataset.yaml` as the start of a proposal. The staging locator reads it in
place, unchecked, with a warning, and never shadows restricted data. Once the
proposal is accepted (6.5), `staging remove NAME`.

Decisions: [0020 Repository bundles](decisions/0020-repository-bundles.md),
[0021 Bundle versions](decisions/0021-one-bundle-version-per-release.md).

## 6.4 The dataset lifecycle {#dataset-lifecycle}

Which states a dataset of the source catalogue passes through, which command
moves it, and where each step is recorded.

<figure markdown="span">
  ![A dataset's lifecycle: add makes a draft; build makes it built; upload, link or materialize make it available; record freezes it; a change or a revision returns it to built; remove withdraws it, and purge, after a release, deletes its bytes and keeps its status file.](../../assets/diagrams/architecture-lifecycle-light.svg#only-light){ .diagram }
  ![A dataset's lifecycle: add makes a draft; build makes it built; upload, link or materialize make it available; record freezes it; a change or a revision returns it to built; remove withdraws it, and purge, after a release, deletes its bytes and keeps its status file.](../../assets/diagrams/architecture-lifecycle-dark.svg#only-dark){ .diagram }
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
only with `--catalog-root <own clone>`, and a release changes no state. The
guards are part of the step: settled licensing
([0024](decisions/0024-licensing-gates-distribution.md)), the access class
([0011](decisions/0011-access-class-picks-the-root.md)), published bytes that
never change ([0019](decisions/0019-revisions-and-successors.md)), and, for a
release, a verified upload of each public dataset. Each command is a
[pipeline](decisions/0023-maintenance-pipelines.md), and the maintainer
merges its records by merge request on JuGit.

Decisions: [0022 Status files](decisions/0022-dataset-status-files.md),
[0026 Internal catalogue](decisions/0026-internal-catalogue-on-the-cluster.md).

## 6.5 Accept and release a dataset

How a proposed dataset reaches its readers: who takes each step, where it
runs, and what it changes.

<figure markdown="span">
  ![From proposal to served release: the package maintainer runs propose and posts the proposal in an issue (on GitHub, or on JuGit for internal or restricted data); the catalogue maintainer, in their own clone, adds and builds the dataset, makes its bytes available by access class (upload to dCache for public data, link or materialize into the cluster's shared cache for internal or linked data, link a restricted installation into the restricted cache), records it, and commits on a branch for a merge request on JuGit. From the merged state, catalog release pushes both catalogues to GitHub and JuGit and syncs the public catalogue to dCache; catalog update-checkout then fast-forwards the cluster's served checkout to that latest release, and the answer is posted in the proposal's issue.](../../assets/diagrams/architecture-accept-light.svg#only-light){ .diagram }
  ![From proposal to served release: the package maintainer runs propose and posts the proposal in an issue (on GitHub, or on JuGit for internal or restricted data); the catalogue maintainer, in their own clone, adds and builds the dataset, makes its bytes available by access class (upload to dCache for public data, link or materialize into the cluster's shared cache for internal or linked data, link a restricted installation into the restricted cache), records it, and commits on a branch for a merge request on JuGit. From the merged state, catalog release pushes both catalogues to GitHub and JuGit and syncs the public catalogue to dCache; catalog update-checkout then fast-forwards the cluster's served checkout to that latest release, and the answer is posted in the proposal's issue.](../../assets/diagrams/architecture-accept-dark.svg#only-dark){ .diagram }
</figure>

The catalogue maintainer runs steps 2–5 and 7 in their own clone of the source
catalogue, in their own account on the cluster computer, where the build
inputs are readable, and runs each command first with `--dry-run`.

1. **Propose**, by the package maintainer: `<tool>-data propose DIR`
   (Handoffs) checks the draft as the build would, inventories the bytes and
   drafts the proposal for the tracker its access class names.
2. **Accept**, after review in the issue: `catalog add DRAFT` (Accept) checks
   the name, `source_dir` and the licence documents, writes `dataset.yaml` and
   `status.yaml`, and builds; a purged or existing name is refused. A
   repository bundle goes through `catalog add-bundle DIR`.
3. **Build.** `catalog build` (Inventory builder) hashes `source_dir` and
   writes `datapackage.json`, the shards and the index row.
4. **Make the bytes available**, by access class, each recording a copy:
    - public: `catalog upload NAME` (Uploader) checks the whole batch, copies
      without overwriting, makes the folder world-readable and reads every
      size back anonymously;
    - internal, and public data that cluster users read in place:
      `ethos-data --root <shared cache> link NAME DIR --catalog-root <own clone>`
      or
      `ethos-data --root <shared cache> materialize NAME --catalog-root <own clone>`;
    - restricted: `ethos-data link NAME <licensed dir>` or
      `materialize NAME --from DIR`, with `--catalog-root <own clone>`, into
      the restricted cache.

    The catalogue-wide form,
    `ethos-data link --all --root <shared cache> [--prune] --catalog-root <own clone>`,
    runs only from a clone at the merged state of the served release
    ([0028](decisions/0028-read-only-shared-cache.md)).
5. **Record.** `catalog record NAME [--copy LOC]` (Freeze) checks the chosen
   copy file by file and makes it the authority: the dataset is `frozen`.
6. **Merge**, on JuGit: the maintainer reviews the diff, commits on a branch
   and merges by merge request.
7. **Release**, in the clone at the merged state, beside the public
   catalogue's checkout: `catalog release vYYYY.MM.N --public <checkout>`,
   then again with `--push --upload`. `--push` is the one direct push to the
   release branch; a merge that lands first makes it fail, and the release is
   rerun from the updated branch
   ([0026](decisions/0026-internal-catalogue-on-the-cluster.md)).
8. **Serve**, on the cluster computer while no jobs read the served checkout:
   `ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout`
   (Checkout updater) refuses local changes, fast-forwards to the newest
   release tag and runs `build --check`. The cluster then serves this release
   only.
9. **Answer.** The catalogue maintainer posts the drafted answers and announces
   the release on the ICE-2 wiki. The package maintainer raises
   `catalog.min_version` and runs `bundle update` for bundled data.

<figure markdown="span">
  ![catalog release plans every stage before any acts, and its check refuses before any write unless the build check and the publish check with its leak check pass and every public dataset has a verified upload; it then stamps the version into the maintainer's clone, commits and tags it, generates, commits and tags the public catalogue checkout, pushes both to GitHub and JuGit, syncs the public catalogue to dCache and drafts the notices, after which catalog update-checkout on the cluster fetches the tags and fast-forwards the served checkout, which holds the latest release only. Removal withdraws a dataset, a merge request and a later release leave it out, and catalog remove --purge then deletes its cache entries and dCache folders and leaves a tombstone.](../../assets/diagrams/architecture-release-light.svg#only-light){ .diagram }
  ![catalog release plans every stage before any acts, and its check refuses before any write unless the build check and the publish check with its leak check pass and every public dataset has a verified upload; it then stamps the version into the maintainer's clone, commits and tags it, generates, commits and tags the public catalogue checkout, pushes both to GitHub and JuGit, syncs the public catalogue to dCache and drafts the notices, after which catalog update-checkout on the cluster fetches the tags and fast-forwards the served checkout, which holds the latest release only. Removal withdraws a dataset, a merge request and a later release leave it out, and catalog remove --purge then deletes its cache entries and dCache folders and leaves a tombstone.](../../assets/diagrams/architecture-release-dark.svg#only-dark){ .diagram }
</figure>

The figure shows the release's stages, which
[maintenance pipelines](decisions/0023-maintenance-pipelines.md) lists. Its
`check` stage refuses an unclean checkout, a version that does not follow the
last, a stale build, a public dataset without a verified upload, and a leak.
It reads every non-frozen `source_dir`, so a release runs on the cluster
computer. A rerun does only what is left.

Decisions: [0018 Releases](decisions/0018-numbered-catalogue-releases.md),
[0027 Public catalogue](decisions/0027-public-catalogue-releases-on-github.md).

## 6.6 Remove and purge

How a dataset leaves the catalogues: metadata first, bytes last.

1. `catalog remove NAMES [--reason R]` (Removal), in the maintainer's own
   clone, withdraws the dataset from the index and drafts the removal notice.
   The description, the status file, the cache entries and the bytes stay.
2. Merge, then release (6.5, steps 6–8). Readers are served the dataset until
   that release.
3. `catalog remove NAMES --purge`:
    - `check` requires a release recorded after the removal, and no other
      dataset's uploaded folder in or around this one;
    - `cache` deletes the recorded links and copies in the shared cache and
      the restricted cache. It refuses an entry that differs from its record,
      a recorded link that has become a real directory or a recorded copy
      that has become a link, so that a maintainer first finds out who made
      it. Users' own public caches are not touched;
    - `store` purges every revision folder the store still holds, and reads
      back that it is gone;
    - `tombstone` deletes `datasets/<name>/` except `status.yaml` (`purged`).
4. Merge the tombstone. From then on, `catalog add` refuses the name.

Decisions: [0022 Status files](decisions/0022-dataset-status-files.md),
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
  inventory and writes it; bundled data goes through `bundle update` and
  `catalog add-bundle`. The keys stay; changed and new files go under
  `<remote prefix>@<r+1>/` and into the entry `<dataset>@<r+1>/`. Then
  upload, record, merge and release. Each release describes the revision it
  was made with, so on a public installation a workflow bound to an older
  release reads that release's revision; the cluster serves the latest
  release only ([0026](decisions/0026-internal-catalogue-on-the-cluster.md)).
- **Successor.** A new dataset with `ethos:supersedes: <old>`, accepted as in
  6.5. The build marks the old dataset `ethos:superseded_by`, `ls` shows it
  superseded, and a collection that reads it warns. Collections move their
  named paths to the new keys.

Decisions:
[0019 Revisions and successors](decisions/0019-revisions-and-successors.md),
[0020 Repository bundles](decisions/0020-repository-bundles.md).
