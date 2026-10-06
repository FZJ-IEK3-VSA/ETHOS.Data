# 0018. Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them

**Status:** proposed · **Date:** 2026-10-06 · **Implemented by:** #19, #23

## Context

A package must state which catalogue releases it was tested with, while the
user still chooses which catalogue to read, the internal or the public one. A
released package must resolve the same metadata, and read the same bytes,
later. One release name must cover both catalogues, and readers must be able
to find the list of releases. A reader must see from the name whether a
release changed data or only metadata. Storage is finite, so withdrawn data is
deleted at some point, and a package bound to an older release must know how
long its data stays.

## Decision

A release is named `vMAJOR.MINOR.PATCH`: three decimal numbers without
leading zeros and without a suffix, compared part by part as numbers, so
`v1.10.0` follows `v1.9.0`. The first release is `v1.0.0`. One version names
both catalogues: the source catalogue's tag on JuGit and the public
catalogue's tag on GitHub. Every release tags both, even when only restricted
or hidden data changed.

Each level is judged against the release before it:

| Level | Next after `v1.2.0` | Means |
|---|---|---|
| patch | `v1.2.1` | Metadata only. Every key of both catalogues resolves to the same bytes under the same access class. Descriptions, attribution, contacts, homepages, licence notes and licence status may change. |
| minor | `v1.3.0` | Data changed: datasets added, revised, superseded, changed in place, withdrawn, reclassified (access), or made visible or hidden. |
| major | `v2.0.0` | A retention epoch. No change requires one; the catalogue maintainers plan and announce it. |

- **Retention.** All data that any release of the current major describes is
  retained, so data is purged only after a major release. The rule covers the
  uploads on dCache and the copies the caches own; linked data and restricted
  installations change with their source.
- **The release check.** `catalog release VERSION` accepts only the next
  patch, minor or major release at or above the smallest level that the
  changes since the last release require, and refuses a release that changes
  nothing; `--dry-run` and `catalog status` name that version
  ([0023](0023-maintenance-pipelines.md)). The first release is `v1.0.0`.
- **The purge gate.** `catalog remove NAMES --purge` requires a major release
  recorded after the removal. A major release adds a release step to every
  withdrawn dataset, so the purge sees it
  ([0022](0022-dataset-status-files.md)). A purge deletes withdrawn datasets
  only; earlier revisions of a dataset still in the catalogue stay as long as
  it does ([0019](0019-revisions-and-successors.md)). An urgent deletion, for
  example under a licence that forbids further distribution, needs an
  unplanned major release.
- The public index on `main` lists every release in `ethos:releases`.

A collections file may bound the releases it accepts with `catalog:`:

| `catalog:` | Accepts |
|---|---|
| `{min_version: V}` | V and every later release |
| `{min_version: V, max_version: W}` | V to W, both included |
| `{exact_version: V}` | V only |
| absent | any catalogue, with or without a release |

- Each version may be a prefix, such as `v1` or `v1.3`, that stands for every
  release starting with it: as `min_version` its first release, as
  `max_version` its last, as `exact_version` all of them. So
  `exact_version: v1.3` admits every `v1.3.x`: the same bytes, with the newest
  metadata.
- Malformed bounds raise `CollectionError`, naming the file.
- A catalogue the settings choose (`--catalog`, a package's `catalog=`,
  `ETHOS_DATA_CATALOG`, the `catalog` setting) is refused with
  `CatalogVersionError` (exit 2), naming its release and the bounds, when it
  lies outside the bounds or records no release.
- With bounds and no catalogue configured, once a handle needs the index, a
  full `exact_version`, such as `v1.2.0`, reads that release's tag on GitHub.
  Any range, a prefix `exact_version` included, reads the release list of the
  public `main` index and takes the newest admitted release, from its tag. If
  none is admitted, the error lists the releases there are. With no bounds and
  no catalogue configured, the public `main` index is read.

## Alternatives considered

- **A dated name, `vYYYY.MM.N`.** It orders the releases and shows their age,
  but promises nothing about retention or changed bytes.
- **Semantic versions for readers, in which every removal is a major
  release.** The release that withdraws a dataset would also open its purge,
  so a withdrawn dataset would get no retention period, and every withdrawal
  of restricted data would raise the public catalogue's major version too.
- **Two-part versions, `vMAJOR.MINOR`.** No level would promise unchanged
  bytes.
- **A catalogue location per package.** It would fix the catalogue for every
  user, while the choice between the internal and the public catalogue
  belongs to the user's settings ([0010](0010-one-settings-file-per-account.md)).
- **Git commit hashes.** They are not ordered, so no range can be stated.

## Consequences

- Packages raise `min_version` deliberately, once they are tested with a
  later release.
- A package that reruns a collection bounded to an older release of the
  current major reads the same keys and objects. Withdrawn datasets stay on
  dCache and in the caches at least until the next major release, so storage
  grows until then; a package bounded to the releases of an earlier major can
  lose withdrawn data once it is purged.
- The served checkout on the cluster holds the latest release only. A
  collections file whose bounds exclude it, with an `exact_version` of an
  older release or a `max_version` below it, is refused there, so packages
  that run on the cluster bound with `min_version` only
  ([0026](0026-internal-catalogue-on-the-cluster.md)). A purge never touches
  what the latest release describes, so these packages never notice a major
  release.
- A tag URL never changes and is cached forever; the public `main` index is
  never cached. A handle whose bundles hold every input reads no index
  ([0020](0020-repository-bundles.md)); otherwise offline use needs a
  configured catalogue, or a full `exact_version` whose tag is already in the
  metadata cache ([0005](0005-lazy-index-descriptors-and-shards.md)).
- The self-test collection gets bounds with the first release, `v1.0.0`
  ([0017](0017-self-test-collection.md)).
- See [Declare the catalogue versions](../../../how-to/package-maintainers/write-a-collections-file.md#catalog-version),
  [Release the catalogue](../../../how-to/catalogue-maintainers/release-the-catalogue.md)
  and [Remove a dataset](../../../how-to/catalogue-maintainers/withdraw-a-dataset.md).

## Related

- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0020. Keep attributed data in bundles that are authoritative for their package](0020-repository-bundles.md)
- [0021. Let a bundle be ahead of the catalogue, and warn until it is realigned](0021-bundles-ahead-of-the-catalogue.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0023. Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
- [11. Risks and Technical Debt](../risks-and-technical-debt.md)
