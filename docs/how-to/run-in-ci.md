# Run package tests in CI

This guide is for maintainers of packages such as ETHOS.RESKit. The same test
selection should work locally and in CI. Catalogue maintainers should use
[Run catalogue checks in CI](catalogue-ci.md).

## Choose which tests need live services

Use two distinct jobs or test selections:

| Test selection | Data source | Expected failure behaviour |
|---|---|---|
| Required unit and regression tests | Small repository copy with a local catalogue snapshot | Missing or corrupt required fixtures fail; dCache availability is irrelevant |
| Live data integration tests | A pinned official catalogue and normal download cache | Report catalogue or storage failures as integration failures |

Use [Keep test data in a repository](keep-test-data-in-a-repository.md) to
prepare the first selection. dCache is the authoritative source for released
test data; repository files are explicit snapshots that reduce repeated
transfers. A documented development option can temporarily allow modified
local bytes for bug reproduction without changing the official hashes or
uploading anything. Default and release checks should compare against the
accepted snapshot.

Mark tests which intentionally use the network and register the marker in
your package's pytest configuration, for example:

```ini
[pytest]
markers =
    data_network: exercises the live catalogue or remote dataset store
```

Then run the selections separately, after annotating the relevant tests with
`@pytest.mark.data_network`:

```bash
pytest -m "not data_network"
pytest -m data_network
```

The marker selects tests; it does not block network access. Required tests
should load their local bundle explicitly. Validate them with network access
blocked by the runner or a test fixture so an accidental remote dependency
fails visibly. Do not turn a missing required input into a skip.

## Cache live-test downloads between runs

For the integration job, choose a cache directory within the CI workspace and
restore/save it with your CI provider's cache mechanism:

```bash
export ETHOS_DATA_DIR="$PWD/.cache/ethos-data"
ethos-data -c reskit/data/collections.yaml plan test_suite
ethos-data -c reskit/data/collections.yaml fetch test_suite
ethos-data -c reskit/data/collections.yaml verify test_suite --deep
pytest -m data_network
```

Run from the package checkout and substitute its collection selection.
`plan` estimates dataset transfers but can fetch remote catalogue metadata.
A successful restored cache is an optimisation, not a guarantee that all data
or descriptors are present. `--deep` reads every selected byte; use a suitably
small integration collection when that cost matters.

Include the collections file and chosen catalogue version in the cache key.
If the pin lives in `collections.yaml`, its content hash captures both; if CI
supplies a catalogue override, include that revision separately. Retain the
metadata cache under `.catalog` along with the downloaded data to avoid
repeated requests for pinned descriptors.

## Pin the catalogue and record the version

Use the official version selected for the package release. A public GitHub
commit URL pins the metadata to a specific commit; a release tag should have
an immutability policy. A cluster job can use a versioned filesystem tree.
A path or URL called `current`, `main`, or `latest` is suitable for a deliberate
latest-data integration job, not a reproducible regression baseline.

Record the package revision, catalogue revision, collection names, and any
fixture divergence mode in the job output. See
[Catalogue hosting](catalogue-hosting.md) for internal filesystem deployment
and public release distribution.

## Update test data deliberately

For a code-only bug fix, keep the accepted snapshot unchanged. If reproducing
the bug requires modified input, preserve the original catalogue hashes and
opt in to local divergence for that development run. Do not silently repair
those edits from dCache during the experiment.

After the fix is verified, either restore the accepted bytes or
[propose the changed data](propose-a-dataset.md). Changed published bytes need
new immutable remote paths. Once accepted, refresh the repository snapshot and
its metadata together, review the diff, and return normal tests to strict
verification.

`--skip-unavailable` is appropriate only for an explicitly optional workflow
whose code handles omitted inputs. It is not a way to make a required CI test
pass with missing data.
