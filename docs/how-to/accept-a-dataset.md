# Accept a dataset proposal

This guide is for catalogue maintainers receiving a package maintainer's
[proposal](propose-a-dataset.md). Work in a private source-catalogue checkout
with access to the candidate bytes. Do not edit the live cluster catalogue in
place while readers use it.

## 1. Review the proposal

Check identity, provenance, licensing, visibility, file selection, and test
results. Confirm how you can read the bytes. Agree on a new path or version for
any changed published file; retain the old path needed by existing pins.

Copy the accepted source metadata into `datasets/<name>/dataset.yaml` and set
`source_dir` to the candidate directory on your machine. Do not blindly retain
the contributor's workstation path. See [Describe a dataset](describe-a-dataset.md)
for required fields and include/exclude rules.

## 2. Build and inspect the inventory

```bash
ethos-data catalog build my-dataset
git diff -- datasets/my-dataset datacatalog.json
```

Compare the generated paths, sizes, and hashes with the submitted inventory.
Check that the collection selects the intended inputs and includes companion
files. Resolve any unexpected files or differences before transferring data.
For a new candidate this build computes hashes from local bytes; once a dataset
is marked uploaded, a build preserves its recorded inventory.

For data that will remain local or licensed, continue with
[Add internal and restricted datasets](add-internal-and-restricted-data.md).
Restricted datasets have no upload step; internal datasets can be used locally
without uploading. The following steps describe the upload/release path.

## 3. Upload and verify the accepted bytes

```bash
ethos-data catalog upload my-dataset --dry-run
ethos-data catalog upload my-dataset
```

Use [Upload a dataset](upload-a-dataset.md) for credentials, access-class
restrictions, verification results, and recovery. For a subset, name all
accepted datasets in the same invocation so preflight validation covers the
whole selection. Transfers still run per dataset; a later failure does not
roll back earlier successful transfers.

After successful upload and verification, set `ethos:uploaded: true`, remove
`source_dir`, and rebuild. This explicitly records dCache as the authoritative
copy and freezes the accepted inventory. Do not mark an unverified upload as
complete.

## 4. Generate and review the public view

```bash
ethos-data catalog build
ethos-data catalog publish ../ETHOS.Data-Catalogue
```

The target must be the dedicated generated public checkout: `publish` clears
its generated tree. Inspect its diff and ensure hidden datasets and internal
fields are absent, following [Publish the catalogue](publish-the-catalogue.md).

Generating metadata locally for review is possible before an upload, but
making new downloadable entries available to consumers must follow successful
upload and verification. `publish` itself does not establish storage readiness.

## 5. Release and complete the handoff

Commit the accepted source metadata to the internal repository and the
generated view to the public repository. Deploy the complete reviewed internal
catalogue tree to the cluster and synchronize its revision with JuGit. Release
the public metadata on GitHub at a version that package maintainers can pin.
These are coordinated operator actions; the CLI does not perform a transaction
across dCache, Git hosts, and cluster deployment.
See [Catalogue hosting](catalogue-hosting.md) for the deployment procedure.

Give the contributor the dataset identifiers and catalogue version. Ask them
to remove development overrides and verify the package workflow against that
version. Keep the proposal's validation and release identifiers together so a
later bug report can be traced to the accepted bytes.

See also [Run catalogue checks in CI](catalogue-ci.md),
[Withdraw a dataset](withdraw-a-dataset.md), and
[Troubleshoot catalogue access](troubleshoot-catalogue.md).
