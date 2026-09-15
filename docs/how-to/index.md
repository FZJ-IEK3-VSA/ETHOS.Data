# How-to guides

Each guide gets one task done. Choose a task within your current role: data
users obtain inputs; package maintainers integrate and propose them; catalogue
maintainers accept and release them. The same person can have more than one
role. If you are new to ETHOS.Data, the [tutorials](../tutorials/index.md)
teach the basics first.

<figure markdown="span">
  ![Three columns. Data user: set up the machine with a public and a restricted cache, fetch data, check data integrity. Package maintainer: select catalogued data with a collections file, stage uncatalogued data, propose a dataset, keep catalogued test data in the repository, use data in CI from dCache, from the repository copy, or both. Catalogue maintainer: accept a dataset proposal as public or restricted data, upload public data, add restricted data, publish the catalogue internally and publicly, link data already on disk into the cache, copy data that was linked. The package maintainer's collections file goes to the data user and their proposal goes to the catalogue maintainer. Every role reads from or writes to the shared catalogue and storage.](../assets/diagrams/usecases-overview-light.svg#only-light){ .diagram }
  ![Three columns. Data user: set up the machine with a public and a restricted cache, fetch data, check data integrity. Package maintainer: select catalogued data with a collections file, stage uncatalogued data, propose a dataset, keep catalogued test data in the repository, use data in CI from dCache, from the repository copy, or both. Catalogue maintainer: accept a dataset proposal as public or restricted data, upload public data, add restricted data, publish the catalogue internally and publicly, link data already on disk into the cache, copy data that was linked. The package maintainer's collections file goes to the data user and their proposal goes to the catalogue maintainer. Every role reads from or writes to the shared catalogue and storage.](../assets/diagrams/usecases-overview-dark.svg#only-dark){ .diagram }
  <figcaption>The three roles and their tasks. Package maintainers hand their
  collections file to data users and their proposals to catalogue
  maintainers.</figcaption>
</figure>

## Data users

You use ETHOS.RESKit or another package and need data for an example, workflow,
or analysis.

| Task | Guide |
|---|---|
| Configure public/internal catalogue access and both cache roots | [Set up your machine](set-up-your-machine.md) |
| Choose where the public and restricted caches are | [Configure the cache](configure-the-cache.md) |
| Use your copy of licensed data, or work without it | [Work with restricted data](restricted-data.md) |
| Also use datasets that are only in the internal catalogue | [Add the internal data catalogue](add-internal-catalogue.md) |
| Get the path of a file or folder in a script, or fetch a collection | [Get data for a task](get-data-for-a-task.md) |
| Read a catalogued dataset from a directory you already have | [Use data already on disk](use-data-already-on-disk.md) |
| Check integrity and repair downloads | [Verify and repair](verify-and-repair.md) |
| Identify failures and send a useful report to the right maintainer | [Identify and report a problem](report-a-problem.md) |
| Investigate missing data, catalogue versions, and unexpected paths | [Troubleshoot catalogue access](troubleshoot-catalogue.md) |

## Package maintainers

You maintain a package that consumes the catalogue. Developing or proposing
new data does not require permission to write to the official catalogue or dCache.

| Task | Guide |
|---|---|
| Ship and register your package's collections file | [Use ETHOS.Data in your package](use-from-a-package.md) |
| Declare data for examples, workflows, tests, or an aggregate collection | [Write a collections file](write-a-collections-file.md) |
| Experiment with new data in a development cache | [Stage uncatalogued data](stage-unpublished-data.md) |
| Prepare metadata, provenance, and byte access for review | [Propose a dataset](propose-a-dataset.md) |
| Keep an official test-data snapshot in the repository | [Keep test data in a repository](keep-test-data-in-a-repository.md) |
| Add regression inputs, reproduce data bugs, and refresh accepted fixtures | [Update test data](update-test-data.md) |
| Run required tests and live integration tests locally and in CI | [Run package tests in CI](run-in-ci.md) |
| Check a local copy against the accepted catalogue | [Verify and repair](verify-and-repair.md) |

## Catalogue maintainers

You accept proposals into the source catalogue and release a public metadata
view after the required data is available. These guides use `ethos-data catalog`.

| Task | Guide |
|---|---|
| Review a submission and coordinate its release | [Accept a dataset proposal](accept-a-dataset.md) |
| Write source metadata and control the inventory | [Describe a dataset](describe-a-dataset.md) |
| Configure a maintainer's storage credentials | [Set up dCache access](set-up-dcache-access.md) |
| Transfer and verify a selected set of datasets | [Upload a dataset](upload-a-dataset.md) |
| Create folders, rename unpublished data, or delete selected remote paths | [Manage dCache folders](manage-dcache-folders.md) |
| Register internal or licensed data without a public upload | [Add internal and restricted datasets](add-internal-and-restricted-data.md) |
| Generate and review the public metadata | [Publish the catalogue](publish-the-catalogue.md) |
| Deploy the internal filesystem catalogue and distribute public releases | [Catalogue hosting](catalogue-hosting.md) |
| Bridge data already on a shared machine into the cache as symlinks, without copying or uploading | [Link cluster data into the cache](link-cluster-data.md) |
| Turn those links into copies the cache owns, keeping the original as long as needed | [Move linked data into the cache](move-linked-data-into-the-cache.md) |
| Check generated output in CI | [Run catalogue checks in CI](catalogue-ci.md) |
| Unpublish or remove data | [Withdraw a dataset](withdraw-a-dataset.md) |
| Create the initial catalogue and storage setup | [Bootstrap a catalogue](bootstrap-a-catalogue.md) |
| Diagnose a reported catalogue or tool failure | [Troubleshoot catalogue access](troubleshoot-catalogue.md) |

For flags and file keys, see the [consumer CLI](../reference/cli/ethos-data.md),
[maintainer CLI](../reference/cli/catalog.md), and
[configuration reference](../reference/configuration.md).
