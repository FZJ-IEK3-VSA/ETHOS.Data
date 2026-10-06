# 0019. Publish new versions as revisions or successors; published objects never change

**Status:** implemented · **Date:** 2026-10-02 · **Implemented by:** #24, #25

## Context

Published objects never change, yet datasets get corrected. Changed bytes
must live beside the old ones, so that older releases keep their meaning. A
correction at the byte level should not change any workflow. Some new
versions change the layout so much that they share little with the old one.

## Decision

There are two kinds of new version.

| | Revision | Successor |
|---|---|---|
| For | the same layout; bytes changed, perhaps a few files added | a changed layout |
| Made by | `catalog build NAME --revision [--from DIR] [--remove-missing]`; for bundled data, `bundle update` and then `catalog add-bundle` | a new dataset whose `dataset.yaml` says `ethos:supersedes: <old name>`, accepted like any other |
| Keys | unchanged; collections need no change | new; collections point their named paths at the new keys |
| On the store | changed and new files under `<remote_prefix>@<r>/`; unchanged files keep their objects | a folder of its own |
| In a cache | the entry `<dataset>@<r>/`, seeded from earlier entries for unchanged files after a size and SHA-256 check | an entry of its own |
| The old version | read through older releases, on a public installation; the cluster serves the latest release only ([0026](0026-internal-catalogue-on-the-cluster.md)) | stays a dataset; `ls` marks it superseded, and a collection reading it warns |

- Each resource records `ethos:revision`, the revision its bytes were
  published in; absent means 1. The object address is derived from it:
  `<remote_prefix>/<path>` for revision 1, `<remote_prefix>@<r>/<path>` later.
- Upload copies each file into its revision's folder and never overwrites an
  object.
- A revision is refused when nothing changed; when a file is gone and
  `--remove-missing` is not given (the message suggests a successor); for a
  dataset that is only linked, which changes in place with its source; and
  for a dataset never published.
- A plain `catalog build` refuses other bytes for an uploaded or materialized
  dataset and points to `--revision`.
- The build writes `ethos:superseded_by` into the replaced dataset's
  descriptor and index row.
- The tools assign `ethos:revision`; `version` stays the publisher's own
  string.
- Removal goes metadata first, bytes last ([0023](0023-maintenance-pipelines.md)).

## Alternatives considered

- **New paths chosen by hand.** Someone has to pick them for every change,
  and nothing ties them to the version they replace.
- **An automatic version for a changed layout.** It would share little with
  the version before.
- **An object path stored per resource.** A number keeps the address
  derivable and the descriptors small.

## Consequences

- A revision needs no change to any collections file; a successor needs new
  keys under the same named paths ([0014](0014-named-inputs-and-test-full-variants.md)).
- Every cache entry name follows revisions, in the public cache and the
  restricted caches alike ([0004](0004-cache-paths-from-resource-identity.md)).
- Within a major release, older releases keep their meaning as long as the
  hosts keep their objects. A dataset's earlier revisions stay as long as the
  dataset is in the catalogue ([0018](0018-numbered-catalogue-releases.md));
  see [11. Risks and Technical Debt](../risks-and-technical-debt.md).
- See [Licensing and immutability](../../licensing.md#paths-are-immutable).

## Related

- [0004. Derive cache paths from resource identity, and never reuse a name](0004-cache-paths-from-resource-identity.md)
- [0014. Name workflow inputs in the collection and pair test and full variants](0014-named-inputs-and-test-full-variants.md)
- [0018. Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0020. Keep attributed data in bundles that are authoritative for their package](0020-repository-bundles.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0023. Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
