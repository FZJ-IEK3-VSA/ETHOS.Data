# 0020. Keep attributed data in bundles that are authoritative for their package

**Status:** proposed · **Date:** 2026-10-06 · **Implemented by:** #25

## Context

A package's required tests and its examples must run offline, on external
data that is properly attributed, and the package's test data changes with
its code. Another repository with similar data requirements should be able to
take the same data over, with its attribution. A test must still be able to
read a deliberately changed file while a bug is reproduced, without that
change reaching anyone else. A repository distributes what it holds to
everyone who clones it.

## Decision

A **bundle** is a directory in a repository. It holds the files of a
selection of catalogue datasets, whole datasets or a selection of their
files, together with what makes them properly attributed: each dataset's
description (`dataset.yaml`, and its family's), its licence documents and its
attribution.

| Path | Holds |
|---|---|
| `data/<dataset>/<path>` | the files; for a member of a family, `<dataset>` is `family/member` |
| `datasets/<dataset>/` | the description and the licence documents |
| `bundle.json` | for each dataset: the catalogue revision it was last aligned with (none for a dataset the catalogue does not describe yet) and the release it was taken from, which is only shown; whether it holds every file or a selection; the changes recorded since the alignment; every file's size and SHA-256, the descriptions and licence documents included |

- There is one bundle concept and one format: `bundle.json` has one
  specification, `formats.bundle`
  ([0006](0006-every-file-format-specified-once.md)).
- A bundle serves two purposes. It lets a package use properly attributed
  external data offline, in its required tests and its examples. It also
  exports data to another repository with similar data requirements.
- A bundle holds data with public access, public visibility and settled
  licensing only, because the repository distributes it. Loading a bundle
  refuses anything else with `BundleError`, naming the dataset and what is
  missing; `bundle update`, `bundle export`, `propose` and
  `catalog add-bundle` refuse the same. Data whose licensing is unsettled is
  developed in staging ([0024](0024-licensing-gates-distribution.md)), and
  licensed fixtures belong in restricted CI.
- Within a major release, dCache keeps every version it published, and a
  published version never changes ([0018](0018-numbered-catalogue-releases.md),
  [0019](0019-revisions-and-successors.md)). A package's bundle is
  authoritative for that package: the package reads what its bundle holds,
  even where the bundle is ahead of the catalogue, and its maintainer is
  warned to realign the bundle with the catalogue soon
  ([0021](0021-bundles-ahead-of-the-catalogue.md)).
- A handle lists its bundles with `bundles=`. The bundle locator, second in
  the lookup chain ([0012](0012-one-lookup-chain.md)), reads a listed bundle
  in place, hash-checked against `bundle.json` once per process. The
  catalogue never overrides a bundle's bytes or descriptions. A handle whose
  bundles hold every input reads no catalogue index.
- A missing file, or a change `bundle update` has not recorded, raises
  `BundleError`, never a download. With
  `load_bundle(DIR).fetch(…, allow_modified=True)`, one test reads an
  unrecorded change: a warning names the changed keys, the recorded hashes
  stay, and nothing repairs, republishes or updates dCache.
- A bundle is authoritative for bytes and descriptions, not for access or
  visibility. A bundled dataset that the catalogue describes as restricted or
  hidden is refused with `BundleError` wherever the index is read anyway, and
  in the bundle commands. `catalog add-bundle` refuses an access or
  visibility change that comes from a bundle.
- `bundle create DIR` starts a bundle from data directories
  (`--family NAME` drafts the members of one family) and drafts each new
  dataset's description. Its datasets are ahead until the catalogue accepts
  them.
- `<tool>-data bundle export TARGET COLLECTION...` writes a new bundle, into a
  new directory in this or another repository, of what the package's handle
  reads for those collections: its bundles first, then the caches and the
  download, staging excluded. `--test` selects the test variants.
    - Each dataset keeps its description, licence documents and alignment.
    - Export checks every file's size and SHA-256 as it copies. Its downloads
      use the publication URL of the settings snapshot
      ([0010](0010-one-settings-file-per-account.md)), like every other
      download.
    - A local copy is reached as a cache entry (`link`, or
      `materialize --from`); export takes no `--source-root`.

## Alternatives considered

- **dCache as the only source of truth for test data.** Fixtures could not be
  developed together with the code that reads them.
- **Two kinds of bundle, one for the package's own data and one exported from
  the catalogue.** Two formats for one job.
- **A bundle that may hold restricted or hidden data, or data whose licensing
  is unsettled.** The repository distributes it.

## Consequences

- Required package tests and examples run in a fresh checkout with no
  network.
- Repository files stay under 100 MiB; large data belongs in live tests.
- Whoever clones the repository receives each bundled dataset's description
  and licence documents with its files.
- A bundle that `bundle create` starts can be read once every drafted
  description records settled licensing: a `licenses:` entry or
  `ethos:license_status: resolved` ([0024](0024-licensing-gates-distribution.md)).
- Packages pass `bundles=` instead of reading their bundles themselves.
- See [Keep data in the repository](../../../how-to/package-maintainers/keep-data-in-the-repository.md),
  [Run tests and examples in CI](../../../how-to/package-maintainers/run-in-ci.md)
  and [Test data, development inputs, and reproducibility](../../test-data.md).

## Related

- [0006. Specify every file format once](0006-every-file-format-specified-once.md)
- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0018. Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0021. Let a bundle be ahead of the catalogue, and warn until it is realigned](0021-bundles-ahead-of-the-catalogue.md)
- [0024. Let unresolved licensing block distribution, not development](0024-licensing-gates-distribution.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
