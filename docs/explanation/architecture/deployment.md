# 7. Deployment View

`ethos-data` runs as a Python library or CLI on the caller's machine. Metadata
hosting and remote data storage are external services. The diagram describes the
intended catalogue hosting arrangement and the local repository bundle workflow.

## 7.1 Infrastructure overview

<figure markdown="span">
  ![Deployment nodes: cluster with reader, versioned internal metadata and shared data; JuGit for source metadata; GitHub for public metadata; workstation or CI with reader and local copies; dCache as authoritative published data storage.](../../assets/diagrams/architecture-deployment-light.svg#only-light){ .diagram }
  ![Deployment nodes: cluster with reader, versioned internal metadata and shared data; JuGit for source metadata; GitHub for public metadata; workstation or CI with reader and local copies; dCache as authoritative published data storage.](../../assets/diagrams/architecture-deployment-dark.svg#only-dark){ .diagram }
</figure>

| Environment | Deployed blocks and metadata | Dataset bytes and access |
|---|---|---|
| Institute cluster | Consumer entry points and Data access in each user's environment; generated internal catalogue at a filesystem path | Shared files, public cache, and configured restricted roots; permissions still apply |
| Maintainer environment | Maintainer entry points and Catalogue maintenance; source checkout synchronised through reviewed Git changes with JuGit | Local proposed sources; rclone and oidc-agent for uploads; dCache HTTP checks |
| GitHub public catalogue | Reviewed public metadata view, pinned by consumers to a version or revision | Dataset URLs refer to dCache; hosting metadata does not move authority for bytes |
| Personal workstation | Consuming package and reader; pinned remote catalogue or a local snapshot | Per-user download cache and configured existing copies |
| Package repository and CI runner | Package, collections, and local bundle metadata snapshot for selected test resources | Small repository test copies; larger optional integration inputs may use dCache separately |
| dCache and identity provider | External storage, access, and identity services | Authoritative centrally published dataset bytes, including test data |

## 7.2 Internal catalogue on the cluster

Cluster users should point at the generated `datacatalog.json` on the filesystem;
they do not need to fetch metadata through JuGit. JuGit supplies version control,
review, and synchronisation for maintainers. Git synchronisation alone does not
build metadata or determine which revision is ready for consumers.

A deployment process should build and validate a complete versioned snapshot,
then activate its consumer-facing path. Retain revision-specific paths for
reproducible runs. Avoid editing a live generated tree file by file: an index from
one revision can otherwise be observed alongside descriptors from another.
This activation process is an operational recommendation, not an automatic
`ethos-data` command.

## 7.3 Public metadata distribution

GitHub is a suitable intended home for the public metadata view. Consumers
should use a pinned revision or a locally extracted versioned release snapshot;
maintainers should keep the index, descriptors, shards, and licence files together.
The current reader expects JSON files in their catalogue layout, so a compressed
release asset must be extracted before pointing the reader at its local index.
A release archive URL is not itself a catalogue index URL.

Pinning and local reuse reduce repeated metadata traffic. Creating releases does
not by itself add archive installation, cache refresh policy, or immunity to host
limits to the reader. Keep metadata release and storage verification separate:
files advertised in a release should be ready before consumers can select them.

## 7.4 Local copies, credentials, and offline use

A shared cache saves space when consuming tools derive the same paths under the
same root. A symbolic link delegates a file location; its target and permissions
must remain usable by readers. Neither establishes a storage availability guarantee.

Ordinary public downloads do not require maintainer upload credentials. Uploads
use rclone and oidc-agent, and namespace HTTP operations use a bearer token. The
current reader does not configure that uploader credential flow. An accessible
local root is the documented option where the ordinary download interface cannot
read internal data.

Offline use requires both relevant metadata and selected dataset files locally.
For required tests, repository copies reduce dCache traffic and provide inputs
when dCache is unavailable. `Bundle.fetch(..., allow_modified=True)` lets a developer test edited fixtures
without overwriting those edits or updating the authoritative copy. This workflow
is described in
[Runtime View](runtime.md#64-repository-test-data).

For the hosting procedure, see [Host versioned catalogues](../../how-to/catalogue-hosting.md).
For repository fixtures, see [Keep test data in a repository](../../how-to/keep-test-data-in-a-repository.md).

For setup, use [Installation](../../installation.md),
[Configure the cache](../../how-to/set-up-your-machine.md#cache-locations),
[Run it in CI](../../how-to/run-in-ci.md), and
[Upload a dataset](../../how-to/upload-a-dataset.md).
