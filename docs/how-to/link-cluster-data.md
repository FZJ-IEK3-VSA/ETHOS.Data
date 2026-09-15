# Link cluster data into the cache

Make already catalogued data usable from the public/internal cache without a
copy. You need a source-catalogue checkout, settled licensing, a stable local
source directory, and permission to create cache entries. Example paths below
must be replaced with your installation's paths.

## 1. Describe and build the dataset

Set `source_dir` in `datasets/climate-inputs/dataset.yaml` to the original
directory, then build:

```bash
ethos-data catalog --catalog-root /path/to/source-catalogue build climate-inputs
```

Use [Describe a dataset](describe-a-dataset.md) for a new entry. Keep
`source_dir` pointing at the original, not at the cache link.

## 2. Create the links

```bash
ethos-data catalog --catalog-root /path/to/source-catalogue link-cache --root /shared/ethos/public --dry-run
ethos-data catalog --catalog-root /path/to/source-catalogue link-cache --root /shared/ethos/public
```

Inspect the preview first: this covers all eligible top-level source datasets.
It skips restricted or unresolved-licence entries and never replaces a real
directory. Avoid `--prune` during migration.

To link just one built dataset, including a nested dataset, give its source
explicitly:

```bash
ethos-data --catalog /path/to/source-catalogue/datacatalog.json --root /shared/ethos/public link climate-inputs /legacy/climate-inputs
```

Use `--force` only to repoint an existing link deliberately.

## 3. Configure and verify readers

```bash
ethos-data config set-public-cache /shared/ethos/public --scope site
```

A site setting requires administrator access. Readers also need the appropriate
[internal catalogue](add-internal-catalogue.md) for hidden entries.

Create a collection selecting the entire dataset:

```yaml
collections:
  check_climate_inputs:
    include:
      - dataset: climate-inputs
```

Save it as `maintenance-collections.yaml`, then:

```bash
ethos-data --catalog /path/to/source-catalogue/datacatalog.json --root /shared/ethos/public -c maintenance-collections.yaml plan check_climate_inputs
ethos-data --catalog /path/to/source-catalogue/datacatalog.json --root /shared/ethos/public -c maintenance-collections.yaml verify check_climate_inputs --deep
```

Expect `namespace link` and every selected file matching. Resolve per-dataset
roots or staging that redirect the check. Keep the original directory in place.

## Restricted data

`link-cache` skips restricted datasets. To register one authorised installation,
configure its protected restricted root and name the dataset explicitly:

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted
ethos-data --catalog /path/to/source-catalogue/datacatalog.json link licensed-example /legacy/licensed-example
```

Check the target's permissions as an intended reader. The link grants no access.
See [Add restricted data](add-internal-and-restricted-data.md).

## Network shares

Create and inspect links on the machine hosting the data. Do not rely on mapped
drive link behaviour. On Windows, symbolic links require Developer Mode or
elevation; otherwise use `config set-root`. Do not substitute directory junctions,
which the cache can treat as directories it owns.

Use `ethos-data --catalog /path/to/source-catalogue/datacatalog.json --root /shared/ethos/public unlink climate-inputs`
to remove the link without removing the original. To keep an independent copy,
follow [Move linked data into the cache](move-linked-data-into-the-cache.md).
