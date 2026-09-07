# Add a dataset to the catalogue

You have data that other people's tools should be able to ask for by name. This
is the full maintainer round trip: describe it, build its manifest, upload the
bytes, publish the entry. Follow it once on something small and the how-to
guides afterwards will make sense.

Everything here uses `ice2-data catalog`, the writing half of the package. It finds
the catalogue to act on by searching upward from the current directory for
`catalog.yaml`, so run these from anywhere inside a catalogue checkout.

!!! info "Which repository"
    Datasets are described in **`ice2-data-catalog-internal`** — the source
    catalogue. The public `ice2-data-catalog` is *generated* from it and must
    never be edited by hand. If you do not have a catalogue at all yet, start
    with [Bootstrap a new catalogue](../how-to/bootstrap-a-catalogue.md).

## 1. Describe it

```bash
cd /path/to/ice2-data-catalog-internal
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

Two of those keys carry more weight than they look:

**`source_dir` is a statement about one machine** and is stripped from anything
published. It exists so the manifest can be built from real files; it is not
part of the dataset's identity.

**`licenses:`** — if the redistribution terms have not been checked yet, leave
it out and write `ice2:license_status: unresolved` instead. Every download then
warns until somebody answers the question. An absent licence is a question, not
a default; see [Licensing and immutability](../explanation/licensing.md).

It is a **list**, so a dataset under several sets of terms needs no extension,
and one entry can narrow itself to some of the files with `ice2:applies_to` —
for upstream originals sitting beside conversions you made. See
[More than one licence](../how-to/describe-a-dataset.md#more-than-one-licence).

### If you made this data rather than downloading it

The default assumption is that a dataset was mirrored as obtained. If it was
not, say so — this is what tells a consumer whose rights they are dealing with:

```yaml
ice2:origin: created        # downloaded (default) | derived | created
contributors:
  - title: A Researcher
    roles: [author]
    organization: Forschungszentrum Jülich, ICE-2
```

Claiming `derived` or `created` obliges you to name an author; `derived` also
needs `sources` (from what) and `ice2:derivation` (by what method). See
[Say who made it](../how-to/describe-a-dataset.md#say-who-made-it).

### When `source_dir` holds more than the dataset

The common case is a shared download directory that also holds the zip the data
was extracted from, a `wget-log`, and a colleague's test clip — on storage you
may not have the write access, or the standing, to tidy up. Narrow the
inventory instead of moving files:

```yaml
ice2:include:
  - "wind_speed_cog_10m.tif"
  - "wind_speed_cog_*0m.tif"

ice2:exclude:
  - "**/*.zip"        # the download archives, duplicates of what was extracted
  - "test"            # a whole folder
  - "wget-log"
```

Because the filter is per dataset, **two datasets may share one `source_dir`**
and each describe its own half. Full semantics in
[Describe a dataset](../how-to/describe-a-dataset.md#narrowing-the-inventory).

## 2. Build the inventory

```bash
ice2-data catalog build my-dataset
```

This walks `source_dir`, computes a SHA-256 per file, and writes
`datapackage.json`. It also pulls shapefile companions in automatically and
excludes VCS plumbing, `__pycache__` and root `README*`/`LICENSE*`/`CHANGELOG*`
from the manifest, reporting how many files each filter removed so the number
is never a surprise.

!!! warning "Manifests are generated, never hand-edited"
    `datapackage.json` and anything under `manifests/` are outputs. If one is
    wrong, fix `dataset.yaml` and rebuild. `ice2-data catalog build --check` fails if
    any manifest is stale, which is what CI should run.

For a dataset of tens of thousands of files, add `ice2:shard_depth: N` and the
inventory is split into `manifests/<directory-prefix>.json` files instead of
one array, so a consumer selecting one tile does not parse the whole thing. See
[sharding](../explanation/catalogue-format.md#sharding).

## 3. Upload the bytes

```bash
ice2-data catalog upload my-dataset --dry-run   # see what would transfer
ice2-data catalog upload my-dataset             # do it, then verify
```

The upload itself is one `rclone` call. The part that matters is what happens
afterwards: `upload` sets `0755` on the dataset's prefix, then **HEADs every
file in the manifest with no credentials at all** and reports anything
unreadable or the wrong size. That is the only check that actually proves a
stranger can download what you just published.

```title="Want to see"
readable       12/12
storage locality of docs/README.md: ONLINE
```

It refuses `restricted` datasets outright, requires `--allow-internal` for
`internal` ones, and warns on unresolved licensing.

This step needs `rclone` and `oidc-agent`, and a one-time credential setup —
see [Upload a dataset](../how-to/upload-a-dataset.md), which is the full
runbook including the troubleshooting table.

!!! danger "Published paths are immutable"
    `upload` passes `rclone --immutable`, which fails loudly on an attempted
    overwrite. If a dataset's bytes genuinely change, publish them at a **new
    path** — someone may already have the old ones cached and hash-verified.

## 4. Publish the catalogue entry

```bash
ice2-data catalog build                        # rebuild everything
ice2-data catalog publish ../ice2-data-catalog
```

`publish` regenerates the public catalogue from every dataset marked
`ice2:visibility: public`: `datacatalog.json`, each public
`datasets/<name>/datapackage.json` with `source_dir`, `ice2:embargo` and
`ice2:license_note` stripped, and the README table. Anything it no longer
generates is deleted from the target, so the public repo can never drift from
what this command would produce.

Inspect the diff before committing. The failure that matters is a leak:

```bash
grep -rn 'source_dir\|ice2:embargo\|ice2:license_note' ../ice2-data-catalog   # want no output
```

Then commit and push **both** repositories.

!!! danger "Only ever point `publish` at the public repo"
    It wipes everything in its target except `.git` before regenerating.
    Against this repository, or with the wrong path, it deletes every
    hand-written `dataset.yaml` and `catalog.yaml`. Git-tracked files come back
    with `git checkout HEAD -- <path>`; working-tree-only files do not.

## 5. Let a tool ask for it

In the consuming tool's `collections.yaml`:

```yaml
collections:
  offshore_siting:
    title: Constraint layers for offshore siting
    include:
      - dataset: my-dataset
        files: ["*.shp"]
```

That is the whole change on the consumer side. The dataset's files, checksums
and licence never enter that repository.

## Data that is not ready to publish

Set `ice2:visibility: hidden` and say why:

```yaml
ice2:access: internal
ice2:visibility: hidden
ice2:embargo:
  until: "2027-06-30"          # or "unspecified", with a reason
  reason: "Pending publication of the accompanying paper"
  becomes: public
```

Colleagues can then use it from the internal catalogue, while
`ice2-data catalog publish` withholds it from the public one. The `embargo` block is
**required**, so that nothing stays hidden by accident.

Releasing it later is two edits: set `ice2:access` and `ice2:visibility` to
`public`, delete the `ice2:embargo` block, and repeat steps 2 and 4. The dataset
name and every checksum stay the same, so everything that already referenced it
keeps working.

## What you now know

| You ran | It did |
|---|---|
| `ice2-data catalog build <name>` | walked `source_dir`, hashed every file, wrote the manifest |
| `ice2-data catalog upload <name>` | put the bytes on dCache, then proved anonymous readers can get them |
| `ice2-data catalog publish <target>` | regenerated the public catalogue, stripping everything internal |

## Next

- [Describe a dataset](../how-to/describe-a-dataset.md) — every `dataset.yaml`
  key, and the include/exclude semantics in full.
- [Upload a dataset](../how-to/upload-a-dataset.md) — credentials, the doors,
  and what to do when it fails.
- [Withdraw a dataset](../how-to/withdraw-a-dataset.md) — and why the order is
  the opposite of publishing.
