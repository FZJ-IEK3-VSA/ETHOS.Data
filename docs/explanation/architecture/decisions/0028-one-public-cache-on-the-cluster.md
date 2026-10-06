# 0028. Share one public cache on the cluster

**Status:** implemented · **Date:** 2026-10-06 · **Implemented by:** #39 (repair never touches a link; `link --all` into the public cache)

## Context

Cluster users run batch jobs on shared storage that already holds much of the
data, in project directories. They should read it in place, and download each
missing public file once, for everyone. Many of them read and fetch at the
same time, and nothing on shared storage may depend on a lock
([0004](0004-cache-paths-from-resource-identity.md)). Restricted data needs
groups of its own and stays in restricted caches
([0011](0011-access-class-picks-the-root.md)).

## Decision

Every account has one public cache
([0010](0010-one-settings-file-per-account.md)). On the cluster, every user
sets it to one directory on shared storage, for example `/shared/ethos/cache/`,
as the ICE-2 wiki says: **the cluster's public cache**. Like every cache it has
the layout `<root>/<entry>/<path>`, and it holds public data only: links into
project storage, read in place; copies the cache owns; downloads; and the
metadata cache `.catalog/`.

- The institute group may write it. The cluster administrators set its
  permissions, for example setgid, so that everything in it belongs to the
  group.
- Maintainers link project storage into it and materialize copies there. Any
  user's fetch downloads a missing public file into it, once for everyone.
- The lookup chain reads it as it reads every public cache, with its fourth
  locator ([0012](0012-one-lookup-chain.md)). There is no second cache beside
  it: one setting and one locator serve the cluster and every other machine.

Four rules make the sharing safe:

- A download is hash-checked before it appears in the cache, so a reader never
  sees a partial or wrong file. Two users who download the same file both
  verify it; nothing locks a cache.
- Nothing writes through a link: a download never writes through the
  dataset's own link or its family's.
- A real directory is never replaced by a link: it is a copy the cache owns.
- `verify --repair` downloads a damaged copy again and never removes or
  replaces a link. It never touches restricted or staged data.

A broken link refuses the read: a file read in place must be present, and
`AccessError` names it. `verify` reports the link, and on the cluster `report`
drafts the problem report for the internal tracker
([0025](0025-handoff-templates.md)). A maintainer repairs the link with
`ethos-data link --force NAME DIR` or `ethos-data materialize NAME`, each with
`--catalog-root <own clone>`.

## Alternatives considered

- **A read-only shared cache that maintainers fill, with a personal public
  cache per user.** Every user downloads what the shared cache lacks into
  their own cache, and the shared cache needs a second setting and a locator
  of its own.
- **An ordered list of public caches, a personal one first.** Every user
  still downloads into their own cache what the others lack.
- **A personal cache only.** Users lose the links into project storage.

## Consequences

- The cluster holds one copy of each public file, and no user needs room of
  their own for downloads.
- Every cluster user may write the cache, and the cluster administrators set
  its permissions. The rules above keep one user's download or repair from
  damaging what the others read, and maintainers make the links.
- A broken link stops every user's read of that dataset until a maintainer
  repairs it.
- The cache is not tied to a release: it changes when someone writes it, not
  with `update-checkout`. Maintainers therefore fill and prune it with
  `link --all` only from a clone at the merged state of the served release,
  and link a new dataset by name. A prune from a clone that lacks another
  maintainer's unmerged dataset removes that dataset's link for every user.
  Repointing a link changes the bytes read under the served release, which
  `verify --deep` detects.
- The cache grows with every user's downloads, in project storage.
- Maintainers fill it on the cluster computer with
  `link --all --root <the cluster's public cache>`, `link NAME DIR` and
  `materialize NAME`, and record each copy in their own clone with
  `--catalog-root <own clone>` ([0016](0016-one-link-command-two-modes.md),
  [0022](0022-dataset-status-files.md),
  [0026](0026-internal-catalogue-on-the-cluster.md)).
- Each cluster user sets the served checkout, the cluster's public cache and
  the restricted caches their groups admit in their own settings; a user of
  public data only lists no restricted cache, and there is no machine-wide
  setting.
- See [Caches, classes and roots](../../caches-and-access.md),
  [Cluster users](../../../how-to/data-users/set-up-your-machine.md#cluster-users),
  [Set up the shared machine](../../../how-to/catalogue-maintainers/set-up-the-shared-machine.md)
  and [Check and repair the cache](../../../how-to/data-users/verify-and-repair.md).

## Related

- [0004. Derive cache paths from resource identity, and never reuse a name](0004-cache-paths-from-resource-identity.md)
- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0016. Give one link command two modes](0016-one-link-command-two-modes.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0025. Draft the handoffs between roles from templates](0025-handoff-templates.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [6. Runtime View](../runtime.md)
- [7. Deployment View](../deployment.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
