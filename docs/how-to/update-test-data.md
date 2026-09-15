# Update test data

Add a regression case or refresh a fixture without silently changing the inputs
of existing tests. For the choice of storage, see
[Test data and reproducibility](../explanation/test-data.md).

## Choose the change

| Change needed | Action |
|---|---|
| New test with existing inputs | Add the test; leave data and catalogue pins unchanged. |
| Tiny synthetic input owned by the package | Generate it in the test or commit it alongside tests; review input and expected result together. |
| Experiment with changed bytes in a bundle | Use the temporary override below. |
| New resources or changed catalogued inventory | Stage non-restricted candidates, validate them, then propose a dataset revision. |
| Accepted catalogue revision | Refresh the collection and bundle together. |

## Reproduce a bug with an existing bundled file

Edit the fixture on a development branch and opt in only in the affected test:

```python
files = load_bundle(BUNDLE).fetch("test_suite", allow_modified=True)
```

Keep the original `bundle.json`. Record the changed resource and expected
result. This permits changed existing bytes; new or missing files require an
inventory update.

```bash
ethos-data bundle verify tests/data-bundle test_suite
```

Expect `modified` and a nonzero exit until you restore or replace the fixture.
If the edit is unnecessary for the final regression test, restore it and remove
the override.

## Propose additional or corrected catalogued inputs

1. Put the candidate in a separate development directory.
2. [Stage it](stage-unpublished-data.md) and run the affected tests. Restricted
   inputs must use an authorised local installation instead.
3. [Propose the dataset revision](propose-a-dataset.md), including the bug or new
   test, changed resource keys, provenance, and validation.
4. Use new dataset identifiers or versioned resource paths for changed bytes
   that must coexist with an old release. Keep new remote paths too.

## Refresh after acceptance

Update `collections.yaml` to the released catalogue revision and desired
selection. Remove staging/local-root overrides for the accepted dataset, then:

```bash
ethos-data -c collections.yaml info test_suite
ethos-data -c collections.yaml bundle export tests/data-bundle-next test_suite --source-revision ACCEPTED_REVISION
ethos-data bundle verify tests/data-bundle-next test_suite
```

`ACCEPTED_REVISION` is a provenance label, not a revision selector: the
`catalog:` pin must already select it. Review added/removed paths, hashes,
licences, and expected test results before replacing the tracked old bundle
with the new directory. Export requires a fresh target.

Remove `allow_modified=True`, run the strict local tests, and run the relevant
live integration tests. Commit the pin, collection, bundle, and regression test
together. Ordinary tests must not regenerate or refresh their own fixtures.

