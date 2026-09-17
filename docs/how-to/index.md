# How-to guides

Choose the task you need. Package workflows use the consuming package's API or
data command; ethos-data handles shared configuration, direct catalogue access
and maintenance. For guided practice, start with the [tutorials](../tutorials/index.md).

## Data users

| Task | Guide |
| --- | --- |
| Select metadata and public/restricted caches; use temporary settings | [Set up your machine](data-users/set-up-your-machine.md) |
| Browse and retrieve files, folders or datasets | [Get data by catalogue key](data-users/get-data-for-a-task.md) |
| Check a package's selected inputs and repair downloads | [Verify and repair](data-users/verify-and-repair.md) |
| Diagnose a failure and prepare a useful report | [Troubleshoot catalogue access](data-users/troubleshoot-catalogue.md) |

For RESKit workflow inputs, use
[RESKit's input-data guide](https://ethos-reskit.readthedocs.io/en/latest/how_to/get_input_data.html).

## Package maintainers

| Task | Guide |
| --- | --- |
| Ship a collections file, Python handle and thin CLI wrapper | [Use ETHOS.Data in your package](package-maintainers/use-from-a-package.md) |
| Declare selections, pins, test/full variants and named inputs | [Write a collections file](package-maintainers/write-a-collections-file.md) |
| Stage a candidate, test it and submit it for review | [Develop and propose a dataset](package-maintainers/propose-a-dataset.md) |
| Export, edit deliberately, verify and refresh fixtures | [Keep test data in a repository](package-maintainers/keep-test-data-in-a-repository.md) |
| Separate required local tests from live integrations | [Run package tests in CI](package-maintainers/run-in-ci.md) |

## Catalogue and cache maintainers

| Task | Guide |
| --- | --- |
| Review a proposal and coordinate its release | [Accept a dataset](catalogue-maintainers/accept-a-dataset.md) |
| Describe public, internal and restricted inventories | [Describe a dataset](catalogue-maintainers/describe-a-dataset.md) |
| Use a local override, link/unlink, or materialize files | [Manage local dataset copies](catalogue-maintainers/link-cluster-data.md) |
| Configure storage credentials | [Set up dCache access](catalogue-maintainers/set-up-dcache-access.md) |
| Transfer and verify selected datasets | [Upload a dataset](catalogue-maintainers/upload-a-dataset.md) |
| Administer unpublished storage paths | [Manage dCache folders](catalogue-maintainers/manage-dcache-folders.md) |
| Generate and review public metadata | [Publish the catalogue](catalogue-maintainers/publish-the-catalogue.md) |
| Deploy internal metadata and release public revisions | [Catalogue hosting](catalogue-maintainers/catalogue-hosting.md) |
| Check generated output in CI | [Catalogue CI](catalogue-maintainers/catalogue-ci.md) |
| Unpublish or remove data | [Withdraw a dataset](catalogue-maintainers/withdraw-a-dataset.md) |
| Create the initial repositories and storage root | [Bootstrap a catalogue](catalogue-maintainers/bootstrap-a-catalogue.md) |

For options, see the [ethos-data CLI](../reference/cli/ethos-data.md),
[package data commands](../reference/cli/package-data.md),
[catalogue CLI](../reference/cli/catalog.md) and
[configuration reference](../reference/configuration.md).
