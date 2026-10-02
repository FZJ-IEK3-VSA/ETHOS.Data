# Run tests and examples in CI

Run the required tests from the repository copies without any network, run
the live tests against the catalogue in a separate job, and choose per job
whether bundled data is read from the repository or downloaded. For choosing
fixtures, see [Test data and reproducibility](../../explanation/test-data.md).

## 1. Split the tests

Register a marker and apply it to every test that needs the live catalogue or
the published store:

```ini
[pytest]
markers =
    data_network: exercises the live catalogue or the published store
```

```bash
pytest -m "not data_network"     # required: repository copies and package-owned fixtures only
pytest -m data_network           # live: catalogue and downloads
```

Block network access in the required job so an accidental dependency fails
there; the marker alone does not block anything. A missing input must fail,
never be skipped.

## 2. Choose the source of bundled data {#download-switch}

Data the package ships as a [repository copy](keep-data-in-the-repository.md)
is read from there by default. To make a job download the same data from the
catalogue instead, and so test the download route, set the shared switch:

```bash
ETHOS_DATA_DOWNLOAD=1 pytest -m data_network
```

Run the required job with the switch off and one live job with it on. A
bundled file that is missing or altered is an error in both modes, not a
reason to download, and the live job fails on a bundle version the catalogue
does not hold yet.

!!! warning "Gap: no shared download switch"
    `ETHOS_DATA_DOWNLOAD` does not exist; one package has a variable of its
    own for the purpose. See
    [Keep data in the repository](keep-data-in-the-repository.md#use-a-bundle).

## 3. Download public data the repository does not hold

A live job fetches what its collections select from the published store. A
package on a public installation can download public datasets only; internal
and restricted data need a runner on the cluster computer with the shared caches
configured. Retain the cache between runs with the CI provider's cache
facility:

```bash
export ETHOS_DATA_DIR="$PWD/.cache/ethos-data"
ethos-data selftest
<your-tool>-data fetch test_suite_public --plan
<your-tool>-data fetch test_suite_public
<your-tool>-data verify test_suite_public --deep
pytest -m data_network
```

The [self-test](../data-users/set-up-your-machine.md#check-a-download) comes
first: it downloads under 200 KB and fails with the step that broke when the
runner cannot reach the catalogue or the store, before a large fetch starts.
A runner may also carry a settings file in its account, as a self-hosted
runner on the cluster computer does. To keep the job independent of it, name
a file the repository holds:

```bash
export ETHOS_DATA_CONFIG="$PWD/ci/ethos-data.yaml"
```

ETHOS.Data then reads only that file and the environment variables; see
[Use another settings file](../data-users/set-up-your-machine.md#another-settings-file).

!!! warning "Gap: `selftest` is not implemented"
    It is planned and to be implemented separately. Until then, the
    `fetch --plan` step is the first that needs the catalogue.

Key the cache on the hash of `collections.yaml` and any catalogue override. A
restored cache reuses matching files; an empty runner downloads. For a
collection with `test:` and `full:` variants, the fast job fetches the test
variant, `fetch my_workflow --test`, and only a deliberate integration job
fetches the full data.

## 4. Record the inputs

Log the package revision, the catalogue revision, the collections and the
active overrides in the job output. Use a pinned catalogue for the baseline
job. A package that declares only a minimum catalogue version gets a second,
latest-catalogue job that is allowed to fail and tells you when the catalogue
moved under the package.

When a test needs new or corrected inputs, follow
[Keep data in the repository](keep-data-in-the-repository.md#update-data).
Catalogue maintainers check and release the catalogue itself as described
under [Release the catalogue](../catalogue-maintainers/release-the-catalogue.md#in-ci).
