# Keep test data in a repository

Export a small public catalogue selection as a verified bundle, so tests can run
without the catalogue or dCache. You need a collections file pinned to an
accepted catalogue revision. For tiny fixtures owned entirely by the package,
plain committed or generated test files may suffice; see
[Test data and reproducibility](../explanation/test-data.md).

## 1. Export a new bundle

```bash
ethos-data -c collections.yaml bundle export tests/data-bundle test_suite --source-revision ACCEPTED_REVISION
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
    files = load_bundle(BUNDLE).fetch("test_suite")
    # Pass files.one("known-input.csv") to the function under test.
    assert files
```

Adapt the assertion to test your workflow. Bundle reads check hashes, use only
local files, and fail for missing or changed fixtures.

## 3. Verify and commit

```bash
ethos-data bundle verify tests/data-bundle test_suite
pytest
git add tests/data-bundle
```

Commit both `bundle.json` and `data/<dataset>/<path>`. Check that Git ignore
rules did not omit fixture files. Do not edit the generated snapshot.

Validate the tests from a fresh checkout with network access blocked. If fixtures
must ship in a wheel, configure package-data inclusion and check the installed
layout too; a top-level `tests/` directory does not ensure inclusion.

## Promote an accepted fix

Follow [Update test data](update-test-data.md) for deliberate local edits, new
regression fixtures, and refreshing a bundle after acceptance.

See [Run package tests in CI](run-in-ci.md) and
[Bundle reference](../reference/cli/ethos-data.md#bundle).
