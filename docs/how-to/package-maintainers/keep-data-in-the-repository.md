# Keep data in the repository

Create test data inside your package's repository as a **bundle**, work with
it at once, and have the catalogue updated from it, version by version. A
bundle is one dataset family with sub-datasets, laid out like
`your-tool-test-data/era5`, `your-tool-test-data/placements`, that lives in
the repository so tests run offline and small inputs the software cannot do
without never depend on a download. A package may ship several bundles, for
example `test_data` beside the collections file and `wind/core/data` beside
the code that reads it.

The repository is the source of truth for a bundle. Its files change the way
every file in a repository changes, by commit and pull; the catalogue holds
published versions of the bundle and is updated from the repository, never
the other way round.

A bundle directory holds:

| Path | Content |
| --- | --- |
| `bundle.json` | The family name, the bundle version, every file with size and SHA-256, and the catalogue release the version is published in, if any |
| `data/<family>/<member>/<path>` | The bytes |
| `datasets/<family>/<member>/dataset.yaml` | One description per sub-dataset, with the licence documents it names beside it |

The metadata stays next to the data because a repository redistributes it,
and several datasets require attribution when redistributed.

## 1. Create a bundle

Put the files under `data/<family>/<member>/`, then let the tool inventory
them:

```bash
mkdir -p your_tool/data/test_data/data/your-tool-test-data/era5
cp /scratch/me/era5-cut/*.nc your_tool/data/test_data/data/your-tool-test-data/era5/
<your-tool>-data bundle create your_tool/data/test_data --family your-tool-test-data
```

`bundle create` hashes every file, writes `bundle.json` as version 1, not yet
published, and drafts a `dataset.yaml` per member with its name and
`source_dir`. Fill the drafts in, origin, sources, licence, attribution, and
put the licence documents beside them, as for any
[proposal](propose-a-dataset.md#3-draft-the-description). Commit the whole
directory. Keep every bundle small: Git hosts refuse files over 100 MiB, and
every revision of a fixture stays in the history.

!!! warning "Gap: `bundle create` does not exist"
    A bundle can only be exported from data that is already in the
    catalogue. Creating one from local files, with drafted descriptions and
    a version, is the missing first step of this lifecycle.

## 2. Work with it, published or not {#use-a-bundle}

List the bundle in the package's data module (see
[Use ETHOS.Data in your package](use-from-a-package.md#3-build-the-handle-and-the-command)):

```python
BUNDLES = (Path(__file__).with_name("test_data"),)
```

`paths()`, `fetch()` and `catalog_path()` then answer from whichever bundle
holds what was asked for, hash-checked once per process, and go to the
catalogue only for what no bundle holds. A bundled file that is missing or
altered is an error, not a reason to download.

A bundle version that is not in the catalogue yet keeps working. Every
process that reads it warns once:

```text
your_tool/data/test_data version 2 is not in the catalogue yet; propose it so it can be published.
```

That is the deliberate window in which a package maintainer develops against
new test data without waiting for the catalogue. It is not meant to last:
the live CI job fails on a bundle version the catalogue does not hold, see
[Run tests and examples in CI](run-in-ci.md).

To force the catalogue route instead of the bundle, for example to test the
download, pass `download=True` or set `ETHOS_DATA_DOWNLOAD=1`.

!!! warning "Gap: bundle-first reads, the warning and the download switch are not in ETHOS.Data"
    `ethos_data.collections` takes no `bundles=`, nothing warns about an
    unpublished bundle version, and there is no `ETHOS_DATA_DOWNLOAD`. One
    package implements bundle-first reads and a download switch for itself
    today.

## 3. Change it: extend, or copy {#update-data}

Edit the files as you edit anything in the repository, then re-inventory:

```bash
<your-tool>-data bundle update your_tool/data/test_data
```

| Change | What `bundle update` does |
| --- | --- |
| Files added, or a new member dataset | Records them in the current version. An extension does not change published files, so it needs no new version. |
| The bytes of a published file changed under its path | Refused. Published paths never change: put the new bytes under a new path, a copy, and keep or drop the old file as the tests need. `bundle update` then starts the next bundle version. |
| A file removed | Recorded; the file stays in the published versions on dCache. |

Reproducing a bug with a temporarily edited fixture stays possible without
a version: `load_bundle(DIR).fetch(collection, allow_modified=True)` in the
affected test only, and `bundle verify` keeps reporting `modified` until the
file is restored.

## 4. Have the catalogue updated from the bundle {#sync}

Propose the bundle as under [Propose a dataset](propose-a-dataset.md), naming
the bundle directory: its `datasets/` holds the descriptions and licence
documents and its `data/` the bytes, which is everything the maintainer
needs. The maintainer imports it:

```bash
ethos-data catalog add-bundle /path/to/checkout/your_tool/data/test_data
```

`add-bundle` compares the bundle with the version of the family the
catalogue already holds and writes the difference as the bundle's version:
new members and new files are added, changed files appear under their new
paths, unchanged files keep the paths and remote objects they have. The
maintainer builds, uploads what is new and [releases](../catalogue-maintainers/release-the-catalogue.md).
Once the release is out, raise `catalog.min_version` in your collections
file and run `bundle update` once more: it records the release in
`bundle.json`, and the warning stops.

A later change to the bundle goes the same way and becomes the next version.
Older versions stay on dCache for the packages that still use them; the
repository holds the current one.

!!! warning "Gap: no bundle versions, no `bundle update`, no `catalog add-bundle`"
    `bundle.json` carries no version and no published-release field,
    `bundle export` refuses an existing target, and nothing on the
    maintainer side imports a bundle into the catalogue or compares it with
    the version already there. How a bundle version is encoded in dataset
    names and resource paths, so that two versions can share a cache, is the
    design question behind this feature.

## 5. Reuse test data from the catalogue in another tool

The reverse direction: export what a collection selects from the catalogue
into a new bundle, for example to seed a new tool's test suite with data
another tool already published:

```bash
<your-tool>-data bundle export your_tool/data/test_data test_suite_public
<your-tool>-data bundle verify your_tool/data/test_data test_suite_public
```

The target must not exist. An exported bundle starts published, with the
catalogue's descriptors and licence documents in place; read
`datasets/<family>/<member>/` before committing, because it states the terms
under which your repository now redistributes the files. To take the bytes
from a copy already on the machine, add `--source-root DATASET=/absolute/path`
per dataset; the copy must match the catalogue's hashes.

Tests may also read a bundle directly and explicitly:

```python
from pathlib import Path
from ethos_data import load_bundle

BUNDLE = Path(__file__).resolve().parents[1] / "your_tool" / "data" / "test_data"

def test_my_workflow():
    files = load_bundle(BUNDLE).fetch("test_suite_public")
    run(files.one("aachenShapefile.shp"))
```

See [Run tests and examples in CI](run-in-ci.md) for the CI wiring and the
[bundle reference](../../reference/cli/package-data.md#bundle) for the
options that exist today.
