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
| `ethos_data` reader | Selects resources, resolves locations, retrieves files | Python API, package wrappers, or direct `ethos-data ls/fetch`; local paths returned |
| Source catalogue | Maintainer-owned dataset descriptions, each dataset's status file, and generated inventories | YAML inputs, JSON descriptors and shards |
| Published catalogue | Generated view selected by visibility, with internal fields removed | JSON read locally or over HTTP(S) |
| Remote storage (DESY dCache) | Authoritative centrally published dataset bytes, including test data | Download URLs; maintainer upload interfaces |
| Local roots | Hold downloaded, shared, licensed, or staged files | Filesystem paths and symbolic links |
| Maintainer tooling | Accepts, builds, uploads, freezes, releases and removes datasets, recording each step; drafts the notices | `ethos-data catalog` commands |

A published catalogue entry does not itself grant access to the files.
[Visibility and access are independent](../licensing.md#access-and-visibility-are-two-questions):
a catalogue may describe a restricted dataset that a particular user cannot obtain.

## 3.2 Technical context and boundaries

Catalogue maintainers establish provenance and redistribution terms and review
what they publish. Storage operators manage service availability and permissions.
Users or administrators configure access to existing local copies. Consuming
packages choose their collections and the catalogue releases they work with;
every input a collection names is required.

The package does not host a central data service of its own, run calculations,
or automatically provision licensed datasets. For first use, follow
[Your first fetch](../../tutorials/first-fetch.md); for integration, see
[Use ETHOS.Data in your package](../../how-to/package-maintainers/use-from-a-package.md).

The internal metadata source is the internal catalogue checkout on the
ICE-2 cluster computer, synchronised with JuGit. Public metadata is a
reviewed, stripped view hosted on GitHub. These are metadata locations, not
alternative authorities for dataset bytes. Repository bundles reduce repeated
remote reads and support local debugging; the catalogue publishes their
versions on dCache.

| Boundary | Information exchanged | Technical interface |
|---|---|---|
| Consuming package → reader | Collection name, variant, catalogue location, options; resource keys, named paths and local paths returned | Python `Collections.fetch()` / `paths()`, `Catalog.path()` or CLI; collections YAML |
| Reader → metadata location | Index, requested descriptors and shards | Filesystem reads or HTTP(S) JSON; relative references resolved from the catalogue |
| Reader → local storage | Presence checks, reads and verified cache downloads | Paths, directories and symbolic links |
| Reader → dCache | Published dataset files | HTTP(S), with content hashes supplied by metadata |
| Maintainer tooling → catalogue checkout | Generated index, descriptors, shards, licence copies; status files | YAML inputs and filesystem JSON and YAML outputs |
| Maintainer tooling → storage/identity services | Manifest-limited uploads, permissions and remote checks; the latest public catalogue | The `Store` port: rclone, oidc-agent, HTTP APIs |
| Maintainer tooling → Git hosting | Release commits and tags of both checkouts; fetches of the served checkout | The `Git` port: git |

Review happens outside `ethos-data`. A release is made by
`ethos-data catalog release`, which commits and tags both checkouts and, with
`--push`, pushes them; `catalog update-checkout` moves the checkout cluster
users read to a release. See the physical locations in
[Deployment View](deployment.md).
