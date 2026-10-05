# 5. Building Block View

This view answers what ETHOS.Data is built from: its containers and data
stores, the components of the library, and how they depend on each other.
Section 5.1 is the C4 container view (level 2); 5.2 and 5.3 are component
views of the library (level 3). Arrows point from a block to the block it
uses, and every diagram carries its own key; the tables give each block's
responsibility. How the blocks work together is in the
[Runtime View](runtime.md), and where they run in the
[Deployment View](deployment.md).

## 5.1 Containers and data stores (C4 level 2) {#containers}

<figure markdown="span">
  ![ETHOS.Data is one library, run in the caller's process by a consuming package and by three command lines (the package command, ethos-data and ethos-data catalog), over stores whose formats it specifies: each user's settings, personal public cache, restricted cache and staging root, the package's collections file and bundles, the cluster's read-only shared cache and its served checkout of the latest release, and a maintainer's own clone of the source catalogue. The library reads the published catalogue on GitHub and downloads from dCache; maintainers fill the shared cache with ethos-data, merge their clone by merge request on JuGit, and with ethos-data catalog update the served checkout, push releases to JuGit and GitHub and maintain dCache with tokens from Helmholtz ID.](../../assets/diagrams/architecture-containers-light.svg#only-light){ .diagram }
  ![ETHOS.Data is one library, run in the caller's process by a consuming package and by three command lines (the package command, ethos-data and ethos-data catalog), over stores whose formats it specifies: each user's settings, personal public cache, restricted cache and staging root, the package's collections file and bundles, the cluster's read-only shared cache and its served checkout of the latest release, and a maintainer's own clone of the source catalogue. The library reads the published catalogue on GitHub and downloads from dCache; maintainers fill the shared cache with ethos-data, merge their clone by merge request on JuGit, and with ethos-data catalog update the served checkout, push releases to JuGit and GitHub and maintain dCache with tokens from Helmholtz ID.](../../assets/diagrams/architecture-containers-dark.svg#only-dark){ .diagram }
</figure>

ETHOS.Data is one Python distribution with one console script. It deploys no
server: the library runs in the process that calls it, and every store is a
file, a directory tree or a git working tree whose format ETHOS.Data
specifies.

| Container | Technology | Responsibility | Run by |
|---|---|---|---|
| `ethos_data` library | Python 3.10 or later; PyYAML, platformdirs, pooch; `pydantic>=2`, loaded on first use | The model, adapters, services and package facade, in the calling process. `import ethos_data` loads neither catalogue maintenance nor pydantic. | Consuming packages, scripts, the commands |
| `ethos-data` | The console script | Key access, self-test, problem report, settings, cache entries | Data users; maintainers, for the shared and the restricted cache |
| `ethos-data catalog` | The same script; git, rclone, oidc-agent | Maintains the source catalogue in a maintainer's own clone; updates the served checkout | Catalogue maintainers |
| `<tool>-data` | A script a package defines with `ethos_data.tool_main` | The package's collections: show, fetch, verify, bundles, staging, propose, report, config | Data users, package maintainers |

`ethos-data` and `ethos-data catalog` are one executable, but two containers:
different people run them, on different machines, against different stores.

| Store | Holds | Written by |
|---|---|---|
| Settings file | `public_cache`, `shared_cache`, `restricted_cache`, `staging_cache`, `catalog`, `publication_url`, `dataset_roots`; one per account | `config set-*`, `unset-*` |
| Public cache | Personal, on every machine: public data in entries `<dataset>/` or `<dataset>@<r>/`; the metadata cache | That user's commands |
| Shared cache | On the cluster: public and internal data, never restricted, read in place by every cluster user | Maintainers only, naming it with `--root`; purge |
| Restricted cache | Licensed installations or links; on the cluster, one group per dataset | `link`, `materialize` of a restricted dataset; purge |
| Staging root | Personal: staged links or copies | `staging add`, `remove` |
| Served internal catalogue checkout | The source catalogue at its latest release, for every cluster user | `catalog update-checkout` only |
| Maintainer's clone of the source catalogue | The catalogue, with each dataset's status file, in the maintainer's own account | `ethos-data catalog`; `link`, `materialize` with `--catalog-root`; merged by merge request on JuGit |
| Status files | `status.yaml` per dataset: state, build input, revision, authority, copies, history; never published | The status recorder only |
| Public catalogue checkout | The generated public catalogue | The public-view generator |
| Collections file, bundles | Release bounds and collections; a repository bundle (the package's next test data) or an exported bundle (released public data) | The package maintainer; `bundle` commands |
| Build inputs, validation folder, notices directory | What a dataset is built from until it is frozen; re-downloaded originals; drafted notices | Maintainers; release and removal draft the notices |
| GitHub, dCache | The public catalogue, one tag `vYYYY.MM.N` per release; the world-readable bytes at `<remote_prefix>[@<r>]/<path>` | Release; the uploader and removal on dCache |

A cluster user's settings name the served checkout, the shared cache and the
restricted cache, side by side on shared storage, for example under
`/shared/ethos/` ([§7.2](deployment.md#cluster)). A collections file whose
release bounds exclude the latest release is refused there with
`CatalogVersionError`.

Decisions: [one settings file per account](decisions/0010-one-settings-file-per-account.md),
[the access class picks the root](decisions/0011-access-class-picks-the-root.md),
[package commands own collections](decisions/0015-package-commands-own-collections.md),
[the internal catalogue on the cluster](decisions/0026-internal-catalogue-on-the-cluster.md),
[a read-only shared cache](decisions/0028-read-only-shared-cache.md).

## 5.2 Components by layer (C4 level 3) {#layers}

<figure markdown="span">
  ![Four layers from the bottom: model, adapters, services (data access, with catalogue maintenance above it) and presentation, with the errors and the reporter shared by all. Each module imports only its own layer and those below; catalogue maintenance may use data access, never the reverse; the one listed exception is selection importing the command line. A test holds these rules.](../../assets/diagrams/architecture-blocks-light.svg#only-light){ .diagram }
  ![Four layers from the bottom: model, adapters, services (data access, with catalogue maintenance above it) and presentation, with the errors and the reporter shared by all. Each module imports only its own layer and those below; catalogue maintenance may use data access, never the reverse; the one listed exception is selection importing the command line. A test holds these rules.](../../assets/diagrams/architecture-blocks-dark.svg#only-dark){ .diagram }
</figure>

The library has four layers: [presentation](#presentation), services
([catalogue maintenance](#catalogue-maintenance) over
[data access](#data-access)), [adapters](#ports-and-adapters) and the
[model](#model). A module imports only from its own layer and the layers
below it; every layer may also use `errors` and `report`, which import nothing
from the package.

- No data-access module imports `ethos_data.maintain`, so reading data never
  loads the writer.
- The model reads no settings, makes no network call and writes nothing.
- Services reach external systems only through the ports.
- Library code raises typed errors and reports through the reporter; only the
  presentation prints and chooses the exit status.
- `tests/test_layers.py` checks every import, lazy ones included. Its one
  listed exception, drawn dashed, is `selection` → `cli`, for
  `Collections.main()`; a second test fails when that exception is not
  needed.

### Model components {#model}

| Component | Module | Responsibility |
|---|---|---|
| Format specifications | `formats` | One pydantic model per standardised file; each field says whether it is published, promoted, user-facing and inherited. Files people write are validated through them. |
| Keys and derived values | `formats.keys`, `formats.derived` | Every key, file name and format id, spelled once; what is derived without the models, such as the index row |
| Templates | `formats` | The templates of files people write, and the handoff texts |
| Schemas and reference | `formats` | The committed JSON Schemas and the reference tables |
| Digests | `model.digest` | SHA-256 only; anything else is unverifiable |
| Names and entries | `model.names` | Safe relative paths, families, and the cache entry `<name>` or `<name>@<r>` |
| Resources | `model.resource` | `Resource`, keyed `<dataset>/<path>`: the one reader and writer of a resource record, and transitive sidecars |
| Versions | `model.versions` | Release names `vYYYY.MM.N`, compared as numbers, and release bounds |
| Lifecycle | `model.lifecycle` | A dataset's states, steps and guards; a refused step raises `TransitionError`, naming what the dataset needs first |
| Inventory reader | `model.inventory` | One dataset's descriptor and inventory, read on demand ([5.3.3](#inventory-reader)) |
| Path matching | `model` | One glob semantics, `**` spanning segments, for `files:`, `ethos:include` and `ethos:exclude` |

The model is the contract between independently developed packages, and
between the reader and the writer: both take every key, path rule and shard
rule from the same specifications, and a resource's key, cache entry and
object folder are computed from its identity.

### Presentation and shared modules {#presentation}

| Component | Module | Responsibility |
|---|---|---|
| Package facade | `ethos_data` | The library API; builds handles from one settings snapshot |
| Command line | `cli` | Parses `ethos-data` and `<tool>-data`, wires handles and services, prints, and chooses the exit status; no logic of its own |
| Catalogue command group | `maintain.cli` | Parses `catalog …` and dispatches to the maintenance components |
| Typed errors | `errors` | The error classes, under one base |
| Reporter | `report` | One channel for progress and warnings: printed inside a command, Python warnings outside one |

Every refusal is an `EthosDataError`, importable from `ethos_data.errors` and
from the facade: a request that cannot be served exits 2, for example
`UnknownDataset`, `CatalogVersionError`, `BundleError` or `AccessError` (with
`NotFetched` and `DownloadError`), and a maintenance command that refused its
input raises a `MaintenanceError`, such as `DescriptorError`, `UploadError` or
`TransitionError`, and exits 1.

Decisions: [four layers](decisions/0008-four-layers.md),
[cache paths from resource identity](decisions/0004-cache-paths-from-resource-identity.md),
[every file format specified once](decisions/0006-every-file-format-specified-once.md).

## 5.3 Inside the library (C4 level 3) {#level-3}

This level opens the two service groups, the inventory reader they share, and
the adapters.

### 5.3.1 Data access {#data-access}

<figure markdown="span">
  ![The collections handle answers which resources: it takes the catalogue view from the catalogue reader, which gets each dataset's inventory from the one inventory reader through the metadata sources, and lays bundles and then staging over it. Retrieval asks the lookup chain where each file is read before any transfer, through eight locators from dataset roots to the download, of which bundles, the restricted cache and the download may refuse and the cluster's shared cache is only read, and downloads the rest through the Downloader port from dCache.](../../assets/diagrams/architecture-reader-light.svg#only-light){ .diagram }
  ![The collections handle answers which resources: it takes the catalogue view from the catalogue reader, which gets each dataset's inventory from the one inventory reader through the metadata sources, and lays bundles and then staging over it. Retrieval asks the lookup chain where each file is read before any transfer, through eight locators from dataset roots to the download, of which bundles, the restricted cache and the download may refuse and the cluster's shared cache is only read, and downloads the rest through the Downloader port from dCache.](../../assets/diagrams/architecture-reader-dark.svg#only-dark){ .diagram }
</figure>

The collections handle answers which resources a workflow needs, the lookup
chain where each is read on this machine and whether it may be, and retrieval
makes the files usable. So a plan inspects locations without downloading, and
verification inspects files without changing the selection.

| Component | Module | Responsibility |
|---|---|---|
| Settings | `config` | Resolves every setting once into a frozen snapshot that records each value's source (argument, environment, settings file, default): the roots, the publication URL, the download switch. Chooses the catalogue within the release bounds. |
| Catalogue reader | `catalogs` | Reads only the index when it loads a catalogue, so access, revision, entry name, successors, totals and licence status need no descriptor. Checks a catalogue against release bounds. |
| Collections handle | `selection` | Validates the collections file, lays the bundles and then staging over the catalogue view, and resolves variants, `extends`, `include`, file patterns, sidecars and named paths. Reads the index only for a dataset no bundle holds. |
| Lookup chain | `access` | Decides for every file where it is read ([below](#lookup-chain)); in describe mode, for `plan` and `verify`, a refusal becomes "not available here". Names the root of a cache entry: the restricted cache for restricted data, else the root given with `--root`, or the public cache for public data; internal data gets no entry without `--root`. |
| Retrieval | `retrieval` | Locates every file before any transfer, then downloads the missing ones per revision folder into the user's own public cache, never through a link or into the shared cache. With `fetch=False` it raises `NotFetched`. |
| Integrity | `verify` | Checks each file where the chain finds it, by size or SHA-256, and reports a broken shared-cache entry. Repair writes only the user's own public cache. |
| Bundles | `bundles` | Creates, updates, exports, loads and verifies repository and exported bundles |
| Staging | `staging` | Adds, lists and removes staged datasets, as links or copies; its overlay never shadows a restricted name |
| Cache entries | `linking`, `materialize` | Makes one dataset's entry in the root the chain names: a link, or a verified copy the cache owns; never replaces a real directory. Removes links. Refused while licensing is unsettled. |
| Self-test | `selftest` | Runs the shipped example collection through settings, catalogue and files |
| Handoffs | `handoffs` | Fills the handoff templates, scrubs reports of tokens, credentials and personal paths, and routes each to a tracker by access class |
| Local files | `files` | Walks a data directory, applies `ethos:include` and `ethos:exclude`, and makes hashed resource records |

#### The lookup chain {#lookup-chain}

Eight locators decide where a file is read, in this order: dataset roots,
staging, bundles, the restricted cache, the shared cache, a link in the user's
own public cache, a copy in it, and a download into it; the first that finds a
file wins, and a refusal ends the call before any transfer. The shared cache
is only read, finds or passes and never refuses, and restricted data is never
looked up there; [§6.1](runtime.md#the-lookup-chain) follows one file through
the chain, and [one lookup chain](decisions/0012-one-lookup-chain.md) gives
each locator's places and refusals.

Decisions: [one lookup chain](decisions/0012-one-lookup-chain.md),
[every input is required](decisions/0013-every-input-is-required.md),
[repository bundles](decisions/0020-repository-bundles.md),
[a read-only shared cache](decisions/0028-read-only-shared-cache.md).

### 5.3.2 Catalogue maintenance {#catalogue-maintenance}

<figure markdown="span">
  ![Every catalogue workflow that writes is a pipeline whose stages plan before they act, run by the pipeline runner; the catalogue command group dispatches to the pipelines, and the command line runs link and materialize through the cache-copy recorder and namespace builder. The pipelines record each step through the status recorder in the status files of the maintainer's own clone, read checkouts through the inventory reader, commit, tag, push and fast-forward through the Git port, write dCache through the Store port with a Helmholtz ID token, fill the shared and restricted caches through the cache entries, hash the build inputs through local files, and draft notices into the notices directory.](../../assets/diagrams/architecture-maintainer-light.svg#only-light){ .diagram }
  ![Every catalogue workflow that writes is a pipeline whose stages plan before they act, run by the pipeline runner; the catalogue command group dispatches to the pipelines, and the command line runs link and materialize through the cache-copy recorder and namespace builder. The pipelines record each step through the status recorder in the status files of the maintainer's own clone, read checkouts through the inventory reader, commit, tag, push and fast-forward through the Git port, write dCache through the Store port with a Helmholtz ID token, fill the shared and restricted caches through the cache entries, hash the build inputs through local files, and draft notices into the notices directory.](../../assets/diagrams/architecture-maintainer-dark.svg#only-dark){ .diagram }
</figure>

Maintenance works in a maintainer's own clone of the source catalogue. Every
catalogue workflow that writes is a pipeline that plans all its stages before
any acts and records its steps in the clone without committing them; the
contract and each command's stages are in
[maintenance pipelines](decisions/0023-maintenance-pipelines.md).

| Component | Module | Responsibility |
|---|---|---|
| Pipeline runner | `maintain.pipeline` | Asks every stage for its plan, then runs the actions in order, each followed by its check |
| Checkout access | `maintain` | Finds the catalogue root and reads a clone through the inventory reader |
| Status recorder | `maintain.status` | Reads and writes `status.yaml`, checking each step with the lifecycle; `catalog status [--check]` |
| Accept | `maintain.accept` | `catalog add`: takes a reviewed draft into the clone, with its licence documents and a status file, and builds it |
| Bundle intake | `maintain.bundle_intake` | `catalog add-bundle`: takes a repository bundle's version into the clone |
| Inventory builder | `maintain.manifest` | `catalog build`: renders descriptors, shards and the index from the build input, or from the recorded inventory once frozen; refuses changed published bytes |
| Revision | `maintain.revision` | `catalog build --revision`: renders revision r+1 in memory, compares it with the inventory on disk, writes it |
| Uploader | `maintain.upload` | `catalog upload`: checks the whole batch, copies each revision folder without overwriting, makes it world-readable, reads it back anonymously |
| Cache-copy recorder and namespace builder | `maintain.namespace` | `ethos-data link --all --root <shared cache>` links the whole catalogue into the shared cache; `--catalog-root <own clone>` records what `link` and `materialize` make |
| Freeze | `maintain.freeze` | `catalog record`: checks a copy file by file and makes it the authority |
| Provenance | `maintain.provenance` | `catalog check-source`: hashes re-downloaded originals against the inventory |
| Public-view generator | `maintain.publish` | `catalog publish`: generates the public catalogue without unpublished keys, and runs the leak check |
| Release | `maintain.release` | `catalog release`: stamps, commits and tags both catalogues, pushes them, puts the latest public catalogue on dCache, drafts the notices |
| Checkout updater | `maintain.checkout` | `catalog update-checkout`: fast-forwards the served checkout to the newest release tag; the only command that changes it |
| Removal | `maintain.remove` | `catalog remove`: withdraws datasets; `--purge`, after a later release, deletes their recorded cache entries and store folders and leaves a tombstone |
| Migrator | `maintain.migrate` | `catalog migrate`: the one-time converter of the internal catalogue ([clean break](decisions/0002-clean-break-during-the-beta.md)) |

Decisions: [maintenance pipelines](decisions/0023-maintenance-pipelines.md),
[dataset status files](decisions/0022-dataset-status-files.md),
[one link command, two modes](decisions/0016-one-link-command-two-modes.md),
[the internal catalogue on the cluster](decisions/0026-internal-catalogue-on-the-cluster.md),
[the public catalogue on GitHub](decisions/0027-public-catalogue-releases-on-github.md).

### 5.3.3 The inventory reader {#inventory-reader}

<figure markdown="span">
  ![One inventory reader in the model layer serves both service groups: the catalogue reader, bundles and staging on the data-access side, and checkout access, through which the maintenance components read a maintainer's clone. It reads every descriptor and shard through the metadata source its caller hands it (a file source for the clone or the served checkout, a caching source in front of HTTPS for the published catalogue on GitHub, or an in-memory tree), and the build writes shards with the same shard rules.](../../assets/diagrams/architecture-inventory-light.svg#only-light){ .diagram }
  ![One inventory reader in the model layer serves both service groups: the catalogue reader, bundles and staging on the data-access side, and checkout access, through which the maintenance components read a maintainer's clone. It reads every descriptor and shard through the metadata source its caller hands it (a file source for the clone or the served checkout, a caching source in front of HTTPS for the published catalogue on GitHub, or an in-memory tree), and the build writes shards with the same shard rules.](../../assets/diagrams/architecture-inventory-dark.svg#only-dark){ .diagram }
</figure>

One model component reads every generated catalogue (the served checkout, a
published tree over HTTPS, a maintainer's clone, a tree rendered in memory)
through the metadata source it is handed, and imports no adapter. For one
dataset it answers the descriptor; the resources under a path, from one
shard; the resources that match file patterns, from only the shards a pattern
can match (a shard too many, never one too few); and all resources. It reads
each shard at most once, raises `IncompleteCatalog` for a missing part, naming
the dataset, the part and the location, and gives the writer its shard rules,
so the build writes what the reader reads. The catalogue reader and
checkout access both read through it, so a maintainer sees what a data user
sees.

Decisions: [one inventory reader](decisions/0007-one-inventory-reader.md),
[the index first, inventories on demand](decisions/0005-lazy-index-descriptors-and-shards.md).

### 5.3.4 Ports and adapters {#ports-and-adapters}

Services reach external systems only through four ports, each a
`typing.Protocol`. Adapters read no settings: services pass them what they
need. Failures raise typed errors.

| Port | What it answers and guarantees | Failures |
|---|---|---|
| `Store` | Authenticated maintenance of the publication root: copy listed files, never overwriting; sync a tree; purge a folder; set permissions; a path's locality; whether a folder still exists; an anonymous read-back with the size the server reports. Copy, sync and purge take a dry run. | `UploadError`, `MaintenanceError` |
| `Downloader` | Fetches listed files from a base URL into a directory, given each file's recorded hash; keeps a present file whose hash matches | `DownloadError`, an `AccessError`, naming the URL |
| `Git` | For one checkout: clean or not, tags, fetch, fast-forward, head, commit, tag, push | `MaintenanceError` |
| Metadata source | The bytes of one catalogue file at a location, and where a part lies relative to its base, for paths and URLs alike | `IncompleteCatalog` for an absent part; `CatalogUnavailable` for an unreachable location |

The real adapters are `DcacheStore` (rclone over the WebDAV door, tokens from
`oidc-token`, the dCache REST frontend), `PoochDownloader`, `GitRepository`,
and the metadata sources: files, HTTPS, an in-memory tree, and a caching
decorator that keeps every URL naming no moving ref, such as a release tag, in
the metadata cache. `adapters.fakes` ships one fake per port, so tests, here
and downstream, never leave the machine.

Decision: [ports and fakes for external systems](decisions/0009-ports-and-fakes-for-external-systems.md).

## 5.4 Public API and commands {#interfaces}

The [API reference](../../reference/api/index.md) lists what `ethos_data`
exports; everything else is internal. The command-line reference has every
command, option and exit status: [`ethos-data`](../../reference/cli/ethos-data.md),
[package data commands](../../reference/cli/package-data.md) and
[`ethos-data catalog`](../../reference/cli/catalog.md).
