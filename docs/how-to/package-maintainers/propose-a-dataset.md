# Propose a dataset

Hand a new or changed dataset to the catalogue maintainer so it can be
accepted, published where its terms allow, and used by your package. The
dataset may be something you downloaded or something you created. You need no
catalogue write access and no dCache credentials.

Data that lives in your repository as a [bundle](keep-data-in-the-repository.md)
is proposed the same way. The bundle already carries a description for each
of its datasets, and the maintainer takes in what is ahead of the catalogue:
new datasets, revisions and changed descriptions.

## 1. Decide what kind of change it is

| Situation | Propose |
| --- | --- |
| Data the catalogue does not have | A new dataset with its own name |
| A changed version of a catalogued dataset, for example test data for a changed function | A revision of the dataset: its keys stay, changed files are published beside the old ones, and unchanged files are not downloaded again. A changed layout is a successor, a new dataset whose `dataset.yaml` names the one it replaces with `ethos:supersedes`. See [Publish a new version](../catalogue-maintainers/publish-a-new-version.md). |
| More files for an existing dataset, unchanged otherwise | An addition to the existing dataset |
| A tiny synthetic fixture your package owns | Nothing: keep it in the package |

If the change is only in code, say so; a bug fix does not need new data.

## 2. Put the bytes where the reviewer can read them, and stop changing them

The relative paths inside the directory become the resource keys, so keep the
layout the workflow expects.

=== "Downloaded"

    Put the files as obtained from the source, unpacked but otherwise
    unchanged, into one directory. Keep the download URL and the date; both
    go into the description.

=== "Created or derived"

    Put the output of your script into one directory and keep the script,
    its version and its parameters: they go into the description as
    `ethos:derivation`, and the reviewer may rerun it. Data derived from a
    licensed product inherits that product's terms, so name the inputs.

Then stop changing the files. There is no command for this; make the
directory read-only so nothing can be edited by accident:

```bash
chmod -R a-w /projects/shared/candidates/my-dataset
```

Every edit after the inventory was built invalidates its checksums; if you do
change something, say so and the reviewer rebuilds.

Where the directory lives depends on your installation. On the ICE-2 cluster
computer, a project directory the maintainer can read is enough; say how long
it stays. From a public installation, attach an archive to the proposal or
give a download link, and keep the directory until acceptance.

## 3. Draft the description

Write a `dataset.yaml` beside the data if you can; otherwise supply the same
facts in the proposal. Which facts depend on where the data came from.

=== "Downloaded"

    ```yaml
    name: global-wind-atlas-v4
    title: Global Wind Atlas 4.0 mean wind speed
    description: What it contains and which release.
    source_dir: /projects/shared/candidates/global-wind-atlas-v4
    ethos:access: public
    ethos:visibility: public
    ethos:origin: downloaded
    sources:
      - title: Global Wind Atlas 4.0
        path: https://globalwindatlas.info/
    licenses:
      - name: CC-BY-4.0
        path: https://creativecommons.org/licenses/by/4.0/
    ethos:retrieved: "2026-09-01"
    ethos:attribution: The attribution text the source requires.
    ethos:contact: Your name
    ```

    Record the download URL, the retrieval date and the licence as published
    by the source. The maintainer will [verify the provenance](../catalogue-maintainers/verify-provenance.md)
    against that source.

=== "Created or derived"

    ```yaml
    name: your-tool-test-data/era5
    title: ERA5 fixtures for the test suite of your_tool
    description: Spatial and temporal subsets, resampled; for tests only.
    source_dir: /projects/shared/candidates/era5-fixtures
    ethos:access: public
    ethos:visibility: public
    ethos:origin: derived
    contributors:
      - title: Your name
        roles: [author]
    sources:
      - title: ERA5 hourly data on single levels
        path: https://doi.org/10.24381/cds.adbb2d47
    ethos:derivation: scripts/cut_era5.py at your_tool commit abc1234, bbox 5-7E 50-52N
    licenses:
      - name: CC-BY-4.0
        path: https://creativecommons.org/licenses/by/4.0/
    ethos:attribution: Contains modified Copernicus Climate Change Service information 2026.
    ethos:contact: Your name
    ```

    `created` is data made from scratch here; `derived` is computed from other
    data and inherits that data's obligations, so name the inputs and the
    method. Test data cut from a licensed product is derived data under that
    product's terms.

If the terms are unclear, write `ethos:license_status: unresolved` and the
question in `ethos:license_note`; do not guess a licence. Data that may not be
redistributed, or that the institute holds without publishing it, is
`ethos:access: restricted` and is never uploaded; see
[Add restricted data](../catalogue-maintainers/add-restricted-data.md). The
full key list is in [Add a dataset](../catalogue-maintainers/add-a-dataset.md#write-the-description)
and the [format reference](../../reference/schemas.md#datasetyaml).

## 4. Submit

Let the package's data command check the candidate and draft the proposal:

```bash
<your-tool>-data propose /projects/shared/candidates/my-dataset
<your-tool>-data propose your_tool/data/test_data
```

It takes the directory holding the draft `dataset.yaml`, or a bundle. It
checks the draft as the catalogue's build would and refuses one the build
would refuse, inventories the bytes, warns when files are still writable, and
prints the proposal with the items below filled in as far as the tools know
them, the collections of your package that already name the dataset among
them. Add what only you know, the validation you ran and how long the bytes
stay, and open an issue with it at:

- <https://jugit.fz-juelich.de/iek-3/shared-code/ethos-data-catalog-internal>
  from a cluster installation, or for restricted data;
- <https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/issues> from a public
  installation, for public data.

| Item | Content |
| --- | --- |
| Identity and purpose | Name, version, title, the workflows that use it, new dataset or revision |
| Description | The draft `dataset.yaml`, or the bundle directory that holds it |
| Bytes | The readable directory, archive or link, and how long it stays |
| Validation | The tests or examples you ran against it, staged or bundled, and their result |
| Collection | The `collections.yaml` entry your package will use |

## 5. After acceptance

The maintainer replies with the accepted dataset name and the catalogue
release that contains it.

1. Raise `catalog.min_version` in `collections.yaml` to that release and add
   or update the collection.
2. Remove the [staging entry](stage-development-data.md#4-remove-it) used
   during development.
3. Fetch and run the affected workflow against the released catalogue and
   check that no staging warning remains.
4. If the data lives in your repository as a bundle, run
   [`bundle update`](keep-data-in-the-repository.md#sync) with the catalogue
   readable: it records the new alignment, and the warning stops.
5. Commit the collections file, the bundle and the tests together.

Continue with [Run tests and examples in CI](run-in-ci.md).
