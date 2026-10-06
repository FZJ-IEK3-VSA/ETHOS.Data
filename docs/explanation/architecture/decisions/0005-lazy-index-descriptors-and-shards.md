# 0005. Read the index first and inventories on demand

**Status:** implemented · **Date:** 2026-09-10

## Context

Inventories are large: ERA5 alone has about 170,000 resources. A question
about one dataset must not download or parse another dataset's inventory.
Files that travel together, such as a shapefile's companions or the variables
of one tile, must sit in one shard. Metadata read from a release tag never
changes; metadata read from a branch does.

## Decision

- `load_catalog` reads only the index, `datacatalog.json`. A dataset's
  descriptor is read the first time something asks for its files.
- The index row carries what a reader needs without the descriptor: the
  access class, the visibility, the totals, the remote prefix and the licence
  status. Deciding where a dataset is read never pulls in its inventory.
  [0006](0006-every-file-format-specified-once.md) makes these the keys marked
  `promoted`, and [0019](0019-revisions-and-successors.md) adds the revision
  and the successors.
- A large dataset is sharded by its first `ethos:shard_depth` directory
  segments, as `shards/<prefix>.json` files that `ethos:shards` lists. Files in
  one directory share a shard.
- The shard filter may fetch a shard that holds nothing a pattern matches, but
  never drops one that does.
- The metadata cache keeps catalogue files read over HTTPS:
    - a URL that names no moving ref, such as a release tag, is cached forever;
    - a URL that names `main`, `master`, `HEAD`, `latest`, `dev` or `develop`
      is never cached;
    - setting `ETHOS_CATALOG_NO_CACHE` turns caching off;
    - a write goes to a temporary file, which is then renamed;
    - requests ask for gzip.

## Alternatives considered

- **Eager loading.** Every command reads inventories it does not need; the
  ERA5 inventory alone is about 64 MB.
- **Sharding by something other than the directory.** A companion file can
  land in another shard, and resolving it costs a second fetch.

## Consequences

- A missing descriptor or shard fails later than the index, with
  `IncompleteCatalog` naming the dataset, the part and the location.
- An extra shard costs one fetch, while a dropped one is a wrong result, so
  the filter errs towards fetching.
- The one inventory reader keeps this laziness
  ([0007](0007-one-inventory-reader.md)), and the metadata cache is a
  decorator of the metadata-source port
  ([0009](0009-ports-and-fakes-for-external-systems.md)).
- See [Loading is lazy](../../catalogue-format.md#loading-is-lazy) and
  [Sharding](../../catalogue-format.md#sharding).

## Related

- [0006. Specify every file format once](0006-every-file-format-specified-once.md)
- [0007. Read every generated catalogue through one inventory reader](0007-one-inventory-reader.md)
- [0009. Reach dCache, downloads, metadata sources and git through ports with fakes](0009-ports-and-fakes-for-external-systems.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [5. Building Block View](../building-blocks.md)
- [10. Quality Requirements](../quality-requirements.md)
