# Glossary

Key concepts used across `ethos-data`.

!!! warning "Gap: some terms describe the target"
    These terms describe the [target architecture](../explanation/architecture/glossary.md),
    which the code does not have yet: one **bundle** format and a bundle
    **ahead of the catalogue**, **release** and **withdraw** with
    `catalog release` and `catalog remove`, **status files** and **dataset
    states**, **pipelines** and **handoffs**. The code has only bundles
    exported from the catalogue, and none of those commands.

## Data

| Term | Meaning |
|---|---|
| **Catalogue** | The institute-wide description of the datasets: paths, sizes, SHA-256 checksums, sources and licences. Exists in two forms — a hand-written **source** catalogue and a generated **published** one — distinguished by `ethos:catalog_role`. |
| **Dataset** | One named body of data in the catalogue, described by a Data Package descriptor. The unit of access class, licensing, and cache-root choice. |
| **Resource** | One file in a dataset, with a path, size, checksum and mediatype. |
| **Resource key** | `"<dataset>/<resource path>"` — a resource's logical identity, stable across tools, and also its path inside the cache. |
| **Collection** | A named slice of the catalogue, defined in a tool's `collections.yaml`: one or more datasets, each narrowed by globs. What a tool actually asks for. |
| **Named path** | A handle a collection maps to a catalogue key under `paths:` — `era5`, `gwa_100m` — so a workflow's caller asks for an input by name and never sees a resource key. Resolved to `{handle: absolute path}` by `ethos_data.paths()` and `<your-tool>-data fetch --paths`. |
| **Variant** | One of the two selections a collection may define under `test:` and `full:`: a small selection that runs an example or a test in seconds, and the real inputs. Both must offer the same named paths. `full` is the default; `test=True` / `--test` selects the other. |
| **Sidecar** | A companion file that must travel with another to be usable — a shapefile's `.dbf`, `.shx`, `.prj`, `.cpg`. Added automatically to any selection that picks the `.shp`. |
| **Shard** | One slice of a large dataset's inventory, held in `shards/<prefix>.json` and keyed on a directory prefix, so a selection parses only the shards it can reach. |
| **Revision** | A new version of a dataset's bytes under the same keys, published beside the old ones in `<remote_prefix>@<revision>/` and cached in `<dataset>@<revision>/`. A catalogue release names one revision of each dataset. |
| **Successor** | A new dataset that replaces another whose layout changed, naming it in `ethos:supersedes`; the replaced one stays, shown as superseded. |

## Where bytes live

| Term | Meaning |
|---|---|
| **Public cache** | Each account's root for public data — symbolic links to data already on the machine, plus real directories for anything downloaded or materialized. Defaults to the per-user OS cache directory. On the cluster every user sets the same shared directory, **the cluster's public cache**, so a public file is downloaded once for everyone. |
| **Restricted cache** | A root for restricted data, read in place and never downloaded into. Its file permissions admit one access combination, the people who may read the same data, such as every member of the institute or one licence group. An account lists any number, in order; none by default. |
| **Staging cache** | An optional root holding uncatalogued work in progress, which shadows the catalogue during development. Not checksummed, never uploaded. |
| **Bundle** | Selected catalogue datasets that a package keeps in its repository: their files, descriptions, licence documents and attribution, with every file's size and SHA-256 in `bundle.json`. It holds public, visible data with settled licensing only. It is authoritative for its package, which reads it before the caches; `bundle export` writes a new bundle, for this or another repository. |
| **Ahead of the catalogue** | A bundle is ahead when it holds a recorded change the catalogue has not accepted, or a dataset the catalogue does not describe, and **behind** when the catalogue holds a later revision. Either way it is read as it is, with a warning once per bundle, until it is **realigned**: the catalogue takes its changes, proposed with `<your-tool>-data propose`, or it takes the catalogue's version with `bundle update --from-catalog`. |
| **Namespace link** | A symbolic link in the public cache pointing at data already on the machine. Its presence is what marks a dataset as read **in place** rather than downloaded. |
| **In place** | Read where it lies, never copied. The mode for links, restricted caches, staging entries and bundles. |
| **Materialize** | Replace a namespace link with a real, checksum-verified copy that the cache owns. |

## Classification

| Term | Meaning |
|---|---|
| **Access class** | `public` (published on dCache, world-readable) · `restricted` (not published: licensed data, and data the institute holds without publishing it; read in place from a restricted cache, never downloaded). Decides which root a dataset resolves from. |
| **Visibility** | `public` or `hidden` — whether a dataset appears in the published catalogue. A separate question from access. |
| **Embargo** | The block required on a `hidden` dataset, stating when it lands, why it is withheld, and what it becomes. Stripped from the published catalogue. |
| **Licence status** | `resolved` once somebody has actually read the upstream terms; `unresolved` until then, which makes every download warn. |
| **Origin** | `downloaded` (mirrored as obtained) · `derived` (computed from other data) · `created` (produced here from scratch). Declared, not inferred; decides whose rights a consumer is dealing with. |
| **Narrowed licence** | A `licenses` entry carrying `ethos:applies_to`, covering only the files its patterns match. Rendered as a resource-level `licenses` override. |
| **Catalogue role** | `source` (hand-written, holds `dataset.yaml` and `source_dir`) or `published` (generated, metadata only). Declared, not inferred. |
| **Status file** | A dataset's `status.yaml` in the source catalogue, written by the commands: its state, its build input, the copies of its bytes and the history of every step taken. Never published. |
| **Dataset state** | Where a dataset stands: `draft`, `built`, `available`, `frozen`, `withdrawn` or `purged`. Each command checks its step against it. |
| **Frozen** | A dataset whose inventory is final: its build input is retired, its authoritative copy recorded, and a rebuild keeps the recorded hashes. |

## Operations

| Term | Meaning |
|---|---|
| **Plan** | Report what a fetch would download; resolving remote metadata may require network access. |
| **Fetch** | Make a collection available locally, downloading only what is missing or hash-mismatched. |
| **Verify** | Compare what is on disk against the manifest — sizes by default, checksums with `--deep`. |
| **Repair** | Download a damaged copy again into the public cache. Never removes or replaces a link, and never touches restricted or staged data: a broken link is only reported. |
| **Publish** | Regenerate the public catalogue from the source one, stripping everything internal. |
| **Namespace** | Build the public cache as a directory of links to data already on this machine. |
| **Release** | One version of both catalogues, `vMAJOR.MINOR.PATCH`, made by `ethos-data catalog release VERSION`: stamped, committed, tagged and published. A **patch** release changes metadata only, a **minor** release changes data, and a **major** release opens the purge of data withdrawn before it. A collections file's **release bounds** say which releases a package accepts. |
| **Withdraw** | Take a dataset out of the catalogue, metadata first, with `catalog remove`. Its bytes stay until the next major release; after it, a **purge** may delete them, and only its status file is left. |
| **Pipeline** | A maintainer command made of stages, each of which plans what it would do before any of them acts, so `--dry-run` shows the plan and a rerun does only what is left. |
| **Handoff** | What one role hands another — a proposal, a problem report, an answer or a notice — drafted from a template by the command that knows the facts. |

## Configuration

| Term | Meaning |
|---|---|
| **Settings file** | The one file the settings are read from and written to: the file `ETHOS_DATA_CONFIG` names, else the one in the account. It holds `public_cache`, `restricted_caches`, `staging_cache`, `catalog` and `publication_url`. See [Where the settings are stored](../how-to/data-users/set-up-your-machine.md#settings-file). |
| **Provenance** | The record of *where* a resolved setting came from. Every lookup carries one, because "why is my data going there`" is the question people actually ask. |
| **Pinned catalogue** | A catalogue URL naming an immutable version. Cached on disk forever. A URL naming `main`, `master`, `HEAD`, `latest`, `dev` or `develop` is recognised as moving and never cached. |

## Installations

| Term | Meaning |
|---|---|
| **Cluster installation** | An account on the ICE-2 cluster computer. Reads the internal catalogue, the cluster's public cache and, if it lists any, the restricted caches its groups admit. |
| **Public installation** | Any other machine, a laptop, a workstation or a CI runner, whoever owns it. Reads the public catalogue and its own cache; restricted data is reachable only as a copy the user registers. |
| **`<your-tool>-data`** | The placeholder the guides use for a package's data command, built with `ethos_data.tool_main`; `your_tool.data` is the matching Python module. Each package ships it under its own name. |
