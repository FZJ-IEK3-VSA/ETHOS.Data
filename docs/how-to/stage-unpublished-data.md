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
ice2-data config set-staging-cache /scratch/me/ice2-staging
```

## Use it

```bash
ice2-data staging add my-new-dataset /scratch/me/new-data --note "regenerated 2026-09-04"
ice2-data staging list
ice2-data staging remove my-new-dataset
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

and the calling code never knows the difference:

```python
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
can be verified, `ice2-data verify` reports it as `unverifiable`, and every job
that reads it emits a warning:

```title="UserWarning"
dataset 'my-new-dataset' is being read from the staging root
(/scratch/me/ice2-staging), not from the catalogue. Staged data is not
checksummed and is not reproducible -- do not publish results based on it.
```

That warning is not noise to be silenced. Staged data is a development
convenience, and a result derived from it is not reproducible by anyone else.

## Two guarantees

A development convenience must not become a way to launder data into a result:

**Restricted datasets are never shadowed.** Licence terms are not a development
concern, so a staging entry with the same name as a restricted dataset is
ignored for it.

**Staged data is never uploaded.** These datasets exist only on this machine.
`ice2-data catalog` never sees them, because the staging root is a consumer-side
idea the maintainer tooling knows nothing about — there is no path by which a
staged directory can reach dCache.

## A broken link counts as staged

If a staging entry's link target disappears, the dataset does **not** quietly
fall back to the catalogue. Falling back would silently swap the data under a
job that asked for the new version; being told the link is broken is the more
useful outcome.

## Graduating a dataset

When the data is ready:

1. Describe it properly — [Describe a dataset](describe-a-dataset.md).
2. `ice2-data catalog build <name>` and upload it —
   [Upload a dataset](upload-a-dataset.md).
3. `ice2-data catalog publish ../ice2-data-catalog`.
4. `ice2-data staging remove <name>`.

**Nothing in the calling code changes.** The collections file already names the
dataset; it now resolves through the catalogue instead of through the staging
root, with checksums, and the warning stops.

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
