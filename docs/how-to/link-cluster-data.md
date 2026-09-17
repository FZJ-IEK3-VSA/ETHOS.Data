# Manage local dataset copies

Read existing catalogued data in place, add a shared cache link, or create an
independent verified copy. You need a readable catalogue inventory and source
files with the catalogue's relative layout. Paths below are examples.

## Choose how to use the existing data

| Need | Method |
| --- | --- |
| Use one dataset from another directory for your account/project | A dataset-root setting. |
| Share an existing directory through the cache | A symbolic cache link. |
| Make the cache own an independent copy | Materialize the dataset. |

New datasets first need [source metadata](describe-a-dataset.md) and licensing
review. For unpublished experiments, use [staging](propose-a-dataset.md#stage-development-data).

## Dataset-root overrides {#dataset-root-overrides}

```bash
ethos-data config set-root global-wind-atlas-v4 /data/GWA_4.0
ethos-data config show
```

The directory points directly at the dataset's files. Append `--scope project`
for one project. Files are read in place. Stop using the override with:

```bash
ethos-data config unset-root global-wind-atlas-v4
```

This removes configuration, not files. Future retrieval uses the applicable
cache. It does not make a restricted dataset downloadable.

## Create or remove cache links {#cache-links}

```bash
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public link climate-inputs /legacy/climate-inputs
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public unlink climate-inputs
```

A link is visible to everyone sharing that cache. `unlink` removes only symbolic
links and leaves their sources intact; it refuses real directories.
`--force` on a named dataset deliberately repoints an existing link.

If the directory is omitted, `link` reads `source_dir` from the source checkout
selected with `--catalog-root`. Keep that value pointing at the original.
To populate a cache from every eligible source descriptor at once, pass `--all`
in place of a dataset name:

```bash
ethos-data link --all --catalog-root /path/to/source-catalogue --root /shared/ethos/public --dry-run
ethos-data link --all --catalog-root /path/to/source-catalogue --root /shared/ethos/public
```

Review the preview. Restricted and unresolved-licence datasets are left out of
the namespace, and real directories are never replaced with a link.

Avoid `--prune` during migration: it also removes links for datasets the
catalogue no longer lists, and mid-migration the catalogue is deliberately
behind the filesystem. It never removes a real directory.

Create and inspect links on the hosting machine. Windows symbolic links require
Developer Mode or elevation; otherwise use a dataset-root setting. Directory
junctions are unsuitable because the cache can treat them as owned directories.

## Materialize copies {#materialize-copies}

Set intended destination permissions/default ACLs first; copying does not preserve
source ownership or ACLs. Keep source files unchanged while copying.

```bash
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public materialize climate-inputs --dry-run
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public materialize climate-inputs
```

The complete inventory is copied and checked before replacing the link. Leave
checksum verification enabled. Pause readers for the final switch, when the link
is briefly absent. Existing real directories are skipped even with `--force`.

To seed an absent entry or copy from another source, append
`--from /legacy/climate-inputs` to the same preview and copy commands. This form
requires one dataset. Without a link or `--from`, a source descriptor's
`source_dir` can supply the source.

Expect a real directory, `materialized` in the report, and
`.ethos-data-materialized.json` recording provenance. The original is preserved.

## Verify the complete dataset {#verify-complete-dataset}

Remove staging and per-dataset overrides that would redirect the check to the
original. A package's `verify` checks only its selected files. To check an entire
dataset independently, use the integrity API:

```python
import ethos_data

catalog = ethos_data.load_catalog("/path/to/datacatalog.json")
roots = ethos_data.resolve_roots("/shared/ethos/public")
resources = list(catalog.dataset("climate-inputs").resources.values())
findings = ethos_data.verify(catalog, resources, roots, deep=True)
for finding in findings:
    print(finding.status, finding.resource.key)
assert all(finding.status == "ok" for finding in findings)
```

Confirm the intended paths and permissions, then run a representative workflow.
For a materialized dataset, also confirm that the cache entry is a real directory.

## Restricted data {#restricted-data}

`link --all` and `materialize --all` discover public-cache entries only.
Configure a protected restricted root, then explicitly name a licensed dataset:

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted
ethos-data --catalog /path/to/internal/datacatalog.json link licensed-example /legacy/licensed-example
```

If its terms permit a local copy, use `materialize licensed-example --from
/legacy/licensed-example` with the same catalogue, previewing with `--dry-run`.
Verify the complete dataset and permissions as above, substituting its name.
No restricted bytes are downloaded or uploaded, and a link grants no access.

## Retire an original installation {#retire-the-original}

Keep `source_dir` while the original remains the build input. Already uploaded
datasets retain `ethos:uploaded: true` and no `source_dir`.

Before retiring an original whose verified copy becomes the permanent local
installation, remove `source_dir`, set `ethos:frozen: true`, and rebuild.
Do not rehash the copy to establish a new baseline. See
[Copy ownership and frozen inventories](../explanation/caches-and-access.md#copy-ownership-and-frozen-inventories).

Have the owner check legacy scripts, other links, root overrides, files outside
the inventory, and versions needed by older pins. Retirement is a separate
operation. Public copies can later be [uploaded](upload-a-dataset.md);
restricted copies remain local.
