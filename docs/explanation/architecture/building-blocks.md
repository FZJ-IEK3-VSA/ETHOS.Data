# 5. Building Block View

This view shows the static decomposition of `ethos-data`. Diagrams use arrows
from a component to a component or interface it depends on. They show important
dependencies rather than every Python import. External libraries and services
are labelled separately. The hierarchy follows arc42's [Building Block View](https://docs.arc42.org/section-5/).

## 5.1 Level 1: overall package

<figure markdown="span">
  ![Level 1 decomposition in four layers. Presentation: the package facade, the command line and the catalogue commands. Services: data access, handoffs and catalogue maintenance, over catalogue and configuration. Adapters: the Store, Downloader and Git ports with real adapters and fakes. Model: formats and model. Arrows point down only.](../../assets/diagrams/architecture-blocks-light.svg#only-light){ .diagram }
  ![Level 1 decomposition in four layers. Presentation: the package facade, the command line and the catalogue commands. Services: data access, handoffs and catalogue maintenance, over catalogue and configuration. Adapters: the Store, Downloader and Git ports with real adapters and fakes. Model: formats and model. Arrows point down only.](../../assets/diagrams/architecture-blocks-dark.svg#only-dark){ .diagram }
</figure>

The package has four layers, and each imports only from the layers below it
(see the decision [Four layers](decisions.md#four-layers-2026-10-02)):

| Layer | Holds | Modules |
|---|---|---|
| Presentation | parsing, wiring, printing, exit statuses | `cli`, `maintain.cli`, the package facade `ethos_data` |
| Services | lookup, fetching, verification, bundles, staging, the maintenance pipelines, the handoffs | `selection`, `access`, `retrieval`, `catalogs`, `config`, `bundles`, `staging`, `verify`, `linking`, `materialize`, `selftest`, `handoffs`, `maintain` |
| Adapters | dCache, downloads and git behind ports, each with a fake | `adapters` |
| Model | the file formats, keys, resources, names, releases, the lifecycle; no input or output | `formats`, `model` |

The typed errors of `errors` and the reporter of `report` are shared by all
four. Library code raises the errors and reports progress through the
reporter; only the presentation prints and chooses an exit status. A test,
`tests/test_layers.py`, holds the rule. Its one exception is
`Collections.main()`, the package command a handle can run, which imports the
command line when it is called.

The decomposition separates obtaining data from publishing it. A caller can use
the reader without invoking upload or publication. The model is the shared
contract: one specification per file format keeps resource identities,
selection rules and the writer's output compatible, and the services on both
sides read the same keys from it. Package wrappers own collection workflows,
bundles and staging. The standalone CLI offers catalogue-key access,
configuration, the commands that administer cache entries (`materialize`,
`link`, `unlink`) and, under `catalog`, the maintenance of a source-catalogue
checkout. The two stay apart because consumers and package developers run the
cache commands on their own machines, independently of the maintainer group,
whereas `catalog` rewrites metadata that a maintainer then reviews and
releases. Both use the same library; there is no copied staging implementation
in RESKit.

| Building block | Responsibility | Main interface | Code within `ethos_data` |
|---|---|---|---|
| Consumer entry points | Compose collection resolution, retrieval, inspection, and cache-entry administration for callers | `collections`, `catalog`, `tool_main`; `Collections.fetch` / `paths` / `plan`, `Catalog.path` / `resources`; `ethos-data ls/fetch/report`, `ethos-data materialize/link/unlink` and a package's command built with `ethos_data.tool_main` | `__init__.py`, consumer handlers and `_add_cache_commands` in `cli.py` |
| Maintainer entry points | Parse the source-catalogue commands and locate the checkout they act on | `ethos-data catalog add/build/upload/record/status/release/remove/...`; `add_catalog_parser`, `dispatch` | `maintain/cli.py`, grafted onto the top-level parser in `cli.py` |
| Data access | Select resources, locate bytes through the lookup chain, download, verify, and support local development | `Collections.resolve`, `download`, `chain_for`, `locate`, `verify`, `materialize`, `apply_staging`, `load_bundle` | `selection.py`, `retrieval.py`, `access.py`, `verify.py`, `materialize.py`, `linking.py`, `staging.py`, `bundles.py` |
| Catalogue maintenance | Accept, build, upload, freeze, release and remove datasets as pipelines; record each step in the dataset's status file; generate public metadata | `Pipeline.plan` / `run`; each command's `run` function; `status.take` | `maintain/` |
| Handoffs | Draft what one role hands another: proposals, problem reports, answers and notices | `propose`, `handoff`, `release_notice`, `removal_notice` | `handoffs.py`, templates in `formats/templates/handoffs/` |
| Catalogue and configuration | Represent lazy metadata and resolve configuration sources | `Catalog`, `Dataset`, `Resource`, `load_catalog`; `Roots` and the settings snapshot | `catalogs.py`, `config.py` |
| Adapters | Reach dCache, the network and git through ports a test can replace | `Store`, `Downloader`, `Git`; `DcacheStore`, `PoochDownloader`, `GitRepository`; the fakes | `adapters/` |
| Formats and model | Specify every file once; hold the rules every reader shares | `FORMATS`, `schema`, `template`, `reference.table`; `lifecycle.step`, `Version`, resource records | `formats/`, `model/` |

## 5.2 Level 2: selected building blocks

### 5.2.1 Data access

<figure markdown="span">
  ![Data access decomposition with Selection, Retrieval, the lookup chain, Staging, Local integrity tools and Repository bundles. The lookup chain reads bundled files first and uses Configuration; Retrieval downloads through the Downloader port; Selection reads the Catalogue model and the staging overlay.](../../assets/diagrams/architecture-reader-light.svg#only-light){ .diagram }
  ![Data access decomposition with Selection, Retrieval, the lookup chain, Staging, Local integrity tools and Repository bundles. The lookup chain reads bundled files first and uses Configuration; Retrieval downloads through the Downloader port; Selection reads the Catalogue model and the staging overlay.](../../assets/diagrams/architecture-reader-dark.svg#only-dark){ .diagram }
</figure>

Selection answers **which resources**; the lookup chain answers **where each
of them is read from, and whether it may be**; Retrieval makes the selected
paths usable. This separation permits a plan to inspect locations without
downloading and explicit verification to inspect files without changing
collection selection.

| Block | Responsibility and interface | Dependencies and important boundary |
|---|---|---|
| Selection (`selection`) | Load collections, expand inheritance and `test`/`full` variants, match resource paths, include sidecars, map `paths` handles to catalogue keys; return `list[Resource]` | Reads Catalogue model; exports `path_matches` also used by the manifest builder |
| Retrieval (`retrieval`) | Produce plans or return `DataFiles`, a mapping from resource keys to paths | Calls the lookup chain; downloads through the `Downloader` port, Pooch by default, grouped by revision; checks in-place file presence |
| Lookup chain (`access`) | One locator per place, in order: dataset roots, staging, bundles, the restricted cache, a link in the public cache, a copy in it, a download. Each answers found, pass or refuse | Uses Catalogue model, Configuration and filesystem state; a refusal ends the chain, so licensed data never falls through to a download |
| Staging (`staging`) | Classify and overlay development entries while preserving official metadata separately | Reads Catalogue model and Configuration; its overlay must be applied before selection of new resources |
| Local integrity tools (`verify`, `materialize`, `linking`) | Report integrity findings, repair eligible managed files, link existing data, or create independent local copies | Reuse resource metadata, the chain and hashing; explicit operations distinct from ordinary fetch; given `--catalog-root`, record the copy in the dataset's status file |
| Repository bundles (`bundles`) | A repository bundle is the source of truth for a family of test data: `bundle create` and `update` keep its inventory and version, and the chain reads its files first, hash-checked. An exported bundle is a copy of catalogue data | Export uses Selection with staging disabled; bundle reads ignore ambient roots and network; explicit `allow_modified` preserves original hashes |
| Catalogue model (`catalogs`, shared block) | Load the index, descriptors, and shards lazily; represent dataset/resource metadata, revisions and successors | Filesystem or HTTP(S) metadata sources |
| Configuration (`config`, shared block) | Resolve roots, per-dataset settings, and configuration origins | Explicit options, environment, the one settings file, and defaults; a handle keeps a snapshot |

Consumer entry points coordinate Selection followed by Retrieval; Selection
does not call Retrieval. The [runtime request diagram](runtime.md#61-data-request)
shows that orchestration. The diagram's Local integrity tools grouping keeps
related explicit operations visible without treating every helper as a component.

### 5.2.2 Catalogue maintenance

<figure markdown="span">
  ![Catalogue maintenance decomposition: maintenance pipelines drive the manifest builder, the public-view generator and the uploader, record every step in the status files, and reach the store and git through ports. Outside the boundary, driven by ethos-data link --all rather than by a catalog subcommand, the Namespace builder creates shared-cache links and uses the same maintainer helpers.](../../assets/diagrams/architecture-maintainer-light.svg#only-light){ .diagram }
  ![Catalogue maintenance decomposition: maintenance pipelines drive the manifest builder, the public-view generator and the uploader, record every step in the status files, and reach the store and git through ports. Outside the boundary, driven by ethos-data link --all rather than by a catalog subcommand, the Namespace builder creates shared-cache links and uses the same maintainer helpers.](../../assets/diagrams/architecture-maintainer-dark.svg#only-dark){ .diagram }
</figure>

The maintainer's workflows are commands whose stages plan before they act,
built on `maintain.pipeline`: `Pipeline.plan` asks every stage what it would
do, reading but never writing, and `run` performs the plan stage by stage, so
`--dry-run` is the plan and an interrupted run, run again, does only what is
left. Building metadata, uploading bytes and generating a public view have
different failure modes and authority requirements, so they stay separate
stages and separate commands that a maintainer can validate and review. Their
shared contract is the catalogue's resource inventory, not an implicit copy
of every file found beside a dataset, and their shared record is the
dataset's status file.

| Command | Pipeline stages | Module |
|---|---|---|
| `catalog add SOURCE` | intake, place, build | `maintain.accept` |
| `catalog add-bundle DIR` | update | `maintain.bundle_intake` |
| `catalog record NAME` | check, freeze | `maintain.freeze` |
| `catalog check-source NAME DIR` | compare, record | `maintain.provenance` |
| `catalog build NAME --revision` | compare, revise | `maintain.revision` |
| `catalog release VERSION` | check, stamp, commit, public, push, store, notices | `maintain.release` |
| `catalog remove NAME` | withdraw, index | `maintain.remove` |
| `catalog remove NAME --purge` | check, cache, store, tombstone | `maintain.remove` |
| `catalog update-checkout` | fetch, advance, check | `maintain.checkout` |

Linking existing storage is drawn **outside** the `catalog` boundary, and the
figure means it literally: `dispatch()` in `maintain/cli.py` has no branch
that reaches the namespace builder. The planner still reads a source checkout
the way `build` and `publish` do, and still uses the same maintainer helpers —
which is the one edge crossing into the boundary — but `ethos-data link --all`
drives it and nothing else does. Filling a whole cache from a checkout and
pointing a single dataset at a directory are the same job at two scales, and
keeping them in separate command groups made the smaller one look like an
unrelated maintainer operation.

`_link_all_command` in `cli.py` resolves the cache root to build before calling
the planner, so that the planner is handed an answer rather than asked to repeat
a lookup that could come out differently and write a complete link tree into a
directory nobody named. It is a required argument with no default.

| Block | Responsibility and interface | Dependencies and output |
|---|---|---|
| Maintenance pipelines (`maintain.pipeline` and the command modules) | Plan, then run, the stages of each workflow above | Every other block; the ports for the store and git |
| Manifest builder (`maintain.manifest`) | Build/check descriptors, hashes, indexes, and shards from source descriptions; carry revisions and write `ethos:superseded_by` | Shared `path_matches` and the format specifications; source filesystem and YAML → generated JSON |
| Uploader (`maintain.upload`) | Preflight selected datasets, expand manifest resources, transfer and check remote access, record the copy | Maintainer helpers; the `Store` port, today's dCache through rclone and oidc-agent, and the storage HTTP interfaces; structured per-dataset results |
| Public-view generator (`maintain.publish`) | Filter visibility, strip internal fields, copy referenced shards and licences, run the leak check, write the issue templates | Generated source metadata → target public checkout; does not upload bytes; a release commits and tags it |
| Status files (`maintain.status`) | Read and write `status.yaml`, check each step against the lifecycle of `model.lifecycle`, show where each dataset stands | The status-file format; every command that takes a step |
| Namespace builder (`maintain.namespace`) | Plan and apply shared-cache symbolic links to existing local source trees | Driven by `ethos-data link --all`, never by a `catalog` subcommand; maintainer helpers; source YAML and a namespace root → namespace plan/links |
| Maintainer helpers (`maintain.__init__`) | Find catalogue roots, read descriptors, and interpret dataset directories and inventory resources | Common source-layout rules used by the other blocks |

`check-store` is a diagnostic entry point using the packaged shell script, rather
than a publication stage. See [Maintainer API reference](../../reference/api/maintain.md)
for callable signatures and [Runtime View](runtime.md#63-catalogue-lifecycle) for
ordering, review boundaries, and failures.

### Shared contracts to preserve

`Resource.key` and derived cache paths connect independently developed consuming
packages. Changing their meaning is a compatibility change. Reader and writer
must agree on path matching, descriptor extensions, and shard structure; both
take them from the format specifications in `ethos_data.formats`, which also
generate the JSON Schemas and the tables of [File formats](../../reference/schemas.md).
Public metadata generation must preserve required reader fields while
stripping the fields the specifications mark as never published.

Location decisions are shared by retrieval and integrity operations, through
one lookup chain. The repository bundle workflow preserves ordinary cache
checks and published resource identity while making temporary divergence
explicit. See [Crosscutting Concepts](crosscutting-concepts.md).

The [API reference](../../reference/api/index.md) contains signatures;
[File formats](../../reference/schemas.md) defines fields; and
[Contributing](../../contributing.md) describes the change workflow.
