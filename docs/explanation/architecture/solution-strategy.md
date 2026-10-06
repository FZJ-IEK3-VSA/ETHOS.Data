# 4. Solution Strategy

This chapter answers which fundamental approaches meet the
[quality goals](introduction-and-goals.md#13-quality-goals) within the
[constraints](constraints.md). Each row links the decisions that set the
approach out, with the alternatives considered.

| Goal | Approach | Decisions |
|---|---|---|
| Reuse data across packages | One catalogue describes the data, and package-owned collections files select from it. Cache paths derive from resource identity. On the cluster, every user shares one public cache, so each public file is linked or downloaded there once. | [0003](decisions/0003-one-catalogue-many-collections.md), [0004](decisions/0004-cache-paths-from-resource-identity.md), [0028](decisions/0028-one-public-cache-on-the-cluster.md) |
| Keep large inventories cheap | The index is read first and inventories on demand, through one inventory reader. | [0005](decisions/0005-lazy-index-descriptors-and-shards.md), [0007](decisions/0007-one-inventory-reader.md) |
| Respect access conditions | The access class picks the root. One lookup chain decides where every file is read. Every input is required. Unresolved licensing blocks distribution. | [0011](decisions/0011-access-class-picks-the-root.md), [0012](decisions/0012-one-lookup-chain.md), [0013](decisions/0013-every-input-is-required.md), [0024](decisions/0024-licensing-gates-distribution.md) |
| Keep reader and writer compatible | Every file format is specified once. One inventory reader serves the user side and the maintainer side. Writer and reader ship in one distribution. | [0006](decisions/0006-every-file-format-specified-once.md), [0007](decisions/0007-one-inventory-reader.md) |
| Repeatable inputs | Catalogue releases are numbered `vMAJOR.MINOR.PATCH`, so the number says whether data or only metadata changed, and a collections file bounds the releases it accepts. Published objects never change: changed data becomes a revision or a successor, and data is purged only after a major release. Settings are read once into a snapshot. | [0018](decisions/0018-numbered-catalogue-releases.md), [0019](decisions/0019-revisions-and-successors.md), [0010](decisions/0010-one-settings-file-per-account.md) |
| Safe maintenance | Every catalogue workflow that writes is a pipeline that plans before it acts. Each dataset's state is a state machine recorded in its status file. | [0023](decisions/0023-maintenance-pipelines.md), [0022](decisions/0022-dataset-status-files.md) |
| Tests without dCache | A package's bundles are read before the caches and the download, and are authoritative for that package. A bundle ahead of the catalogue warns until it is realigned. | [0020](decisions/0020-repository-bundles.md), [0021](decisions/0021-bundles-ahead-of-the-catalogue.md), [0012](decisions/0012-one-lookup-chain.md) |
| Changeable code | Four layers, with two service groups. External systems sit behind ports with fakes. | [0008](decisions/0008-four-layers.md), [0009](decisions/0009-ports-and-fakes-for-external-systems.md) |
| Handoffs carry the facts | The command that knows the facts drafts each handoff from a template. | [0025](decisions/0025-handoff-templates.md) |
| A clean target | A clean break, with no compatibility fallbacks; `catalog migrate` converts the internal catalogue once. | [0002](decisions/0002-clean-break-during-the-beta.md) |
| Hosting | The cluster serves the internal catalogue at its latest release from one checkout, which only `catalog update-checkout` changes. Maintainers record in their own clones of the source catalogue and merge by merge request on JuGit, where each release is tagged. The public catalogue is a generated view, tagged on GitHub. | [0026](decisions/0026-internal-catalogue-on-the-cluster.md), [0027](decisions/0027-public-catalogue-releases-on-github.md) |

[Section 8](crosscutting-concepts.md) states the rules these approaches share,
and [section 9](decisions/index.md) lists every decision.
