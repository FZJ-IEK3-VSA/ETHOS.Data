# Develop and propose a dataset

You maintain a package and want to test a new input before asking a catalogue
maintainer to publish it. This lesson creates a tiny CSV, reads it through the
ordinary collection API, and prepares the handoff. It uses local files only and
needs an installed `ethos-data`; it needs no catalogue account or upload
credentials. Use Bash, zsh, or Git Bash; symbolic links on Windows require
Developer Mode or elevation. Allow about 20 minutes.

## 1. Create a local workspace

In a terminal with your package's Python environment active:

```bash
mkdir ethos-local-lesson
cd ethos-local-lesson
mkdir candidate
export ETHOS_STAGING_DIR="$PWD/.ethos-staging"
export ETHOS_DATA_DIR="$PWD/.ethos-cache"
```

These environment variables apply to this shell and its child processes. The
staging directory holds development entries; the ordinary cache has a separate
location.

Create the input and a minimal local catalogue index:

```python
from pathlib import Path

Path("candidate/temperatures.csv").write_bytes(b"station,value\nA,12.5\nB,13.0\n")
Path("datacatalog.json").write_text('{"name": "local-lesson", "datasets": []}\n')
Path("collections.yaml").write_text("""catalog: datacatalog.json
collections:
  example_input:
    include:
      - dataset: lesson-temperatures
        files: ["temperatures.csv"]
  all:
    extends: [example_input]
""")
```

The empty index deliberately does not describe `lesson-temperatures`. It is a
local teaching fixture, not the generated index of an official catalogue. The
next step supplies the dataset through staging.

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


## 2. Register and inspect the candidate

```bash
python data_cli.py staging add lesson-temperatures "$PWD/candidate" --note "local CSV lesson"
python data_cli.py staging list
python data_cli.py --catalog "$PWD/datacatalog.json" info example_input
python data_cli.py --catalog "$PWD/datacatalog.json" info all
```

Both collections resolve the same CSV; `all` aggregates the inputs this example
workflow uses. Naming the local
catalogue explicitly also overrides any catalogue configured for your usual
project. No remote metadata is needed for this lesson.

## 3. Use the same API your package will use

Run Python in this directory and shell:

```python
import csv
from pathlib import Path
from ethos_data import fetch

files = fetch("example_input", collections="collections.yaml",
              catalog=str(Path("datacatalog.json").resolve()))
with files.one("temperatures.csv").open() as handle:
    rows = list(csv.DictReader(handle))

assert [float(row["value"]) for row in rows] == [12.5, 13.0]
```

The staging warning identifies the development input; an unresolved-licensing
warning is also expected because this staging entry has no approved metadata.
`files` contains the
ordinary resource key `lesson-temperatures/temperatures.csv`, so the workflow
does not need to know the candidate's filesystem path.

Change the second value to `14.0` in `candidate/temperatures.csv`, then repeat
the fetch and update the assertion to `[12.5, 14.0]`. A fresh fetch sees the
candidate on disk. Staging records sizes but no canonical checksums; it is for
experiments and cannot establish that an input matches a released version.

## 4. Prepare a proposal

Once the experiment works, preserve the candidate version and prepare a draft
`dataset.yaml` for the reviewer:

```yaml
name: lesson-temperatures
title: Synthetic temperatures for the local development lesson
description: Two invented station observations used to exercise a CSV reader.
ethos:origin: created
contributors:
  - title: Your name
    roles: [author]
ethos:access: public
ethos:visibility: public
ethos:remote_prefix: lesson-temperatures-v1
licenses:
  - name: CC0-1.0
    path: https://creativecommons.org/publicdomain/zero/1.0/
```

The licence here applies to the invented example; choose appropriate terms for
real data. The catalogue maintainer will set `source_dir` to the candidate
location they can read. For a minimal inventory to accompany this proposal:

```python
import hashlib
from pathlib import Path

candidate = Path("candidate/temperatures.csv")
print(candidate.name, candidate.stat().st_size,
      "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest())
```

With real data, you would now hand the CSV, this inventory, the draft metadata,
and the validation result to a catalogue maintainer. This teaching example stays
on your machine.

## 5. End the experiment

```bash
python data_cli.py staging remove lesson-temperatures
unset ETHOS_STAGING_DIR ETHOS_DATA_DIR
```

Removing this linked staging entry leaves `candidate/temperatures.csv` intact.
The empty local catalogue can no longer resolve the collection, as expected.
For real data, after acceptance you would instead choose the released
catalogue, remove the development override, and rerun the workflow against the
verified official copy.

## What you did

You read an uncatalogued input through the same `fetch` call a package uses,
saw that staging follows the files on disk without checksums, and prepared the
metadata and inventory a catalogue maintainer reviews.

## Next

- [Run a test with repository data](bundled-tests.md) — the next lesson:
  catalogued test data in a repository, and deliberate local edits to it.
- [Stage uncatalogued data](../how-to/propose-a-dataset.md#stage-development-data) — staging for
  real data.
- [Propose a dataset](../how-to/propose-a-dataset.md) — a real submission,
  including provenance and access to the bytes.
