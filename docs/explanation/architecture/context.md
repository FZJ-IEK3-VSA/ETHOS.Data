# 3. Context and Scope

This chapter answers which people and systems ETHOS.Data exchanges
information with, over which channels, and where its responsibility ends. It
is the C4 system context: ETHOS.Data is one box here, and
[section 5](building-blocks.md) opens it.

<figure markdown="span">
  ![System context. Data users, package maintainers and catalogue maintainers use ETHOS.Data through a consuming package such as ETHOS.RESKit or through its commands. ETHOS.Data reads catalogue metadata from the public catalogue on GitHub or, on the cluster, from the served checkout of the source catalogue; it downloads files anonymously from dCache, maintains dCache with tokens from Helmholtz ID, and releases both catalogues through JuGit, GitHub and dCache. Catalogue maintainers merge their records into the source catalogue on JuGit by merge request. Dashed arrows are handoffs people post: proposals, problem reports, answers and notices on the trackers, and the cluster locations on the ICE-2 wiki.](../../assets/diagrams/architecture-context-light.svg#only-light){ .diagram }
  ![System context. Data users, package maintainers and catalogue maintainers use ETHOS.Data through a consuming package such as ETHOS.RESKit or through its commands. ETHOS.Data reads catalogue metadata from the public catalogue on GitHub or, on the cluster, from the served checkout of the source catalogue; it downloads files anonymously from dCache, maintains dCache with tokens from Helmholtz ID, and releases both catalogues through JuGit, GitHub and dCache. Catalogue maintainers merge their records into the source catalogue on JuGit by merge request. Dashed arrows are handoffs people post: proposals, problem reports, answers and notices on the trackers, and the cluster locations on the ICE-2 wiki.](../../assets/diagrams/architecture-context-dark.svg#only-dark){ .diagram }
</figure>

## 3.1 Business context

| Person | Uses ETHOS.Data to | Through |
|---|---|---|
| Data user, on a public installation or as a cluster user | run workflows, examples and tests that need inputs; configure their account; run the self-test; list, fetch and verify files by key; draft a problem report | the consuming package and its `<tool>-data` command; `ethos-data` |
| Package maintainer | wire a collections file and a handle into a package; keep repository bundles; stage development data; draft proposals | the Python API; `<tool>-data` |
| Catalogue maintainer | review proposals; accept, build and record datasets and make their bytes available; fill the cluster's shared cache and restricted cache; release both catalogues; publish new versions; withdraw and purge; check provenance; diagnose reports | `ethos-data catalog`; `ethos-data link` and `materialize` |

The supporting roles of [section 1.2](introduction-and-goals.md#12-stakeholders)
act outside the package: catalogue maintainers escalate dCache problems to the
storage operator, a data user asks a dataset custodian for access to
restricted data, and the cluster administrator grants group memberships and
lets only maintainers write the shared cache.

| System | What it exchanges with ETHOS.Data |
|---|---|
| Consuming package, for example ETHOS.RESKit | Names the data its workflows need in one collections file, and holds a handle and a `<tool>-data` command. It gets local paths back, reads the files and computes. |
| dCache at DESY (HIFIS) | Holds the published bytes, and the latest public catalogue under `<publication root>/catalogue/`. Readers download from it. Maintainer commands copy, sync and purge objects, set permissions, ask for locality and read uploads back. |
| Helmholtz ID (DESY Keycloak) | Issues the bearer tokens for writes to dCache and for its REST calls. |
| `FZJ-IEK3-VSA/ETHOS.Data-Catalogue` on GitHub | The public catalogue: one tag `vYYYY.MM.N` per release, and an index on `main` that lists every release. Readers fetch metadata from it, and `catalog release --push` pushes the public view and its tag. Its tracker takes public proposals and problem reports. |
| `iek-3/shared-code/ethos-data-catalog-internal` on JuGit | The source catalogue, one tag per release. Maintainers merge their records and descriptor changes into it by merge request. `catalog release --push` pushes the release commit and tag, and `catalog update-checkout` fetches the tags to move the cluster's served checkout. Its tracker takes proposals for internal or restricted data and reports from cluster users. |
| `FZJ-IEK3-VSA/ETHOS.Data` on GitHub | The code and the docs, and the tracker for the commands, the API and the docs. |
| Upstream data providers | The originals, sometimes with checksums, and their licence and attribution terms. Maintainers download originals again to check provenance. |
| ICE-2 wiki | The real cluster locations, groups and contacts; the `config set-*` commands that point cluster users at the served checkout, the shared cache and the restricted cache, and where to keep a personal public cache; release announcements. |

Read the Docs and conda-forge serve only the docs build and the installation.

The roles hand each other proposals, answers, release and removal notices,
and problem reports. The command that knows the facts drafts each one, and a
person posts it. The [use-case figure](../../how-to/index.md#roles-together)
shows these handoffs task by task.

A catalogue entry grants no access to its files.
[Visibility and access are separate questions](../licensing.md#access-and-visibility-are-two-questions):
a catalogue may describe a restricted dataset that a particular user cannot
obtain.

## 3.2 Technical context

| Partner | Channel | What travels |
|---|---|---|
| Consuming package | Python, in-process: `collections()`, `paths()`, `fetch()`, `catalog.path()`, `tool_main()` | A collection, its variant and options; resource keys, named paths and local paths back |
| Public catalogue repository | HTTPS GET from `raw.githubusercontent.com`, gzip | The index of a release tag or of `main`, descriptors, shards and licence documents |
| | git over HTTPS or SSH | The public view and its release tag, pushed |
| Source catalogue repository | git | The release commit and tag, pushed; tags fetched for the served checkout |
| | git and merge requests, by hand | A maintainer's commits from their own clone |
| dCache | Anonymous HTTPS GET and HEAD, through the download door | Downloads; the read-back of uploads |
| | rclone over WebDAV, and the REST frontend, with a bearer token | Copy, sync and purge; permissions and locality |
| Helmholtz ID | `oidc-token` from oidc-agent; the OIDC code flow in a browser, once per profile | Bearer tokens |
| Trackers, the ICE-2 wiki, upstream providers | By hand; curl for re-downloads | Posted drafts; cluster settings and announcements; originals for a provenance check |

On the cluster computer, cluster users reach the internal catalogue and the
shared data through the file system, not through a network service: the
served checkout of the source catalogue's latest release, the shared cache
that maintainers fill with links into project storage and copies of public
and internal data, and the restricted cache. Cluster users read all three and
write none of them; their downloads go into their own public cache. Internal
data is readable only there. These stores belong to ETHOS.Data:
[section 5](building-blocks.md) describes them and
[section 7](deployment.md) places them.

## 3.3 Scope

ETHOS.Data resolves selections, and locates, downloads and verifies files.
It maintains the catalogues, records each dataset's state and drafts the
handoffs between roles. It does not:

- host a data service of its own;
- run calculations: the consuming package reads the files and computes;
- provision licensed data: settings locate data and grant no permission;
- lock or synchronise caches;
- offer optional inputs: every input a collection names is required;
- write to an issue tracker: people post the drafts.
