# Adding a dataset to the catalogue

Tools never describe files themselves — they only say which datasets they
need (in their own `collections.yaml`), so a dataset shared by several tools
is described once here and downloaded once into a shared cache. This is the
maintainer-side workflow for adding one. Uploading the bytes once it's
described is [UPLOAD.md](UPLOAD.md); using it from a tool is
[USING-IN-A-LIBRARY.md](USING-IN-A-LIBRARY.md) in `ice2-data`.

## 1. Describe it

```bash
mkdir datasets/my-dataset
```

`datasets/my-dataset/dataset.yaml`:

```yaml
name: my-dataset
title: A short human-readable title
description: >-
  What this is, and what it is used for.

# Where the files are on YOUR machine, for building the inventory.
# Never published.
source_dir: /benchtop/shared_data/MyDataset

# Who may read the bytes:  public | internal | restricted
ice2:access: public
# Whether the dataset is listed in the public catalogue:  public | hidden
ice2:visibility: public

# Folder name on the public store. Omit for restricted data.
ice2:remote_prefix: my-dataset

sources:
  - title: Where the data originally came from
    path: https://doi.org/...

licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/

ice2:retrieved: "2026-09-01"
ice2:contact: your-username
```

Leave out `licenses:` and add `ice2:license_status: unresolved` if the
redistribution terms haven't been checked yet — an absent licence is a
question, not a default, and `fetch()` warns on every download until someone
answers it.

**A large dataset** (tens of thousands of files, e.g. a gridded time series)
should shard: add `ice2:shard_depth: N` and the inventory is split into
`manifests/<directory-prefix>.json` files instead of one array, so selecting
one tile doesn't parse the whole thing. `ice2:shard_depth: 2` on
`era5-like/2020/temperature.nc` shards on `era5-like/2020`.

## 2. Build the inventory

```bash
ice2-catalog build my-dataset
```

Walks `source_dir`, computes a SHA-256 per file, and writes
`datapackage.json` (and `manifests/*.json` if sharded). **Never hand-edit
either — regenerate them.**

It also drags shapefile companions in automatically: selecting a `.shp`
brings its `.shx`, `.dbf`, `.prj`, `.cpg` (etc.) along, and excludes VCS
plumbing, `__pycache__`, and root `README*`/`LICENSE*`/`CHANGELOG*` from the
manifest.

```bash
ice2-catalog build            # rebuild every dataset
ice2-catalog build --check     # CI: fail if any manifest is stale
```

## 3. Upload it, if it's public

See [UPLOAD.md](UPLOAD.md). Short version:

```bash
ice2-catalog upload my-dataset --dry-run
ice2-catalog upload my-dataset
```

**Never overwrite a file at an already-published path.** A revision gets a
new path — that's what lets an update reuse every unchanged file instead of
forcing a full re-download.

## 4. Publish the catalogue entry

```bash
ice2-catalog publish ../ice2-data-catalog
```

Regenerates the public catalogue from every dataset marked
`ice2:visibility: public` — `datacatalog.json`, each public
`datasets/<name>/datapackage.json` (with `source_dir`, `ice2:embargo` and
`ice2:license_note` stripped), and the README table. Anything it no longer
generates (a withdrawn dataset, a stray file) is deleted from the target, so
the public repo never drifts from what this command would produce. Commit
and push both repositories.

**Only ever point this at the public repo (`../ice2-data-catalog`).** It
wipes everything in its target except `.git` before regenerating — running
it against this repo itself, or with the wrong path, deletes every
hand-written `dataset.yaml`, `catalog.yaml` and file this repo isn't
generated from. If that happens: anything git-tracked comes back with `git
checkout HEAD -- <path>`; anything that was only ever a working-tree file
(never committed) does not.

## 5. Let a tool ask for it

In the tool's `collections.yaml`:

```yaml
collections:
  offshore_siting:
    title: Constraint layers for offshore siting
    include:
      - dataset: my-dataset
        files: ["*.shp"]
```

`files` accepts globs — `*` matches within one path segment, `**` matches any
depth, and omitting `files` (or `["**"]`) takes everything. Collections can
build on each other with `extends: [other_collection]`. See
[USING-IN-A-LIBRARY.md](USING-IN-A-LIBRARY.md) for the full
pattern, including how a Python package like RESKit wraps this.

## Data that isn't ready to publish

Set `ice2:visibility: hidden` and say why:

```yaml
ice2:access: internal
ice2:visibility: hidden
ice2:embargo:
  until: "2027-06-30"          # or "unspecified", with a reason
  reason: "Pending publication of the accompanying paper"
  becomes: public
```

It's then usable by colleagues from the internal catalogue, but
`ice2-catalog publish` withholds it from the public one — the `embargo` block
is required so nothing stays hidden by accident.

**Releasing it later is two edits.** Change `ice2:access` and
`ice2:visibility` to `public`, delete the `ice2:embargo` block, then repeat
steps 3–4. The dataset name and every checksum stay the same, so everything
that already referenced it keeps working.

## Two rules that matter

**Paths are immutable.** Never overwrite a file at a path that has already
been published (see step 3).

**An absent licence is a question, not a default.** `ice2:license_status:
unresolved` until somebody has actually read the upstream terms and added a
`licenses:` block with an
[Open Definition licence id](http://licenses.opendefinition.org/).
