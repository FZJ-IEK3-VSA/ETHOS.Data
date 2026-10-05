# 0014. Name workflow inputs in the collection and pair test and full variants

**Status:** implemented · **Date:** 2026-09-15

## Context

Workflow code should not know resource keys. Examples and tests should run
the production code on small inputs, and then, unchanged, on the real ones. A
forgotten flag must not produce a wrong result that looks right.

## Decision

- A collection's `paths:` maps names to catalogue keys; each such name is a
  **named path**. `data.paths("onshore_wind", test=True)` returns
  `{name: Path}`.
- Every named path points to a file or a folder the collection selects. This
  is checked before anything is fetched, and by `show` and `fetch --plan`.
- A `test:` and a `full:` variant offer the same named paths. Resolving a
  collection checks this, for the collection and for every collection it
  reaches through `extends`.
- The full data is the default; `test=True` or `--test` is opt-in.

## Alternatives considered

- **Callers use resource keys.** Workflow code and examples change whenever a
  dataset gets a successor with new keys.
- **Test data by default.** A forgotten flag runs a real calculation on
  fixtures: a wrong result that looks right.
- **A bundle as the test variant.** A bundle is an offline copy of a selection
  and does not promise the named paths of the full data.

## Consequences

- Named paths are a contract between the package maintainer and the
  workflow.
- A successor changes the keys under the same named paths
  ([0019](0019-revisions-and-successors.md)).
- A forgotten `test=True` costs a large download, which is visible and can be
  interrupted.
- Every named path is required ([0013](0013-every-input-is-required.md)).
- See [Test and full variants of a collection](../../test-data.md#test-and-full-variants-of-a-collection),
  [Write a collections file](../../../how-to/package-maintainers/write-a-collections-file.md)
  and [Run on test data or the full data](../../../how-to/data-users/use-data-in-a-script.md#test-variant).

## Related

- [0003. One catalogue describes the data; each package's collections file selects from it](0003-one-catalogue-many-collections.md)
- [0013. Treat every input as required, and describe what is missing](0013-every-input-is-required.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0020. Keep a package's test data in a repository bundle that the catalogue publishes](0020-repository-bundles.md)
- [6. Runtime View](../runtime.md)
