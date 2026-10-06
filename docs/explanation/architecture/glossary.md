# 12. Glossary

This chapter answers what the terms of this architecture mean. The terms a data
user meets in every guide, such as dataset, resource, collection, named path,
variant, sidecar, shard, access class, visibility, embargo, staging cache and
materialize, are defined in the [glossary](../../reference/glossary.md). The
terms below are the ones the architecture adds, or uses in a narrower sense.

**Data user**, **package maintainer** and **catalogue maintainer** are the roles
of [section 1](introduction-and-goals.md); one person can hold several. The
storage operator, the cluster administrator and the dataset custodian are
supporting roles outside the package.

## Catalogues and releases

| Term | Meaning | Decision |
|---|---|---|
| source catalogue | The hand-written catalogue on JuGit, which the catalogue maintainers keep (`ethos:catalog_role: source`) | [0003][adr-0003] |
| public catalogue | The public view that `catalog publish` generates from the source catalogue, tagged on GitHub at each release (`ethos:catalog_role: published`) | [0027][adr-0027] |
| maintainer's clone | A catalogue maintainer's own clone of the source catalogue, in their own account. Every command that records writes there; the maintainer commits on a branch and merges by merge request on JuGit. | [0026][adr-0026] |
| served checkout | The checkout of the source catalogue's latest release on the cluster computer, which cluster users read. Only `catalog update-checkout` changes it, by fast-forward. | [0026][adr-0026] |
| public checkout | A maintainer's clone of the public catalogue, which `catalog publish` and `catalog release` regenerate | [0027][adr-0027] |
| catalogue release | A tag `vMAJOR.MINOR.PATCH` of both catalogues, stamped in `catalog.yaml`'s `version` and listed in the public index's `ethos:releases`. The three parts are compared as numbers, and the first release is `v1.0.0`. | [0018][adr-0018] |
| major, minor, patch release | What a release changes, judged against the release before it. A patch release changes metadata only: every key resolves to the same bytes under the same access class. A minor release changes data, for example by adding, revising or withdrawing a dataset, or by changing its access class or visibility. A major release starts a retention epoch; no change requires one, and the catalogue maintainers plan and announce it. | [0018][adr-0018] |
| retention | All data that any release of the current major version describes is kept, on dCache and in the copies the caches own. Data is purged only after a major release. | [0018][adr-0018] |
| release bounds | The releases a collections file accepts: `min_version` with an optional `max_version`, or `exact_version`. A bound may be a prefix: `exact_version: v1.3` admits every `v1.3.x`. | [0018][adr-0018] |
| cluster installation | An account on the ICE-2 cluster computer. It reads the served checkout, the cluster's public cache and, if it lists any, the restricted caches its groups admit. | [0028][adr-0028] |
| public installation | Any other machine, a cluster member's laptop and a CI runner included. It reads the public catalogue and its own caches. | [0011][adr-0011] |

## Catalogue files

| Term | Meaning | Decision |
|---|---|---|
| descriptor | A dataset's description: `dataset.yaml`, which people write, and `datapackage.json`, which the build generates | [0006][adr-0006] |
| index | `datacatalog.json`: one row per dataset with the promoted keys, which give access, visibility, totals and licence status without the descriptor | [0005][adr-0005] |
| inventory | A dataset's list of resources, inline in `datapackage.json` or split into shards | [0005][adr-0005] |
| family | A dataset that groups members named `family/member`. It has no files, access class or licences of its own. | [0004][adr-0004] |
| specification | The model in `ethos_data.formats` that defines one file format. Validation, the JSON Schema, the templates and the reference tables derive from it. | [0006][adr-0006] |
| published, promoted, user-facing, inherited | The four properties of a field: kept by `publish`; copied into the index row; printed to users; taken from the family | [0006][adr-0006] |
| strip list | The keys marked unpublished, which `publish` removes | [0027][adr-0027] |
| leak check | The refusal by `publish` of a public tree that names a withheld dataset or holds an unpublished key | [0027][adr-0027] |
| status file | `datasets/<name>/status.yaml`: a dataset's state, build input, copies, authority and history. Only commands write it, and it is never published. | [0022][adr-0022] |

## Reading data

| Term | Meaning | Decision |
|---|---|---|
| handle | The object `ethos_data.collections()` or `ethos_data.catalog()` returns. It holds one settings snapshot, and the catalogue chosen from it. A name under `paths:` is a named path, not a handle in this sense. | [0010][adr-0010] |
| settings file | The one YAML file per account, written by the `config` commands. A file named in `ETHOS_DATA_CONFIG`, such as a lesson's or a CI job's, replaces it. | [0010][adr-0010] |
| settings snapshot | The settings a handle or command reads once, each with its source: argument, environment, settings file or default | [0010][adr-0010] |
| inventory reader | The one component that reads descriptors and inventories, for data users and maintainer commands alike, each part on first need | [0007][adr-0007] |
| metadata source | The port through which catalogue files are read: from files, over HTTPS, through the metadata cache, or from memory | [0007][adr-0007] |
| metadata cache | `<public cache>/.catalog/`: catalogue files read from URLs that name no moving ref, a release tag for example, kept forever | [0005][adr-0005] |
| lookup chain, locator | The five places a file may be read from, in order: staging, bundles, restricted caches, public cache, download. Each locator finds the file, passes, or refuses; the first that finds it decides, and a refusal ends the call before any transfer. | [0012][adr-0012] |
| describe mode | The lookup chain as `plan` and `verify` run it: a refusal becomes "not available here" | [0012][adr-0012] |
| download switch | `download=True` or `ETHOS_DATA_DOWNLOAD=1`: a bundled file whose recorded SHA-256 the catalogue holds for the same key is read through the catalogue route; every other bundled file is read from the bundle | [0021][adr-0021] |
| self-test | `ethos-data selftest`: checks the settings, the catalogue and the files of the example collection that ships with the package | [0017][adr-0017] |

## Where bytes live

| Term | Meaning | Decision |
|---|---|---|
| public cache | Each account's root for public data: links, read in place; copies the cache owns; downloads; and the metadata cache. Default: the per-user cache directory. On the cluster every user sets the same directory, the cluster's public cache: maintainers link project storage into it and materialize copies there, and a missing public file is downloaded into it once, for everyone. | [0028][adr-0028] |
| restricted cache | A directory of restricted data, read in place, whose file permissions admit one access combination, the people who may read the same data: on the cluster, every member of the institute or one licence group; on a workstation, the user alone. The `restricted_caches` setting lists any number, in order. It has no default: an account that reads public data only lists none. | [0011][adr-0011] |
| staging root | The staging cache of the [reference glossary](../../reference/glossary.md), whose directory the `staging_cache` setting (`ETHOS_STAGING_DIR`) names: a personal root with no default, whose entries shadow the catalogue during development. | [0010][adr-0010] |
| cache entry | `<root>/<dataset>/`, or `<root>/<dataset>@<r>/` for a revision r above 1: a link, read in place, or a directory the cache owns | [0004][adr-0004] |
| publication root, publication URL | The dCache folder that holds the published bytes, and its anonymous HTTPS address (`ethos:publication_url`) | [0019][adr-0019] |
| bundle | Selected catalogue datasets kept in a package's repository: their files, descriptions and licence documents, with every file's size and SHA-256 in `bundle.json`. It holds only data with public access, public visibility and settled licensing. It is authoritative for its package, and `bundle export` writes a new one, in this or another repository. | [0020][adr-0020] |
| ahead of the catalogue, behind | Each bundled dataset records the catalogue revision it was last aligned with. A bundle is ahead when it holds changes recorded since then, or a dataset the catalogue does not describe, and behind when the catalogue holds a later revision. Reading it never fails; it warns, once per bundle, until it is realigned. | [0021][adr-0021] |
| realign | Bring a bundle and the catalogue together again: propose the bundle's changes with `<tool>-data propose`, which a catalogue maintainer takes in with `catalog add-bundle` and releases, or take the catalogue's version with `bundle update --from-catalog`. Either way `bundle update` records the new alignment, and the warning stops. | [0021][adr-0021] |

## Dataset lifecycle

| Term | Meaning | Decision |
|---|---|---|
| state, step | Where a dataset stands (`draft`, `built`, `available`, `frozen`, `withdrawn`, `purged`), and a recorded transition between states (see the [lifecycle](runtime.md#dataset-lifecycle)) | [0022][adr-0022] |
| build input | The directory a dataset is built from until it is frozen (`source_dir` in its status file) | [0022][adr-0022] |
| copy, authority | A recorded place of a dataset's bytes (`uploaded`, `linked` or `materialized`); the copy a frozen dataset trusts | [0022][adr-0022] |
| freeze | `catalog record`: make a verified copy the authority and retire the build input | [0022][adr-0022] |
| revision | A new version of a dataset under the same keys. Its changed and new objects lie under `<remote_prefix>@<r>/`, and readers use the entry `<dataset>@<r>/`. | [0019][adr-0019] |
| successor | A new dataset that replaces another: it names it in `ethos:supersedes`, and the build writes `ethos:superseded_by` | [0019][adr-0019] |
| withdraw, purge, tombstone | Take a dataset out of the catalogue; delete its bytes after a major release; the `status.yaml` that stays and keeps the name taken | [0022][adr-0022] |
| check-source | `catalog check-source`: compare a re-download of the originals with the recorded hashes | [0022][adr-0022] |

## Maintenance and code structure

| Term | Meaning | Decision |
|---|---|---|
| pipeline, stage, action, plan, dry run | Every catalogue workflow that writes is a pipeline of stages. Every stage plans, reading only, before any acts; each action with an external effect carries a check; `--dry-run` prints the plan and writes nothing. | [0023][adr-0023] |
| handoff | What one role hands another: a proposal, a problem report, an answer, a release notice or a removal notice, drafted from a template by the command that knows the facts. People post it. | [0025][adr-0025] |
| layer | Model, adapters, services and presentation, from the bottom. A module imports only its own layer and those below. | [0008][adr-0008] |
| service group | Data access and catalogue maintenance, the two groups of services. Catalogue maintenance may use data access, never the reverse. | [0008][adr-0008] |
| port, adapter, fake | The interface to an external system (the store, downloads, metadata sources, git); its real implementation; its implementation for tests, shipped in the package | [0009][adr-0009] |
| facade | The library API of `import ethos_data`: the handles, types, operations and errors | [0008][adr-0008] |
| reporter | The one channel for progress and warnings (`report`); only the command lines print | [0008][adr-0008] |
| typed error | An error class of `ethos_data.errors` that carries its exit status: 2 for a request that cannot be served, 1 for a refused maintenance input | [0008][adr-0008] |
| building block, container, component | A part of the package that [section 5](building-blocks.md) names. A container (C4 level 2) is the library, a command or a data store; a component (level 3) is a part of the library with one responsibility, such as the lookup chain. | [0001][adr-0001] |

[adr-0001]: decisions/0001-arc42-c4-one-file-per-decision.md
[adr-0003]: decisions/0003-one-catalogue-many-collections.md
[adr-0004]: decisions/0004-cache-paths-from-resource-identity.md
[adr-0005]: decisions/0005-lazy-index-descriptors-and-shards.md
[adr-0006]: decisions/0006-every-file-format-specified-once.md
[adr-0007]: decisions/0007-one-inventory-reader.md
[adr-0008]: decisions/0008-four-layers.md
[adr-0009]: decisions/0009-ports-and-fakes-for-external-systems.md
[adr-0010]: decisions/0010-one-settings-file-per-account.md
[adr-0011]: decisions/0011-access-class-picks-the-root.md
[adr-0012]: decisions/0012-one-lookup-chain.md
[adr-0017]: decisions/0017-self-test-collection.md
[adr-0018]: decisions/0018-numbered-catalogue-releases.md
[adr-0019]: decisions/0019-revisions-and-successors.md
[adr-0020]: decisions/0020-repository-bundles.md
[adr-0021]: decisions/0021-bundles-ahead-of-the-catalogue.md
[adr-0022]: decisions/0022-dataset-status-files.md
[adr-0023]: decisions/0023-maintenance-pipelines.md
[adr-0025]: decisions/0025-handoff-templates.md
[adr-0026]: decisions/0026-internal-catalogue-on-the-cluster.md
[adr-0027]: decisions/0027-public-catalogue-releases-on-github.md
[adr-0028]: decisions/0028-one-public-cache-on-the-cluster.md
