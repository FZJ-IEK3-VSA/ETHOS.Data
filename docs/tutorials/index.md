# Tutorials

Follow these lessons from start to finish to learn by doing. Choose the role
that matches your task; one person may use all three paths. For a specific
operation, use the [how-to guides](../how-to/index.md).

## Data users

You use ETHOS.RESKit or another package and need its input data.

1. [Your first fetch](first-fetch.md): discover the package's collections,
   inspect the required files, fetch one collection, and use it from Python.
2. Continue with [Get data for a task](../how-to/get-data-for-a-task.md) to
   choose a workflow subset or all data declared by your package.

## Package maintainers

You integrate data into a library, examples, workflows, or tests.

1. [Use it from your own package](use-from-a-library.md): define collections,
   wrap the API, and choose a catalogue version for a package release.
2. [Develop and propose a dataset](develop-and-propose-data.md): create a small
   local dataset, use it through staging, and prepare a proposal without
   catalogue write access or upload credentials.
3. [Run a test with repository data](bundled-tests.md): export a local snapshot,
   test offline, and explicitly allow a temporary fixture edit.
4. [Run package tests in CI](../how-to/run-in-ci.md): choose required local
   tests and separate tests of live services.

## Catalogue maintainers

You review proposals, maintain the internal catalogue, upload data, and release
its generated public view.

1. [Add a dataset to the catalogue](add-a-dataset.md): accept a described
   dataset, build its inventory, upload and verify it, and publish the metadata.
2. Use [Accept a dataset proposal](../how-to/accept-a-dataset.md) as the
   checklist for the next real submission.

For the package's design and responsibilities, see
[Explanation](../explanation/index.md). For commands and settings, see
[API reference](../reference/api/index.md) and
[CLI reference](../reference/cli/ethos-data.md).


For existing cluster installations, continue with [Add internal and restricted datasets](../how-to/add-internal-and-restricted-data.md) and [Migrate cluster data](../how-to/migrate-cluster-data.md).
