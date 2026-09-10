# Stage uncatalogued data

Preparing a dataset takes weeks. The files change shape, get regenerated, get
renamed — and none of that belongs in a catalogue that other people's
reproducible runs resolve against. But the code being written against that data
wants the ordinary API, `fetch("my_collection")`, from the first day, not a pile
of hard-coded paths that have to be unpicked later.

The **staging root** is that middle ground.

## Turn it on

Staging has no default location, on purpose — it is opt-in by nature:

```bash
ethos-data config set-staging-cache /scratch/me/ethos-staging
```

## Use it

```bash
ethos-data staging add my-new-dataset /scratch/me/new-data --note "regenerated 2026-09-04"
ethos-data staging list
ethos-data staging remove my-new-dataset
```

An entry here **shadows the catalogue completely** for that dataset name. It is
an ordinary directory whose entries are dataset names, exactly like the public
cache — and it is described by **what is on disk** rather than by any manifest,
which is the point: the file list is still changing.

Your collections file references it by name like any other dataset:

```yaml
collections:
  my_workflow:
    include:
      - dataset: my-new-dataset
        files: ["**"]
```

The collections file must also name a valid catalogue, or the caller must
supply one; staging adds or shadows datasets after that index is loaded. See
[Develop and propose a dataset](../tutorials/develop-and-propose-data.md) for an
entirely local example. Python and CLI collection access both use the overlay:

```python
from ethos_data import fetch

files = fetch("my_workflow", collections="collections.yaml")
```

| Flag | |
|---|---|
| `--note "…"` | what this is, for the next person to run `staging list` |
| `--copy` | copy the data instead of linking to it |
| `--new-only` (on `list`) | only datasets with no entry in the public or restricted cache |
| `--force` (on `remove`) | required if the entry is a real directory, not a link |

## What you give up

Sizes come from `stat`. There are **no checksums**, so nothing about staged data
can be verified, `ethos-data verify` reports it as `unverifiable`, and every job
that reads it emits a warning:

```title="UserWarning"
dataset 'my-new-dataset' is being read from the staging root
(/scratch/me/ethos-staging), not from the catalogue. Staged data is not
checksummed and is not reproducible -- do not publish results based on it.
```

That warning is not noise to be silenced. Staged data is a development
convenience, and a result derived from it is not reproducible by anyone else.

## Two guarantees

A development convenience must not become a way to launder data into a result:

**Restricted datasets are never shadowed.** Licence terms are not a development
concern, so a staging entry with the same name as a restricted dataset is
ignored for it.

**Staging does not upload data.** `ethos-data catalog` does not discover or
promote staging entries automatically. Publishing a candidate requires a
separate reviewed source description whose `source_dir` points to the accepted
bytes, followed by an explicit maintainer upload.

## A broken link counts as staged

If a staging entry's link target disappears, the dataset does **not** quietly
fall back to the catalogue. Falling back would silently swap the data under a
job that asked for the new version; being told the link is broken is the more
useful outcome.

## Graduating a dataset

When the data is ready:

1. [Propose the dataset](propose-a-dataset.md), including source metadata,
   provenance, inventory, validation, and a location the reviewer can read.
2. The catalogue maintainer [accepts the proposal](accept-a-dataset.md), builds
   the inventory, uploads and verifies the bytes, and releases metadata.
3. Choose that accepted catalogue version in your package.
4. Remove the entry with `ethos-data staging remove <name>` and remove any
   dataset-specific root override used for development.
5. Rerun the workflow against the official version and check that no staging
   warning remains.

If the accepted identifier and resource paths are unchanged, the calling code
keeps the same resource keys. The collection now resolves through official
metadata and the recorded checksums. Package maintainers need no storage
credentials for this handoff.

For a temporary edit to an existing repository test-data copy, use
[Keep test data in a repository](keep-test-data-in-a-repository.md). That
workflow preserves the canonical inventory while explicitly allowing selected
local bytes to differ; staging instead takes its inventory from current files.

## Staging vs. a configured root

Both read data in place, and they are for different things:

| | `staging add` | `config set-root` |
|---|---|---|
| For | a dataset that does **not** exist in the catalogue yet | a private or local copy of one that **does** |
| Described by | what is on disk, right now | the catalogue manifest |
| Verifiable | no | yes |
| Warns on every read | yes | no |
| Wins over the other | no | yes — a configured root is the most specific thing anybody can say |

## See also

- [Caches, classes and roots](../explanation/caches-and-access.md) — where
  staging sits in the resolution order.
- [Use data already on disk](use-data-already-on-disk.md).
