# 10. Quality Requirements

## 10.1 Quality tree

The tree connects the goals in [section 1](introduction-and-goals.md) to concrete
scenarios. A scenario is a review and test criterion; it is not a measured
performance guarantee. Repository bundle checks cover both normal offline use and explicit temporary
fixture divergence.

<figure markdown="span">
  ![Quality tree with traceability and integrity, access control, reuse and availability, safe maintenance, metadata scalability, and changeable code; leaves refer to scenarios Q1 through Q15.](../../assets/diagrams/architecture-quality-light.svg#only-light){ .diagram }
  ![Quality tree with traceability and integrity, access control, reuse and availability, safe maintenance, metadata scalability, and changeable code; leaves refer to scenarios Q1 through Q15.](../../assets/diagrams/architecture-quality-dark.svg#only-dark){ .diagram }
</figure>

## 10.2 Quality scenarios

| ID | Trigger and environment | Expected response | Evidence or acceptance check |
|---|---|---|---|
| Q1 | Two tools select the same resource under the same public cache root | Both derive the same path; a valid download is reused | `retrieval.local_path`, the downloader's hash check; [deduplication](../deduplication.md) |
| Q2 | A download-managed file is corrupt | Hash validation prevents accepting it as a valid cache hit; retrieval replaces it from its declared source | The `Downloader` port in `retrieval.download`; [verification guide](../../how-to/data-users/verify-and-repair.md) |
| Q3 | A required licensed dataset has no available local root | Fail before anything is downloaded, describing the dataset and how to register a copy; `plan()` reports it as not available here | The `RestrictedCache` locator of `access.chain_for`; `retrieval.download` |
| Q4 | Internal metadata contains hidden datasets and private fields | Public generation omits hidden entries and the fields the specifications mark as never published; the leak check refuses a public tree that still holds one | `maintain.publish` with the strip list of `formats`; the release's `check` stage |
| Q5 | A caller loads an index containing large dataset inventories | Inventories remain lazy until needed by selection | `catalogs.load_catalog`, `Dataset`; [catalogue format](../catalogue-format.md) |
| Q6 | A later dataset in a selected upload batch fails preflight | No selected dataset begins transfer | Subset-upload regression tests for `maintain.upload.run` |
| Q7 | A source directory includes files excluded from its inventory | Transfer file list contains only manifest resources | Manifest-filter and subset-upload tests for `upload_one` |
| Q8 | Required tests run in a fresh checkout, with an empty user cache and network unavailable | Repository bundles supply all required inputs and their metadata; a missing or changed file fails without fallback | `tests/test_repository_bundles.py`: a handle reads what its bundle holds, and an altered bundled file is an error, not a download; [runtime scenario](runtime.md#64-repository-test-data) |
| Q9 | A developer changes a repository fixture to reproduce a bug | The change is refused until `bundle update` records it, or, for an exported bundle, used under `allow_modified` without changing authoritative hashes or dCache | `bundle update`, `Bundle.fetch` and divergence regression checks, including no automatic repair |
| Q10 | A package reruns an older pinned collection | Selection retains the same resource identities; published objects, a revision's folder included, match the recorded hashes | The catalogue releases a collections file names; limited by host retention and local overrides |
| Q11 | A maintainer takes a step the dataset's state does not allow, such as uploading a draft or a frozen dataset | The command refuses before it changes anything and names what the dataset needs first | `model.lifecycle.step`; `tests/test_status_files.py` |
| Q12 | A release or a removal is interrupted and run again | The rerun does only what is left; a stamp, a tag or a withdrawal already made is not made again | `Pipeline.plan`; `test_running_it_again_finishes_what_is_left`, `test_removing_again_withdraws_nothing_new` |
| Q13 | A maintainer purges a withdrawn dataset | Nothing is deleted until a release without the dataset is recorded; its name stays taken | `maintain.remove` purge stages; `tests/test_release.py::TestPurge` |
| Q14 | A key is added to a file format | Validation, the JSON Schema, the templates' checks and the reference table change with the model; a committed schema left stale fails a test | `tests/test_formats.py`, `tests/test_reference.py` |
| Q15 | Library code imports a layer above its own | A test fails, naming the module and the import | `tests/test_layers.py` |

## 10.3 Measurement boundaries

Lazy loading is an implemented mechanism. Latency, peak memory, and concurrent
reader/writer targets require representative inventories and an agreed machine
and storage environment before numeric thresholds can be adopted. Upload
verification currently checks reachability and size, not a remote content audit.
The resulting risks are documented in [section 11](risks-and-technical-debt.md).
