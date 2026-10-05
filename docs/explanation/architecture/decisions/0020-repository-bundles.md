# 0020. Keep a package's test data in a repository bundle that the catalogue publishes

**Status:** proposed · **Date:** 2026-10-05 · **Implemented by:** #25

## Context

A package's required tests must run without dCache, and its own test data
changes with its code. Two versions of the same test data must share a
cache, and nobody should pick paths by hand. A test must still be able to
read a deliberately changed file while a bug is reproduced, without that
change reaching anyone else.

## Decision

- A **repository bundle** holds one family of test data in the package's
  repository: `bundle.json` (format `ethos-data-bundle-v2`, with the family,
  the version and the `release` that holds it), the files under
  `data/<family>/<member>/`, and the descriptions and licence documents under
  `datasets/<family>/<member>/`.
    - The bundle is the source of truth for its next, unpublished version.
      dCache holds every published version, and a published version never
      changes.
    - `bundle create` starts version 1, unpublished; `bundle update` records
      every change ([0021](0021-one-bundle-version-per-release.md)).
      `catalog add-bundle DIR` takes a version into the catalogue and
      publishes changed members as revisions
      ([0019](0019-revisions-and-successors.md)).
- A handle lists its bundles with `bundles=`. The bundle locator, third in
  the lookup chain ([0012](0012-one-lookup-chain.md)), reads them in place,
  hash-checked once per process. A missing or changed file raises
  `BundleError` and is never downloaded. Reading a version that no release
  holds warns once per process.
- The handle reads its bundles' metadata from the bundles. It reads the
  catalogue index only when a call needs a dataset no bundle holds, and checks
  the release bounds then; each bundle's recorded release is checked against
  the bounds too.
- The download switch (`download=True`, `ETHOS_DATA_DOWNLOAD=1`) takes the
  catalogue route instead, which refuses a version that no release holds.
- An **exported bundle** (format `ethos-data-bundle-v1`) is a copy of released
  public catalogue data with its collections. `bundle export` downloads the
  files from the publication URL in effect, or takes them from `--source-root`
  copies, and checks them against the catalogue's hashes. It starts published.
  Restricted, internal, hidden and staged data are refused.
- Both kinds are read through the lookup chain or directly with
  `load_bundle(DIR).fetch(collection)`. With `allow_modified=True`, one test
  reads a changed file: the recorded hashes are kept, a warning names the
  changed keys, and nothing repairs, republishes or updates dCache.

## Alternatives considered

- **dCache as the only source of truth for test data.** Fixtures could not be
  developed together with the code that reads them.
- **Exported copies only.** Data a package owns would have no source of
  truth.

## Consequences

- Required package tests run in a fresh checkout with no network.
- Repository files stay under 100 MiB; large data belongs in live tests.
- A member's build input lies in the maintainer's package checkout until the
  member is frozen, so a release that checks it runs where that checkout is.
- Packages pass `bundles=` instead of reading their bundles themselves.
- See [Keep data in the repository](../../../how-to/package-maintainers/keep-data-in-the-repository.md),
  [Run tests and examples in CI](../../../how-to/package-maintainers/run-in-ci.md#download-switch)
  and [Test data, development inputs, and reproducibility](../../test-data.md).

## Related

- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0021. Make a bundle version exactly what one release holds](0021-one-bundle-version-per-release.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
