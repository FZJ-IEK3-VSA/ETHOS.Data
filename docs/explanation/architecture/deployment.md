# 7. Deployment View

`ethos-data` runs as a Python library or CLI on the caller's machine. Metadata
hosting and remote data storage are external services. The diagram describes
the catalogue hosting arrangement, the commands that move metadata between
its places, and the repository bundle workflow.

## 7.1 Infrastructure overview

<figure markdown="span">
  ![Deployment nodes: the ICE-2 cluster computer with reader, maintainer tooling, the internal catalogue at a release and shared caches; JuGit for the internal source catalogue; GitHub for the public catalogue; workstation or CI with reader and repository bundles; dCache as authoritative published data storage that also holds the latest public catalogue. The arrows are the commands catalog release, update-checkout and upload.](../../assets/diagrams/architecture-deployment-light.svg#only-light){ .diagram }
  ![Deployment nodes: the ICE-2 cluster computer with reader, maintainer tooling, the internal catalogue at a release and shared caches; JuGit for the internal source catalogue; GitHub for the public catalogue; workstation or CI with reader and repository bundles; dCache as authoritative published data storage that also holds the latest public catalogue. The arrows are the commands catalog release, update-checkout and upload.](../../assets/diagrams/architecture-deployment-dark.svg#only-dark){ .diagram }
</figure>

| Environment | Deployed blocks and metadata | Dataset bytes and access |
|---|---|---|
| ICE-2 cluster computer | Consumer entry points and Data access in each user's environment; the internal catalogue checkout at its latest release, at a filesystem path | Shared files, public cache, and configured restricted roots; permissions still apply |
| Maintainer environment | Maintainer entry points and Catalogue maintenance; the source checkout in JuGit and the public checkout from GitHub; `catalog release` commits and tags both, and pushes them with `--push` | Local proposed sources; rclone and oidc-agent for uploads; dCache HTTP checks |
| GitHub public catalogue | The released public metadata, one tag per release; packages name the releases they work with | Dataset URLs refer to dCache; hosting metadata does not move authority for bytes |
| Personal workstation | Consuming package and reader; the newest public release the package accepts, or a local snapshot | Per-user download cache and configured existing copies |
| Package repository and CI runner | Package, collections, and repository bundles, read first by the package's handle | Small repository test copies; larger optional integration inputs may use dCache separately |
| dCache and identity provider | External storage, access, and identity services | Authoritative centrally published dataset bytes, including test data, and a copy of the latest public catalogue under `<publication root>/catalogue/` |

## 7.2 Internal catalogue on the ICE-2 cluster computer

Cluster users point at the `datacatalog.json` of the internal catalogue
checkout on the filesystem; they do not need to fetch metadata through
JuGit. JuGit supplies version control, review, and synchronisation for
maintainers: `catalog release --push` pushes a release and its tag there.

The checkout readers are served is moved to a release on the machine that
serves it, with `ethos-data catalog update-checkout`: it fetches the remote's
branches and tags, moves the checkout to the newest release by fast-forward
only, and checks every manifest against its files without writing. Nothing is
rebuilt in a served checkout, so its index and inventories always come from
the same release. The fast-forward changes files in place, so run it when no
jobs are reading the checkout: a reader that lists the index during the update
can find inventories of the other release. Serving each release from its own
directory and switching a link to it would avoid that; it is an operational
choice, not a command.

## 7.3 Public metadata distribution

GitHub is the home of the public metadata view. A release is a tag of the
public checkout, made by `catalog release`, and a package names the releases
it works with in its collections file; with no catalogue configured, the
reader takes the newest public release within them. The current reader
expects JSON files in their catalogue layout, so a compressed release asset
must be extracted before pointing the reader at its local index. A release
archive URL is not itself a catalogue index URL.

`catalog release --upload` also puts the public catalogue beside the data on
the store, under `<publication root>/catalogue/`, replacing the previous one:
the store keeps the latest release only. Pinning and local reuse reduce
repeated metadata traffic. Releases do not by themselves add archive
installation, cache refresh policy, or immunity to host limits to the reader.
Keep metadata release and storage verification separate: the release's check
stage refuses a public dataset without a verified upload, so files a release
advertises are ready before consumers can select them.

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
For required tests, a repository bundle provides both, so tests run while
dCache is unavailable: the package's handle reads bundled files first and
never falls back to a download. A developer reproduces a bug against an edited
fixture and records the change with `bundle update`; an exported bundle offers
`Bundle.fetch(..., allow_modified=True)` instead. Neither updates the
authoritative copy. This workflow is described in
[Runtime View](runtime.md#64-repository-test-data).

For the release procedure, see [Release the catalogue](../../how-to/catalogue-maintainers/release-the-catalogue.md).
For repository fixtures, see [Keep data in the repository](../../how-to/package-maintainers/keep-data-in-the-repository.md).

For setup, use [Installation](../../installation.md),
[Configure the cache](../../how-to/data-users/set-up-your-machine.md#public-installation-users),
[Run it in CI](../../how-to/package-maintainers/run-in-ci.md), and
[Upload a dataset](../../how-to/catalogue-maintainers/upload-a-dataset.md).
