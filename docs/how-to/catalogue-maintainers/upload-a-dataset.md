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

Check the plan: the files each stage would transfer, the folder it would make
world-readable, the URL it would read them back from, and the record. A dry
run contacts no store.

## 2. Upload and inspect the result

```bash
ethos-data catalog upload my-dataset
```

For several datasets, name them in one invocation; naming a family such as
`reskit-test-data` uploads every member beneath it that has something to
upload; members frozen or withdrawn already are passed over. Every named dataset is checked
before transfer. A dataset that fails afterwards does not stop the others, and
earlier successes stay; run the command again to finish, since a dataset whose
upload is verified and recorded is not uploaded again.

Require `readable N/N`, no wrong sizes, and a successful exit. The final check
uses anonymous HTTP HEAD requests, not a remote SHA-256 read. For end-to-end
content verification, fetch the selected files into an independent cache and
run consumer `verify --deep`. A verified upload is recorded in the dataset's
`status.yaml`: the dataset is `available`, with its copy on dCache.

The command refuses restricted data, which never has a copy on dCache, and
unresolved licensing. If `--immutable` reports a conflict, a published file
changed: make the change a [revision](publish-a-new-version.md#revision); do
not delete and overwrite a released object.

## 3. Recheck without transferring or changing permissions

```bash
ethos-data catalog upload my-dataset --verify-only --no-chmod
```

`--verify-only` alone sets the permissions of the dataset's folder as well.
Pair it with `--no-chmod` for a diagnostic that does not change permissions.
The storage-locality lookup requires authentication. A recheck that passes is recorded as
well, and a frozen dataset can only be rechecked.

For failures, use [Diagnose a report](diagnose-a-report.md).

## 4. Record and release the accepted inventory

After successful transfer and verification, freeze the dataset. `record`
checks the copy on dCache again, makes it the authoritative copy and retires
`source_dir`, so later rebuilds keep the recorded inventory:

```bash
ethos-data catalog record my-dataset
```

Commit the status file on a branch and merge it by merge request on JuGit,
then [release the catalogue](release-the-catalogue.md): the release generates
the public catalogue, and its check refuses a public dataset whose upload was
not verified after its last inventory change.

See [Upload options](../../reference/cli/catalog.md#upload-dataset-dataset) for the
complete reference.
