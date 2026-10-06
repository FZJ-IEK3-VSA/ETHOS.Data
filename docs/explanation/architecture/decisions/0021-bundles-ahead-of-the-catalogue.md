# 0021. Let a bundle be ahead of the catalogue, and warn until it is realigned

**Status:** implemented · **Date:** 2026-10-06 · **Implemented by:** #25

## Context

A package's bundle changes with the package's code
([0020](0020-repository-bundles.md)). The catalogue takes a change in only
through review, a build and a release. Development must not wait for the
catalogue, yet a bundle that drifts from the catalogue unnoticed leaves two
versions of one dataset. The package's required tests run offline, and its
maintainer runs them most. No read may load more catalogue metadata because a
package has bundles ([0005](0005-lazy-index-descriptors-and-shards.md)).

## Decision

`bundle update DIR` records changed, added and removed files and new datasets
in `bundle.json`, against each dataset's alignment: the catalogue revision it
was last aligned with. A bundled dataset is aligned, or in one of three other
states:

| State | When | Found |
|---|---|---|
| Ahead | the bundle holds recorded changes to the dataset, or the catalogue does not describe it | from `bundle.json` alone, offline included |
| Behind | the index row's `ethos:revision` is later than the recorded revision | where the handle reads the catalogue index anyway: for a dataset no bundle holds, or with the download switch |
| Withdrawn from the catalogue | the dataset has a recorded alignment, but the index does not describe it | as for behind |

- Reading a bundle never fails because of these states, so development never
  waits for the catalogue.
- Every process that reads a dataset of an ahead bundle warns once per
  bundle, offline included, so the package's required tests show it. A
  bundle that is behind warns the same way. The warning names the bundle,
  the datasets and both ways to realign; for a withdrawn dataset it says to
  drop it from the bundle or switch to its successor:

```text
warning: bundle tests/data/bundle is ahead of the catalogue: era5-cutout (2 files changed),
wind-sites (not in the catalogue). Realign it soon: <tool>-data propose tests/data/bundle,
or take the catalogue's version: <tool>-data bundle update tests/data/bundle --from-catalog era5-cutout
```

- The warning has its own category, exported from `ethos_data`, so a package
  can filter it and keep it a warning in a test run that turns warnings into
  errors.
- No read loads more catalogue metadata than it would without bundles. The
  handle compares revisions only with index rows it reads anyway, and a
  handle whose bundles hold every input reads no index and compares no
  revision.
- `bundle verify`, `bundle update`, `propose` and `catalog add-bundle`
  compare files, descriptions and licence documents with the catalogue. That
  also finds a description corrected in a patch release
  ([0018](0018-numbered-catalogue-releases.md)).
- **Realigning towards the catalogue:**
    1. `<tool>-data propose DIR` drafts the proposal for the ahead datasets
       ([0025](0025-handoff-templates.md)).
    2. The catalogue maintainer runs `catalog add-bundle DIR [DATASET...]`. It
       takes new datasets, changed descriptions and revisions
       ([0019](0019-revisions-and-successors.md)), a revision only while the
       catalogue is still at the bundle's alignment. It copies the files into
       a build input the catalogue maintainers own, so the catalogue never
       reads a package checkout.
    3. The catalogue maintainers build, upload, record, merge and release.
    4. The package maintainer runs `bundle update DIR` with the catalogue
       readable. It records the new alignment, and the warning stops.
- **Realigning from the catalogue:**
  `bundle update DIR --from-catalog NAME...` takes the catalogue's files of
  the bundled selection, with the description and licence documents, and
  records the alignment.
- **The download switch** (`download=True`, `ETHOS_DATA_DOWNLOAD=1`): a
  bundled file whose recorded SHA-256 the catalogue holds for the same key is
  read through the catalogue route, from the public cache or a download.
  Every other bundled file is read from the bundle, with the warning. Being
  ahead never raises. The switch changes where a file is read from, never
  which bytes, and a bundle's own bytes never enter a cache.

## Alternatives considered

- **One bundle version per release, with a version counter.** Every
  extension waits for a release, and the download route refuses a version no
  release holds: it blocks development.
- **Refusing a bundle that is ahead of the catalogue, on the download route
  or in the live job.** It blocks development the same way.
- **Comparing every bundled file with the catalogue's inventory wherever the
  catalogue is read.** It reads every bundled dataset's descriptor and
  shards.
- **Warning only where the catalogue is read.** The offline required tests,
  where the maintainer runs them, would never show it.

## Consequences

- Development and a package's releases never wait for the catalogue; the
  warning keeps an ahead bundle visible until it is realigned.
- Users of a released package whose bundle is ahead see the warning too.
- In an ahead bundle, a key can name other bytes than in the catalogue, for
  that package only. They are read in place and never enter a cache
  ([0004](0004-cache-paths-from-resource-identity.md)).
- See [Keep data in the repository](../../../how-to/package-maintainers/keep-data-in-the-repository.md#sync)
  and [Run tests and examples in CI](../../../how-to/package-maintainers/run-in-ci.md#download-switch).

## Related

- [0004. Derive cache paths from resource identity, and never reuse a name](0004-cache-paths-from-resource-identity.md)
- [0005. Read the index first and inventories on demand](0005-lazy-index-descriptors-and-shards.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0018. Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0020. Keep attributed data in bundles that are authoritative for their package](0020-repository-bundles.md)
- [0025. Draft the handoffs between roles from templates](0025-handoff-templates.md)
- [6. Runtime View](../runtime.md)
