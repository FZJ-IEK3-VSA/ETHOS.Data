# Move linked data into the cache

Replace a [linked](link-cluster-data.md) cache entry with a verified copy the
cache owns, then retire the storage it pointed at. The dataset keeps its name, so
nothing that reads it through ETHOS.Data changes.

```text
before   /shared/ethos/public/climate-inputs -> /legacy/climate-inputs
after    /shared/ethos/public/climate-inputs/    a directory the cache owns
```

Before starting:

- the dataset has a built inventory — `materialize` copies the manifest's
  resources and checks each one against it;
- the cache entry is a symbolic link (`test -L`);
- nobody writes to the original during the copy;
- readers can pause briefly at the [switch](#3-copy-it);
- run it on the machine that holds the data, not through a mapped drive.

## 1. Prepare the destination

`materialize` creates new directories and does not reproduce the original's
ownership and ACLs. Set the intended permissions and default ACLs on the cache
root first. Remove per-dataset roots and staging for the checks below —
`ethos-data config show` lists them.

## 2. Price it

```bash
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public materialize climate-inputs --dry-run
```

Name the dataset: `--all`, and a bare `materialize`, take every link in the public
cache. Only files the catalogue describes are copied, and the whole dataset
inventory is copied even if a consumer collection selects part of it. It refuses
if the copy would leave under 2% of the filesystem free.

## 3. Copy it

```bash
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public materialize climate-inputs
```

It copies into a temporary sibling directory, checks each file's size and SHA-256
against the manifest, and only then puts it in place. Leave verification on
(`--no-verify` gives up the only evidence the copy is sound). A failure deletes
the partial copy and leaves the link untouched.

The link is unlinked before the directory is renamed over it, so the entry is
briefly absent — short, but not atomic. On success the directory contains
`.ethos-data-materialized.json`, recording the old target and the verification.
**The original is not deleted.**

## Copy from somewhere else

`--from` copies a directory you name instead of the entry's link target, and
fills an entry that does not exist yet:

```bash
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public materialize climate-inputs --from /legacy/climate-inputs
```

Use it when the bytes are already on this machine — seeding a cache from a
colleague's copy, or from data that has been uploaded, beats downloading it
back. It takes one dataset, not `--all`, and refuses to write over a directory
the cache already owns. Everything else is the same, verification included.

## 4. Verify independence

```bash
test ! -L /shared/ethos/public/climate-inputs
test -d /shared/ethos/public/climate-inputs
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public -c /shared/ethos/maintenance-collections.yaml \
  verify check_climate_inputs --deep
ls -ld /shared/ethos/public/climate-inputs
```

Every expected file must report `ok`, and the permissions must be the intended
ones. Then rerun a representative package workflow.

## 5. Update the descriptor

- **Still maintained from local files:** point `source_dir` at the new directory
  and rebuild — but only after the entry has become a directory, or the next
  `link-cache` run creates a self-link.
- **Already uploaded:** keep `ethos:uploaded: true` and leave `source_dir` absent.
  A local copy does not change which copy is authoritative.

`link-cache` leaves the entry alone from now on: it never replaces a real
directory with a link.

## 6. Retire the original

Only after verification passes and every dependent has moved.

- Find what still reads the old path: job scripts, configuration, per-dataset
  roots at any scope, other links into the same tree.
- Files outside the inventory were **not** copied; they exist only in the original.
- Catalogue revisions still served may name the old `source_dir` for rebuilds.
- Nothing deletes the original for you.

## Restricted data

Licensed data belongs in the restricted cache as a real, owned copy rather than a
link — which is why `link-cache` skips it — so there is no link for a copy to
follow. Name the dataset and its `source_dir` is used:

```bash
ETHOS_RESTRICTED_DIR=/shared/ethos/restricted \
  ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  materialize licensed-example --dry-run
ETHOS_RESTRICTED_DIR=/shared/ethos/restricted \
  ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  materialize licensed-example
```

Copying licensed files is subject to that installation's terms. Name the dataset
explicitly — `--all` only finds public-cache links — and set the restricted
namespace's permissions and default ACLs first. `--from` overrides the
`source_dir`, and `--catalog-root` says which checkout to read it from.

Verify as in step 4, against the restricted root, and check the resulting access
rights. Never upload, stage or export licensed files.

## Then upload

A materialised dataset is a copy on one machine: fast to produce, but lost with
that filesystem and unreachable from anywhere else. Copying is how the data
becomes usable now; uploading is how it becomes durable and available off the
cluster. Follow [Upload a dataset](upload-a-dataset.md), then set
`ethos:uploaded: true` and remove `source_dir`, which freezes the inventory and
makes dCache the source of truth.

## See also

- [Link cluster data into the cache](link-cluster-data.md) — the first step.
- [Verify, repair, and materialize](verify-and-repair.md) — flags and failure
  cases.
