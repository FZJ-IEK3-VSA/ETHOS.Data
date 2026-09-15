# Move linked data into the cache

Replace a cache link with a verified local copy. You need a complete catalogue
inventory, readable source files that remain unchanged during copying, and free
disk space. Work on the machine holding the cache.

## 1. Prepare the destination

Set intended permissions and default ACLs on the destination root. The copy does
not reproduce the source's ownership or ACLs. Check `ethos-data config show`
for per-dataset roots and staging that could redirect later verification.

## 2. Preview and copy

```bash
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public materialize climate-inputs --dry-run
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public materialize climate-inputs
```

The whole dataset inventory is copied, even if your workflow selects only part.
Leave checksum verification enabled. Readers should pause during the final
switch, when the link is briefly absent.

Expect `materialized`, a real cache directory, and
`.ethos-data-materialized.json` recording provenance. The original remains
untouched. Existing real directories are skipped, even with `--force`.

## Copy from somewhere else

To seed an absent entry or use a different source:

```bash
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public materialize climate-inputs --from /legacy/climate-inputs --dry-run
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public materialize climate-inputs --from /legacy/climate-inputs
```

`--from` requires one dataset and a source with the catalogue's relative layout.

## 3. Verify independence {#4-verify-independence}

Use a collection selecting the complete dataset, as in the
[linking guide](link-cluster-data.md#3-configure-and-verify-readers):

```bash
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public -c maintenance-collections.yaml verify check_climate_inputs --deep
```

Confirm the cache entry is a real directory, all expected files match, permissions
are correct, and a representative workflow succeeds without a local-root override.

## 4. Update the descriptor, usually not at all {#5-update-the-descriptor-usually-not-at-all}

Keep `source_dir` while the original remains the build input. Keep
`ethos:uploaded: true` and no `source_dir` for already uploaded datasets.

If the original is to be retired and the verified copy is the permanent local
installation, remove `source_dir`, set `ethos:frozen: true`, and rebuild
**before** retirement. Do not rehash the cache copy to establish a new baseline.
See [Copy ownership and frozen inventories](../explanation/caches-and-access.md#copy-ownership-and-frozen-inventories).

## 5. Retiring the original, when you are ready {#6-retiring-the-original-when-you-are-ready}

Have its owner check legacy scripts, other links, dataset-root overrides, and
files outside the inventory, which were not copied. Keep versions required by
old catalogue pins. Retirement is a separate operation; `materialize` does not
delete the original.

## Restricted data

Set the protected restricted root, then explicitly name the dataset and source:

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted
ethos-data --catalog /path/to/internal/datacatalog.json materialize licensed-example --from /legacy/licensed-example --dry-run
ethos-data --catalog /path/to/internal/datacatalog.json materialize licensed-example --from /legacy/licensed-example
```

Copy only when the installation's terms permit it. Verify the complete restricted
selection and resulting permissions. `--all` discovers public-cache links only.

## Then upload

For public data, a local copy can later be
[uploaded](upload-a-dataset.md). Restricted data stays local.
See [Materialize reference](../reference/cli/ethos-data.md#materialize-datasets)
for source-directory fallback and other options.
