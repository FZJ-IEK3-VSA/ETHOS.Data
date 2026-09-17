# Keep test data in a repository

Export a small public catalogue selection as a verified bundle, so tests can run
without the catalogue or dCache. Your package must ship a collections file pinned to an
accepted catalogue revision. The examples use RESKit's public test collection;
substitute your own wrapper and collection. For tiny fixtures owned entirely by the package,
plain committed or generated test files may suffice; see
[Test data and reproducibility](../../explanation/test-data.md).

## 1. Export a new bundle

```bash
reskit-data bundle export tests/data-bundle test_suite_public --source-revision ACCEPTED_REVISION
```

Replace the revision label. It records provenance; it does not select metadata.
The file's `catalog:` or an explicit `--catalog` must already select that revision.

To use an existing local copy, append `--source-root DATASET=/absolute/path/to/dataset`.
Repeat for each dataset. The source must have the catalogue's relative layout and
match its hashes. The target must not already exist. Export refuses internal and
restricted datasets; check redistribution terms before committing public fixtures.

## 2. Read the bundle in tests

```python
from pathlib import Path
from ethos_data import load_bundle

BUNDLE = Path(__file__).resolve().parent / "data-bundle"

def test_my_workflow():
    files = load_bundle(BUNDLE).fetch("test_suite_public")
    # Pass files.one("known-input.csv") to the function under test.
    assert files
```

Adapt the assertion to test your workflow. Bundle reads check hashes, use only
local files, and fail for missing or changed fixtures.

## 3. Verify and commit

```bash
reskit-data bundle verify tests/data-bundle test_suite_public
pytest
git add tests/data-bundle
```

Commit both `bundle.json` and `data/<dataset>/<path>`. Check that Git ignore
rules did not omit fixture files. Do not edit the generated snapshot.

Validate the tests from a fresh checkout with network access blocked. If fixtures
must ship in a wheel, configure package-data inclusion and check the installed
layout too; a top-level `tests/` directory does not ensure inclusion.


## Promote an accepted fix {#promote-an-accepted-fix}

### Choose the change

| Change needed | Action |
|---|---|
| New test with existing inputs | Add the test; leave data and catalogue pins unchanged. |
| Tiny synthetic input owned by the package | Generate it in the test or commit it alongside tests; review input and expected result together. |
| Experiment with changed bytes in a bundle | Use the temporary override below. |
| New resources or changed catalogued inventory | Stage non-restricted candidates, validate them, then propose a dataset revision. |
| Accepted catalogue revision | Refresh the collection and bundle together. |

### Reproduce a bug with an existing bundled file

Edit the fixture on a development branch and opt in only in the affected test:

```python
files = load_bundle(BUNDLE).fetch("test_suite_public", allow_modified=True)
```

Keep the original `bundle.json`. Record the changed resource and expected
result. This permits changed existing bytes; new or missing files require an
inventory update.

```bash
reskit-data bundle verify tests/data-bundle test_suite_public
```

Expect `modified` and a nonzero exit until you restore or replace the fixture.
If the edit is unnecessary for the final regression test, restore it and remove
the override.

### Propose additional or corrected catalogued inputs

1. Put the candidate in a separate development directory.
2. [Stage it](propose-a-dataset.md#stage-development-data) and run the affected tests. Restricted
   inputs must use an authorised local installation instead.
3. [Propose the dataset revision](propose-a-dataset.md), including the bug or new
   test, changed resource keys, provenance, and validation.
4. Use new dataset identifiers or versioned resource paths for changed bytes
   that must coexist with an old release. Keep new remote paths too.

### Refresh after acceptance

Update `collections.yaml` to the released catalogue revision and desired
selection. Remove staging/local-root overrides for the accepted dataset, then:

```bash
reskit-data show test_suite_public
reskit-data bundle export tests/data-bundle-next test_suite_public --source-revision ACCEPTED_REVISION
reskit-data bundle verify tests/data-bundle-next test_suite_public
```

`ACCEPTED_REVISION` is a provenance label, not a revision selector: the
`catalog:` pin must already select it. Review added/removed paths, hashes,
licences, and expected test results before replacing the tracked old bundle
with the new directory. Export requires a fresh target.

Remove `allow_modified=True`, run the strict local tests, and run the relevant
live integration tests. Commit the pin, collection, bundle, and regression test
together. Ordinary tests must not regenerate or refresh their own fixtures.


See [Run package tests in CI](run-in-ci.md) for CI wiring and
[Bundle reference](../../reference/cli/package-data.md#bundle) for command options.
