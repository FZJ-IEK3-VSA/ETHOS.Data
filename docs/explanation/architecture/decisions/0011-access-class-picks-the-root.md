# 0011. Let the access class pick the root, and a link mean "read in place"

**Status:** proposed · **Date:** 2026-09-10 · **Implemented by:** #15 (internal data is never downloaded, and `repair` skips it), a new PR (shared cache: internal data is read only through it), a new PR (pipelines: `catalog upload` refuses internal data)

## Context

Licensed data may not be redistributed, and authorised installations exist
on some machines only. Internal data is not published and readers hold no
credentials for it, yet cluster users need it. Where a dataset is read must
follow from facts already recorded, the catalogue entry and the file system,
and not from a table someone keeps per dataset. Such a table does not scale
and goes out of step with what is on disk.

## Decision

The dataset's access class, in the catalogue, picks the root:

| Access class | Means | Read from | Never |
|---|---|---|---|
| `public` | published on dCache | downloaded from the publication root into the user's own public cache; on the cluster, read in place from the shared cache where maintainers provide it | — |
| `internal` | held by the institute, not published | on the cluster, the shared cache, where maintainers link or copy it ([0028](0028-read-only-shared-cache.md)); or a per-dataset root | downloaded, uploaded, held in a personal public cache, touched by `verify --repair` |
| `restricted` | licensed | the restricted cache, in place | downloaded, uploaded, written into a public cache or the shared cache, shadowed by staging; it may not declare `ethos:remote_prefix` |

- Within a root, the file system picks the mode. A symlink entry means "read
  in place". A real directory is owned by the cache: it holds downloads and
  materialized copies.
- The public cache is personal and has a default, the per-user cache
  directory. The shared cache, the restricted cache and the staging root have
  none: where shared or licensed bytes are read is something someone decides
  on purpose. `dataset_roots` is the escape hatch for one dataset.
- Access and visibility are independent
  ([0027](0027-public-catalogue-releases-on-github.md)): visibility decides
  whether the public catalogue lists a dataset, access how its bytes may be
  obtained.

## Alternatives considered

- **A credentialed download into a private cache.** Readers would need a
  credential flow of their own, and licensed bytes would be copied to every
  machine that asks for them.
- **A per-dataset configuration table.** Somebody has to write it for every
  dataset, and it goes out of step with what is on disk.
- **A non-anonymous dCache folder for internal data.** It would keep a copy of
  internal data off the cluster. But the publication root is world-readable,
  and the upload's read-back is anonymous and cannot check private bytes, so
  it would need a private folder outside that root and a read-back with the
  maintainer's token. Whether to add it is an open point
  ([11.3](../risks-and-technical-debt.md#open-points)).

## Consequences

- Re-pointing one link in the shared cache moves every cluster user at once.
- Internal data is not readable off the cluster, and its only copies are on
  cluster storage: dCache holds none.
- A user without an installation of licensed data needs an accessible local
  copy, obtained under its terms. The refusal says how
  ([0013](0013-every-input-is-required.md)).
- Licensed fixtures belong in restricted CI, not in repository bundles
  ([0020](0020-repository-bundles.md)).
- See [Caches, classes and roots](../../caches-and-access.md),
  [Restricted data is read in place](../../licensing.md#restricted-data-is-never-copied)
  and [Add restricted data](../../../how-to/catalogue-maintainers/add-restricted-data.md).

## Related

- [0004. Derive cache paths from resource identity, and never reuse a name](0004-cache-paths-from-resource-identity.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0013. Treat every input as required, and describe what is missing](0013-every-input-is-required.md)
- [0016. Give one link command two modes](0016-one-link-command-two-modes.md)
- [0024. Let unresolved licensing block distribution, not development](0024-licensing-gates-distribution.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [0028. Serve shared data on the cluster from a read-only shared cache](0028-read-only-shared-cache.md)
- [7. Deployment View](../deployment.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
