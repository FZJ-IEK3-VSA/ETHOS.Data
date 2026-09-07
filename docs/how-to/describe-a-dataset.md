# Describe a dataset

A dataset is described once, in the source catalogue
(`ice2-data-catalog-internal`), by a hand-written `dataset.yaml` plus a
generated manifest. Tools never describe files themselves — they only say which
datasets they need. For the whole round trip in order, see
[Add a dataset to the catalogue](../tutorials/add-a-dataset.md).

## `dataset.yaml`

`datasets/<name>/dataset.yaml`:

```yaml
name: my-dataset
title: A short human-readable title
description: >-
  What this is, and what it is used for.

# Where the files are on YOUR machine, for building the inventory.
# Never published.
source_dir: /benchtop/shared_data/MyDataset

ice2:access: public          # public | internal | restricted
ice2:visibility: public      # public | hidden
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

Every key is documented in [File formats](../reference/schemas.md). The two
that decide behaviour:

**`ice2:access`** — who may read the bytes, and therefore which cache root the
dataset resolves from. `public` is on dCache with `o+rx`; `internal` is held by
ICE-2 and not published; `restricted` is licensed and may never be copied. See
[Caches, classes and roots](../explanation/caches-and-access.md).

**`ice2:visibility`** — whether the dataset is listed in the public catalogue at
all. `hidden` requires an `ice2:embargo` block, so nothing stays hidden by
accident.

## Narrowing the inventory

`ice2-data catalog build` inventories everything under `source_dir`. That is fine for
a directory somebody created for the dataset, and wrong for the common case: a
shared download directory that also holds the zip the data was extracted from,
a `wget-log`, and a colleague's test clip — on storage you may not have the
write access, or the standing, to tidy up.

Narrow the inventory instead of moving files:

```yaml
# Only these are the dataset. Everything else under source_dir is ignored.
ice2:include:
  - "wind_speed_cog_10m.tif"
  - "wind_speed_cog_*0m.tif"

# Or keep everything except the strays.
ice2:exclude:
  - "**/*.zip"        # the download archives, duplicates of what was extracted
  - "test"            # a whole folder
  - "wget-log"
```

Patterns are matched against the path **relative to `source_dir`**, by the same
code that resolves a collection's `files:` — `*` matches within one path
segment, `**` matches any depth. Two conveniences on top:

- a pattern with **no wildcard** means that path *and everything under it*, so
  naming a folder does the obvious thing;
- a **trailing slash** means the subtree only, for when a file and a folder
  share a name.

Both keys are optional and can be combined; `ice2:exclude` is applied after
`ice2:include`.

### The asymmetry is deliberate

| | If it matches nothing |
|---|---|
| `ice2:include` | **fails the build**, naming the pattern |
| `ice2:exclude` | warns only |

A typo, or a file renamed upstream, must not silently shrink a published
dataset. But the stray an `exclude` named may have been cleaned up since, and
failing the build for a cleanup that happened would be perverse.

Shapefile companions are pulled back in automatically, so
`ice2:include: ["*.shp"]` still yields a readable shapefile.

### Two datasets, one `source_dir`

Because the filter is per dataset, two datasets may share one `source_dir` and
each describe its own half. That is how `global-wind-atlas` and
`global-wind-atlas-era5-expanded` both live in `GWA_4.0` without either seeing
the other's files.

## Build the manifest

```bash
ice2-data catalog build my-dataset       # one dataset
ice2-data catalog build                  # all of them
ice2-data catalog build --check          # CI: fail if any manifest is stale
```

This walks `source_dir`, computes a SHA-256 per file, and writes
`datapackage.json` (and `manifests/*.json` if sharded). It reports how many
files each filter removed, so the number is never a surprise.

Excluded automatically, without being asked: VCS plumbing, `__pycache__`, and
root `README*` / `LICENSE*` / `CHANGELOG*`.

!!! warning "Never hand-edit a manifest"
    `datapackage.json` and everything under `manifests/` are generated. Fix
    `dataset.yaml` and rebuild. `--check` in CI is what keeps that true.

## Sharding a large dataset

A dataset of tens of thousands of files — a gridded time series, say — should
shard:

```yaml
ice2:shard_depth: 2
```

The inventory is then split into `manifests/<directory-prefix>.json` files, one
per directory prefix of that many segments, instead of a single array. With
depth 2, `era5-like/2020/temperature.nc` shards on `era5-like/2020`.

The payoff is on the consumer side: selecting `4/6/5/**` parses the 664
resources of that one tile rather than all 170,000. Sharding is transparent —
code that asks for the whole inventory still gets it. See
[sharding](../explanation/catalogue-format.md#sharding).

Files sitting at the dataset root, above any shard directory, land in a
`_root` shard.

## Datasets that are not ready to publish

```yaml
ice2:access: internal
ice2:visibility: hidden
ice2:embargo:
  until: "2027-06-30"          # or "unspecified", with a reason
  reason: "Pending publication of the accompanying paper"
  becomes: public
```

Colleagues can use it from the internal catalogue;
[`publish`](publish-the-catalogue.md) withholds it from the public one.

Releasing it later is two edits — set both keys to `public`, delete the embargo
block — then rebuild and republish. The dataset name and every checksum stay
the same, so everything that already referenced it keeps working.

## Say who made it

Most of this catalogue is mirrored data: somebody else made it, we hold a copy,
and the upstream terms are the terms. Some of it is not. When a dataset is
yours, say so — `ice2:origin` is what a downstream consumer reads to know whose
rights they are dealing with.

```yaml
ice2:origin: derived        # downloaded (default) | derived | created

ice2:derivation: >-
  The GeoTIFFs are lossless gdalwarp conversions of the netCDF beside them,
  reprojected to EPSG:3035 with nearest-neighbour resampling.

contributors:
  - title: A Researcher
    roles: [author]
    organization: Forschungszentrum Jülich, ICE-2
  - title: ICE-2 RESKit maintainers
    roles: [maintainer]
```

| `ice2:origin` | Means | Build requires |
|---|---|---|
| `downloaded` | mirrored as obtained; the upstream terms are the terms | nothing |
| `derived` | computed from other data — ours, but downstream of somebody else's | an `author` contributor, `sources`, and `ice2:derivation` |
| `created` | produced here from scratch; ICE-2 holds the rights | an `author` contributor |

`downloaded` is the default, so every dataset written before this key existed
keeps building untouched. It is also the conservative answer: claiming less
authorship than is true is safe, claiming more is not.

`contributors` is the Frictionless field, and `roles` is a **list** in Data
Package v2 — a v1-style `roles: author` is rejected rather than quietly
coerced. Valid roles: `author`, `contributor`, `maintainer`, `publisher`,
`wrangler`.

`derived` asks for both halves of the claim. `sources` says what it came from —
derived data inherits obligations from its inputs, and a derivation with no
named input cannot be checked against them. `ice2:derivation` says how, in
enough detail that somebody could redo it.

## More than one licence

`licenses:` is a list, so a dataset under several terms needs no extension:

```yaml
licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
  - name: CC0-1.0
    path: https://creativecommons.org/publicdomain/zero/1.0/
```

Each entry needs a `name` (an
[Open Definition id](http://licenses.opendefinition.org/)) or a `path` to the
terms. A bare `title` is rejected: it reads as a licence and identifies nothing,
which is worse than an honest `ice2:license_status: unresolved`.

### When the files differ

The real case: upstream originals sitting beside conversions you made. They are
one dataset by every other measure, and splitting them in two just to record two
licences would be the tail wagging the dog. Narrow an entry instead:

```yaml
licenses:
  # The upstream originals we mirror.
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
    ice2:applies_to: ["originals/**"]

  # Everything else: our conversions, and the product documentation.
  - name: CC0-1.0
    path: https://creativecommons.org/publicdomain/zero/1.0/
```

That renders as a resource-level `licenses` override on each matching file —
Frictionless's own mechanism for exactly this. See
[how it renders](../reference/schemas.md#how-a-narrowed-licence-renders).

Patterns use the same matcher as `ice2:include`. Two guardrails:

- a pattern matching **nothing fails the build**, like `ice2:include` — silently
  licensing no files is how a dataset ends up published under terms nobody
  applied;
- if **every** entry is narrowed and some files are left over, the build warns:
  those files would be covered by no licence at all.

## Unresolved licensing

If nobody has read the upstream terms yet, leave `licenses:` out and say so:

```yaml
ice2:license_status: unresolved
ice2:license_note: "Terms unclear; enquiry sent to <contact> 2026-08-14."
```

`fetch()` then emits a `UserWarning` on every download until somebody answers.
`ice2:license_note` is stripped from the published catalogue. See
[Licensing and immutability](../explanation/licensing.md).

## See also

- [File formats](../reference/schemas.md) — every key, with types.
- [Upload a dataset](upload-a-dataset.md) — the next step.
- [Write a collections file](write-a-collections-file.md) — the consumer side
  of the same pattern grammar.
