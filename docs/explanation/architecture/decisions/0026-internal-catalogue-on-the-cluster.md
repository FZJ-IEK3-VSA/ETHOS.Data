# 0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit

**Status:** proposed · **Date:** 2026-09-10 · **Implemented by:** #23; implemented once the first versioned release is served

## Context

Cluster users must read the internal catalogue without access to Git
hosting. Maintainers need review and version control, and several of them
record work in parallel. A served checkout must never pair the index of one
release with the inventories of another. A runner outside the cluster cannot
reach the cluster computer's file system.

## Decision

| Place | Holds | Changes through |
|---|---|---|
| The served checkout on the cluster computer, for example `/shared/ethos/catalogue/`, readable by every cluster user | the latest release only | `catalog update-checkout` alone |
| A maintainer's own clone of the source catalogue, in their own account | that maintainer's work: descriptors, status files, generated files | the maintainer's commands; their commits on a branch |
| The source catalogue on JuGit | the history, one tag per release, merge requests | merge requests; `catalog release --push` |

- Cluster users read `datacatalog.json` of the served checkout. It holds the
  latest release only. A collections file whose bounds exclude that release is
  refused there with `CatalogVersionError`
  ([0018](0018-numbered-catalogue-releases.md)).
- `catalog update-checkout [--to VERSION]` runs on the cluster computer, in
  the served checkout, while no jobs read it, and rebuilds nothing. Its stages:
  `fetch` gets the tags and refuses local changes; `advance` fast-forwards to
  the newest release tag, or to `--to`, and checks that `catalog.yaml` names
  that release; `check` runs `build --check` and writes nothing.
- Each maintainer builds, records and releases in their own clone; there is
  no shared working checkout. Every command that records an upload, a link, a
  copy, a freeze or a provenance check writes `status.yaml` in that clone
  only. The maintainer reviews the diff, commits on a branch and merges by
  merge request on JuGit.
- No command commits or pushes a record. `catalog release` commits and tags
  the release it makes, in a clone at the merged state.
- `catalog release --push` is the one direct push to the release branch on
  JuGit, and needs push rights there; every other change goes by merge
  request. A merge that lands between the release commit and the push makes
  the push fail, and the release is rerun from the updated branch.

## Alternatives considered

- **Readers fetch the metadata through JuGit.** Cluster users have no access
  to Git hosting.
- **Rebuild in the served checkout.** The served files would change outside a
  release, while jobs read them.
- **One directory per release behind a switched `current` link.** It would
  make the switch atomic and could serve packages bounded below the latest
  release. Rejected in favour of one checkout at the latest release.
- **A shared working checkout on the cluster.** Records would land there
  unreviewed, beside other maintainers' uncommitted work.
- **Commands that commit and push their own records.** Every record would
  reach JuGit without review.

## Consequences

- `update-checkout` changes files in place, so it runs when no jobs read the
  checkout: a reader that lists the index during the update can see
  inventories of the other release.
- The cluster offers the latest release only, so packages that run there
  bound with `min_version` and raise it deliberately.
- A record reaches cluster users through a merge request, the next release
  and `update-checkout`.
- The maintainer who releases needs push rights to a branch that is
  otherwise changed only by merge request.
- A release's `build --check` needs every build input that is not frozen, so
  while a dataset is only linked the release runs on the cluster computer.
- See [Set up the shared machine](../../../how-to/catalogue-maintainers/set-up-the-shared-machine.md)
  and [Update the internal catalogue](../../../how-to/catalogue-maintainers/release-the-catalogue.md#internal).

## Related

- [0018. Number catalogue releases `vYYYY.MM.N` and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0023. Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [0028. Serve shared data on the cluster from a read-only shared cache](0028-read-only-shared-cache.md)
- [6. Runtime View](../runtime.md)
- [7. Deployment View](../deployment.md)
- [11. Risks and Technical Debt](../risks-and-technical-debt.md)
