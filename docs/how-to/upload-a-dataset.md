# Upload a public dataset

Upload accepted public bytes from a source-catalogue checkout. You need built
manifests, unchanged source files, settled licensing, and dCache credentials.

## Credentials (once per machine)

Follow [Set up dCache access](set-up-dcache-access.md). If the publication root
does not exist, [bootstrap it](bootstrap-a-catalogue.md#2-prepare-the-publication-root)
before uploading.

## 1. Check the candidate

Run from the source checkout:

```bash
ethos-data catalog build my-dataset --check
ethos-data catalog upload my-dataset --dry-run
```

Check the selected files, source, destination, and public URL. A dry run can
contact storage through rclone but does not transfer files or change permissions.
Do not combine it with `--verify-only`.

## 2. Upload and inspect the result

```bash
ethos-data catalog upload my-dataset
```

For several datasets, name them in one invocation. Every named dataset is checked
before transfer; uploads then run per dataset without rollback of earlier successes.

Require `readable N/N`, no wrong sizes, and a successful exit. The final check
uses anonymous HTTP HEAD requests, not a remote SHA-256 read. For end-to-end
content verification, fetch the selected files into an independent cache and
run consumer `verify --deep`.

The command refuses restricted data and unresolved licensing. If `--immutable`
reports a conflict, assign new published paths; do not delete and overwrite a
released object.

## 3. Recheck without transferring or changing permissions

```bash
ethos-data catalog upload my-dataset --verify-only --no-chmod
```

`--verify-only` alone still attempts to chmod a public prefix. Pair it with
`--no-chmod` for a diagnostic that does not change permissions. Storage-locality
lookup still requires authentication.

For failures, use [Diagnose catalogue problems](troubleshoot-catalogue.md).

## 4. Record and release the accepted inventory

After successful transfer and verification, set `ethos:uploaded: true` in
`dataset.yaml` and remove `source_dir`. Then:

```bash
ethos-data catalog build my-dataset
ethos-data catalog build --check
ethos-data catalog publish ../ETHOS.Data-Catalogue
```

[Review and release the generated metadata](publish-the-catalogue.md).
`upload` does not mark the dataset uploaded automatically, and `publish` does
not push or deploy it.

## Internal uploads

`--allow-internal` permits an internal dataset and skips automatic public chmod.
It does **not** establish private permissions, add authenticated consumer
downloads, or switch verification to authenticated requests. The current command
still checks anonymously and can report failure for correctly private bytes.

Use a separate protected storage location agreed with the administrator; never
assume `--allow-internal` makes a public parent private. Prefer the
[local internal-data workflow](add-internal-and-restricted-data.md) until an
authenticated transfer/read procedure is established.

See [Upload options](../reference/cli/catalog.md#upload-dataset-dataset) for the
complete reference.
