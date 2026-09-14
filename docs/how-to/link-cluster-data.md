# Link cluster data into the cache

Give data that already sits on shared storage a cache name, without copying it.
The bytes stay where they are and code reading the old path keeps working.

```text
/shared/ethos/public/climate-inputs  ->  /legacy/climate-inputs
```

Nothing here uploads anything. Linking, and later
[copying](move-linked-data-into-the-cache.md), makes a dataset usable on this
machine immediately, instead of waiting for an upload and a download back. It
does not replace the upload — see [Then upload](move-linked-data-into-the-cache.md#then-upload).

Run these commands on the machine that holds the data, not through a mapped
network drive: see [Network shares](#network-shares).

## 1. Describe the dataset

In the source catalogue, create `datasets/climate-inputs/dataset.yaml`:

```yaml
name: climate-inputs
title: Climate input data
source_dir: /legacy/climate-inputs
ethos:access: internal
ethos:visibility: hidden
ethos:embargo:
  until: "unspecified"
  reason: Description not finished; linked from existing storage.
  becomes: public
licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
```

`source_dir` is the only required key: `ethos:access` and `ethos:visibility`
default to `public`, `ethos:origin` to `downloaded`, and the name comes from the
directory. A hidden dataset needs the embargo block.

**The licence is not deferrable.** A dataset with unresolved licensing is skipped
by `link-cache` and refused by `link`, because a cache entry hands it to everyone
reading that cache. Record a `licenses:` entry, or
`ethos:license_status: resolved` once somebody has read the terms. To work with
it before then, [stage it](stage-unpublished-data.md) — staging is not gated.
Provenance and the rest can still follow later:
[Describe a dataset](describe-a-dataset.md),
[Add internal and restricted datasets](add-internal-and-restricted-data.md).

## 2. Create the links

```bash
ethos-data catalog --catalog-root /shared/ethos/ethos-data-catalog-internal \
  link-cache --root /shared/ethos/public --dry-run
ethos-data catalog --catalog-root /shared/ethos/ethos-data-catalog-internal \
  link-cache --root /shared/ethos/public
```

This reads `dataset.yaml` only, so no inventory has to exist yet. It covers the
whole catalogue, not the dataset you last edited — read the dry run, which
reports each entry as `link`, `repoint`, `keep` (a real directory, never replaced
by a link), `skip` (restricted, or no `source_dir`) or `missing`. Only top-level
`datasets/` directories are linked. Avoid `--prune` mid-migration. Without
`--root` it builds the cache this machine is configured to read, which is the
form to use for your own cache rather than a shared one.

## 3. Build the inventory

```bash
ethos-data catalog --catalog-root /shared/ethos/ethos-data-catalog-internal \
  build climate-inputs
```

This reads every selected file to hash it. Narrow the selection with
`ethos:include` / `ethos:exclude` when `source_dir` holds more than the dataset.
The inventory is what `verify --deep` and
[the move](move-linked-data-into-the-cache.md) need; until it exists,
`build --check` reports the dataset as stale and re-hashes it on every CI run.

## 4. Point users at the cache

```bash
ethos-data config set-public-cache /shared/ethos/public --scope site
```

`--scope site` is machine-wide and needs an administrator; `--scope user`
otherwise. `ethos-data config show` reports per-dataset roots and staging, which
both win over the cache.

## 5. Check it

```bash
ls -l /shared/ethos/public
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public -c /shared/ethos/maintenance-collections.yaml \
  plan check_climate_inputs
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public -c /shared/ethos/maintenance-collections.yaml \
  verify check_climate_inputs --deep
```

Use a collection selecting `files: ["**"]`, as in
[the registration guide](add-internal-and-restricted-data.md#5-verify-a-complete-dataset-and-use-it-from-a-package).
The plan must report the origin as **namespace link**, and deep verification
every expected file as `ok`.

## One dataset, or your own cache

`link-cache` builds a shared namespace at a root you name. To fill the cache this
machine is configured to read, or to link one dataset:

```bash
ethos-data link --all                 # every dataset with a source_dir
ethos-data link climate-inputs        # one, from its source_dir
ethos-data link climate-inputs /legacy/climate-inputs    # one, explicitly
ethos-data unlink climate-inputs
```

Both forms read `source_dir` from the catalogue checkout — pass `--catalog-root`
if you are not inside one. `--all` skips restricted datasets, as `link-cache`
does; naming one explicitly links it into the restricted root, which is how an
authorised installation is registered. An uploaded dataset has no `source_dir`
left, so name its directory.

Entries go in the root for the dataset's access class, a real directory is never
replaced, and a link that looks like the wrong level is reported. To copy the
files in rather than link them, use
[`materialize --from`](move-linked-data-into-the-cache.md#copy-from-somewhere-else).

On Windows this needs Developer Mode or an elevated shell; without either, use
`ethos-data config set-root <dataset> <directory>`. Do not substitute a junction
(`mklink /J`) — it is reported as an ordinary directory, so the cache would treat
the borrowed data as a copy it owns and could write into it.

## Restricted data

`link-cache` skips restricted datasets. An administrator creates the entry in the
restricted root instead:

```bash
ln -sT /legacy/licensed-example /shared/ethos/restricted/licensed-example
ethos-data config set-restricted-cache /shared/ethos/restricted --scope site
```

A link grants no access: the target's permissions still decide who may read it,
and the restricted root is only ever read in place. Restricted descriptors keep
`source_dir` and must not declare `ethos:remote_prefix`.

## Network shares

Create the links in a shell on the machine that holds the data. Through a mapped
drive:

- `ln -s` in Git Bash copies the whole tree instead of linking, silently, with
  exit status 0;
- a link must record the path that machine uses — a drive letter or UNC path
  resolves for nobody;
- a share may present a link as an ordinary directory, so check links with `ls -l`
  and `readlink` on the machine itself.

## Rules

- Do not move the original: the link exists so that nothing has to move yet.
- Do not point `source_dir` at the cache entry — the next `link-cache` run would
  create a self-link.
- To follow reorganised storage, edit `source_dir` and re-run `link-cache`: every
  user of the machine follows at once.

## See also

- [Move linked data into the cache](move-linked-data-into-the-cache.md) — replace
  the link with a copy.
- [Stage uncatalogued data](stage-unpublished-data.md) — data nobody is ready to
  describe yet.
- [Caches, classes and roots](../explanation/caches-and-access.md).
