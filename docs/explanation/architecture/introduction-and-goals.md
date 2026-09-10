# 1. Introduction and Goals

## 1.1 Requirements overview

Scientific packages need subsets of shared datasets. `ethos-data` gives these
packages one vocabulary for identifying resources and one way to obtain local
paths, whether the bytes are downloaded, already present on a cluster, or kept
with tests. A consuming package owns its collections and reads the resulting
files; the catalogue describes the files and their provenance.

Catalogue maintainers need to accept proposed datasets, generate inventories,
upload and verify approved data, and release an appropriate public metadata view.
Data bytes and metadata are separate publication outputs.

## 1.2 Stakeholders

| Role | Needed behaviour and understanding |
|---|---|
| Data user, including an ETHOS.RESKit user | Obtain all data needed by a package or only a task collection; understand origin, size, access failures, and reuse |
| Package maintainer | Wire collections into workflows, test locally and in CI, develop new datasets before submission, and update catalogue pins deliberately |
| Catalogue maintainer | Review submissions, maintain the internal catalogue, upload data, generate public metadata, release versions, and diagnose package failures |

A person can perform more than one role. Cluster and storage administration are
supporting responsibilities: filesystem permissions and service availability
remain outside the Python package.

## 1.3 Quality goals

These are the priorities used to evaluate design choices; the concrete acceptance
scenarios are in [section 10](quality-requirements.md).

| Priority | Goal | Why it matters |
|---|---|---|
| 1 | Traceable, repeatable inputs | A workflow must identify its catalogue version and dataset resources; local experiments must remain distinguishable from published data |
| 2 | Controlled access and publication | Licence, visibility, and filesystem restrictions must survive catalogue generation and retrieval |
| 3 | Reuse and availability | Shared paths reduce duplicate downloads; small repository copies should keep required tests independent of dCache availability |
| 4 | Safe maintenance and diagnosis | Invalid upload selections should fail early; failures must identify useful resources and locations |
| 5 | Scalable metadata access | Large inventories should not be loaded to answer unrelated requests |

These priorities are a working ordering for this guide, to refine with measured
workloads and maintainer experience. dCache remains authoritative for centrally
published data, including test data. Repository test copies are deliberate local
copies. Temporarily changing one to reproduce a bug must not imply approval to
update dCache or published metadata.
