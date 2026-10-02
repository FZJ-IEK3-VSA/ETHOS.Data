# Glossary

Key concepts used across `ethos-data`.

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

## Where bytes live

| Term | Meaning |
|---|---|
| **Public cache** | The shared root for public and internal data — symbolic links to data already on the machine, plus real directories for anything downloaded. Defaults to the per-user OS cache directory. |
| **Restricted cache** | The root for authorised licensed data. Retrieval reads it in place and never downloads it; explicit local administration can create entries. No built-in default. |
| **Staging cache** | An optional root holding uncatalogued work in progress, which shadows the catalogue during development. Not checksummed, never uploaded. |
| **Namespace link** | A symbolic link in the public cache pointing at data already on the machine. Its presence is what marks a dataset as read **in place** rather than downloaded. |
| **Dataset root** | The per-dataset escape hatch (`config set-root`), for a private copy. Wins over everything else. |
| **In place** | Read where it lies, never copied. The mode for links, the restricted cache, staging entries, and configured roots. |
| **Materialize** | Replace a namespace link with a real, checksum-verified copy that the cache owns. |

## Classification

| Term | Meaning |
|---|---|
| **Access class** | `public` (on dCache, world-readable) · `internal` (held by ICE-2, not published) · `restricted` (licensed, read from authorised local storage). Decides which root a dataset resolves from. |
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
| **Repair** | Re-fetch whatever no longer matches. Cannot repair restricted, staged, or unreachable data. |
| **Publish** | Regenerate the public catalogue from the source one, stripping everything internal. |
| **Namespace** | Build the public cache as a directory of links to data already on this machine. |

## Configuration

| Term | Meaning |
|---|---|
| **Settings file** | The one file the settings are read from and written to: the file `ETHOS_DATA_CONFIG` names, else the one in the account. See [Where the settings are stored](../how-to/data-users/set-up-your-machine.md#settings-file). |
| **Provenance** | The record of *where* a resolved setting came from. Every lookup carries one, because "why is my data going there`" is the question people actually ask. |
| **Pinned catalogue** | A catalogue URL naming an immutable version. Cached on disk forever. A URL naming `main`, `master`, `HEAD`, `latest`, `dev` or `develop` is recognised as moving and never cached. |

## Installations

| Term | Meaning |
|---|---|
| **Cluster installation** | An account on the ICE-2 cluster computer. Reads the internal catalogue and the shared public and restricted caches; restricted data is read in place by group membership. |
| **Public installation** | Any other machine, a laptop, a workstation or a CI runner, whoever owns it. Reads the public catalogue and its own cache; restricted data is reachable only as a copy the user registers. |
| **`<your-tool>-data`** | The placeholder the guides use for a package's data command, built with `ethos_data.tool_main`; `your_tool.data` is the matching Python module. Each package ships it under its own name. |
