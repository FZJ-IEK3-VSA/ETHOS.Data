# 0027. Release the public catalogue as a generated view, tagged on GitHub

**Status:** proposed · **Date:** 2026-10-06 · **Implemented by:** #12, #19, #23, #26; implemented with the first versioned release

## Context

Public consumers need reproducible metadata without the internal catalogue.
Hidden datasets and internal fields must never leak into it. Whoever holds the
published bytes should also hold their descriptors and licence documents.

## Decision

- `ETHOS.Data-Catalogue` on GitHub is never edited by hand. `catalog publish`
  generates it from the source catalogue as a subset view with the same
  `name`, stamped `ethos:catalog_role: published`. The role is declared, never
  inferred, and `publish` refuses a source catalogue as its target.
- Descriptors are selected by `ethos:visibility`. Every key the
  specifications mark unpublished is stripped, `ethos:store` included. Shards
  and licence documents are copied. A published index row equals its source
  row.
- The leak check refuses a tree that names a withheld dataset, as a word or as
  `datasets/<name>/`, or holds an unpublished key. A name counts only on its
  own: a withheld `era5` does not match `era5-land`.
- Each release is a tag `vMAJOR.MINOR.PATCH` of the public catalogue, made
  by `catalog release` and listed in `ethos:releases` of the index on `main`
  ([0018](0018-numbered-catalogue-releases.md)). Every release tags it, even
  one that changes only restricted or hidden data.
- `publish` writes the public tracker's issue templates
  ([0025](0025-handoff-templates.md)).
- `catalog release --upload` puts the latest public catalogue beside the data,
  under `<publication root>/catalogue/` on dCache. The store keeps the latest
  release only; the history is on GitHub. That copy is not a reader entry
  point: readers use the release tags or the served checkout on the cluster.

## Alternatives considered

- **A public catalogue kept by hand.** It would drift from the source
  catalogue, and nothing would stop a leak.
- **Inferring the role from the layout.** A source catalogue could then be
  taken for a published one.
- **Release archives as reader input.** An archive URL is not an index URL.
- **Pointing consumers at a moving branch.** The metadata would change under a
  finished workflow.

## Consequences

- Access and visibility are independent: the public catalogue can describe
  data whose bytes are restricted ([0011](0011-access-class-picks-the-root.md)).
- The store's copy changes at every release under a URL that names no moving
  ref, so the metadata cache would keep the first copy a machine read; that is
  why readers do not use it ([0005](0005-lazy-index-descriptors-and-shards.md)).
- Running the release in CI is a feature request (GitHub issue #34). A release
  refuses a tag it did not make unless the tagged commit is already stamped,
  so CI either runs the whole command or finishes a release a maintainer
  started.
- See [Generate the public catalogue](../../../how-to/catalogue-maintainers/release-the-catalogue.md#public)
  and [The catalogue format](../../catalogue-format.md#two-catalogues-one-format).

## Related

- [0006. Specify every file format once](0006-every-file-format-specified-once.md)
- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0018. Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0023. Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md)
- [0025. Draft the handoffs between roles from templates](0025-handoff-templates.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [7. Deployment View](../deployment.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
