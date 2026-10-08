# Keep data in the repository

Keep the data your package's required tests and examples read in its
repository, as a **bundle**, so they run offline and the data stays properly
attributed. A bundle holds the files of a selection of catalogue datasets,
whole datasets or some of their files, with each dataset's description,
licence documents and attribution. Work with it at once, ahead of the
catalogue if need be, realign it with the catalogue soon after, and export it
to another repository with similar data requirements. A package may ship
several bundles, for example `test_data` beside the collections file and
`wind/core/data` beside the code that reads it.

The package reads what its bundle holds, even where the bundle is ahead of
the catalogue, and you are warned to realign it soon
([0020](../../explanation/architecture/decisions/0020-repository-bundles.md)).
A bundle's files change the way every file in a repository changes, by commit
and pull.

A bundle directory holds:

| Path | Content |
| --- | --- |
| `bundle.json` | For each dataset: its alignment with the catalogue, whether it holds every file or a selection, the changes recorded since the alignment, and every file's size and SHA-256, the descriptions and licence documents included |
| `data/<dataset>/<path>` | The bytes; a member of a family is `<family>/<member>` |
| `datasets/<dataset>/` | The dataset's description, `dataset.yaml`, with the licence documents it names; a family's description lies under `datasets/<family>/` |

A dataset's alignment is the catalogue revision it was last aligned with, none
for a dataset the catalogue does not describe yet, and the release it was
taken from, which is only shown.

The descriptions stay next to the data because a repository redistributes it,
and several datasets require attribution when redistributed. For the same
reason a bundle holds only public, visible data with settled licensing;
anything else is refused with `BundleError`, naming the dataset and what is
missing.

Develop data whose licensing is unsettled in
[staging](stage-development-data.md). Licensed fixtures belong in restricted
CI, not in a bundle; see
[Run tests and examples in CI](run-in-ci.md#3-download-public-data-the-repository-does-not-hold).

## 1. Create a bundle

Put each dataset's files under `data/<dataset>/`, the members of a family
under `data/<family>/<member>/`, then let the tool inventory them:

```bash
mkdir -p your_tool/data/test_data/data/your-tool-test-data/era5
cp /scratch/me/era5-cut/*.nc your_tool/data/test_data/data/your-tool-test-data/era5/
<your-tool>-data bundle create your_tool/data/test_data --family your-tool-test-data
```

`bundle create` hashes every file, writes `bundle.json` and drafts a
`dataset.yaml` for each new dataset; `--family NAME` drafts the members of one
family. Fill the drafts in, origin, sources, licence, attribution, and put the
licence documents beside them, as for any
[proposal](propose-a-dataset.md#3-draft-the-description): a bundle whose
licensing is not settled is refused when it is read. The new datasets are
ahead of the catalogue until the catalogue accepts them. Commit the whole
directory. Keep every bundle small: Git hosts refuse files over 100 MiB, and
every revision of a fixture stays in the history.

## 2. Work with it {#use-a-bundle}

List the bundle in the package's data module (see
[Use ETHOS.Data in your package](use-from-a-package.md#3-build-the-handle-and-the-command)):

```python
BUNDLES = (Path(__file__).with_name("test_data"),)
```

`paths()`, `fetch()` and `catalog_path()` then answer from whichever bundle
holds what was asked for, hash-checked against `bundle.json` once per
process, and go to the catalogue only for what no bundle holds. A handle whose
bundles hold every input reads no catalogue index, so the required tests run
offline. A bundled file that is missing, or changed without `bundle update`
recording it, raises `BundleError`; it is never downloaded instead.

A bundle is ahead of the catalogue when it holds changes that `bundle update`
recorded, or a dataset the catalogue does not describe. It is read all the
same, so development never waits for the catalogue. Every process that reads
one of its datasets warns once per bundle, offline included, so your required
tests show it, and your package's users see it too:

```text
warning: bundle your_tool/data/test_data is ahead of the catalogue:
your-tool-test-data/era5 (2 files changed), your-tool-test-data/placements (not in the catalogue).
Realign it soon: <your-tool>-data propose your_tool/data/test_data, or take the catalogue's version:
<your-tool>-data bundle update your_tool/data/test_data --from-catalog your-tool-test-data/era5
```

Where the handle reads the catalogue index anyway, for a dataset no bundle
holds or with the download switch, it also compares each bundled dataset's
recorded revision with the catalogue's. A later revision there means the
bundle is behind, and it warns the same way. A bundled dataset the catalogue
has withdrawn is named too: drop it from the bundle, or switch to its
successor. `bundle verify` and `bundle update` compare the files, descriptions
and licence documents with the catalogue, so they also find a description the
catalogue corrected in a patch release.

The warning has its own category, exported from `ethos_data`, so a package can
filter it. [Run tests and examples in CI](run-in-ci.md#download-switch) shows
how to keep it a warning when tests turn warnings into errors.

To read through the catalogue route instead, for example to test the
download, pass `download=True` or set `ETHOS_DATA_DOWNLOAD=1`. A bundled file
whose recorded SHA-256 the catalogue holds for the same key is then read from
the public cache, or downloaded into it; every other bundled file is still
read from the bundle, with the warning. The switch changes where a file is
read from, never which bytes, and a bundle's own bytes never enter a cache.

## 3. Change it {#update-data}

Edit the files as you edit anything in the repository, then record the
change:

```bash
<your-tool>-data bundle update your_tool/data/test_data
```

`bundle update` records every changed, added and removed file, the
descriptions and licence documents included, and every new dataset. The
bundle is then ahead of the catalogue: it is read as recorded, with the
warning, until you realign it. A change that `bundle update` has not recorded
is refused when it is read.

To reproduce a bug with a temporarily edited file, record nothing: read it
with `load_bundle(DIR).fetch(…, allow_modified=True)` in the affected test
only. That read warns with the changed keys and keeps the recorded hashes;
nothing repairs, republishes or updates dCache, and `bundle verify` reports
the file as `modified` until it is restored.

## 4. Realign it with the catalogue {#sync}

Realign a bundle soon after it is ahead, in one of two ways.

**The catalogue takes the bundle's version.** It goes in five steps, the
first and last yours, the others the catalogue maintainer's.

1. Record your changes with the catalogue readable, and check that every
   dataset you changed is ahead:

    ```bash
    <your-tool>-data bundle update your_tool/data/test_data
    <your-tool>-data bundle verify your_tool/data/test_data
    ```

    `bundle update` compares each dataset's files, description and licence
    documents with the catalogue, every key of the description included. A
    dataset the catalogue holds as the bundle does is `aligned`, and its
    recorded changes are cleared. Every other changed dataset is listed as
    `ahead`, with what changed. Only these are taken in: a dataset listed as
    `aligned` is not, even when it is named. Commit `bundle.json` with the
    change.

2. Draft the proposal for the datasets that are ahead and submit it as under
   [Propose a dataset](propose-a-dataset.md#4-submit):

    ```bash
    <your-tool>-data propose your_tool/data/test_data
    ```

    The bundle's `datasets/` holds the descriptions and licence documents and
    its `data/` the bytes, which is everything the catalogue maintainer needs.

3. The catalogue maintainer takes the ahead datasets in, in a clone on the
   machine that uploads:

    ```bash
    ethos-data catalog add-bundle /path/to/checkout/your_tool/data/test_data --dry-run
    ethos-data catalog add-bundle /path/to/checkout/your_tool/data/test_data
    ethos-data catalog status your-tool-test-data
    ```

    `add-bundle` takes new datasets, revisions of changed ones and changed
    descriptions. It copies the files of new and revised datasets into
    `build-inputs/` in the clone, a folder that ignores itself in git, so the
    catalogue never reads your checkout. It takes a revision only while the
    catalogue is still at the bundle's alignment. A changed description needs
    no copy: the dataset is built again with it, and a frozen one stays
    frozen.

4. The maintainer makes what was taken in available, and freezes it, by
   naming the bundle's family:

    ```bash
    ethos-data catalog upload your-tool-test-data --dry-run
    ethos-data catalog upload your-tool-test-data
    ethos-data catalog record your-tool-test-data
    ```

    Both pass over the members frozen already, so only new and revised
    datasets are uploaded and frozen. A member whose description alone changed
    stays frozen and needs neither.

    A revision's changed and new files go to dCache under
    `<remote_prefix>@<revision>/`, and its unchanged files stay where they
    are. `record` makes the upload the authoritative copy and deletes the
    build input from `build-inputs/`. The maintainer then commits, merges and
    [releases](../catalogue-maintainers/release-the-catalogue.md) the
    catalogue.

5. Once the release is out, raise `catalog.min_version` in your collections
   file and run `bundle update` with the catalogue readable. It lists each
   dataset taken in as `aligned`, with the catalogue's revision, and the
   warning stops. `bundle verify` then exits 0. A dataset it names as
   differing from the catalogue was not taken in as the bundle holds it:
   find out why before you take the catalogue's version.

**The bundle takes the catalogue's version.** To drop your changes to a
dataset, or to catch up with a later revision, take what the catalogue holds:

```bash
<your-tool>-data bundle update your_tool/data/test_data --from-catalog your-tool-test-data/era5
```

It takes the catalogue's files of the bundled selection, with the description
and licence documents, and records the alignment.

A later change makes the bundle ahead again and goes the same way.

## 5. Export it to another repository

`bundle export` writes a new bundle of what your package reads for some of
its collections, into a new directory in this or another repository, for
example to give another tool's tests the data yours already use:

```bash
<your-tool>-data bundle export ../other-tool/other_tool/data/test_data my_workflow --test
```

Export reads through your package's handle: its bundles first, then the
caches and the download, never staging. `--test` selects the test variants.
Each dataset keeps its description, licence documents and alignment. Export
checks every file's size and SHA-256 as it copies, and downloads from the
publication URL your settings give, like every other download. The target
must not exist. To export from a copy already on the machine, make it a cache
entry first, with
[`ethos-data link NAME DIR`](../../reference/cli/ethos-data.md#link-dataset-directory)
or `ethos-data materialize NAME --from DIR`.

Read `datasets/` in the new bundle before committing it: it states the terms
under which that repository redistributes the files. The other package lists
the bundle in its `bundles=`, like any bundle.

See [Run tests and examples in CI](run-in-ci.md) for the CI wiring and the
[bundle reference](../../reference/cli/package-data.md#bundle) for the
options the code has.
