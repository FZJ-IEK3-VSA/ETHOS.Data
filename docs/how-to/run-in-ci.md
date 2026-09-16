# Run package tests in CI

Run required tests without remote data dependencies and check live access in a
separate test selection. For choosing fixtures, see
[Test data and reproducibility](../explanation/test-data.md).

## 1. Mark live data tests

Register this pytest marker in your package configuration:

```ini
[pytest]
markers =
    data_network: exercises the live catalogue or remote dataset store
```

Apply `@pytest.mark.data_network` to the relevant tests, then run:

```bash
pytest -m "not data_network"
pytest -m data_network
```

Required local tests should read their
[repository bundle](keep-test-data-in-a-repository.md) or package-owned fixtures.
Block network access in the required-test job to detect accidental dependencies;
the marker alone does not block it. Missing required data must fail.

## 2. Retain the live-test cache

Restore/save a cache directory using your CI provider's cache facility:

```bash
export ETHOS_DATA_DIR="$PWD/.cache/ethos-data"
ethos-data -c collections.yaml plan test_suite
ethos-data -c collections.yaml fetch test_suite
ethos-data -c collections.yaml verify test_suite --deep
pytest -m data_network
```

Replace the file and collection with your package's and use its accepted
catalogue pin; a package with a data command of its own can use it here
equivalently. Include the collections-file hash and any explicit catalogue
revision override in the cache key. Retain metadata under `.catalog` too. An
empty runner needs downloads; a restored cache can reuse matching files. For a
collection with `test:` and `full:` variants, the fast job uses the test
variant — `fetch onshore_wind --test` here, `test=True` in `paths()` in the
tests — and only a deliberate integration job fetches the full data.

Do not use `--skip-unavailable` to pass a required test with missing inputs.
Restricted integration tests require an authorised runner and local installation.

## 3. Record and update inputs

Log the package revision, catalogue revision, collections, and active overrides.
Use a commit URL or a versioned internal tree for a reproducible baseline.
A deliberately moving catalogue belongs in a separate latest-data integration job.

For new regressions or corrected inputs, follow
[Update test data](update-test-data.md). Keep default and release checks strict;
ordinary test runs must not refresh fixtures or accept unexplained changes.

Catalogue maintainers should use [Catalogue CI](catalogue-ci.md) instead.
