# 4. Solution Strategy

| Goal | Chosen approach | Consequence and detailed explanation |
|---|---|---|
| Reuse data across packages | One catalogue inventory; package-owned collections select resources | Shared keys derive shared cache paths. [Why one catalogue](../deduplication.md) |
| Preserve understandable ownership | Separate metadata from authoritative dataset storage | Catalogues can be mirrored and versioned without duplicating large data archives. [Context](context.md) |
| Support large inventories | Load descriptors and inventory shards on demand | Later selection may encounter metadata failures even after an index has loaded. [Catalogue format](../catalogue-format.md) |
| Respect data access conditions | Resolve explicit roots and access classes before downloads | Existing restricted copies are used in place; missing required files fail with locations. [Caches and access](../caches-and-access.md) |
| Keep reader and writer compatible | Ship them in one distribution with shared matching and format rules | Maintainer dependencies are imported at their command boundary. [Building blocks](building-blocks.md) |
| Preserve published input identities | Immutable uploaded paths, manifest hashes, and explicit catalogue version pins | Changed bytes need a new published path; pins also depend on retention. [Licensing and immutability](../licensing.md) |
| Catch avoidable transfer failures early | Validate a selected upload batch before transferring its first dataset | Later network failures still require recovery; there is no batch rollback. [Runtime](runtime.md#63-catalogue-lifecycle) |
| Reduce repeated CI downloads while allowing bug investigation | Keep selected test copies and metadata in consuming repositories, with explicit temporary divergence | dCache remains authoritative; bundle operations are separate from ordinary cache repair. [Testing scenario](runtime.md#64-repository-test-data) |

Repository bundles provide the last approach through a self-contained local
manifest and explicit `allow_modified` reads. Ordinary public cache downloads
continue to enforce their checksum checks. Hosting choices and versioned catalogue
snapshots are described in [Deployment View](deployment.md).
