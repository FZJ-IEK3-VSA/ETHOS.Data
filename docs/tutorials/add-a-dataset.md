# Add a dataset to the catalogue

You are the catalogue maintainer accepting data that other packages will ask
for by name. This is the round trip from an accepted proposal to a released
entry: describe it, build its manifest, upload and verify the bytes, and publish
the metadata. Follow it with a small approved dataset.

Package maintainers who are still developing their candidate should start with
[Develop and propose a dataset](develop-and-propose-data.md); that path needs
no upload credentials or write access to the source catalogue.

Everything here uses `ethos-data catalog`, the writing half of the package. It finds
the catalogue to act on by searching upward from the current directory for
`catalog.yaml`, so run these from anywhere inside a catalogue checkout.

!!! info "Which repository"
    Datasets are described in **`ethos-data-catalog-internal`** — the source
    catalogue. The public `ethos-data-catalog` is *generated* from it and must
    never be edited by hand. If you do not have a catalogue at all yet, start
    with [Bootstrap a new catalogue](../how-to/bootstrap-a-catalogue.md).

## 1. Review and describe it

Start with the contributor's [proposal](../how-to/propose-a-dataset.md): confirm
provenance, redistribution, selected files, validation results, and access to
the candidate bytes. Use the following description as a template, replacing its
example values with the reviewed metadata.

```bash
cd /path/to/ethos-data-catalog-internal
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
ethos:access: public
# Whether the dataset is listed in the public catalogue:  public | hidden
ethos:visibility: public

# Folder name on the public store. Omit for restricted data.
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

Two of those keys carry more weight than they look:

**`source_dir` is a statement about one machine** and is stripped from anything
published. It exists so the manifest can be built from real files; it is not
part of the dataset's identity.

**`licenses:`** — if the redistribution terms have not been checked yet, leave
it out and write `ethos:license_status: unresolved` instead. Every download then
warns until somebody answers the question. An absent licence is a question, not
a default; see [Licensing and immutability](../explanation/licensing.md).

It is a **list**, so a dataset under several sets of terms needs no extension,
and one entry can narrow itself to some of the files with `ethos:applies_to` —
for upstream originals sitting beside conversions you made. See
[More than one licence](../how-to/describe-a-dataset.md#more-than-one-licence).

### If you made this data rather than downloading it

The default assumption is that a dataset was mirrored as obtained. If it was
not, say so — this is what tells a consumer whose rights they are dealing with:

```yaml
ethos:origin: created        # downloaded (default) | derived | created
contributors:
  - title: A Researcher
    roles: [author]
    organization: Forschungszentrum Jülich, ICE-2
```

Claiming `derived` or `created` obliges you to name an author; `derived` also
needs `sources` (from what) and `ethos:derivation` (by what method). See
[Say who made it](../how-to/describe-a-dataset.md#say-who-made-it).

### When `source_dir` holds more than the dataset

The common case is a shared download directory that also holds the zip the data
was extracted from, a `wget-log`, and a colleague's test clip — on storage you
may not have the write access, or the standing, to tidy up. Narrow the
inventory instead of moving files:

```yaml
ethos:include:
  - "wind_speed_cog_10m.tif"
  - "wind_speed_cog_*0m.tif"

ethos:exclude:
  - "**/*.zip"        # the download archives, duplicates of what was extracted
  - "test"            # a whole folder
  - "wget-log"
```

Because the filter is per dataset, **two datasets may share one `source_dir`**
and each describe its own half. Full semantics in
[Describe a dataset](../how-to/describe-a-dataset.md#narrowing-the-inventory).

## 2. Build the inventory

```bash
ethos-data catalog build my-dataset
```

This walks `source_dir`, computes a SHA-256 per file, and writes
`datapackage.json`. It also pulls shapefile companions in automatically and
excludes VCS plumbing, `__pycache__` and root `README*`/`LICENSE*`/`CHANGELOG*`
from the manifest, reporting how many files each filter removed so the number
is never a surprise.

!!! warning "Manifests are generated, never hand-edited"
    `datapackage.json` and anything under `manifests/` are outputs. If one is
    wrong, fix `dataset.yaml` and rebuild. `ethos-data catalog build --check` fails if
    any manifest is stale, which is what CI should run.

For a dataset of tens of thousands of files, add `ethos:shard_depth: N` and the
inventory is split into `manifests/<directory-prefix>.json` files instead of
one array, so a consumer selecting one tile does not parse the whole thing. See
[sharding](../explanation/catalogue-format.md#sharding).

## 3. Upload the bytes

```bash
ethos-data catalog upload my-dataset --dry-run   # see what would transfer
ethos-data catalog upload my-dataset             # do it, then verify
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

After successful upload and verification, set `ethos:uploaded: true` in
`dataset.yaml` and remove `source_dir`. Rebuild to preserve the accepted
inventory while recording that dCache is the authoritative copy, including for
test data. Retain the generated descriptor and shards in the source repository.

## 4. Publish the catalogue entry

```bash
ethos-data catalog build                        # rebuild everything
ethos-data catalog publish ../ethos-data-catalog
```

`publish` regenerates the public catalogue from every dataset marked
`ethos:visibility: public`: `datacatalog.json`, each public
`datasets/<name>/datapackage.json` with `source_dir`, `ethos:embargo` and
`ethos:license_note` stripped, and the README table. Anything it no longer
generates is deleted from the target, so the public repo can never drift from
what this command would produce.

Inspect the diff before committing. The failure that matters is a leak:

```bash
rg -n 'source_dir|ethos:embargo|ethos:license_note|ethos:uploaded' ../ethos-data-catalog   # expect no output
```

After the checks pass, commit and release the paired source and public
revisions. Deploy the complete reviewed internal tree to the cluster and
synchronize its revision with JuGit; publish the generated public tree through
the agreed GitHub release process. See
[Catalogue hosting](../how-to/catalogue-hosting.md).

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

Give the package maintainer the released catalogue version so they can update
the pin and remove development overrides. Ordinary workflows need only the
collection declaration; a small repository test-data snapshot may additionally
carry generated metadata and files for offline tests. dCache remains the
authoritative store for those files.

## Data that is not ready to publish

Set `ethos:visibility: hidden` and say why:

```yaml
ethos:access: internal
ethos:visibility: hidden
ethos:embargo:
  until: "2027-06-30"          # or "unspecified", with a reason
  reason: "Pending publication of the accompanying paper"
  becomes: public
```

Colleagues can then use it from the internal catalogue, while
`ethos-data catalog publish` withholds it from the public one. The `embargo` block is
**required**, so that nothing stays hidden by accident.

To release it later, set `ethos:access` and `ethos:visibility` to `public`, delete
the `ethos:embargo` block, and rebuild. For bytes already marked uploaded, use
`ethos-data catalog upload my-dataset --verify-only` to establish public
readability; for a candidate not uploaded yet, perform the upload in step 3.
Then generate and release the public metadata in step 4. Resource keys and
checksums can remain unchanged when only access and visibility change, but
consumers need a public catalogue version that includes the new entry.

## What you now know

| You ran | It did |
|---|---|
| `ethos-data catalog build <name>` | walked `source_dir`, hashed every file, wrote the manifest |
| `ethos-data catalog upload <name>` | put the bytes on dCache, then proved anonymous readers can get them |
| `ethos-data catalog publish <target>` | regenerated the public catalogue, stripping everything internal |

## Next

- [Accept a dataset proposal](../how-to/accept-a-dataset.md) — the review
  checklist and package-maintainer handoff.
- [Describe a dataset](../how-to/describe-a-dataset.md) — every `dataset.yaml`
  key, and the include/exclude semantics in full.
- [Upload a dataset](../how-to/upload-a-dataset.md) — credentials, the doors,
  and what to do when it fails.
- [Withdraw a dataset](../how-to/withdraw-a-dataset.md) — and why the order is
  the opposite of publishing.
