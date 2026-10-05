# 0007. Read every generated catalogue through one inventory reader

**Status:** proposed · **Date:** 2026-10-05 · **Implemented by:** a new PR (inventory reader)

## Context

The generated catalogue, an index with descriptors and shards, is read on two
sides: by data users, over HTTPS or from the served checkout on the cluster,
and by maintainer commands, from a maintainer's own clone or from a tree
rendered in memory. Maintainers must see exactly the resources that readers
see, and the build must write shards by the rules the readers apply. Writer
and reader ship in one distribution, so that a format change is one commit.
Separate readers drift apart in digests, sidecars, names, errors, laziness and
result types.

## Decision

One inventory reader, in the model layer, reads one dataset's descriptor and
its inventory, inline or in shards.

| Aspect | The inventory reader |
|---|---|
| Source | Reads each part through a part reader it is handed. Every metadata source is one ([0009](0009-ports-and-fakes-for-external-systems.md)): a file or a checkout, HTTPS, the metadata cache in front of HTTPS, or a tree held in memory. It does no input or output of its own. |
| Answers | The descriptor; the resources of the whole inventory, of one path or of a pattern, typed and built lazily; the records as written, in inventory order. |
| Reads | The descriptor on first access, and each shard at most once, when asked: one shard for a path; for a pattern, only the shards it can reach, never dropping one that holds a match ([0005](0005-lazy-index-descriptors-and-shards.md)); every shard for the whole inventory. |
| Owns | The shard rules the build shares: the shard key, the root shard, pruning, splitting and the shard file names. |
| Also built from | Records, for bundles, and resources, for staging; it then reads nothing. |
| Fails | With one error for a missing part, `IncompleteCatalog`, naming the dataset, the part and the location. Maintainer commands word it as a `DescriptorError` that says to run `ethos-data catalog build <name>`. |

- `catalogs.Dataset` is an index row plus an inventory from this reader.
- Maintainer commands open the inventories of their clone through the same
  reader, over a file source.
- `publish` copies the shards the inventory lists. A revision compares the
  inventory in the clone with one over the next revision, rendered in memory.
- One reader and writer of resource records, and one set of shard rules, serve
  the build. Writing stays in catalogue maintenance.

## Alternatives considered

- **Two readers with a parity test.** The test finds drift after it happens,
  and every format change is still made twice.
- **One shared reading function that opens files and URLs itself.** The model
  then does input and output, and there is neither a fake nor a cache
  decorator.
- **Maintainer commands reading their clone with `load_catalog`, without a
  port.** A smaller change, but it loses the in-memory fake and the cache
  decorator.

## Consequences

- Maintainers see the resources readers see, and both sides refuse a missing
  shard with the same error.
- The metadata cache takes its directory from the settings snapshot
  ([0010](0010-one-settings-file-per-account.md)).
- Tests read inventories from a tree held in memory, with no checkout and no
  HTTP server.
- The resource record has one parser and one writer.
- See [5. Building Block View](../building-blocks.md) and
  [Writer and reader ship together](../../catalogue-format.md#writer-and-reader-ship-together).

## Related

- [0005. Read the index first and inventories on demand](0005-lazy-index-descriptors-and-shards.md)
- [0006. Specify every file format once](0006-every-file-format-specified-once.md)
- [0008. Build the package in four layers: model, adapters, services, presentation](0008-four-layers.md)
- [0009. Reach dCache, downloads, metadata sources and git through ports with fakes](0009-ports-and-fakes-for-external-systems.md)
- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [5. Building Block View](../building-blocks.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
