# Glossary

Key concepts used across `ice2-data`.

## Data

| Term | Meaning |
|---|---|
| **Catalogue** | The institute-wide description of the datasets: paths, sizes, SHA-256 checksums, sources and licences. Exists in two forms — a hand-written **source** catalogue and a generated **published** one — distinguished by `ice2:catalog_role`. |
| **Dataset** | One named body of data in the catalogue, described by a Data Package descriptor. The unit of access class, licensing, and cache-root choice. |
| **Resource** | One file in a dataset, with a path, size, checksum and mediatype. |
| **Resource key** | `"<dataset>/<resource path>"` — a resource's logical identity, stable across tools, and also its path inside the cache. |
| **Collection** | A named slice of the catalogue, defined in a tool's `collections.yaml`: one or more datasets, each narrowed by globs. What a tool actually asks for. |
| **Sidecar** | A companion file that must travel with another to be usable — a shapefile's `.dbf`, `.shx`, `.prj`, `.cpg`. Added automatically to any selection that picks the `.shp`. |
| **Shard** | One slice of a large dataset's inventory, held in `manifests/<prefix>.json` and keyed on a directory prefix, so a selection parses only the shards it can reach. |

## Where bytes live

| Term | Meaning |
|---|---|
| **Public cache** | The shared root for public and internal data — symbolic links to data already on the machine, plus real directories for anything downloaded. Defaults to the per-user OS cache directory. |
| **Restricted cache** | The root for licensed data. Always read in place, never downloaded, never written to. No default: somebody must say where it is. |
| **Staging cache** | An optional root holding uncatalogued work in progress, which shadows the catalogue during development. Not checksummed, never uploaded. |
| **Namespace link** | A symbolic link in the public cache pointing at data already on the machine. Its presence is what marks a dataset as read **in place** rather than downloaded. |
| **Dataset root** | The per-dataset escape hatch (`config set-root`), for a private copy. Wins over everything else. |
| **In place** | Read where it lies, never copied. The mode for links, the restricted cache, staging entries, and configured roots. |
| **Materialize** | Replace a namespace link with a real, checksum-verified copy that the cache owns. |

## Classification

| Term | Meaning |
|---|---|
| **Access class** | `public` (on dCache, world-readable) · `internal` (held by ICE-2, not published) · `restricted` (licensed, may never be copied). Decides which root a dataset resolves from. |
| **Visibility** | `public` or `hidden` — whether a dataset appears in the published catalogue. A separate question from access. |
| **Embargo** | The block required on a `hidden` dataset, stating when it lands, why it is withheld, and what it becomes. Stripped from the published catalogue. |
| **Licence status** | `resolved` once somebody has actually read the upstream terms; `unresolved` until then, which makes every download warn. |
| **Origin** | `downloaded` (mirrored as obtained) · `derived` (computed from other data) · `created` (produced here from scratch). Declared, not inferred; decides whose rights a consumer is dealing with. |
| **Narrowed licence** | A `licenses` entry carrying `ice2:applies_to`, covering only the files its patterns match. Rendered as a resource-level `licenses` override. |
| **Catalogue role** | `source` (hand-written, holds `dataset.yaml` and `source_dir`) or `published` (generated, metadata only). Declared, not inferred. |

## Operations

| Term | Meaning |
|---|---|
| **Plan** | Report what a fetch would download, without touching the network. |
| **Fetch** | Make a collection available locally, downloading only what is missing or hash-mismatched. |
| **Verify** | Compare what is on disk against the manifest — sizes by default, checksums with `--deep`. |
| **Repair** | Re-fetch whatever no longer matches. Cannot repair restricted, staged, or unreachable data. |
| **Publish** | Regenerate the public catalogue from the source one, stripping everything internal. |
| **Namespace** | Build the public cache as a directory of links to data already on this machine. |

## Configuration

| Term | Meaning |
|---|---|
| **Scope** | Where a setting is written: `project` (an `ice2-data.yaml` found by walking up), `user`, `environment` (inside the conda env or venv), or `site` (machine-wide). Precedence runs in that order. |
| **Provenance** | The record of *where* a resolved setting came from. Every lookup carries one, because "why is my data going there?" is the question people actually ask. |
| **Pinned catalogue** | A catalogue URL naming an immutable version. Cached on disk forever. A URL naming `main`, `master`, `HEAD`, `latest`, `dev` or `develop` is recognised as moving and never cached. |
