# Add a dataset to the catalogue

You are the catalogue maintainer. In this lesson you take a tiny dataset through
the steps every catalogued dataset goes through — describe it, build its
inventory, publish the catalogue — and then make it available on a shared
machine: first by linking it into a cache, later by turning that link into a
copy. Everything happens in a practice catalogue on your own machine. Nothing is
uploaded to dCache and nothing is published anywhere.

You need an installed `ethos-data` and a shell: bash, zsh, or Git Bash on
Windows. Step 5 creates a symbolic link, which on Windows requires Developer
Mode.
Allow about 30 minutes. The paths in this exercise are local practice paths.

## 1. Set up the practice catalogue

```bash
mkdir catalogue-lesson
cd catalogue-lesson
mkdir -p source-catalogue/datasets/station-temperatures public-catalogue incoming/station-temperatures
printf 'station,value\nA,12.5\nB,13.0\n' > incoming/station-temperatures/temperatures.csv
printf 'downloaded 2026-09-11\n' > incoming/station-temperatures/download.log
```

`incoming/station-temperatures` plays the part of the data a package maintainer
proposed: a CSV, and next to it a download log that is not part of the dataset.
`source-catalogue` is your practice copy of the internal source catalogue, and
`public-catalogue` will receive the public view generated from it.

Create `source-catalogue/catalog.yaml`:

```yaml
name: practice-catalogue
ethos:catalog_role: source
ethos:publication_url: https://example.invalid/practice
```

The publication URL is deliberately unreachable: no bytes are downloaded in
this lesson.

## 2. Describe the dataset

Create `source-catalogue/datasets/station-temperatures/dataset.yaml`:

```yaml
name: station-temperatures
title: Synthetic station temperatures
description: Two invented observations, used to practise catalogue maintenance.
source_dir: ../../../incoming/station-temperatures
ethos:access: public
ethos:visibility: public
ethos:remote_prefix: station-temperatures-v1
ethos:origin: created
contributors:
  - title: Your name
    roles: [author]
ethos:exclude:
  - download.log
licenses:
  - name: CC0-1.0
    path: https://creativecommons.org/publicdomain/zero/1.0/
```

`source_dir` points at the files on this machine, relative to the dataset's own
directory. It is what the inventory is built from, and it is never published.
`ethos:exclude` leaves the download log out of the dataset without moving or
deleting it. `ethos:origin: created` says that you made this data, which is why
an author is named.

## 3. Build the inventory

In a catalogue, the commands keep `source_dir` in a file of their own beside
the description, the dataset's `status.yaml`. Move it there, then build:

```bash
cd source-catalogue
ethos-data catalog migrate station-temperatures
ethos-data catalog build station-temperatures
```

```title="Output (abridged)"
  migrated       station-temperatures             draft      source_dir moved out of dataset.yaml
…
  station-temperatures: 1 of 2 files under …/catalogue-lesson/incoming/station-temperatures selected, 1 filtered out
  station-temperatures                   1 files     0.000 GB  public/public
  datacatalog.json           1 datasets
```

The log was filtered out. Open `datasets/station-temperatures/datapackage.json`:
its one resource records the path, size and SHA-256 hash of `temperatures.csv`.
The `datacatalog.json` next to `catalog.yaml` now lists the dataset.

`datasets/station-temperatures/status.yaml` holds `source_dir` and the history
of what the commands did to the dataset. Ask where the dataset stands:

```bash
ethos-data catalog status
```

```title="Output"
  dataset               state      access      next
  station-temperatures  built      public      ethos-data catalog upload station-temperatures
```

It is `built`: described and inventoried, with no copy of its bytes made
available yet.

Change the data behind the inventory, and ask whether the catalogue still
describes it:

```bash
printf 'station,value\nA,12.5\nB,14.0\n' > ../incoming/station-temperatures/temperatures.csv
ethos-data catalog build --check
```

```title="Output (abridged)"
Out of date (re-run `ethos-data catalog build`):
  datasets/station-temperatures/datapackage.json
```

`--check` writes nothing and exits with an error; it is what a catalogue's CI
runs. Rebuild, and check again:

```bash
ethos-data catalog build station-temperatures
ethos-data catalog build --check
```

This time the check ends with `All manifests up to date.` Rebuilding is how an
inventory follows its files only until the dataset is uploaded. After that its
published paths are immutable, and changed bytes get new paths.

## 4. Publish the public view

```bash
ethos-data catalog publish ../public-catalogue
```

```title="Output"
Published to …/catalogue-lesson/public-catalogue
  + .gitignore
  + README.md
  + datacatalog.json
  + datasets/station-temperatures/datapackage.json

Review and commit in the public repo, then push.
```

`publish` regenerates the public catalogue from every dataset marked
`ethos:visibility: public`, and strips the fields that only make sense to a
maintainer. It refuses to write a tree that still carries one, or that names
a hidden dataset. To see for yourself that none of them leaked:

```bash
grep -rn -E 'source_dir|ethos:license_note|ethos:embargo' ../public-catalogue
```

No output means no leak. You now have both views of the catalogue: the
internal one in `source-catalogue/datacatalog.json`, and the public one in
`public-catalogue`. A hidden dataset would appear only in the first.

## 5. Link the data into the public cache

On the cluster, every user's public cache is one shared directory, and data
already on disk there is never downloaded: a maintainer links it into that
cache. Do the same for the lesson's public cache, `public-cache`:

```bash
ethos-data link --all --root ../public-cache --dry-run
ethos-data link --all --root ../public-cache
cd ..
```

```title="Output (abridged)"
  link         station-temperatures             -> …/catalogue-lesson/incoming/station-temperatures

1 change(s) applied.
```

`public-cache/station-temperatures` is now a symbolic link to
`incoming/station-temperatures`. Nothing was copied.

## 6. Read the dataset as a data user

A data user names the catalogue they read in their settings. Name a settings
file for the lesson in this shell, and the public catalogue in it, so that a
catalogue you may have configured for your everyday work cannot take its
place:

```bash
export ETHOS_DATA_CONFIG="$PWD/lesson-settings.yaml"
ethos-data config set-catalog "$PWD/public-catalogue/datacatalog.json"
```

While `ETHOS_DATA_CONFIG` names it, ETHOS.Data reads this file instead of the
settings in your account. Create `collections.yaml` in `catalogue-lesson`:

```yaml
collections:
  temperatures:
    include:
      - dataset: station-temperatures
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


Plan the collection the way a data user on the cluster would, whose public
cache is the one the data was linked into:

```bash
python data_cli.py --root public-cache fetch temperatures --plan
```

```title="Output"
public cache:    public-cache
used in place:      1 files        28 B  (namespace link, never copied)
already cached:     0 files         0 B
to download:        0 files         0 B
```

Now fetch the collection and check it against the catalogue:

```bash
python data_cli.py --root public-cache fetch temperatures
python data_cli.py --root public-cache verify temperatures --deep
```

The fetch reports `1 used in place`, and verification ends with
`1 file(s) match the catalogue.`

## 7. Turn the link into a copy

A link is only as durable as the directory it points at. Before that storage is
reorganised or retired, replace the link with a verified copy that the cache
owns:

```bash
ethos-data --root public-cache materialize station-temperatures --dry-run
ethos-data --root public-cache materialize station-temperatures
```

```title="Output (abridged)"
  materialized   station-temperatures  1 files, 28 bytes copied from …/catalogue-lesson/incoming/station-temperatures
```

`public-cache/station-temperatures` is now a real directory, and
`.ethos-data-materialized.json` inside it records where the copy came from. Run
the `fetch --plan` command from step 6 again: the file is now `already cached` rather
than `used in place`. `incoming/station-temperatures` is still there;
`materialize` never deletes the original.

## What you did

| You ran | It did |
|---|---|
| `ethos-data catalog migrate` | moved `source_dir` into the dataset's `status.yaml` |
| `ethos-data catalog build` | inventoried `source_dir`, left out the excluded log, hashed the rest |
| `ethos-data catalog status` | listed the dataset's state and its next step |
| `ethos-data catalog build --check` | compared the inventory with the files, and wrote nothing |
| `ethos-data catalog publish` | generated the public view without maintainer-only fields |
| `ethos-data link --all` | linked data already on disk into the public cache |
| `ethos-data materialize` | replaced that link with a verified copy |

A real catalogue has one more step between building and publishing:
`ethos-data catalog upload` puts public bytes on dCache and proves that anyone
can download them. It needs storage credentials, so this lesson left it out.

When you are done, remove `ETHOS_DATA_CONFIG` from the shell
(`unset ETHOS_DATA_CONFIG`) and delete the `catalogue-lesson` directory.

## Next

- [Catalogues and storage](../explanation/catalogues-and-storage.md) — why metadata
  publication, local access, and remote storage are separate operations.

- [Add a dataset](../how-to/catalogue-maintainers/add-a-dataset.md) — the checklist for
  a real submission, from review to release.
- [Upload a dataset](../how-to/catalogue-maintainers/upload-a-dataset.md) — credentials, transfer, and
  verification.
- [Add a dataset, restricted datasets](../how-to/catalogue-maintainers/add-a-dataset.md#restricted-installations)
  — data that is not uploaded publicly.
- [Link existing data into the cache](../how-to/catalogue-maintainers/link-existing-data.md) — linking and
  copying on real shared storage.
