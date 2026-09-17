# Run catalogue checks in CI

This guide is for catalogue maintainers. For a consuming package's tests, see
[Run package tests in CI](../package-maintainers/run-in-ci.md).

Run the source-catalogue checks from a checkout containing `catalog.yaml` with
the maintainer tooling installed:

```bash
ethos-data catalog build --check
ethos-data catalog publish ../ETHOS.Data-Catalogue --check
```

Both commands compare generated output and fail if it is stale without writing
it. The publication target is a separate checkout of the public catalogue at
the revision paired with the source catalogue under review.

## Choose the runner for the build check

The source state determines which inputs are required:

| Dataset state | Runner requirement |
|---|---|
| Candidate with `source_dir` | Read access to that directory to check its inventory against the candidate bytes |
| Uploaded with `ethos:uploaded: true` and no `source_dir` | Existing generated descriptor and any shards; the recorded inventory is preserved |

A cluster runner can inspect candidate directories that an external hosted
runner cannot read. Checking an uploaded dataset's metadata does not download
its data or prove that dCache is currently available. Preserve descriptors and
shards in the source checkout because they contain the frozen inventory.

The manifest builder uses a local size/mtime hash cache to avoid rereading
unchanged candidates. For a review that must hash every candidate byte, ensure
the ephemeral CI checkout has no restored `.ice2-hash-cache.json` files.

## Separate checks from publication

A metadata review job should run the two `--check` commands. Upload, storage
verification, repository release, and cluster deployment are later actions
with the appropriate runner access. Follow
[Accept a dataset proposal](accept-a-dataset.md) for their ordering.

To check storage availability without repeating a transfer, use an explicitly
selected dataset:

```bash
ethos-data catalog upload my-dataset --verify-only --no-chmod
```

`--no-chmod` prevents the verification run changing directory permissions.
This performs network checks; it is a separate integration or release check,
not a substitute for comparing generated metadata. Consult
[Upload a dataset](upload-a-dataset.md) for the verification semantics and
access-class limitations.

## Keep release evidence together

Record the source commit, public commit or release tag, build/check results,
and upload verification result for the same accepted dataset version. Deploy
a complete reviewed catalogue tree for filesystem readers; do not let CI
rebuild individual files in the live directory while jobs are reading it.
