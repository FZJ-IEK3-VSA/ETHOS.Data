# 0028. Serve shared data on the cluster from a read-only shared cache

**Status:** proposed · **Date:** 2026-10-05 · **Implemented by:** a new PR (shared cache)

## Context

Cluster users run batch jobs on shared storage that already holds much of the
data, in project directories. They should read it in place rather than each
download it, and internal data must reach them without ever being downloaded.
A cache that every user writes needs group permissions that others operate,
and one user's download or repair changes what every other user reads.
Restricted data needs one group per dataset and must never sit in a cache that
every user reads.

## Decision

The cluster has a **shared cache** that maintainers fill and cluster users only
read. Every user's **public cache** is personal, on the cluster too. Both have
one layout, `<root>/<entry>/<path>`
([0004](0004-cache-paths-from-resource-identity.md)).

| | Public cache | Shared cache | Restricted cache |
|---|---|---|---|
| Where | every machine; one per user | the cluster computer, for example `/shared/ethos/cache/` | where someone sets it; on the cluster, for example `/shared/ethos/restricted/` |
| Holds | public data: the user's downloads, links and copies | public and internal data: links into project storage and copies the cache owns | licensed installations, one group per dataset on the cluster |
| Written by | that user's commands | maintainers only | maintainers, or the user for their own licensed copy |
| Read by | that user | every cluster user, in place | whoever its permissions admit, in place |
| Setting | `public_cache`, `ETHOS_DATA_DIR`; default the per-user cache directory | `shared_cache`, `ETHOS_SHARED_DIR`; no default | `restricted_cache`, `ETHOS_RESTRICTED_DIR`; no default |

- `config set-shared-cache DIR` and `config unset-shared-cache` write the
  setting. `config show` and the settings snapshot include it
  ([0010](0010-one-settings-file-per-account.md)).
- The lookup chain reads the shared cache with the fifth of its eight
  locators, after the restricted cache and before the public-cache link, the
  public-cache copy and the download ([0012](0012-one-lookup-chain.md)). It
  reads a file in place when the file is there, passes otherwise, and never
  refuses. Restricted data is never looked up there.
- Internal data is read only on the cluster, through the shared cache, unless
  someone sets a per-dataset root or stages it on purpose. A public cache
  never holds it, and the download's refusal of internal data points at the
  shared cache.
- No user command writes the shared cache. Downloads go into the user's own
  public cache. `verify --repair` writes only that cache too, where it may
  replace a link to public data with a downloaded copy, which `--dry-run`
  lists first. It reports a broken shared entry, and a maintainer fixes it.

Maintainers fill the shared cache on the cluster computer by naming it with
`--root`, and record the copies in their own clone with `--catalog-root`
([0022](0022-dataset-status-files.md),
[0026](0026-internal-catalogue-on-the-cluster.md)):

```bash
ethos-data link --all --root <shared cache> --catalog-root <own clone>
ethos-data --root <shared cache> link NAME DIR --catalog-root <own clone>
ethos-data --root <shared cache> materialize NAMES --catalog-root <own clone>
```

An internal dataset gets no entry without `--root`. A restricted dataset's
entry goes into the restricted cache instead.

## Alternatives considered

- **A group-writable shared cache that users download into**, one setgid
  directory with no extra locator. Every user's download or repair would
  change the files every other user reads, the whole group would need write
  access to a tree that holds internal links, and a repair could remove a
  link that only a maintainer can restore.
- **A personal cache only.** Cluster users would lose the shared links, and
  with them every internal dataset and every in-place read of project
  storage.

## Consequences

- A public file the shared cache lacks is downloaded once per user, so each
  cluster user needs room in their own public cache. The ICE-2 wiki
  recommends where to keep it, for example on scratch storage, and
  maintainers link or materialize much-used public data into the shared cache.
- A broken or missing shared entry affects every cluster user of that
  dataset and waits for a maintainer: public files fall back to a download
  into each user's own cache, and internal data is refused. `verify` reports
  the entry, and the problem report goes to the internal tracker
  ([0025](0025-handoff-templates.md)).
- The shared cache is not tied to a release: it changes when a maintainer
  writes it, not with `update-checkout`. Maintainers therefore fill and prune
  it with `link --all` only from a clone at the merged state of the served
  release; a new dataset is linked by name. Pruning from a clone that lacks another maintainer's unmerged dataset
  removes that dataset's link for every cluster user, and repointing a link
  changes the bytes read under the served release, which `verify --deep`
  detects.
- Internal data is not readable off the cluster
  ([0011](0011-access-class-picks-the-root.md)).
- Each cluster user sets the served checkout, the shared cache and the
  restricted cache in their own settings; there is no machine-wide setting.
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
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [6. Runtime View](../runtime.md)
- [7. Deployment View](../deployment.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
