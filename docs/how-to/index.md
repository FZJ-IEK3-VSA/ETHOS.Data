# How-to guides

Choose a task within your current role. Data users obtain inputs; package
maintainers integrate and propose them; catalogue maintainers accept and
release them. The same person can have more than one role. For a guided first
experience, start with the [tutorials](../tutorials/index.md).

<figure markdown="span">
  ![Tasks grouped by data users, package maintainers, and catalogue maintainers](../assets/diagrams/usecases-overview-light.svg#only-light){ .diagram }
  ![Tasks grouped by data users, package maintainers, and catalogue maintainers](../assets/diagrams/usecases-overview-dark.svg#only-dark){ .diagram }
  <figcaption>The three roles and their tasks, including the proposal handoff
  from package maintenance to catalogue maintenance.</figcaption>
</figure>

## Data users

You use ETHOS.RESKit or another package and need data for an example, workflow,
or analysis.

| Task | Guide |
|---|---|
| Discover collections and fetch a task subset or all package inputs | [Get data for a task](get-data-for-a-task.md) |
| Choose a cache directory or use a shared cluster cache | [Configure the cache](configure-the-cache.md) |
| Read a catalogued dataset from an existing local directory | [Use data already on disk](use-data-already-on-disk.md) |
| Set up licensed data or run an explicitly optional workflow without it | [Work with restricted data](restricted-data.md) |
| Check integrity, repair downloads, or replace a borrowed symlink | [Verify and repair](verify-and-repair.md) |
| Investigate missing data, catalogue versions, and unexpected paths | [Troubleshoot catalogue access](troubleshoot-catalogue.md) |

## Package maintainers

You maintain a package that consumes the catalogue. Developing or proposing
new data does not require permission to write to the official catalogue or dCache.

| Task | Guide |
|---|---|
| Declare data for examples, workflows, tests, or an aggregate collection | [Write a collections file](write-a-collections-file.md) |
| Wire the API into the package | [Use it from your own package](../tutorials/use-from-a-library.md) |
| Experiment with new data in a development cache | [Stage unpublished data](stage-unpublished-data.md) |
| Prepare metadata, provenance, and byte access for review | [Propose a dataset](propose-a-dataset.md) |
| Keep an official test-data snapshot in the repository and allow temporary local edits | [Keep test data in a repository](keep-test-data-in-a-repository.md) |
| Run required tests and live integration tests locally and in CI | [Run package tests in CI](run-in-ci.md) |
| Check a local copy against the accepted catalogue | [Verify and repair](verify-and-repair.md) |

Start with [Develop and propose a dataset](../tutorials/develop-and-propose-data.md)
for a small local example. The handoff to the next role is a reviewed proposal,
not an upload by the package maintainer.

## Catalogue maintainers

You accept proposals into the source catalogue and release a public metadata
view after the required data is available. These guides use `ethos-data catalog`.

| Task | Guide |
|---|---|
| Review a submission and coordinate its release | [Accept a dataset proposal](accept-a-dataset.md) |
| Write source metadata and control the inventory | [Describe a dataset](describe-a-dataset.md) |
| Transfer and verify a selected set of datasets | [Upload a dataset](upload-a-dataset.md) |
| Generate and review the public metadata | [Publish the catalogue](publish-the-catalogue.md) |
| Deploy the internal filesystem catalogue and distribute public releases | [Catalogue hosting](catalogue-hosting.md) |
| Register internal or licensed data without a public upload | [Add internal and restricted datasets](add-internal-and-restricted-data.md) |
| Bridge old cluster storage with symlinks, then make independent copies | [Migrate cluster data](migrate-cluster-data.md) |
| Check generated output in CI | [Run catalogue checks in CI](catalogue-ci.md) |
| Unpublish or remove data | [Withdraw a dataset](withdraw-a-dataset.md) |
| Create the initial catalogue and storage setup | [Bootstrap a catalogue](bootstrap-a-catalogue.md) |
| Diagnose a reported catalogue or tool failure | [Troubleshoot catalogue access](troubleshoot-catalogue.md) |

For implementation responsibilities and failure boundaries, see
[Architecture](../explanation/architecture/index.md). For flags and file keys,
see the [consumer CLI](../reference/cli/ethos-data.md),
[maintainer CLI](../reference/cli/catalog.md), and
[configuration reference](../reference/configuration.md).
