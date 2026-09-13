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

```bash
cd source-catalogue
ethos-data catalog build station-temperatures
```

```title="Output"
  station-temperatures: 1 of 2 files under …/catalogue-lesson/incoming/station-temperatures selected, 1 filtered out
  station-temperatures                   1 files     0.000 GB  public/public
  datacatalog.json           1 datasets
```

The log was filtered out. Open `datasets/station-temperatures/datapackage.json`:
its one resource records the path, size and SHA-256 hash of `temperatures.csv`.
The `datacatalog.json` next to `catalog.yaml` now lists the dataset.

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
maintainer. Check that none of them leaked:

```bash
grep -rn -E 'source_dir|ethos:uploaded|ethos:license_note|ethos:embargo' ../public-catalogue
```

No output means no leak. You now have both views of the catalogue: the
internal one in `source-catalogue/datacatalog.json`, and the public one in
`public-catalogue`. A hidden dataset would appear only in the first.

## 5. Link the data into a shared cache

On a machine that several people or projects share, data already on disk does
not need to be downloaded at all. Link it into the cache everybody uses:

```bash
ethos-data catalog link-cache --root ../shared-cache --dry-run
ethos-data catalog link-cache --root ../shared-cache
cd ..
```

```title="Output (abridged)"
  link         station-temperatures             -> …/catalogue-lesson/incoming/station-temperatures

1 change(s) applied.
```

`shared-cache/station-temperatures` is now a symbolic link to
`incoming/station-temperatures`. Nothing was copied.

## 6. Read the dataset as a data user

Create `collections.yaml` in `catalogue-lesson`:

```yaml
catalog: public-catalogue/datacatalog.json
collections:
  temperatures:
    include:
      - dataset: station-temperatures
```

Plan the collection the way a data user would, with the shared cache as the
public cache:

```bash
ethos-data -c collections.yaml --catalog public-catalogue/datacatalog.json \
  --root shared-cache plan temperatures
```

```title="Output"
public cache:    shared-cache
used in place:      1 files        28 B  (namespace link, never copied)
already cached:     0 files         0 B
to download:        0 files         0 B
```

`--catalog` repeats the pin from the collections file, so that a catalogue you
may have configured for your everyday work cannot take its place. Now fetch the
collection and check it against the catalogue:

```bash
ethos-data -c collections.yaml --catalog public-catalogue/datacatalog.json \
  --root shared-cache fetch temperatures
ethos-data -c collections.yaml --catalog public-catalogue/datacatalog.json \
  --root shared-cache verify temperatures --deep
```

The fetch reports `1 used in place`, and verification ends with
`1 file(s) match the catalogue.`

## 7. Turn the link into a copy

A link is only as durable as the directory it points at. Before that storage is
reorganised or retired, replace the link with a verified copy that the cache
owns:

```bash
ethos-data -c collections.yaml --catalog public-catalogue/datacatalog.json \
  --root shared-cache materialize station-temperatures --dry-run
ethos-data -c collections.yaml --catalog public-catalogue/datacatalog.json \
  --root shared-cache materialize station-temperatures
```

```title="Output (abridged)"
  materialized   station-temperatures  1 files, 28 bytes copied from …/catalogue-lesson/incoming/station-temperatures
```

`shared-cache/station-temperatures` is now a real directory, and
`.ethos-data-materialized.json` inside it records where the copy came from. Run
the `plan` command from step 6 again: the file is now `already cached` rather
than `used in place`. `incoming/station-temperatures` is still there;
`materialize` never deletes the original.

## What you did

| You ran | It did |
|---|---|
| `ethos-data catalog build` | inventoried `source_dir`, left out the excluded log, hashed the rest |
| `ethos-data catalog build --check` | compared the inventory with the files, and wrote nothing |
| `ethos-data catalog publish` | generated the public view without maintainer-only fields |
| `ethos-data catalog link-cache` | linked data already on disk into a shared cache |
| `ethos-data materialize` | replaced that link with a verified copy |

A real catalogue has one more step between building and publishing:
`ethos-data catalog upload` puts public bytes on dCache and proves that anyone
can download them. It needs storage credentials, so this lesson left it out.

When you are done, delete the `catalogue-lesson` directory.

## Next

- [Accept a dataset proposal](../how-to/accept-a-dataset.md) — the checklist for
  a real submission, from review to release.
- [Upload a dataset](../how-to/upload-a-dataset.md) — credentials, transfer, and
  verification.
- [Add internal and restricted datasets](../how-to/add-internal-and-restricted-data.md)
  — data that is not uploaded publicly.
- [Migrate cluster data](../how-to/migrate-cluster-data.md) — linking and
  copying on real shared storage.
