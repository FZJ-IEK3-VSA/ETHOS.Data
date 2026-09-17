# 5. Building Block View

This view shows the static decomposition of `ethos-data`. Diagrams use arrows
from a component to a component or interface it depends on. They show important
dependencies rather than every Python import. External libraries and services
are labelled separately. The hierarchy follows arc42's [Building Block View](https://docs.arc42.org/section-5/).

## 5.1 Level 1: overall package

<figure markdown="span">
  ![Level 1 decomposition: APIs, package wrappers and the key CLI call Data access; catalogue/cache entry points call maintenance; both use Catalogue and configuration. Catalogue maintenance shares path matching with Data access.](../../assets/diagrams/architecture-blocks-light.svg#only-light){ .diagram }
  ![Level 1 decomposition: APIs, package wrappers and the key CLI call Data access; catalogue/cache entry points call maintenance; both use Catalogue and configuration. Catalogue maintenance shares path matching with Data access.](../../assets/diagrams/architecture-blocks-dark.svg#only-dark){ .diagram }
</figure>

The decomposition separates obtaining data from publishing it. A caller can use
the reader without invoking upload or publication. The shared metadata contract
keeps resource identities, selection rules, and writer output compatible.
Entry points compose these responsibilities and translate results into Python
objects or command-line output. Package wrappers own collection workflows,
bundles and staging. The standalone CLI offers catalogue-key access,
configuration, the commands that administer cache entries (`materialize`,
`link`, `unlink`) and, under `catalog`, the maintenance of a source-catalogue
checkout. The two stay apart because consumers and package developers run the
cache commands on their own machines, independently of the maintainer group,
whereas `catalog` rewrites metadata that a maintainer then reviews and
publishes. Both use the same library; there is no copied staging implementation
in RESKit.

| Building block | Responsibility | Main interface | Code within `ethos_data` |
|---|---|---|---|
| Consumer entry points | Compose collection resolution, retrieval, inspection, and cache-entry administration for callers | `collections`, `catalog`, `tool_main`; `Collections.fetch` / `paths` / `plan`, `Catalog.path` / `resources`; `ethos-data ls/fetch`, `ethos-data materialize/link/unlink` and a package's command built with `ethos_data.tool_main` | `__init__.py`, consumer handlers and `_add_cache_commands` in `cli.py` |
| Maintainer entry points | Parse the source-catalogue commands and locate the checkout they act on | `ethos-data catalog build/publish/upload/check-store`; `add_catalog_parser`, `dispatch` | `maintain/cli.py`, grafted onto the top-level parser in `cli.py` |
| Data access | Select resources, locate bytes, download, verify, and support local development | `Collections.resolve`, `download`, `locate`, `verify`, `materialize`, `apply_staging`, `load_bundle` | `selection.py`, `retrieval.py`, `access.py`, `verify.py`, `materialize.py`, `staging.py`, `bundles.py` |
| Catalogue maintenance | Build inventories, transfer manifest-listed files, generate public metadata, and plan the shared-cache namespace that `ethos-data link --all` drives | Per-command `run` functions; generated metadata and upload results | `maintain/manifest.py`, `upload.py`, `publish.py`, `namespace.py`, helpers in `maintain/__init__.py` and `maintain/scripts/` |
| Catalogue and configuration | Represent lazy metadata and resolve configuration sources | `Catalog`, `Dataset`, `Resource`, `load_catalog`; `Roots` and setting resolvers | `catalogs.py`, `config.py` |

## 5.2 Level 2: selected building blocks

### 5.2.1 Data access

<figure markdown="span">
  ![Data access decomposition with Selection, Retrieval, Access policy, Staging, Repository bundles, and Local integrity tools. Dependencies connect them to the Catalogue model, Configuration, and external Pooch and filesystem.](../../assets/diagrams/architecture-reader-light.svg#only-light){ .diagram }
  ![Data access decomposition with Selection, Retrieval, Access policy, Staging, Repository bundles, and Local integrity tools. Dependencies connect them to the Catalogue model, Configuration, and external Pooch and filesystem.](../../assets/diagrams/architecture-reader-dark.svg#only-dark){ .diagram }
</figure>

Selection answers **which resources**; Access policy answers **where and whether
those resources are available**; Retrieval makes the selected paths usable. This
separation permits a plan to inspect locations without downloading and explicit
verification to inspect files without changing collection selection.

| Block | Responsibility and interface | Dependencies and important boundary |
|---|---|---|
| Selection (`selection`) | Load collections, expand inheritance and `test`/`full` variants, match resource paths, include sidecars, map `paths` handles to catalogue keys; return `list[Resource]` | Reads Catalogue model; exports `path_matches` also used by the manifest writer |
| Retrieval (`retrieval`) | Produce plans or return `DataFiles`, a mapping from resource keys to paths | Calls Access policy; delegates verified downloads to external Pooch; checks in-place file presence |
| Access policy (`access`) | Produce `Location` decisions: in-place, download, or unavailable | Uses Catalogue model, Configuration, and filesystem state; enforced before downloads |
| Staging (`staging`) | Classify and overlay development entries while preserving official metadata separately | Reads Catalogue model and Configuration; its overlay must be applied before selection of new resources |
| Local integrity tools (`verify`, `materialize`) | Report integrity findings, repair eligible managed files, or create independent local copies | Reuse resource metadata, access rules, and hashing; explicit operations distinct from ordinary fetch |
| Repository bundles (`bundles`) | Export selected canonical public resources and metadata; load, hash-check, and use the local copy through `Bundle.fetch` | Uses Selection with staging disabled at export; local reads ignore ambient roots and network; explicit `allow_modified` preserves original hashes |
| Catalogue model (`catalog`, shared block) | Load the index, descriptors, and shards lazily; represent dataset/resource metadata | Filesystem or HTTP(S) metadata sources |
| Configuration (`config`, shared block) | Resolve roots, per-dataset settings, and configuration origins | Explicit options, environment, configuration files, and defaults |

Consumer entry points coordinate Selection followed by Retrieval; Selection
does not call Retrieval. The [runtime request diagram](runtime.md#61-data-request)
shows that orchestration. The diagram's Local integrity tools grouping keeps
related explicit operations visible without treating every helper as a component.

### 5.2.2 Catalogue maintenance

<figure markdown="span">
  ![Catalogue maintenance decomposition: Manifest builder reads source files and writes metadata; Uploader transfers listed files through rclone and verifies through HTTP; Public-view generator filters metadata. Outside the boundary, driven by ethos-data link --all rather than by a catalog subcommand, the Namespace builder creates shared-cache links and uses the same maintainer helpers.](../../assets/diagrams/architecture-maintainer-light.svg#only-light){ .diagram }
  ![Catalogue maintenance decomposition: Manifest builder reads source files and writes metadata; Uploader transfers listed files through rclone and verifies through HTTP; Public-view generator filters metadata. Outside the boundary, driven by ethos-data link --all rather than by a catalog subcommand, the Namespace builder creates shared-cache links and uses the same maintainer helpers.](../../assets/diagrams/architecture-maintainer-dark.svg#only-dark){ .diagram }
</figure>

Building metadata, uploading bytes and generating a public view have different
failure modes and authority requirements. They remain separate `catalog`
subcommands so maintainers can validate and review each output. Their shared
contract is the catalogue's resource inventory, not an implicit copy of every file
found beside a dataset.

Linking existing storage is drawn **outside** that boundary, and the figure means
it literally: `dispatch()` in `maintain/cli.py` routes `build`, `publish`,
`upload` and `check-store`, and has no branch that reaches the namespace builder.
The planner still reads a source checkout the way `build` and `publish` do, and
still uses the same maintainer helpers — which is the one edge crossing into the
boundary — but `ethos-data link --all` drives it and nothing else does. Filling a
whole cache from a checkout and pointing a single dataset at a directory are the
same job at two scales, and keeping them in separate command groups made the
smaller one look like an unrelated maintainer operation.

`_link_all_command` in `cli.py` resolves two things before calling the planner.
The cache root to build, so that the planner is handed an answer rather than
asked to repeat a lookup that could come out differently and write a complete
link tree into a directory nobody named. And what that root *is* — this
installation's public cache, its restricted cache, or a directory it cannot
identify — because whether a link the namespace must not hold may be *removed*
depends on the answer, and a planner that infers it from a path will be wrong in
the direction that deletes. Both are required arguments with no defaults.

| Block | Responsibility and interface | Dependencies and output |
|---|---|---|
| Manifest builder (`maintain.manifest`) | Build/check descriptors, hashes, indexes, and shards from source descriptions | Shared `path_matches` and catalogue format constants; source filesystem and YAML → generated JSON |
| Uploader (`maintain.upload`) | Preflight selected datasets, expand manifest resources, transfer and check remote access | Maintainer helpers; external rclone, oidc-agent, and storage HTTP interfaces; structured per-dataset results |
| Public-view generator (`maintain.publish`) | Filter visibility, strip internal fields, copy referenced shards and licences | Generated source metadata → target public checkout; does not upload bytes or create a release |
| Namespace builder (`maintain.namespace`) | Plan and apply shared-cache symbolic links to existing local source trees; report what the cache already holds that the catalogue no longer allows | Driven by `ethos-data link --all`, never by a `catalog` subcommand; maintainer helpers; source YAML, a namespace root and what that root is → namespace plan/links |
| Maintainer helpers (`maintain.__init__`) | Find catalogue roots and interpret dataset directories and inventory resources | Common source-layout rules used by the other blocks |

`check-store` is a diagnostic entry point using the packaged shell script, rather
than a publication stage. See [Maintainer API reference](../../reference/api/maintain.md)
for callable signatures and [Runtime View](runtime.md#63-catalogue-lifecycle) for
ordering, review boundaries, and failures.

### Shared contracts to preserve

`Resource.key` and derived cache paths connect independently developed consuming
packages. Changing their meaning is a compatibility change. Reader and writer
must agree on path matching, descriptor extensions, and shard structure. Public
metadata generation must preserve required reader fields while stripping the
specified internal fields.

Location decisions are shared by retrieval and integrity operations. The repository bundle
workflow preserves ordinary cache checks and published resource identity while
making temporary divergence explicit. See [Crosscutting Concepts](crosscutting-concepts.md).

The [API reference](../../reference/api/index.md) contains signatures;
[File formats](../../reference/schemas.md) defines fields; and
[Contributing](../../contributing.md) describes the change workflow.
