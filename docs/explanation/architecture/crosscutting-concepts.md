# 8. Crosscutting Concepts

These rules apply across the building blocks. The linked Data concepts pages
are the canonical detailed explanations, avoiding a second account of the same
behaviour inside Architecture.

| Concept | Shared rule | Canonical explanation or reference |
|---|---|---|
| Identity and paths | `<dataset>/<resource path>` connects selection, cache reuse, verification, and upload | [Why one catalogue](../deduplication.md) |
| Configuration and location | Explicit roots, configured roots, staging, access class, and filesystem state determine where bytes are used | [Caches, classes and roots](../caches-and-access.md); [configuration precedence](../../reference/configuration.md) |
| Metadata representation | Internal inventories and the public view share a reader contract; descriptors and shards are lazy | [Catalogue format](../catalogue-format.md); [field definitions](../../reference/schemas.md) |
| Integrity | Download-managed files are hash-checked; ordinary in-place access checks existence; explicit verification serves a separate purpose | [Runtime View](runtime.md#61-data-request); [verify and repair](../../how-to/data-users/verify-and-repair.md) |
| Access and publication | Visibility determines metadata publication; access determines how bytes may be used | [Licensing and immutability](../licensing.md) |
| Reproducibility | Pin metadata and retain immutable published paths; declare development overrides and changed local test copies | [Licensing and immutability](../licensing.md); [quality scenarios](quality-requirements.md) |
| Errors and optional data | Missing required data fails; explicit skipping warns and removes keys from the result | [Runtime View](runtime.md#62-access-failures-and-development-data) |
| Publication readiness | Build, upload, verification, and metadata release are separate operations with an explicit review boundary | [Catalogue lifecycle](runtime.md#63-catalogue-lifecycle) |

## Local test divergence

A repository test copy can serve two purposes: repeatable tests without remote
traffic, and a temporary changed input used to verify a bug fix. `Bundle.fetch()` distinguishes those states, retains the authoritative resource
key and expected checksum, and warns when `allow_modified=True` accepts changed
bytes. It does not update the official manifest to disguise the difference. Catalogue maintainers still review
and publish accepted changes. See the [runtime scenario](runtime.md#64-repository-test-data).
