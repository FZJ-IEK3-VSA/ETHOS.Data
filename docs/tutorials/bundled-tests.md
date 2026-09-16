# Run a test with repository data

In this lesson you make a small teaching catalogue, export one verified fixture,
and observe how strict checking differs from a deliberate development edit.
The synthetic local catalogue stands in for released metadata: no shared catalogue
or dCache files are changed. In a real package, export from its pinned official
catalogue instead.

You need an installed `ethos-data` and pytest. Work in a new directory so the lesson
has no existing test data to replace. Allow about 20 minutes. Create the directory
tree before adding the files below:

```bash
python -c "from pathlib import Path; Path('catalogue/datasets/lesson/input').mkdir(parents=True)"
```

## Build the teaching catalogue

Create `catalogue/catalog.yaml`:

```yaml
name: bundle-lesson
ethos:catalog_role: source
ethos:publication_url: https://example.invalid/data
```

Create `catalogue/datasets/lesson/dataset.yaml`:

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

Create `catalogue/datasets/lesson/input/value.txt` containing `3`, then build:

```bash
cd catalogue
ethos-data catalog build
cd ..
```

Create `collections.yaml`:

```yaml
catalog: catalogue/datacatalog.json
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


## Export the fixture

```bash
python data_cli.py --catalog catalogue/datacatalog.json bundle export tests/data-bundle tiny_test \
  --source-root lesson=catalogue/datasets/lesson/input --source-revision lesson-1
```

The explicit catalogue overrides any catalogue configured for your normal work.
The local source is verified against the built manifest. The deliberately
unreachable publication URL is not used because you supplied the existing bytes.
Inspect `tests/data-bundle/bundle.json`: it records the selected resource and its
original SHA-256 hash.

## Use it in a test

Create `tests/test_value.py`:

```python
from pathlib import Path
from ethos_data import load_bundle

BUNDLE = Path(__file__).parent / "data-bundle"

def test_value():
    files = load_bundle(BUNDLE).fetch("tiny_test")
    assert int(files.one("value.txt").read_text()) == 3
```

```bash
pytest -q tests/test_value.py
```

The test passes using the repository copy. No catalogue or dataset network
request occurs during the bundle read.

## Observe a deliberate change

Change `tests/data-bundle/data/lesson/value.txt` to `4` and run pytest again.
Fetching the fixture fails its hash check before the numerical assertion runs.

For a bug-fix experiment, change the test to use
`fetch("tiny_test", allow_modified=True)` and expect `4`. The test now passes
with a warning that the input differs from the catalogue. The snapshot's
original hash is unchanged.

```bash
python data_cli.py bundle verify tests/data-bundle tiny_test
```

Verification still reports `modified` and exits unsuccessfully. Accepting local
changes for an experiment has not promoted them to authoritative data.

Restore the fixture to its original bytes and restore the strict test to finish
the lesson:

```bash
python -c "from pathlib import Path; import shutil; shutil.copyfile('catalogue/datasets/lesson/input/value.txt', 'tests/data-bundle/data/lesson/value.txt')"
python data_cli.py bundle verify tests/data-bundle tiny_test
pytest -q tests/test_value.py
```

Both checks pass again. For real changes, follow
[Keep test data in a repository](../how-to/keep-test-data-in-a-repository.md#promote-an-accepted-fix)
to publish a revision and refresh the copy after the fix has been verified.
