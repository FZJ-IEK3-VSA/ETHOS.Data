# 0011. Let the access class pick the root, and a link mean "read in place"

**Status:** implemented · **Date:** 2026-10-06 · **Implemented by:** #15 (restricted data is never downloaded, and `repair` skips it), #39 (two access classes, several restricted caches), #42 (pipelines: `catalog upload` refuses restricted data)

## Context

Licensed data may not be redistributed, and authorised installations exist
on some machines only. The institute also holds data that it does not
publish. Readers hold no credentials for either, and who may read such data
differs: every member of the institute, or one licence group. Where a dataset
is read must follow from facts already recorded, the catalogue entry and the
file system, and not from a table someone keeps per dataset. Such a table
does not scale and goes out of step with what is on disk.

## Decision

The dataset's access class, in the catalogue, picks the root:

| Access class | Means | Read from | Never |
|---|---|---|---|
| `public` | published on dCache, world-readable | the account's public cache: in place where the entry is a link, else a copy of the recorded size, else downloaded into it from the publication root | — |
| `restricted` | not published: licensed data, and data the institute holds without publishing it | in place, from a restricted cache whose file permissions admit the reader | downloaded, uploaded, written into a public cache, shadowed by staging, put into a bundle; it declares no `ethos:remote_prefix` |

- Data the institute holds without publishing it is restricted data that
  every member of the institute may read. Who may obtain a restricted
  dataset, and how, is told by its descriptor's `ethos:restriction`, with
  `homepage` and `ethos:contact`.
- A restricted cache is a directory whose file permissions admit one access
  combination: the people who may read the same data. On the cluster, for
  example, each group has one setgid directory,
  `/shared/ethos/restricted/<group>/`, for every institute member or for one
  licence group; every new entry inherits its group. On a workstation, it is
  a directory with the user's own licensed copies.
- An account lists the restricted caches its groups admit, in order, and no
  others. A restricted file is read from the first listed cache whose entry
  is readable ([0012](0012-one-lookup-chain.md)).
- Within a root, the file system picks the mode. A symbolic link means "read
  in place". A real directory is owned by the cache: it holds downloads and
  materialized copies.
- The public cache has a default, the per-user cache directory; on the
  cluster every user sets it to one shared directory
  ([0028](0028-one-public-cache-on-the-cluster.md)). The restricted caches
  and the staging root have none: someone decides on purpose where restricted
  data is read, and what is staged. An account that lists no restricted cache
  is a valid set-up, on the cluster too.
- The public cache, the staging root and each restricted cache are separate
  directories: `config` refuses a root that is, contains or lies inside
  another ([0010](0010-one-settings-file-per-account.md)).
- Access and visibility are independent
  ([0027](0027-public-catalogue-releases-on-github.md)): visibility decides
  whether the public catalogue lists a dataset, access how its bytes may be
  obtained.

## Alternatives considered

- **A credentialed download into a private cache.** Readers would need a
  credential flow of their own, and licensed bytes would be copied to every
  machine that asks for them.
- **A per-dataset configuration table, per-dataset roots included.** Somebody
  has to write it for every dataset, and it goes out of step with what is on
  disk. A root set for one dataset also escapes the rules of its class.
- **`internal` as a class of its own, for data the institute holds.** The
  permissions of the restricted cache that holds such data already say who
  may read it. A third class would add exceptions to every component that
  reads the class.
- **One restricted cache with a group per entry.** The lookup reads that
  layout too, but one cache cannot be shared by people with different
  access: each would meet entries they may not read.
- **A non-anonymous dCache folder for restricted data the institute holds.**
  It would keep a copy of that data off the cluster. But the publication root
  is world-readable, and the upload's read-back is anonymous and cannot check
  private bytes, so it would need a private folder outside that root and a
  read-back with the maintainer's token. Whether to add it is an open point
  ([11.3](../risks-and-technical-debt.md#open-points)).

## Consequences

- Re-pointing one link in the cluster's public cache or in a restricted cache
  moves every reader at once.
- Restricted data has no copy on dCache: `catalog upload` refuses it, and
  dCache holds public bytes and the latest public catalogue only.
- When a restricted dataset becomes public, the lookup reads it through the
  public cache: `verify` reports its leftover entry in a restricted cache, and
  the maintainer unlinks it.
- An account without a restricted cache runs every workflow that needs public
  data only. A restricted input it cannot read is refused before anything is
  downloaded, and the refusal says how to obtain a copy
  ([0013](0013-every-input-is-required.md)).
- Licensed fixtures belong in restricted CI, not in bundles
  ([0020](0020-repository-bundles.md)).
- See [Caches, classes and roots](../../caches-and-access.md),
  [Restricted data is read in place](../../licensing.md#restricted-data-is-never-copied)
  and [Add restricted data](../../../how-to/catalogue-maintainers/add-restricted-data.md).

## Related

- [0004. Derive cache paths from resource identity, and never reuse a name](0004-cache-paths-from-resource-identity.md)
- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0013. Treat every input as required, and say what is missing](0013-every-input-is-required.md)
- [0016. Give one link command two modes](0016-one-link-command-two-modes.md)
- [0020. Keep attributed data in bundles that are authoritative for their package](0020-repository-bundles.md)
- [0024. Let unresolved licensing block distribution, not development](0024-licensing-gates-distribution.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [0028. Share one public cache on the cluster](0028-one-public-cache-on-the-cluster.md)
- [7. Deployment View](../deployment.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
