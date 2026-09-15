# Find data through an internal catalogue

In this ten-minute lesson we will see why selecting internal metadata and
locating restricted files are separate steps. Everything is synthetic and local;
you need no cluster account, licence, server, or symbolic-link permissions.

You need ETHOS.Data installed. Use the files created by the
[first-fetch lesson](first-fetch.md), or save
[create-fetch-lesson.py](../assets/examples/create-fetch-lesson.py) in a new
directory and run `python create-fetch-lesson.py`. Work inside
`first-fetch-lesson`. The setup includes a project config so settings stay in
the practice directory.
Use a terminal without `ETHOS_RESTRICTED_DIR` or `ETHOS_SKIP_UNAVAILABLE`
environment overrides so the exercise's project settings take effect.

## 1. Look for a hidden dataset in the public view

```bash
ethos-data --catalog catalogue/datacatalog.json --root cache -c restricted-collections.yaml list
```

Expect `licensed_input` to be `[unresolvable]` and the command to exit with an
error. The public practice catalogue does not list `lesson-licensed`.
This is a metadata selection problem; no data download has been attempted.

## 2. Select the internal view

```bash
ethos-data --catalog internal-catalogue/datacatalog.json --root cache -c restricted-collections.yaml info licensed_input
ethos-data --catalog internal-catalogue/datacatalog.json --root cache -c restricted-collections.yaml fetch licensed_input
```

The first command lists `lesson-licensed/factor.csv`. The fetch still fails:
knowing the file's name has not told this machine where its authorised copy lives.
Notice that the error describes restricted data rather than attempting a download.
If an earlier run configured the practice installation, remove that project
setting with `ethos-data config unset-restricted-cache --scope project` and retry.

## 3. Locate the practice installation

Get its absolute path:

```bash
python -c "from pathlib import Path; print(Path('restricted-installation').resolve())"
```

Copy the printed path into the following command, replacing `ABSOLUTE_PATH`:

```bash
ethos-data config set-restricted-cache "ABSOLUTE_PATH" --scope project
ethos-data config show
ethos-data --catalog internal-catalogue/datacatalog.json --root cache -c restricted-collections.yaml plan licensed_input
ethos-data --catalog internal-catalogue/datacatalog.json --root cache -c restricted-collections.yaml fetch licensed_input
ethos-data --catalog internal-catalogue/datacatalog.json --root cache -c restricted-collections.yaml verify licensed_input --deep
```

`config show` should name the lesson's installation and project config. If an
`ETHOS_RESTRICTED_DIR` environment variable overrides it, clear that override in
this shell before continuing.

Expect one file used in place, no download, and one matching file on verification.
Open `restricted-installation/lesson-licensed/factor.csv`: it contains a factor
of `2`. No copy should appear under `cache/lesson-licensed`.

## 4. End the exercise

```bash
ethos-data config unset-restricted-cache --scope project
```

The original CSV remains. The setting located an installation; removing it
removed neither the data nor its metadata.

You have distinguished an absent description from an unavailable installation.
For real cluster use, obtain the actual catalogue path, restricted root, and
access permission from your administrator. Continue with
[Work with restricted data](../how-to/restricted-data.md), or read
[Catalogues and storage](../explanation/catalogues-and-storage.md) for the
relationship between access and visibility.
