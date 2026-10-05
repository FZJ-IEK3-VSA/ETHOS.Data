# 0003. One catalogue describes the data; each package's collections file selects from it

**Status:** implemented · **Date:** 2026-09-10

## Context

Packages at one institute need overlapping inputs: ERA5, land cover, wind
atlases, bathymetry. Each package must still say, in its own repository, which
slices of those datasets its workflows need. Inventories kept per package,
each with its own URLs and checksums, drift apart without anyone seeing it,
and a shared cache over them either corrupts files or duplicates them.

## Decision

| | Lives in | Says |
|---|---|---|
| The catalogue | the source catalogue, and the public catalogue generated from it ([0027](0027-public-catalogue-releases-on-github.md)) | what a dataset is: paths, sizes, SHA-256 checksums, sources, licences |
| A collections file | each package's repository | which slices the package needs: dataset or family names (globs allowed) and file globs, named paths under `paths:` ([0014](0014-named-inputs-and-test-full-variants.md)), `test:` and `full:` variants, `extends` and `include` |

- A collections file holds no paths, sizes, checksums or data URLs.
- A change to a dataset is made once, in the catalogue, where every package
  sees it.
- Which catalogue is read is a setting
  ([0010](0010-one-settings-file-per-account.md)). Which releases a collections
  file accepts are its release bounds
  ([0018](0018-numbered-catalogue-releases.md)).

## Alternatives considered

- **An inventory per package, with URLs and checksums.** A revision reaches
  some inventories and not others, and nothing shows the disagreement.
- **A shared cache over per-package inventories.** Different bytes at one path
  are a corruption, and the same bytes at two paths are the duplicate disk use
  the cache exists to avoid.

## Consequences

- A package is told what a dataset contains. It cannot patch a checksum or
  ship a slightly different copy.
- Every package shares resource identity, and with it the places in a cache
  ([0004](0004-cache-paths-from-resource-identity.md)).
- A new input starts with a proposal to the catalogue
  ([0025](0025-handoff-templates.md)).
- See [Why one catalogue](../../deduplication.md) and
  [Write a collections file](../../../how-to/package-maintainers/write-a-collections-file.md).

## Related

- [0004. Derive cache paths from resource identity, and never reuse a name](0004-cache-paths-from-resource-identity.md)
- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0014. Name workflow inputs in the collection and pair test and full variants](0014-named-inputs-and-test-full-variants.md)
- [0018. Number catalogue releases `vYYYY.MM.N` and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [3. Context and Scope](../context.md)
- [4. Solution Strategy](../solution-strategy.md)
