# Run a test with repository data

In this lesson you make a small teaching catalogue, export one of its datasets
into a bundle through a package's handle, read the bundle in a test, and see
how strict checking differs from a deliberate development edit. The local
catalogue stands in for released metadata: no shared catalogue or dCache files
are changed.

You need an installed `ethos-data` and pytest. Work in a new directory so the lesson
has no existing test data to replace. Allow about 20 minutes. Create the directory
tree before adding the files below:

```bash
python -c "from pathlib import Path; Path('catalogue').mkdir(); Path('lesson/input').mkdir(parents=True)"
export ETHOS_DATA_CONFIG="$PWD/lesson-settings.yaml"
ethos-data config set-public-cache "$PWD/cache"
```

`ETHOS_DATA_CONFIG` names the lesson's settings file: while it is named,
ETHOS.Data reads it instead of the settings in your account, and writes any
setting into it. The last command gives the lesson a public cache of its own.

## Build the teaching catalogue

Create `catalogue/catalog.yaml`:

```yaml
name: bundle-lesson
ethos:catalog_role: source
ethos:publication_url: https://example.invalid/data
```

Create `lesson/input/value.txt` containing `3`, and the draft description
`lesson/dataset.yaml` beside it:

```yaml
name: lesson
title: Tiny test input
source_dir: input
ethos:access: public
ethos:visibility: public
ethos:remote_prefix: lesson
licenses:
  - name: CC0-1.0
```

Take the draft into the teaching catalogue, which builds it:

```bash
cd catalogue
ethos-data catalog add ../lesson
cd ..
ethos-data config set-catalog "$PWD/catalogue/datacatalog.json"
```

`catalog add` writes `catalogue/datasets/lesson/dataset.yaml` without
`source_dir`, which goes into the dataset's `status.yaml`. The last command
names the teaching catalogue in the lesson's settings file, so the catalogue
configured for your normal work is not read. Create
`collections.yaml`:

```yaml
collections:
  tiny_test:
    include:
      - dataset: lesson
        files: [value.txt]
```

Save this small package-style wrapper as `data_cli.py` beside `collections.yaml`:

```python
from pathlib import Path
from ethos_data import tool_main

if __name__ == "__main__":
    raise SystemExit(tool_main(
        Path(__file__).with_name("collections.yaml"), prog="python data_cli.py"
    ))
```

It provides the same collection, bundle and staging commands a consuming package
exposes through `tool_main`, without needing RESKit installed for this lesson.

## Export the dataset into a bundle

The teaching catalogue's bytes are not on any store: its publication URL is
deliberately unreachable. Make them a cache entry, the way a maintainer
registers data already on a machine, then export:

```bash
ethos-data link lesson "$PWD/lesson/input"
python data_cli.py bundle export tests/data-bundle tiny_test
```

Export reads through the package's handle, as a workflow does: the cache entry
you just made is found in place, and every file is checked against the
catalogue's size and SHA-256 as it is copied. Inspect
`tests/data-bundle/bundle.json`: `lesson` is aligned with revision 1 of the
catalogue and holds all of its files. `tests/data-bundle/datasets/lesson/`
holds its description, the terms under which a repository passes the file on.

## Use it in a test

Create `tests/test_value.py`:

```python
from pathlib import Path

import ethos_data

HERE = Path(__file__).parent
data = ethos_data.collections(
    HERE.parent / "collections.yaml", bundles=[HERE / "data-bundle"]
)

def test_value():
    files = data.fetch("tiny_test")
    assert int(files["lesson/value.txt"].read_text()) == 3
```

```bash
pytest -q tests/test_value.py
```

The test passes using the repository copy. The handle reads the bundle first,
and since it holds every input of the collection, no catalogue is read at all.

## Observe a deliberate change

Change `tests/data-bundle/data/lesson/value.txt` to `4` and run pytest again.
Reading the bundle fails its hash check before the numerical assertion runs:
a change `bundle update` has not recorded is an error, never a reason to
download.

For a bug-fix experiment, read the changed file in that one test:

```python
from ethos_data import load_bundle

def test_value():
    files = load_bundle(HERE / "data-bundle").fetch("lesson", allow_modified=True)
    assert int(files["lesson/value.txt"].read_text()) == 4
```

The test passes, with a warning that names the changed file. The recorded hash
is unchanged:

```bash
python data_cli.py bundle verify tests/data-bundle
```

Verification reports `modified` and exits unsuccessfully. Reading a change for
an experiment has not made it the bundle's data.

## Realign the bundle

To drop the experiment, take the catalogue's version back:

```bash
python data_cli.py bundle update tests/data-bundle --from-catalog lesson
python data_cli.py bundle verify tests/data-bundle
```

`--from-catalog` takes the catalogue's files of the bundled selection, with its
description, and records the alignment. Restore the strict test, and both
checks pass again:

```bash
pytest -q tests/test_value.py
```

Remove `ETHOS_DATA_CONFIG` from the shell (`unset ETHOS_DATA_CONFIG`) to return
to your own settings. To keep a change instead, record it with `bundle update`
and realign the bundle the other way, towards the catalogue: see
[Keep data in the repository](../how-to/package-maintainers/keep-data-in-the-repository.md#sync).
