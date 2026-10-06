# 9. Architectural Decisions

Which decisions shape the architecture of ETHOS.Data, and why? Each one that
is important, costly or hard to reverse has a file of its own, listed below.

Every decision file has the same parts: the context, which names the forces
that shape the problem; the decision, as the target architecture has it; the
alternatives considered and why they were not chosen; the consequences for
users, maintainers and the code; and the related decisions and sections. Its
status line says whether the code on develop does what the Decision section
says. A decision is `proposed` until it does, and the last pull request in its
"Implemented by" list marks it `implemented`. A decision that also needs an
event outside the code, such as a first release, names that event there. A
dash means that the decision is implemented and needs no pull request.

| No. | Decision | Status | Implemented by |
|---|---|---|---|
| | **Process** | | |
| 0001 | [Describe the target architecture in arc42, with C4 views and one file per decision](0001-arc42-c4-one-file-per-decision.md) | implemented | #36 |
| 0002 | [Make a clean break during the beta; `catalog migrate` converts the internal catalogue once](0002-clean-break-during-the-beta.md) | proposed | #10–#27, #21 (`catalog migrate`); implemented once `catalog migrate` is removed |
| | **Data and identity** | | |
| 0003 | [One catalogue describes the data; each package's collections file selects from it](0003-one-catalogue-many-collections.md) | implemented | — |
| 0004 | [Derive cache paths from resource identity, and never reuse a name](0004-cache-paths-from-resource-identity.md) | implemented | — |
| 0005 | [Read the index first and inventories on demand](0005-lazy-index-descriptors-and-shards.md) | implemented | — |
| 0006 | [Specify every file format once](0006-every-file-format-specified-once.md) | proposed | #11, #12, #13, #27 |
| 0007 | [Read every generated catalogue through one inventory reader](0007-one-inventory-reader.md) | proposed | a new PR (inventory reader) |
| | **Code structure** | | |
| 0008 | [Build the package in four layers: model, adapters, services, presentation](0008-four-layers.md) | proposed | #10, #13, #17, #20, a new PR (service groups) |
| 0009 | [Reach dCache, downloads, metadata sources and git through ports with fakes](0009-ports-and-fakes-for-external-systems.md) | proposed | #20, a new PR (inventory reader), #23 |
| | **Reading data** | | |
| 0010 | [Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md) | proposed | #14, #15, #39, #19, a new PR (inventory reader), #25 |
| 0011 | [Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md) | proposed | #15, #39, a new PR (pipelines) |
| 0012 | [Find every file through one lookup chain](0012-one-lookup-chain.md) | proposed | #15, #39, #16, #24, #25 |
| 0013 | [Treat every input as required, and say what is missing](0013-every-input-is-required.md) | implemented | #16, #18 |
| 0014 | [Name workflow inputs in the collection and pair test and full variants](0014-named-inputs-and-test-full-variants.md) | implemented | — |
| 0015 | [Let each package's data command own its collection workflows](0015-package-commands-own-collections.md) | implemented | — |
| 0016 | [Give one link command two modes](0016-one-link-command-two-modes.md) | implemented | #39 |
| 0017 | [Ship a self-test collection with the package](0017-self-test-collection.md) | implemented | #18 |
| | **Versions** | | |
| 0018 | [Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them](0018-numbered-catalogue-releases.md) | proposed | #19, #23 |
| 0019 | [Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md) | proposed | #24, #25 |
| 0020 | [Keep attributed data in bundles that are authoritative for their package](0020-repository-bundles.md) | proposed | #25 |
| 0021 | [Let a bundle be ahead of the catalogue, and warn until it is realigned](0021-bundles-ahead-of-the-catalogue.md) | proposed | #25 |
| | **Maintaining the catalogue** | | |
| 0022 | [Record each dataset's state in a status file](0022-dataset-status-files.md) | proposed | #21, #22, #23 |
| 0023 | [Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md) | proposed | #20, #22, a new PR (pipelines), #23, #26 |
| 0024 | [Let unresolved licensing block distribution, not development](0024-licensing-gates-distribution.md) | proposed | #21, #25 |
| 0025 | [Draft the handoffs between roles from templates](0025-handoff-templates.md) | proposed | #26 |
| | **Deployment** | | |
| 0026 | [Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md) | proposed | #23; implemented once the first versioned release is served |
| 0027 | [Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md) | proposed | #12, #19, #23, #26; implemented with the first versioned release |
| 0028 | [Share one public cache on the cluster](0028-one-public-cache-on-the-cluster.md) | implemented | #39 |
