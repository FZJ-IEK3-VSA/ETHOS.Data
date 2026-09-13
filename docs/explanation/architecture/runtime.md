# 6. Runtime View

The scenarios use the block names from [section 5](building-blocks.md).

The ordinary Python `fetch()` path loads a collections file, selects catalogue
resources, determines where they belong on this machine, and returns a mapping
from resource keys to local paths. It may read metadata over the network even
when all dataset bytes are already local.

## 6.1 Data request

<figure markdown="span">
  ![The Consumer entry points resolve a collection through Selection and Catalogue model, then Retrieval asks Access policy for locations and obtains verified files from local storage or dCache.](../../assets/diagrams/architecture-fetch-light.svg#only-light){ .diagram }
  ![The Consumer entry points resolve a collection through Selection and Catalogue model, then Retrieval asks Access policy for locations and obtains verified files from local storage or dCache.](../../assets/diagrams/architecture-fetch-dark.svg#only-dark){ .diagram }
</figure>

### Selection and location

The catalogue index identifies datasets without loading all inventories.
Selection loads the required descriptors and relevant shards, expands collection
inheritance, matches file patterns, and includes declared sidecars. Resources
are identified by `<dataset>/<resource path>`.

Location resolution then applies configured dataset roots, eligible staging
entries, the restricted root, and finally the public cache. A symbolic-link
entry in the public cache means use the existing files in place. The existing
[resolution diagram](../caches-and-access.md#resolution-order) shows this order.

### Cache hit, cache miss, and local files

| Situation | Behaviour | Meaning for the caller |
|---|---|---|
| Download-managed file exists and matches its manifest hash | Pooch reuses it | No dataset transfer is needed |
| Download-managed file is absent or fails its hash check | Pooch retrieves and verifies it | Network/storage failures can stop the request |
| File resolves in place | Fetch checks that it exists and returns its path without copying | Fetch does not hash-check this local file; use explicit verification when needed |
| Expected in-place file is missing | Raises an access error with concrete paths | A configured location does not silently fall back to another copy |
| Restricted data has no configured location | Fails, or marks it unavailable when skipping is enabled | Skipped resources are absent from the returned mapping and a warning is emitted |

A download also checks that its destination dataset directory is not a symbolic
link before passing work to Pooch. This protects storage borrowed by the cache
from being treated as a download destination.

`plan()` estimates download work from presence and size; it does not establish
checksum validity. See [Check and repair the cache](../../how-to/verify-and-repair.md)
for explicit integrity checks.

## 6.2 Access failures and development data

### Reproducibility has prerequisites

A consuming package should pin an actual versioned catalogue URL. Reusing that
metadata and retaining immutable dataset bytes makes the same selection
repeatable. A version-looking URL alone cannot prevent a host from changing
content or deleting files.

Configured local roots can point to changed files, and staging deliberately
supports changing work in progress. Neither should be mistaken for a verified
copy solely because fetch returned a path. Staging warnings and the
[licensing and immutability rules](../licensing.md) explain these boundaries.

For configuration steps, see [Use data already on disk](../../how-to/use-data-already-on-disk.md)
and [Work with restricted data](../../how-to/restricted-data.md).

### Failure boundaries

Selection rejects unknown datasets and collections. A pattern that matches no
resources can produce an empty selection; consuming packages must check that
their required inputs were selected. Bundle export rejects empty collections. If Access
policy finds inaccessible required data,
Retrieval fails before returning an apparently complete result. Explicitly
skipping unavailable data changes the returned keys, so the consuming workflow
must distinguish required from optional inputs.

Local development can overlay catalogue data with staging entries. A staging
overlay changes metadata selection as well as file locations: new resources must
be visible to Selection before Retrieval can use them. Python collection loading and CLI collection loading both apply the overlay;
`fetch_one()` applies it before looking up the resource. The overlay uses a
separate catalogue object so the caller's canonical `Catalog` is retained. Export
operations use `include_staging=False` to select authoritative metadata.

## 6.3 Catalogue lifecycle

### Proposal and acceptance

A package maintainer first develops against local source data and submits the
metadata, provenance, proposed resource identifiers, collection changes, a way to
access the bytes, and validation results. The catalogue maintainer reviews this
proposal before accepting it into the internal catalogue. Access to the internal
repository is not a prerequisite for proposing a dataset.

Maintainers manage two related outputs: dataset bytes in storage and metadata
that lets consumers find and verify those bytes. Uploading files and generating
the published catalogue are separate operations.

<figure markdown="span">
  ![Describe and build metadata, validate the selected upload batch, upload and verify each dataset, then generate and release the public catalogue. Transfer failures require review before release.](../../assets/diagrams/architecture-lifecycle-light.svg#only-light){ .diagram }
  ![Describe and build metadata, validate the selected upload batch, upload and verify each dataset, then generate and release the public catalogue. Transfer failures require review before release.](../../assets/diagrams/architecture-lifecycle-dark.svg#only-dark){ .diagram }
</figure>

### Describe and build

The source catalogue holds hand-maintained YAML describing the dataset, source
location, provenance, licences, and publication policy. Building produces the
JSON index, descriptors, and any inventory shards. Consumers read these generated
files; they do not need access to a maintainer's source directory.

[Describe a dataset](../../how-to/describe-a-dataset.md) gives the procedure;
[The catalogue format](../catalogue-format.md) explains the representation.

### Validate the selected upload batch

For a subset upload, arguments are resolved and deduplicated in input order.
The uploader loads each selected dataset and applies preflight checks before
starting any transfer. These checks reject restricted data, require explicit
permission for internal uploads, and check prerequisites such as manifests and
local source availability.

This catches several avoidable errors early. It is not a transaction or a
complete simulation: resource expansion, network requests, and storage operations
can still fail after earlier datasets have transferred.

### Transfer and verify

For each dataset, the uploader expands the manifest resources and supplies that
file list to `rclone`. Files merely present in the source directory are not
implicitly included. The transfer uses `--checksum` and `--immutable`; changed
content belongs at a new published path.

For public datasets, the uploader can set the dataset prefix's permissions.
It then checks anonymous readability and content length for manifest files and
queries a sample file's storage locality. These HTTP checks establish reachability
and size, not a remote SHA-256 audit.

The current verification path is anonymous even for an explicitly allowed
internal upload. Such an upload can transfer successfully and report failed
verification because anonymous access is intentionally unavailable. See
[risks and technical debt](risks-and-technical-debt.md).

A batch records returned per-dataset failures and reports an unsuccessful exit
status; completed transfers are not rolled back. Review the results before
releasing catalogue metadata. See [Upload a dataset](../../how-to/upload-a-dataset.md)
for commands and recovery steps.

### Generate and release the published catalogue

Publication selects descriptors by visibility, strips internal fields, and copies
required shards and archived licence documents into the target catalogue checkout.
It does not upload dataset bytes or by itself commit, push, or tag the repository.
The maintainer reviews and releases that generated output as described in
[Publish the catalogue](../../how-to/publish-the-catalogue.md).

Publication is not gated by a transaction shared with upload. The maintainer must
ensure that advertised files are ready before consumers see the new metadata.

### Revision and withdrawal

Changed bytes need new paths so existing catalogue versions retain their meaning.
Withdrawing a dataset starts by removing its entry from the published view; any
necessary deletion of remote bytes follows. Old catalogue pins still describe
old resources, but cannot make deleted bytes available. Follow
[Withdraw a dataset](../../how-to/withdraw-a-dataset.md) for the procedure.

## 6.4 Repository test data

A package repository can contain a bundle: selected local test copies and the
metadata needed to resolve them without dCache access. `export_bundle()` creates
a new bundle from canonical public catalogue resources; `load_bundle()` reads
its local manifest.
Published bytes remain authoritative on dCache. This serves both routine testing
with lower storage-service load and temporary experiments during bug fixing.

1. A package maintainer selects a test collection from a pinned catalogue and
   records its resource identities, authoritative hashes, source revision, and
   local copies. Export verifies bytes from explicit local inputs or downloads
   from the catalogue publication URL; ambient staging and configured roots are ignored.
2. Required tests call `Bundle.fetch()` to hash-check local metadata selections
   and files without remote fallback.
   Missing required files fail explicitly rather than downloading or skipping.
3. The maintainer may use `allow_modified=True` while modifying a fixture
   to reproduce and verify a bug. The expected published hash remains unchanged,
   and a warning identifies changed resource keys. Missing files remain errors.
4. After verification, the maintainer either restores the local authoritative
   copy or submits the changed dataset through the acceptance boundary above.
5. Catalogue maintainers publish accepted revised bytes at a new path and release
   updated metadata. The package then deliberately refreshes its pin and copies.

An allowance to use a changed repository fixture must be scoped to that local
workflow. It must not disable ordinary download checksum checks, silently repair
a developer's edited file, or update dCache during a test run.

`Bundle.verify()` reports integrity findings without modifying files. Exporting
a refreshed bundle requires a new target directory, so updates can be compared
before replacing the repository copy. The current feature supports public,
non-staged datasets; it rejects internal/restricted data and hidden entries.
The exported bundle retains the selected metadata and expanded sidecars needed
by its collections. It is a bundle manifest, not a replacement full catalogue.
See [Keep test data in a repository](../../how-to/keep-test-data-in-a-repository.md)
for commands and examples.
