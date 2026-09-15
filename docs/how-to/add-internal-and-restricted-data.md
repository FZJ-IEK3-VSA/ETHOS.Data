# Add internal and restricted datasets

Register approved local data in the internal catalogue and make it available to
authorised cluster users. You need stable source files and a source-catalogue
checkout. Replace all example paths with the actual internal locations.

## 1. Describe the installation

Create `datasets/licensed-example/dataset.yaml`:

```yaml
name: licensed-example
title: Licensed input data
source_dir: /legacy/licensed-example
ethos:access: restricted
ethos:visibility: hidden
ethos:restriction: Contact the dataset custodian for authorised cluster access.
ethos:embargo:
  until: "unspecified"
  reason: Metadata publication has not been approved; review with the custodian.
  becomes: restricted
ethos:license_status: unresolved
ethos:license_note: Record the actual agreement and review outcome here.
ethos:include:
  - "inputs/**"
```

Record actual provenance, selection, and terms. Complete the licensing review
before creating links or copies; replace the unresolved marker with the reviewed
metadata. Restricted entries must have no `ethos:remote_prefix` and must never
be marked `ethos:uploaded: true`.

For non-restricted internal data, use `ethos:access: internal`, an appropriate
remote prefix if needed, and a hidden visibility/embargo block. Metadata approved
for public listing can use `ethos:visibility: public`; that does not change access.

## 2. Build and inspect

```bash
ethos-data catalog --catalog-root /path/to/source-catalogue build licensed-example
ethos-data catalog --catalog-root /path/to/source-catalogue build licensed-example --check
```

Review the generated descriptor, shards, and index. Confirm paths, file counts,
hashes, classification, and the restriction note.

## 3. Register the existing directory

To read the original directly:

```bash
ethos-data config set-root licensed-example /legacy/licensed-example
```

To populate the protected restricted cache instead:

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted
ethos-data --catalog /path/to/source-catalogue/datacatalog.json materialize licensed-example --from /legacy/licensed-example --dry-run
ethos-data --catalog /path/to/source-catalogue/datacatalog.json materialize licensed-example --from /legacy/licensed-example
```

Before copying, establish permissions/default ACLs and confirm the licence permits
the copy. An authorised link is also supported; see
[Restricted cache links](link-cluster-data.md#restricted-data).
For internal data use a local root or a public/internal cache link.

## 4. Verify a complete dataset and use it from a package {#5-verify-a-complete-dataset-and-use-it-from-a-package}

Create `maintenance-collections.yaml`:

```yaml
collections:
  check_licensed_example:
    include:
      - dataset: licensed-example
```

```bash
ethos-data --catalog /path/to/source-catalogue/datacatalog.json -c maintenance-collections.yaml plan check_licensed_example
ethos-data --catalog /path/to/source-catalogue/datacatalog.json -c maintenance-collections.yaml verify check_licensed_example --deep
```

Check that the plan names the intended installation and every required file
matches. Remove a per-dataset override before verifying a newly populated cache,
otherwise the check still reads the original.

## 5. Release and update

Commit and [deploy the complete internal metadata](catalogue-hosting.md).
Give users the catalogue location and cache root through the internal channel.
Package maintainers can now select the dataset in their collections.

For additional files, update the source selection, rebuild, and repeat review
and verification. For changed bytes, retain versions required by older pins and
assign new resource paths or dataset identifiers.

Keep `source_dir` while it is the build input. If it is retired after a verified
copy, remove it and use `ethos:frozen: true`.
See [Move linked data](move-linked-data-into-the-cache.md).

Restricted data has no upload step. Internal data can remain local; see the
[current internal-upload limits](upload-a-dataset.md#internal-uploads) before
attempting an authenticated store workflow.
