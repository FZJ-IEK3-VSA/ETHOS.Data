# 10. Quality Requirements

## 10.1 Quality tree

The tree connects the goals in [section 1](introduction-and-goals.md) to concrete
scenarios. A scenario is a review and test criterion; it is not a measured
performance guarantee. Repository bundle checks cover both normal offline use and explicit temporary
fixture divergence.

<figure markdown="span">
  ![Quality tree with traceability and integrity, access control, reuse and availability, maintainability, and metadata scalability; leaves refer to scenarios Q1 through Q10.](../../assets/diagrams/architecture-quality-light.svg#only-light){ .diagram }
  ![Quality tree with traceability and integrity, access control, reuse and availability, maintainability, and metadata scalability; leaves refer to scenarios Q1 through Q10.](../../assets/diagrams/architecture-quality-dark.svg#only-dark){ .diagram }
</figure>

## 10.2 Quality scenarios

| ID | Trigger and environment | Expected response | Evidence or acceptance check |
|---|---|---|---|
| Q1 | Two tools select the same resource under the same public cache root | Both derive the same path; a valid download is reused | `retrieval.local_path`, Pooch registry; [deduplication](../deduplication.md) |
| Q2 | A download-managed file is corrupt | Hash validation prevents accepting it as a valid cache hit; retrieval replaces it from its declared source | Pooch fetch in `retrieval.download`; [verification guide](../../how-to/verify-and-repair.md) |
| Q3 | A required restricted dataset has no available local root | Fail without downloading; explicit skipping warns and omits keys | `access.locate`, `retrieval.download` |
| Q4 | Internal metadata contains hidden datasets and private fields | Public generation omits hidden entries and removes defined internal fields | `maintain.publish.strip` and `public_datasets`; schema review |
| Q5 | A caller loads an index containing large dataset inventories | Inventories remain lazy until needed by selection | `catalog.load_catalog`, `Dataset`; [catalogue format](../catalogue-format.md) |
| Q6 | A later dataset in a selected upload batch fails preflight | No selected dataset begins transfer | Subset-upload regression tests for `maintain.upload.run` |
| Q7 | A source directory includes files excluded from its inventory | Transfer file list contains only manifest resources | Manifest-filter and subset-upload tests for `upload_one` |
| Q8 | Required tests run in a fresh checkout, with an empty user cache and network unavailable | Local metadata and repository copies supply all required inputs; missing copies fail without fallback | Bundle regression tests with remote access blocked; [runtime scenario](runtime.md#64-repository-test-data) |
| Q9 | A developer changes a repository fixture to reproduce a bug | Explicit divergence mode uses that copy without changing authoritative hashes or dCache; normal validation reports divergence | `Bundle.fetch` and divergence regression checks, including no automatic repair |
| Q10 | A package reruns an older pinned collection | Selection retains the same resource identities; immutable retained published bytes match the recorded hashes | Version-pin and manifest review; limited by host retention and local overrides |

## 10.3 Measurement boundaries

Lazy loading is an implemented mechanism. Latency, peak memory, and concurrent
reader/writer targets require representative inventories and an agreed machine
and storage environment before numeric thresholds can be adopted. Upload
verification currently checks reachability and size, not a remote content audit.
The resulting risks are documented in [section 11](risks-and-technical-debt.md).
