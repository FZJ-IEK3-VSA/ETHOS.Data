# 0004. Derive cache paths from resource identity, and never reuse a name

**Status:** implemented · **Date:** 2026-09-10

## Context

Packages developed independently must reuse the same local files without
coordinating, on a laptop and on shared storage alike. A lock, a daemon or an
index of downloads is one more thing to fail on shared storage. A name must
keep its meaning, so that a collections file and a cache entry written years
apart still agree.

## Decision

- A place is computed, never configured: `<root>/<entry>/<resource path>`.
  The entry is the dataset's name; a later revision's entry, `<dataset>@<r>`,
  is part of [0019](0019-revisions-and-successors.md).
- Identity is the key `<dataset>/<resource path>`. A family member is named
  `family/member`, which is at once its cache path, its default remote prefix
  and its address in a collections file.
- Nothing synchronises: there is no lock, no index of downloads and no daemon.
  Two processes racing for one file both verify it against the same checksum.
- A collection's `files:` patterns and a dataset's `ethos:include` patterns are
  matched by one matcher, so the build and a collection select the same files.
- A name keeps its meaning forever. After a purge, the dataset's tombstone
  keeps the name taken ([0022](0022-dataset-status-files.md)).

## Alternatives considered

- **A configured or per-package layout.** Two packages compute different paths
  for one file, and sharing stops without an error.
- **A cache manager, a lock, a daemon or a farm of symlinks.** Each needs
  coordination on shared storage and can fail by itself.

## Consequences

- `Resource.key`, entry names and object folders are contracts between
  independently developed packages. A change to them stops the sharing
  without failing anything.
- Staging and per-dataset roots are keyed by the dataset's name, not by its
  entry.
- Every cache has this layout: each user's public cache, the cluster's shared
  cache ([0028](0028-read-only-shared-cache.md)) and the restricted cache. The
  lookup chain reads them all the same way
  ([0012](0012-one-lookup-chain.md)).
- Two jobs that fetch the same file cost at most one redundant download.
- See [What makes the sharing work](../../deduplication.md#what-makes-the-sharing-work).

## Related

- [0003. One catalogue describes the data; each package's collections file selects from it](0003-one-catalogue-many-collections.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0028. Serve shared data on the cluster from a read-only shared cache](0028-read-only-shared-cache.md)
- [5. Building Block View](../building-blocks.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
