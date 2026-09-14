# Describe a dataset

A dataset is described once, in the source catalogue
(`ethos-data-catalog-internal`), by a hand-written `dataset.yaml` plus a
generated manifest. Tools never describe files themselves — they only say which
datasets they need. For the whole round trip in order, see
[Accept a dataset proposal](accept-a-dataset.md).

Package maintainers can use this schema to draft a
[dataset proposal](propose-a-dataset.md) without write access to the source
repository. The catalogue maintainer integrates the accepted description.

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

ethos:access: public          # public | internal | restricted
ethos:visibility: public      # public | hidden
ethos:remote_prefix: my-dataset

sources:
  - title: Where the data originally came from
    path: https://doi.org/...

licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/

ethos:retrieved: "2026-09-01"
ethos:contact: your-username
```

Every key is documented in [File formats](../reference/schemas.md). The two
that decide behaviour:

**`ethos:access`** — who may read the bytes, and therefore which cache root the
dataset resolves from. `public` is on dCache with `o+rx`; `internal` is held by
ICE-2 and not published; `restricted` is licensed and read from authorised local storage. See
[Caches, classes and roots](../explanation/caches-and-access.md).

**`ethos:visibility`** — whether the dataset is listed in the public catalogue at
all. `hidden` requires an `ethos:embargo` block, so nothing stays hidden by
accident.

## Narrowing the inventory

`ethos-data catalog build` inventories everything under `source_dir`. That is fine for
a directory somebody created for the dataset, and wrong for the common case: a
shared download directory that also holds the zip the data was extracted from,
a `wget-log`, and a colleague's test clip — on storage you may not have the
write access, or the standing, to tidy up.

Narrow the inventory instead of moving files:

```yaml
# Only these are the dataset. Everything else under source_dir is ignored.
ethos:include:
  - "wind_speed_cog_10m.tif"
  - "wind_speed_cog_*0m.tif"

# Or keep everything except the strays.
ethos:exclude:
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

Both keys are optional and can be combined; `ethos:exclude` is applied after
`ethos:include`.

### The asymmetry is deliberate

| | If it matches nothing |
|---|---|
| `ethos:include` | **fails the build**, naming the pattern |
| `ethos:exclude` | warns only |

A typo, or a file renamed upstream, must not silently shrink a published
dataset. But the stray an `exclude` named may have been cleaned up since, and
failing the build for a cleanup that happened would be perverse.

Shapefile companions are pulled back in automatically, so
`ethos:include: ["*.shp"]` still yields a readable shapefile.

### Two datasets, one `source_dir`

Because the filter is per dataset, two datasets may share one `source_dir` and
each describe its own half. That is how `global-wind-atlas` and
`global-wind-atlas-era5-expanded` both live in `GWA_4.0` without either seeing
the other's files.

## Build the manifest

```bash
ethos-data catalog build my-dataset       # one dataset
ethos-data catalog build                  # all of them
ethos-data catalog build --check          # CI: fail if any manifest is stale
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
ethos:shard_depth: 2
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
ethos:access: internal
ethos:visibility: hidden
ethos:embargo:
  until: "2027-06-30"          # or "unspecified", with a reason
  reason: "Pending publication of the accompanying paper"
  becomes: public
```

Colleagues can use it from the internal catalogue;
[`publish`](publish-the-catalogue.md) withholds it from the public one.

To release it, set both keys to `public` and delete the embargo block. Rebuild,
establish public readability of the bytes, then release the generated public
metadata as described in [Publish the catalogue](publish-the-catalogue.md).
Changing visibility need not change resource keys or checksums, but consumers
need a catalogue version that includes the newly public entry.

## Say who made it

Most of this catalogue is mirrored data: somebody else made it, we hold a copy,
and the upstream terms are the terms. Some of it is not. When a dataset is
yours, say so — `ethos:origin` is what a downstream consumer reads to know whose
rights they are dealing with.

```yaml
ethos:origin: derived        # downloaded (default) | derived | created

ethos:derivation: >-
  The GeoTIFFs are lossless gdalwarp conversions of the netCDF beside them,
  reprojected to EPSG:3035 with nearest-neighbour resampling.

contributors:
  - title: A Researcher
    roles: [author]
    organization: Forschungszentrum Jülich, ICE-2
  - title: ETHOS.RESKit maintainers
    roles: [maintainer]
```

| `ethos:origin` | Means | Build requires |
|---|---|---|
| `downloaded` | mirrored as obtained; the upstream terms are the terms | nothing |
| `derived` | computed from other data — ours, but downstream of somebody else's | an `author` contributor, `sources`, and `ethos:derivation` |
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
named input cannot be checked against them. `ethos:derivation` says how, in
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
which is worse than an honest `ethos:license_status: unresolved`.

### When the files differ

The real case: upstream originals sitting beside conversions you made. They are
one dataset by every other measure, and splitting them in two just to record two
licences would be the tail wagging the dog. Narrow an entry instead:

```yaml
licenses:
  # The upstream originals we mirror.
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
    ethos:applies_to: ["originals/**"]

  # Everything else: our conversions, and the product documentation.
  - name: CC0-1.0
    path: https://creativecommons.org/publicdomain/zero/1.0/
```

That renders as a resource-level `licenses` override on each matching file —
Frictionless's own mechanism for exactly this. See
[how it renders](../reference/schemas.md#how-a-narrowed-licence-renders).

Patterns use the same matcher as `ethos:include`. Two guardrails:

- a pattern matching **nothing fails the build**, like `ethos:include` — silently
  licensing no files is how a dataset ends up published under terms nobody
  applied;
- if **every** entry is narrowed and some files are left over, the build warns:
  those files would be covered by no licence at all.

## Unresolved licensing

If nobody has read the upstream terms yet, leave `licenses:` out and say so:

```yaml
ethos:license_status: unresolved
ethos:license_note: "Terms unclear; enquiry sent to <contact> 2026-08-14."
```

`fetch()` then emits a `UserWarning` on every download until somebody answers.
`ethos:license_note` is stripped from the published catalogue. See
[Licensing and immutability](../explanation/licensing.md).

## See also

- [File formats](../reference/schemas.md) — every key, with types.
- [Upload a dataset](upload-a-dataset.md) — the next step.
- [Write a collections file](write-a-collections-file.md) — the consumer side
  of the same pattern grammar.


For internal-only or licensed entries, follow [Add internal and restricted datasets](add-internal-and-restricted-data.md). For an existing cluster layout, use [Link cluster data into the cache](link-cluster-data.md).

## A dataset made of smaller datasets

Some datasets are one thing by every measure except licensing. RESKit's test
fixtures are twelve upstreams under six sets of terms, two of them unsettled;
`landcover` is CDS netCDFs beside GeoTIFFs we converted ourselves.

`ethos:access` cannot help with that, and it is worth being clear why it never
will. A dataset is exactly one entry in a cache root, and whether it is read in
place or downloaded is decided by whether that entry is a symbolic link — see
[Caches, classes and roots](../explanation/caches-and-access.md). One file that
may not be redistributed therefore makes the whole dataset unpublishable.

So describe the family as a **namespace** with a `dataset.yaml` per member:

```
datasets/reskit-test-data/dataset.yaml           the family
datasets/reskit-test-data/era5/dataset.yaml      one member
datasets/reskit-test-data/icon-lam/dataset.yaml  another
```

A member's name is its path below `datasets/`, so it is addressed as
`reskit-test-data/era5` — in a collections file, in the cache, and in the
download URL. The cache rule is untouched: `reskit-test-data/era5` is still one
entry, one level deeper.

### The namespace

```yaml
name: reskit-test-data
title: RESKit test fixtures
description: >-
  What the family is.
homepage: https://github.com/FZJ-IEK3-VSA/RESKit
ethos:contact: ETHOS.RESKit maintainers
ethos:attribution: >-
  Carried by every member.
```

It has no `source_dir`, no `resources`, and the build refuses three things
outright:

| Refused on a namespace | Why |
|---|---|
| `source_dir`, `ethos:include`/`exclude`, `ethos:shard_depth` | otherwise `reskit-test-data` means two things — the parent's own inventory, or everything beneath it |
| `ethos:access` | it has no bytes for an access class to be about |
| `licenses`, `ethos:license_status` | a licence inherited without being read is how a dataset ends up published under terms nobody applied |

Its generated descriptor carries `ethos:namespace: true` and reports the file
count and byte total of everything beneath it, so `ethos-data list` can show what
the family costs without loading a single member's inventory.

### What a member inherits

Only `homepage`, `ethos:contact` and `ethos:attribution` — the keys that cannot
weaken a claim. Attribution is an obligation, so inheriting it can only add a
duty; the other two are descriptive.

**Everything else is stated or absent.** A member with no `licenses:` block is
unlicensed, not covered by its parent's, and a member with no `ethos:access`
defaults to `public` exactly as a top-level dataset does. That is the point: the
members of one family routinely differ in both.

A member restating an inherited key overrides it.

### Naming

A member's `name:` must match where it sits. The directory decides, and a
`dataset.yaml` that disagrees fails the build rather than resolving to nothing
much later.

### Selecting from a family

```yaml
collections:
  everything:
    include:
      - dataset: reskit-test-data          # the family: every member
  one_member:
    include:
      - dataset: reskit-test-data/era5     # just that one
        files: ["100m_*.nc"]               # paths are relative to the member
  by_pattern:
    include:
      - dataset: reskit-test-data/*        # a glob over member names
```

Naming the family expands to its members, so a consumer never has to know where
the seams are — which is what lets a member be split off later without touching
anybody's collections file.

`files:` patterns match a member's own resource paths. `dataset: reskit-test-data`
with `files: ["era5/*.nc"]` selects nothing; `dataset: reskit-test-data/era5`
with `files: ["*.nc"]` selects what you meant.

### Publishing

Members are withheld individually on `ethos:visibility`, and a namespace is
published only while it still has a published member — a family name pointing at
nothing is worse than no family name.
