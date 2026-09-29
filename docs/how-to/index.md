# How-to guides

Each guide gets one task done. The guides are grouped by role, and one person
often holds more than one role. For guided practice on local data, start with
the [tutorials](../tutorials/index.md).

Two kinds of installation run through every guide. A **cluster installation**
is an account on the ICE-2 cluster computer: it reads the internal catalogue
and the shared public and restricted caches. A **public installation** is
everything else, a laptop, a workstation or a CI runner, whoever owns it: it
reads the public catalogue and its own cache, and reaches no restricted data.
The locations on the cluster computer are on the ICE-2 wiki and never in
these pages; the guides use clearly marked example paths instead.

Every package built on ETHOS.Data ships the same data command under its own
name. The guides write it as `<your-tool>-data` and the matching Python module
as `your_tool.data`; the package's own documentation names its collections and
handles.

Where a guide describes behaviour the current release does not have yet, a
box marked **Gap** says so. Those boxes are the input to the architecture
review; grep the documentation for `Gap:` to list them.

## Data users

You run ETHOS workflows, examples and tests and need their input data.

| Task | Guide |
| --- | --- |
| Point your account at the right catalogue and caches, on a public or a cluster installation | [Set up your machine](data-users/set-up-your-machine.md) |
| Get the inputs of a workflow in a Python script, fetching them or only resolving their paths, and see how much a fetch downloads | [Use data in a script](data-users/use-data-in-a-script.md) |
| Check the files on disk against the catalogue and repair downloads | [Check and repair the cache](data-users/verify-and-repair.md) |
| Report a dataset that cannot be downloaded or found | [Report a problem](data-users/report-a-problem.md) |

For the concrete collections and commands of one package, see that package's
documentation, for example
[RESKit's input-data guide](https://ethos-reskit.readthedocs.io/en/latest/how_to/get_input_data.html).

## Package maintainers

You wire data into a package: its workflows, examples and tests.

| Task | Guide |
| --- | --- |
| Ship a collections file, a Python handle and a `<your-tool>-data` command | [Use ETHOS.Data in your package](package-maintainers/use-from-a-package.md) |
| Select catalogue data for your workflows, name their inputs, pair test and full data, bound the catalogue version | [Write a collections file](package-maintainers/write-a-collections-file.md) |
| Work with data that is not catalogued yet | [Stage development data](package-maintainers/stage-development-data.md) |
| Hand a new or changed dataset, downloaded or self-created, to the catalogue maintainer | [Propose a dataset](package-maintainers/propose-a-dataset.md) |
| Create test data in the repository as a bundle, work with it, and have the catalogue updated from it version by version | [Keep data in the repository](package-maintainers/keep-data-in-the-repository.md) |
| Run tests and examples in CI, from the repository copy or from the catalogue | [Run tests and examples in CI](package-maintainers/run-in-ci.md) |

## Catalogue maintainers

You look after the catalogue, the shared caches on the cluster computer and
the published bytes on dCache.

Setup, done once:

| Task | Guide |
| --- | --- |
| Get credentials and an rclone remote for dCache | [Set up dCache access](catalogue-maintainers/set-up-dcache-access.md) |
| Create the catalogue checkout and the shared caches on the cluster computer | [Set up the shared machine](catalogue-maintainers/set-up-the-shared-machine.md) |
| Create a source catalogue, its public counterpart and the publication root | [Bootstrap a catalogue](catalogue-maintainers/bootstrap-a-catalogue.md) |

Regular tasks:

| Task | Guide |
| --- | --- |
| Review a `dataset.yaml`, provided or self-written, put it into the catalogue and build | [Add a dataset](catalogue-maintainers/add-a-dataset.md) |
| Check that a downloaded dataset still matches its original source | [Verify provenance](catalogue-maintainers/verify-provenance.md) |
| Put public bytes on dCache and verify them | [Upload a public dataset](catalogue-maintainers/upload-a-dataset.md) |
| Make data that cannot move yet available through the public cache | [Link existing data into the cache](catalogue-maintainers/link-existing-data.md) |
| Turn a linked dataset into a verified copy the cache owns | [Materialize linked data](catalogue-maintainers/materialize-linked-data.md) |
| Register or move a licensed dataset in the restricted cache | [Add restricted data](catalogue-maintainers/add-restricted-data.md) |
| Remove a dataset that should not have been added, from the catalogue and from dCache | [Remove a dataset](catalogue-maintainers/withdraw-a-dataset.md) |
| Build, check and release the internal and the public catalogue | [Release the catalogue](catalogue-maintainers/release-the-catalogue.md) |
| Create, rename and delete folders on dCache | [Manage dCache folders](catalogue-maintainers/manage-dcache-folders.md) |
| Trace a user's report through metadata, files and storage | [Diagnose a report](catalogue-maintainers/diagnose-a-report.md) |

For options, see the [ethos-data CLI](../reference/cli/ethos-data.md),
[package data commands](../reference/cli/package-data.md),
[catalogue CLI](../reference/cli/catalog.md) and
[configuration reference](../reference/configuration.md).
