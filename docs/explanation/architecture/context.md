# 3. Context and Scope

A RESKit user may encounter `ethos-data` through a calculation that needs input
files, without calling its CLI directly. The consuming package chooses a
collection; `ethos-data` resolves that selection and returns local file paths.
The consuming package remains responsible for reading those files and performing
the calculation.

<figure markdown="span">
  ![A consuming package calls ethos-data, which reads catalogue metadata and obtains files from remote storage or local roots. Maintainer tooling generates metadata and uploads bytes separately.](../../assets/diagrams/architecture-context-light.svg#only-light){ .diagram }
  ![A consuming package calls ethos-data, which reads catalogue metadata and obtains files from remote storage or local roots. Maintainer tooling generates metadata and uploads bytes separately.](../../assets/diagrams/architecture-context-dark.svg#only-dark){ .diagram }
</figure>

## 3.1 Business context

| Component | Responsibility | Interface |
|---|---|---|
| Consuming package, such as ETHOS.RESKit | Declares the slices of data its workflows need | Collections YAML and Python API |
| `ethos-data` reader | Selects resources, resolves locations, retrieves files | Python API or CLI; local paths returned |
| Source catalogue | Maintainer-owned dataset descriptions and generated inventories | YAML inputs, JSON descriptors and shards |
| Published catalogue | Generated view selected by visibility, with internal fields removed | JSON read locally or over HTTP(S) |
| Remote storage (DESY dCache) | Authoritative centrally published dataset bytes, including test data | Download URLs; maintainer upload interfaces |
| Local roots | Hold downloaded, shared, licensed, or staged files | Filesystem paths and symbolic links |
| Maintainer tooling | Builds inventories, uploads files, generates public metadata | `ethos-data catalog` commands |

A published catalogue entry does not itself grant access to the files.
[Visibility and access are independent](../licensing.md#access-and-visibility-are-two-questions):
a catalogue may describe a restricted dataset that a particular user cannot obtain.

## 3.2 Technical context and boundaries

Catalogue maintainers establish provenance and redistribution terms and review
what they publish. Storage operators manage service availability and permissions.
Users or administrators configure access to existing local copies. Consuming
packages choose their collections and catalogue versions and decide whether a
missing optional dataset is acceptable to the calculation.

The package does not host a central data service of its own, run calculations,
or automatically provision licensed datasets. For first use, follow
[Your first fetch](../../tutorials/first-fetch.md); for integration, see
[Use ETHOS.Data in your package](../../how-to/use-from-a-package.md).

The intended internal metadata source is a generated catalogue on cluster
storage, synchronised with JuGit. Public metadata is a reviewed, stripped view
hosted on GitHub. These are metadata locations, not alternative authorities for
dataset bytes. Repository test copies reduce repeated remote reads and support
local debugging; their published origin remains dCache.

| Boundary | Information exchanged | Technical interface |
|---|---|---|
| Consuming package → reader | Collection name, variant, catalogue location, options; resource keys, named paths and local paths returned | Python `fetch()` / `paths()` / `fetch_one()` or CLI; collections YAML |
| Reader → metadata location | Index, requested descriptors and shards | Filesystem reads or HTTP(S) JSON; relative references resolved from the catalogue |
| Reader → local storage | Presence checks, reads and verified cache downloads | Paths, directories and symbolic links |
| Reader → dCache | Published dataset files | HTTP(S), with content hashes supplied by metadata |
| Maintainer tooling → catalogue checkout | Generated index, descriptors, shards, licence copies | YAML inputs and filesystem JSON outputs |
| Maintainer tooling → storage/identity services | Manifest-limited uploads, permissions and remote checks | rclone, oidc-agent, HTTP APIs |

Repository synchronisation, review, tagging, and release creation happen outside
`ethos-data`; the package's publish command generates files. See the intended
physical locations in [Deployment View](deployment.md).
