# 6. Runtime View

The scenarios use the block names from [section 5](building-blocks.md).

The ordinary Python `fetch()` path loads a collections file, selects catalogue
resources, checks the collection's `paths` handles against that selection,
determines where the resources belong on this machine, and returns a mapping
from resource keys to local paths, with the handles resolved beside it. It may
read metadata over the network even when all dataset bytes are already local.

## 6.1 Data request

<figure markdown="span">
  ![The Consumer entry points resolve a collection through Selection and Catalogue model, then Retrieval asks the lookup chain for locations and obtains verified files from local storage or dCache through the downloader.](../../assets/diagrams/architecture-fetch-light.svg#only-light){ .diagram }
  ![The Consumer entry points resolve a collection through Selection and Catalogue model, then Retrieval asks the lookup chain for locations and obtains verified files from local storage or dCache through the downloader.](../../assets/diagrams/architecture-fetch-dark.svg#only-dark){ .diagram }
</figure>

### Selection and location

The catalogue index identifies datasets without loading all inventories.
Selection loads the required descriptors and relevant shards, expands collection
inheritance, matches file patterns, and includes declared sidecars. Resources
are identified by `<dataset>/<resource path>`.

Location then runs every resource through the lookup chain, one locator per
place, in this order: a configured dataset root, an eligible staging entry,
the package's bundles, the restricted cache, a link in the public cache, a
copy already in it, and a download from the publication root. Each locator
answers *found*, *pass* or *refuse*. The first that finds the file decides
where it is read, and a refusal ends the chain: licensed data without an
installation is never downloaded, and a bundled file that no longer matches
its hash is never replaced by a download. A symbolic-link entry in the public
cache means use the existing files in place. A package's handle reads bundles
only when it lists them with `bundles=`; `download=True` or
`ETHOS_DATA_DOWNLOAD=1` takes the catalogue route instead. See
[where a file is read](../../reference/configuration.md#lookup-order) and the
[resolution diagram](../caches-and-access.md#resolution-order).

A revision changes where a file is fetched from, not its key. A file
published in revision 2 is downloaded from `<remote_prefix>@2/<path>` into
the cache entry `<dataset>@2/`, which is seeded from the entry before it, after
a hash check, for the files that did not change.

### Cache hit, cache miss, and local files

| Situation | Behaviour | Meaning for the caller |
|---|---|---|
| Download-managed file exists and matches its manifest hash | The downloader, Pooch by default, reuses it | No dataset transfer is needed |
| Download-managed file is absent or fails its hash check | The downloader retrieves and verifies it | Network/storage failures can stop the request |
| File resolves in place | Fetch checks that it exists and returns its path without copying | Fetch does not hash-check this local file; use explicit verification when needed |
| File is in one of the package's bundles | Read in place after a hash check | A changed or missing bundled file is refused, never downloaded; `bundle update` records a change |
| Expected in-place file is missing | Raises an access error with concrete paths | A configured location does not silently fall back to another copy |
| Licensed data has no configured location | Fails before anything is downloaded, with the dataset's description, provenance and licence and how to register a copy | Every input is required; `plan()` and `verify()` report it as not available here instead |
| `fetch=False` and a file would have to be downloaded | Nothing is downloaded and no store is contacted; `NotFetched` names the path the file belongs at | A copy already in the public cache is returned as it is |

A download also checks that its destination dataset directory is not a symbolic
link before passing work to the downloader. This protects storage borrowed by
the cache from being treated as a download destination.

`plan()` estimates download work from presence and size; it does not establish
checksum validity. See [Check and repair the cache](../../how-to/data-users/verify-and-repair.md)
for explicit integrity checks.

## 6.2 Access failures and development data

### Reproducibility has prerequisites

A consuming package should name the catalogue releases it works with —
`min_version` and `max_version`, or `exact_version`, in its collections file —
or pin an actual versioned catalogue URL. Reusing that metadata and retaining
immutable dataset bytes makes the same selection repeatable. A version-looking
URL alone cannot prevent a host from changing content or deleting files.

Configured local roots can point to changed files, and staging deliberately
supports changing work in progress. Neither should be mistaken for a verified
copy solely because fetch returned a path. Staging warnings and the
[licensing and immutability rules](../licensing.md) explain these boundaries.

For configuration steps, see [Link existing data into the cache](../../how-to/catalogue-maintainers/link-existing-data.md#dataset-root-overrides)
and [Work with restricted data](../../how-to/data-users/set-up-your-machine.md#public-installation-users).

### Failure boundaries

Loading a collections file fails first if the catalogue index it pins cannot be
read (`CatalogUnavailable`), and a catalogue outside the releases it names is
refused with both versions in the message. Selection rejects unknown datasets
and collections, and a collection whose `test` and `full` variants name
different `paths` — the check runs for every collection a resolution reaches
through `extends`, so a plain collection extending a lopsided one is rejected
too. A pattern that matches no resources can produce an empty selection;
consuming packages must check that their required inputs were selected. Bundle
export rejects empty collections. If the lookup chain refuses required data,
Retrieval fails before returning an apparently complete result, with the
dataset's description. Every input is required, so a result either holds
every handle the collection names or is not returned at all.

Local development can overlay catalogue data with staging entries. A staging
overlay changes metadata selection as well as file locations: new resources must
be visible to Selection before Retrieval can use them. Python collection loading and CLI collection loading both apply the overlay;
`Catalog.path()` applies it, once per handle, before looking up the resource. The overlay uses a
separate catalogue object so the caller's canonical `Catalog` is retained. Export
operations use `include_staging=False` to select authoritative metadata.

A user reporting a problem runs `<your-tool>-data report` or
`ethos-data report`: the self-test, the settings in effect and the fetch plan,
in the report template, with tokens, the home directory and the account name
removed.

## 6.3 Catalogue lifecycle

### Proposal and acceptance

A package maintainer first develops against local source data, then runs
`<your-tool>-data propose DIR`: it checks the draft `dataset.yaml` as the
catalogue's build would, inventories the bytes, and drafts the proposal with
the metadata, provenance, proposed resource identifiers, the collections that
already name the dataset, and the tracker to submit it to. The catalogue
maintainer reviews the proposal before accepting it with
`ethos-data catalog add`, whose stages take in the draft, place its
description and status file, and build it; a repository bundle is accepted
with `catalog add-bundle`. Access to the internal repository is not a
prerequisite for proposing a dataset.

Maintainers manage two related outputs: dataset bytes in storage and metadata
that lets consumers find and verify those bytes. Uploading files and releasing
the catalogue are separate operations.

<figure markdown="span">
  ![A dataset's lifecycle: add makes a draft; build makes it built; upload, link or materialize make it available; record freezes it. A change or a revision returns it to built. Remove withdraws it from the catalogue, and purge, after a release without it, deletes its bytes.](../../assets/diagrams/architecture-lifecycle-light.svg#only-light){ .diagram }
  ![A dataset's lifecycle: add makes a draft; build makes it built; upload, link or materialize make it available; record freezes it. A change or a revision returns it to built. Remove withdraws it from the catalogue, and purge, after a release without it, deletes its bytes.](../../assets/diagrams/architecture-lifecycle-dark.svg#only-dark){ .diagram }
</figure>

Each dataset's `status.yaml` records where it stands. Every command checks its
step against that state before it acts and records the step after, so a draft
cannot be uploaded and a frozen dataset is only rechecked.
`ethos-data catalog status` shows every dataset's state, access class, last
release and what it needs next, and with `--check` tests the record against
the copies and the files. The states and steps are listed in
[File formats](../../reference/schemas.md#statusyaml).

The maintainer commands are pipelines: every stage plans before any acts,
`--dry-run` prints the plan, and a command run again after an interruption
does only what is left.

### Describe and build

The source catalogue holds hand-maintained YAML describing the dataset,
provenance, licences, and publication policy, and a status file per dataset
that holds the build input, `source_dir`, while there is one. Building
produces the JSON index, descriptors, and any inventory shards. Consumers read
these generated files; they do not need access to a maintainer's source
directory.

[Add a dataset](../../how-to/catalogue-maintainers/add-a-dataset.md) gives the procedure;
[The catalogue format](../catalogue-format.md) explains the representation.

### Validate the selected upload batch

For a subset upload, arguments are resolved and deduplicated in input order.
The uploader loads each selected dataset and applies preflight checks before
starting any transfer. These checks reject restricted data, require explicit
permission for internal uploads, check that each dataset's state allows the
upload, and check prerequisites such as manifests and local source
availability.

This catches several avoidable errors early. It is not a transaction or a
complete simulation: resource expansion, network requests, and storage operations
can still fail after earlier datasets have transferred.

### Transfer and verify

For each dataset, the uploader expands the manifest resources and supplies that
file list to the store, today `rclone` against dCache. Files merely present in
the source directory are not implicitly included. The transfer uses
`--checksum` and `--immutable`; changed content belongs at a new published
path, a new revision's folder.

For public datasets, the uploader can set the dataset prefix's permissions.
It then checks anonymous readability and content length for manifest files and
queries a sample file's storage locality. These HTTP checks establish reachability
and size, not a remote SHA-256 audit. A verified upload is recorded in the
dataset's status file as a copy on the store, and makes a built dataset
available; `catalog record` then checks that copy complete, retires the build
input and freezes the inventory.

The current verification path is anonymous even for an explicitly allowed
internal upload. Such an upload can transfer successfully and report failed
verification because anonymous access is intentionally unavailable. See
[risks and technical debt](risks-and-technical-debt.md).

A batch records returned per-dataset failures and reports an unsuccessful exit
status; completed transfers are not rolled back. See [Upload a dataset](../../how-to/catalogue-maintainers/upload-a-dataset.md)
for commands and recovery steps.

### Generate and release the published catalogue

`ethos-data catalog release VERSION --public CHECKOUT` makes a release as one
pipeline:

| Stage | What it does |
|---|---|
| `check` | the version follows the last release; both checkouts are clean and the public one is not a source catalogue; every manifest is current; every public dataset the public catalogue lists has a verified upload recorded; the public tree does not leak |
| `stamp` | write the version into `catalog.yaml` and the index, and a release step into the history of every dataset with steps since its last release |
| `commit` | commit the source checkout and tag it with the version |
| `public` | generate the public catalogue in its checkout, commit and tag it |
| `push` | with `--push`: push both checkouts and the tag |
| `store` | with `--upload`: put the public catalogue on the store under `<publication root>/catalogue/`, replacing the previous one |
| `notices` | draft the release notice and the answer to every proposal the release accepts |

Publication selects descriptors by visibility, strips the fields the
specifications mark as never published, and copies required shards and
archived licence documents into the public checkout; the check stage refuses
a public tree that would leak them. A release made without `--push` and
`--upload` is pushed and uploaded by running it again with them. On the ICE-2
cluster computer, `catalog update-checkout` then advances the internal
checkout to the newest release tag. See
[Release the catalogue](../../how-to/catalogue-maintainers/release-the-catalogue.md).

Upload and release share no transaction, but the check stage refuses a
release that lists a public dataset without a verified upload, so readiness is
checked rather than assumed.

### Revision and withdrawal

Changed bytes are a new revision, published beside the old ones under
`<remote_prefix>@<revision>/` and numbered by `catalog build NAME --revision`,
or a successor dataset that names the one it replaces with
`ethos:supersedes`. Existing catalogue releases retain their meaning.

Removal is the reverse of publishing: metadata first, bytes second.
`catalog remove` withdraws the dataset, rebuilds the index without it, and
drafts the removal notice for the packages that read it. Once a release
without it is recorded, `catalog remove --purge` unlinks its cache entries,
deletes its folder on the store, and leaves only its status file, which keeps
its name from being given to other bytes. Old catalogue pins still describe
old resources, but cannot make deleted bytes available. Follow
[Remove a dataset](../../how-to/catalogue-maintainers/withdraw-a-dataset.md) for the procedure.

## 6.4 Repository test data

A package repository can hold its test data as a **repository bundle**: the
files under `data/<family>/<member>/`, their inventory and version in
`bundle.json`, and their descriptions under `datasets/`. The repository is the
source of truth for these files; the catalogue publishes a version of them.
This serves both routine testing with lower storage-service load and
temporary experiments during bug fixing.

1. A package maintainer starts the bundle with `bundle create` and commits it.
   The package's handle lists it with `bundles=`, and the lookup chain reads
   bundled files first, hash-checked and in place, with no remote fallback:
   a missing or changed file fails rather than downloading.
2. A deliberate change to a bundled file is recorded with `bundle update`. A
   version a catalogue release holds is never changed: the first change after
   its release starts the next version. Until a release holds the current
   version, reading the bundle warns.
3. `<your-tool>-data propose` drafts the proposal for the new version, the
   catalogue maintainer takes it in with `catalog add-bundle`, and a release
   publishes it. `bundle update` then records the release that holds it.
4. `download=True` or `ETHOS_DATA_DOWNLOAD=1` reads the same data through the
   catalogue route instead, to check that the published copy serves the tests.

An **exported bundle** is the older form, a copy of canonical public catalogue
resources: `export_bundle()` creates it from a pinned catalogue, verifying
bytes from explicit local inputs or downloads from the catalogue publication
URL, with ambient staging and configured roots ignored, and `load_bundle()`
reads it. `Bundle.fetch()` hash-checks its files without remote fallback;
`allow_modified=True` lets a developer test an edited fixture, keeping the
expected published hash and warning with the changed resource keys.

An allowance to use a changed repository fixture must be scoped to that local
workflow. It must not disable ordinary download checksum checks, silently repair
a developer's edited file, or update dCache during a test run.

`Bundle.verify()` reports integrity findings without modifying files. Exporting
a refreshed bundle requires a new target directory, so updates can be compared
before replacing the repository copy. Export supports public, non-staged
datasets; it rejects internal/restricted data and hidden entries. See
[Keep data in the repository](../../how-to/package-maintainers/keep-data-in-the-repository.md)
for commands and examples.
