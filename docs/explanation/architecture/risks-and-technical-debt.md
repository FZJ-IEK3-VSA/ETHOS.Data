# 11. Risks and Technical Debt

This chapter answers which risks the target architecture carries, which
technical debt it accepts, and which of its defaults are still open. Each risk
names what limits it; each item of debt is a simplification the design keeps,
with what holds it in check.

## 11.1 Risks

### The cluster

| Risk | Mitigation |
|---|---|
| **Only the latest internal release is served.** The served checkout holds the source catalogue's latest release only. A collections file whose bounds exclude it, with an `exact_version` of an older release or a `max_version` below it, is refused on the cluster with `CatalogVersionError` as soon as the next release is served. | Packages that run on the cluster bound their collections file with `min_version` only, and raise it deliberately. The refusal names both versions. Per-release directories behind a switched link would serve older releases too; [ADR 0026][adr-0026] rejects them in favour of one checkout. |
| **Each cluster user needs room for their own downloads.** Every public cache is personal, on the cluster too, so a public file the shared cache lacks is downloaded once per user. | Maintainers link or materialize much-used public data into the shared cache. The ICE-2 wiki recommends a public-cache location with enough room, for example on scratch storage; a file lost from there is downloaded again ([ADR 0028][adr-0028]). |
| **A broken shared entry affects every cluster user, and no user can repair it.** Public files then fall back to a download into each user's own public cache, and internal data is refused. | `verify` reports the broken entry, and `report` drafts the problem report for the internal tracker on JuGit. Maintainers fix the entry with `ethos-data --root <shared cache> link --force NAME DIR`, or copy it again with `materialize`; `link --all` skips a frozen dataset, which has no build input. `verify --repair` never writes the shared cache ([ADR 0028][adr-0028]). |
| **The shared cache is not tied to a release.** It changes when a maintainer writes it, not with `update-checkout`. `link --all --prune` from a clone that lacks another maintainer's unmerged dataset removes that dataset's link for every cluster user, and repointing a link changes the bytes read under the served release. | Maintainers fill and prune the shared cache with `link --all` only from a clone at the merged state of the served release; a new dataset is linked by name. `verify --deep` finds bytes that do not match the served release's hashes ([ADR 0028][adr-0028]). |
| **Internal data has no copy off the cluster.** Its only copies are on cluster storage, in project storage and in the shared cache's copies; dCache holds none, because internal data is never uploaded. | Materializing a dataset into the shared cache makes a second copy beside project storage, on the same storage system. A non-anonymous dCache folder for internal data would add one off the cluster; [ADR 0011][adr-0011] weighs it, and it is an [open point](#open-points). |
| **An update changes the served checkout in place.** `catalog update-checkout` fast-forwards it, so a job that lists the index during the update can read inventories of the other release. | Run the update while no jobs read the checkout ([ADR 0026][adr-0026]). |
| **Internal data is readable only on the cluster.** Readers have no credential flow; only maintainers authenticate, to write to dCache. Internal data is never published, so it is read only from the shared cache. Every other machine, a cluster member's laptop included, is a public installation. | Deliberate ([ADR 0011][adr-0011], [ADR 0028][adr-0028]). |
| **Shared storage is operated by others.** Its permissions and availability, and the project directories the shared links point into, are outside the package. Nothing locks a cache. | Only maintainers write the shared cache. A user's concurrent jobs write only that user's public cache, where two downloads of one file both verify it against the same checksum ([ADR 0004][adr-0004]). |

### Published data and metadata

| Risk | Mitigation |
|---|---|
| **Reproducibility depends on retention.** Release bounds cannot stop DESY or GitHub from deleting or changing hosted objects. | Objects are uploaded immutably and releases are tags; `verify --deep` finds bytes that do not match their hashes ([ADR 0019][adr-0019]). |
| **Remote verification checks reachability and size, not content.** The read-back after an upload is an anonymous HEAD request. | Every download is hash-checked, and `verify --deep` hashes local files on request. |
| **A range of bounds with nothing configured needs the network whenever a handle reads the index.** Finding the newest admitted release reads the public `main` index, which is never cached, and GitHub's request limits apply. | A handle whose bundles hold every input reads no index ([ADR 0020][adr-0020]). Otherwise a configured catalogue avoids it, and so does an `exact_version`, whose tag is read once and kept in the metadata cache ([ADR 0018][adr-0018]). |
| **The store's copy of the latest public catalogue goes stale in a metadata cache.** Its URL names no moving ref, so a machine that read it once keeps that copy, although every release replaces it. | It is not a reader entry point: readers use the release tags or the served checkout. `ETHOS_CATALOG_NO_CACHE` turns the metadata cache off ([ADR 0027][adr-0027]). |
| **Repository bundles are limited.** A bundle holds one family, with files under 100 MiB, and needs explicit package-data inclusion. Nothing republishes a developer's edits. | Large data belongs in live tests ([ADR 0020][adr-0020]). |

### Catalogue maintenance and operations

| Risk | Mitigation |
|---|---|
| **A batch upload is not atomic.** Completed transfers stay when a later dataset fails. | The whole batch is checked before the first transfer, and a rerun finishes the job ([ADR 0023][adr-0023]). |
| **The purge gate is a recorded release.** A release made in a maintainer's clone and never pushed satisfies it. | Release with `--push` before purging. A stricter gate, a pushed release or one the served checkout has reached, would close the gap; the gate is an [open point](#open-points). |
| **The release pushes past review.** `catalog release --push` is the one direct push to the release branch on JuGit, so the maintainer who releases needs push rights to a branch that is otherwise changed only by merge request. A merge that lands between the release commit and the push makes the push fail. | The release runs in a clone at the merged state, and every other change goes by merge request. After a failed push, the release is rerun from the updated branch ([ADR 0026][adr-0026]). |
| **Releases and updates hash every build input again.** The `build --check` in `catalog release` and `catalog update-checkout` hashes the build input of every dataset that is not frozen, which ties both to the cluster while any dataset is only linked. | Freeze datasets with `catalog record`: a frozen dataset is checked against its recorded inventory, without a build input. |
| **What the specifications add is a warning.** A value of the wrong type or outside a closed vocabulary passes the build. | The build names each such value in a warning ([ADR 0006][adr-0006]). |
| **dCache's permissions are partly out of reach.** Under the root-owned "Simple" model only HIFIS support can change some permissions, and anonymous reads need world-readable folders. | `catalog check-store` probes what the account may do; maintainers take the rest to the storage operator. |
| **The OIDC login needs a browser.** Every write to dCache needs a token from a maintainer's oidc-agent session, so a CI job has no token of its own. | On a remote machine, forward the login's redirect port. Running the release in CI is a feature request (GitHub issue #34). |
| **Performance targets are not quantified.** | Measure with agreed workloads ([section 10.3](quality-requirements.md#103-measurement-boundaries)). |

## 11.2 Technical debt

| Debt | What holds it in check |
|---|---|
| `cli.py` is one module of about 2,000 lines, for `ethos-data` and the package commands together. | It parses, wires, prints and chooses exit statuses; the logic is in the services. |
| One import goes up a layer: `Collections.main()`, the package command a handle can run, imports the command line. | The layer test lists it as its one exception, and a second test fails once the exception is not needed ([ADR 0008][adr-0008]). |
| Data-access services import each other in cycles: `catalogs` ↔ `selection`, `catalogs` ↔ `retrieval`, `catalogs` ↔ `staging`, `access` → `bundles` → `retrieval` → `access`, `selection` ↔ `bundles`, and `config` ↔ `catalogs` through the catalogue resolver. | Lazy imports keep them from failing at import time. No rule orders the services within their group; the component views of [section 5](building-blocks.md) draw each dependency in its main direction. |
| Endpoints are written in code: the tracker URLs, the public release URL, and the store endpoints of the `check-store` script. | The tracker URLs and the release URL are written once, in `formats`. The script reads `ethos:store` from `catalog.yaml` when it runs inside a checkout. |
| No command writes the internal tracker's issue templates. | They are generated once with `handoffs.issue_template` and committed by hand; `publish` writes the public catalogue's ([ADR 0025][adr-0025]). |
| No CI runs the catalogue release. | A maintainer runs `catalog release` ([ADR 0027][adr-0027]); running it in CI is a feature request (GitHub issue #34). |
| Importing any module of the package runs the facade first, and the facade imports every data-access service, so the model cannot be loaded on its own. | `import ethos_data` loads neither catalogue maintenance nor pydantic, and the layer test checks every import statically ([ADR 0008][adr-0008]). |

## 11.3 Open points {#open-points}

These defaults are open for review. The chapters and decisions describe each
one as the target; another answer changes the decision named.

| Default under review | Decision |
|---|---|
| Releases are named `vYYYY.MM.N`, and a collections file bounds the releases it accepts with `min_version`, `max_version` or `exact_version`. | [ADR 0018][adr-0018] |
| A bundle version is exactly what one release holds: any change after a release, an added file included, starts the next version. | [ADR 0021][adr-0021] |
| Internal data is never uploaded: dCache holds public bytes and the latest public catalogue only. | [ADR 0011][adr-0011] |
| The offline handle: a handle whose bundles hold every input reads no catalogue index, so required package tests run with no network. | [ADR 0020][adr-0020] |
| The purge gate is a release recorded after the removal, not a pushed release or one the served checkout has reached. | [ADR 0023][adr-0023] |
| The store's copy of the latest public catalogue on dCache is not a reader entry point: readers use the release tags or the served checkout. | [ADR 0027][adr-0027] |

Smaller questions, each with the default these pages describe, are collected
on the project's [GitHub Discussions](https://github.com/FZJ-IEK3-VSA/ETHOS.Data/discussions).

[adr-0004]: decisions/0004-cache-paths-from-resource-identity.md
[adr-0006]: decisions/0006-every-file-format-specified-once.md
[adr-0008]: decisions/0008-four-layers.md
[adr-0011]: decisions/0011-access-class-picks-the-root.md
[adr-0018]: decisions/0018-numbered-catalogue-releases.md
[adr-0019]: decisions/0019-revisions-and-successors.md
[adr-0020]: decisions/0020-repository-bundles.md
[adr-0021]: decisions/0021-one-bundle-version-per-release.md
[adr-0023]: decisions/0023-maintenance-pipelines.md
[adr-0025]: decisions/0025-handoff-templates.md
[adr-0026]: decisions/0026-internal-catalogue-on-the-cluster.md
[adr-0027]: decisions/0027-public-catalogue-releases-on-github.md
[adr-0028]: decisions/0028-read-only-shared-cache.md
