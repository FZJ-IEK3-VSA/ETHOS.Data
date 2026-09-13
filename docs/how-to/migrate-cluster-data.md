# Migrate cluster data from symlinks to independent copies

Use a stable catalogue/cache layout while an older cluster directory structure
is still in use. Start with directory symlinks (softlinks) to avoid duplicating
bytes. Once the old layout can be retired, copy and verify the data behind the
same cache paths so consuming packages keep working.

| Stage | Example cache entry | Extra storage |
|---|---|---|
| Existing installation | `/legacy/climate-inputs` | Original files only |
| Migration bridge | `/shared/ethos/public/climate-inputs -> /legacy/climate-inputs` | A symlink; bytes remain in the original directory |
| Independent copy | `/shared/ethos/public/climate-inputs/…` | Copied manifest files; original remains until retirement |

The first workflow is for **public and internal datasets**. For licensed files,
use the [restricted-data procedure](#restricted-data) below. These are maintainer
operations on shared storage: coordinate the final path switch with running jobs,
and keep source files stable while hashing and copying.

## 1. Catalogue the original files

Add or update `datasets/climate-inputs/dataset.yaml` in the internal source
catalogue. Set `source_dir: /legacy/climate-inputs`, the appropriate access and
visibility, and any include/exclude patterns. Then build and inspect its inventory:

```bash
ethos-data catalog --catalog-root /shared/ethos/ethos-data-catalog-internal build climate-inputs
```

See [Add internal and restricted datasets](add-internal-and-restricted-data.md)
or [Describe a dataset](describe-a-dataset.md) for complete metadata examples.
Use the actual source directory; do not make it point at a cache link that is
itself about to be generated from that `source_dir`.

## 2. Create the shared namespace as links

```bash
ethos-data catalog --catalog-root /shared/ethos/ethos-data-catalog-internal \
  link-cache --root /shared/ethos/public --dry-run
ethos-data catalog --catalog-root /shared/ethos/ethos-data-catalog-internal \
  link-cache --root /shared/ethos/public
```

`link-cache` considers the **whole source catalogue**, not just the last dataset
built. Inspect the dry run for links it will create or repoint. It skips restricted
datasets and entries without `source_dir`; it keeps real directories already in
the cache. Avoid `--prune` during the migration unless removing stale namespace
links is also intended. The command can apply valid actions even while reporting
other missing sources, so review its complete output.

For a single dataset, or one already marked uploaded with no `source_dir`, create
an explicit link instead:

```bash
mkdir -p /shared/ethos/public
ln -sT /legacy/climate-inputs /shared/ethos/public/climate-inputs
```

These are Linux cluster commands. `-T` treats the destination as the link name
and refuses an existing entry instead of creating a link inside a directory.
Do not use a force option to replace an existing cache entry. Inspect it first.
Do not restore `source_dir` to an uploaded record just to generate this link:
its frozen dCache inventory should stay frozen.

Configure the cache for consumers:

```bash
ethos-data config set-public-cache /shared/ethos/public --scope user
```

A cluster administrator can choose `--scope site`. Remove obsolete per-dataset
root overrides at the scope where they were set, because they take precedence
over this cache. Disable development staging for the migration verification.
A symlink does not alter permissions on its target; internal data stays behind
its existing filesystem access controls. Before making a copy later, also set
the intended permissions and default ACLs on the destination namespace:
materialization creates new directories rather than preserving the source
directory ownership and ACL layout.

## 3. Verify the bridge

Create a maintainer collection selecting every manifest resource of this dataset
(`files: ["**"]`), as in
[the registration guide](add-internal-and-restricted-data.md#5-verify-a-complete-dataset-and-use-it-from-a-package).
Use a concrete catalogue version containing that inventory:

```bash
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public -c /shared/ethos/maintenance-collections.yaml \
  plan check_climate_inputs
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public -c /shared/ethos/maintenance-collections.yaml \
  verify check_climate_inputs --deep
```

Replace `REV` and the collection name with the deployed revision and your
collection. Check that the plan reports **namespace link** as the origin, and
that deep verification reports the expected number of `ok` files. Ordinary
in-place fetch checks existence; it does not substitute for this hash check.

## 4. Make the copy before retiring the original

While the original source still exists and is stable:

```bash
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public materialize climate-inputs --dry-run
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public materialize climate-inputs
```

Name the dataset explicitly: `--all` operates on all dataset-level links in the
public cache. `materialize` copies the **full dataset inventory**, even if a
consumer collection selects only a few resources. It does not copy unlisted
files from the original project directory. It checks free space, copies into a
temporary sibling directory, and verifies sizes/hashes before switching the entry.
Leave hash verification enabled.

Copy or verification failures leave the original link in place. The final switch
unlinks the symlink and renames the verified directory into place, so there is a
brief interval when the cache entry is absent. Arrange a quiet period for readers;
this is not an atomic directory/symlink exchange or a shared-storage lock.

On success the cache entry is a real directory. `.ethos-data-materialized.json` records
the old target, catalogue, and copy verification. **The original target has not
been deleted.** A copy is needed on disk before space from that target can be freed.

## 5. Verify independence and update maintenance metadata

```bash
test ! -L /shared/ethos/public/climate-inputs
test -d /shared/ethos/public/climate-inputs
ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  --root /shared/ethos/public -c /shared/ethos/maintenance-collections.yaml \
  verify check_climate_inputs --deep
```

Rerun a representative package workflow with staging and old dataset-root
overrides removed. Check other namespace links, configuration files, and jobs
that may still refer directly to `/legacy/climate-inputs`.

If the dataset is still maintained from local files, change `source_dir` to the
new real directory and rebuild/check its metadata. Do this **after** the link has
become a directory, otherwise a later `link-cache` run could create a self-link.
If the dataset is already uploaded, keep `ethos:uploaded: true` and leave
`source_dir` absent; local materialization does not change dCache authority.

Only retire the old directory after verification and dependent-job migration.
Account separately for files outside the catalogue inventory: successful
materialization does not mean the entire old project directory was backed up.
Old catalogue revisions whose local manifests are needed for rebuilding may also
still name the old `source_dir`. Neither `materialize` nor `link-cache` retires
or deletes that source storage for you.

## Restricted data

Restricted data belongs in the restricted root or a configured dataset location,
not the public cache. `catalog link-cache` deliberately skips it. You can register
an authorised installation without copying it, either with `config set-root`, or
with an administrator-managed directory symlink in the restricted namespace:

```bash
mkdir -p /shared/ethos/restricted
ln -sT /legacy/licensed-example /shared/ethos/restricted/licensed-example
ethos-data config set-restricted-cache /shared/ethos/restricted --scope user
```

The reader uses these files in place. Keep the namespace and target accessible
only to the authorised users; a symlink grants no additional access. If a
per-dataset override exists, remove it at its configured scope before testing the
namespace. Run the full-dataset `verify --deep` check from the registration guide.

A later local copy is subject to the terms for that installation. Where permitted,
an administrator can use `materialize` with an **explicit dataset name**: the
command chooses the restricted root from the dataset's access class. `--all`
only discovers links in the public cache, so it will not discover this link.
Do not upload, stage, or export the licensed files as a portable test bundle.

Before copying, configure the restricted namespace's permissions and default
ACLs to protect newly created directories. The command does not reproduce the
original directory ownership and ACL layout. Then, with the original files
stable and a quiet period arranged for the final path switch:

```bash
ETHOS_RESTRICTED_DIR=/shared/ethos/restricted \
  ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  materialize licensed-example --dry-run
ETHOS_RESTRICTED_DIR=/shared/ethos/restricted \
  ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  materialize licensed-example
```

This copies the full manifest inventory into the restricted namespace and
verifies it before replacing the link. It leaves the original installation in
place. The space requirements and brief path-switch interval from step 4 also
apply here.

```bash
test ! -L /shared/ethos/restricted/licensed-example
test -d /shared/ethos/restricted/licensed-example
ETHOS_RESTRICTED_DIR=/shared/ethos/restricted \
  ethos-data --catalog /shared/ethos/catalogue/versions/REV/datacatalog.json \
  -c /shared/ethos/maintenance-collections.yaml verify check_licensed_example --deep
```

Require every expected file to pass, check the resulting access permissions, and
rerun a package workflow with old dataset-root overrides removed. Update the
internal catalogue's `source_dir` after the build input moves, keeping resource
identities and hashes for unchanged bytes. Retain the original target until all
consumers and checks have migrated, as in step 5.

If making another copy is not permitted, keep using the authorised installation
through the link or configured root and arrange the relocation with its custodian.
The restricted access class itself does not authorise a local copy or remove
filesystem permissions.

## See also

- [Use data already on disk](use-data-already-on-disk.md) for consumer configuration.
- [Verify, repair, and materialize](verify-and-repair.md) for command details.
- [Catalogue hosting](catalogue-hosting.md) for versioned cluster metadata paths.
