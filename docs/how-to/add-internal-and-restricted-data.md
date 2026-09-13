# Add internal and restricted datasets

For catalogue maintainers adding datasets, or additional files in an existing
dataset, to the internal catalogue on the cluster. The **internal catalogue**
is the source metadata repository synchronized with jugit. **Restricted** is an
access class for particular datasets; it is not a separate catalogue format.

Registering metadata does not copy or upload data. Start from an existing
cluster directory you are entitled to read, build its inventory, and configure
how consumers find those files.

## 1. Choose access and visibility

| Situation | `ethos:access` | `ethos:visibility` | Where consumers read bytes |
|---|---|---|---|
| Institute data available to colleagues but not ready for public release | `internal` | `hidden` | Existing local directory or shared-cache link; an internal upload is a separate operation |
| Licensed data whose metadata must also stay private | `restricted` | `hidden` | An authorised local directory or restricted root |
| Licensed data whose description may be listed publicly | `restricted` | `public` | The same authorised local storage; public metadata does not open access to the bytes |

Hidden entries need an `ethos:embargo` block explaining the reason and intended
review or transition. `until: "unspecified"` is available when no date can be
promised, with an explicit reason. The block is metadata, not a scheduled job
that automatically releases the dataset.

For public downloadable data use [Describe a dataset](describe-a-dataset.md).
Do not classify data as restricted merely because its metadata lives in the
internal repository. Equally, changing visibility to public does not remove a
dataset's restricted access class.

## 2. Describe the existing bytes

Work in a maintainer checkout, for example
`/shared/ethos/ethos-data-catalog-internal`. The paths and names in this guide are
examples; substitute the actual cluster paths. Keep edits out of the versioned
catalogue directory currently served to readers.

For licensed data, create `datasets/licensed-example/dataset.yaml`:

```yaml
name: licensed-example
title: Licensed input data used on the cluster
source_dir: /legacy/licensed-example
ethos:access: restricted
ethos:visibility: hidden
ethos:restriction: >-
  Access is limited to authorised users. Contact the dataset custodian for
  access to the existing cluster installation; these files are not downloaded.
ethos:embargo:
  until: "unspecified"
  reason: Metadata publication has not been approved; review with the custodian.
  becomes: restricted
ethos:license_status: unresolved
ethos:license_note: Record the applicable agreement and review outcome here.
ethos:include:
  - "inputs/**"
```

Replace the example file selection and restriction message. Add actual `sources`,
`licenses`, and provenance using [Describe a dataset](describe-a-dataset.md).
The unresolved marker is for metadata awaiting review, not permission to use or
redistribute data. Do not substitute an open licence for a vendor agreement.
If the description may be public, set `ethos:visibility: public` and remove the
embargo block; keep `ethos:access: restricted`.

Restricted datasets have **no `ethos:remote_prefix`**; the builder rejects it.
Keep `source_dir` and do not mark these files `ethos:uploaded: true`. That flag
means the inventory has been frozen after upload to dCache, which is not the
restricted-data workflow.

For an internal dataset, use the same source-directory/provenance pattern but
replace the classification block:

```yaml
ethos:access: internal
ethos:visibility: hidden
ethos:remote_prefix: institute-example-v1
ethos:embargo:
  until: "unspecified"
  reason: Local validation is in progress; review before publication.
  becomes: public
```

Use the internal dataset's own `name`, title, paths, and licence information.
`source_dir` is a maintainer build input. Consumers do not automatically use it;
the next steps configure their location separately.

## 3. Build and inspect

From anywhere, pass the source checkout to the maintainer command:

```bash
ethos-data catalog --catalog-root /shared/ethos/ethos-data-catalog-internal build licensed-example
ethos-data catalog --catalog-root /shared/ethos/ethos-data-catalog-internal build licensed-example --check
```

Review `datasets/licensed-example/datapackage.json`, any generated shards, and
`datacatalog.json` in that checkout. Confirm the selected paths, file counts,
sizes, hashes, and access/visibility values. The input files remain in their
original directory. `--check` checks generated metadata for staleness; consumer
`verify --deep` below is the separate check of the actual accessible bytes.

Do not hand-edit generated JSON to add a resource. Fix the source YAML, file
selection, or underlying input and rebuild.

## 4. Give consumers an existing local location

For one dataset, configure the original directory:

```bash
ethos-data config set-root licensed-example /legacy/licensed-example --scope user
```

Or let the cluster administrator establish a restricted namespace and configure
its root for readers:

```text
/shared/ethos/restricted/
  licensed-example/inputs/...
```

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted --scope user
```

An administrator can use `--scope site` for a machine default. A directory that
is already an authorised installation need not be copied to register it. The
[cluster migration guide](migrate-cluster-data.md#restricted-data) also describes
a temporary symlink to that installation and its later relocation.

For internal data, use `config set-root` or the public/internal namespace-link
workflow in that guide. The public cache's name does not grant access: filesystem
permissions must still restrict internal directories to the appropriate users.

## 5. Verify a complete dataset and use it from a package

Create a maintainer collections file, such as
`/shared/ethos/maintenance-collections.yaml`:

```yaml
catalog: /shared/ethos/ethos-data-catalog-internal/datacatalog.json
collections:
  check_licensed_example:
    include:
      - dataset: licensed-example
        files: ["**"]
```

```bash
ethos-data --catalog /shared/ethos/ethos-data-catalog-internal/datacatalog.json \
  -c /shared/ethos/maintenance-collections.yaml plan check_licensed_example
ethos-data --catalog /shared/ethos/ethos-data-catalog-internal/datacatalog.json \
  -c /shared/ethos/maintenance-collections.yaml verify check_licensed_example --deep
```

Confirm the plan names the intended in-place location and verification reports
all expected files as `ok`. Do not accept an empty selection or skipped required
files as validation. Inspect `ethos-data config show` for per-dataset overrides
and active staging if the location is unexpected.

The package maintainer can then select this dataset in a package collection.
Users read it through the served internal catalogue; see
[Add the internal data catalogue](add-internal-catalogue.md) and
[Write a collections file](write-a-collections-file.md).

## 6. Add more files later

Keep new files under the dataset's source directory and extend `ethos:include`
when necessary. Rebuild that dataset, review the added resource paths and hashes,
and repeat full verification. A separate product, release, or access policy is
usually clearer as a new dataset entry rather than an unrelated extension.

For changed existing bytes, retain the old version needed by existing catalogue
pins and introduce versioned resource paths or a new dataset identifier. Updating
metadata cannot restore an old licensed input that has been overwritten locally.
Use [staging](stage-unpublished-data.md) for changing **non-restricted** development
inventories; it deliberately does not shadow restricted datasets.

## 7. Release the metadata to readers

Commit the reviewed internal metadata and synchronize it with jugit. Activate a
complete validated filesystem snapshot as described in
[Catalogue hosting](catalogue-hosting.md). Hidden entries are left out of the
public catalogue when it is regenerated. A restricted entry with public visibility
may be listed there, but its bytes remain local and access-controlled.

There is no upload step for restricted data. Internal data can remain local;
if an internal upload is needed, follow [Upload a dataset](upload-a-dataset.md)
and its `--allow-internal` and verification caveats. The published dCache source
of truth applies to uploaded datasets; the authorised local installation remains
the source for restricted data.
