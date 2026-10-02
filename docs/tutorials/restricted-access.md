# Find data through an internal catalogue

This ten-minute lesson separates metadata selection from locating restricted
files. All data is synthetic and local; no account, licence, server or symbolic
link permissions are needed.

With ETHOS.Data installed, run the
[practice-file generator](../assets/examples/create-fetch-lesson.py) in a new
directory, then work inside `first-fetch-lesson`. An existing first-fetch lesson
directory also works. Name the lesson's settings file, as in
[Your first fetch](first-fetch.md#1-prepare-the-practice-files), so the
setting this lesson makes goes into the lesson and not into your account:

```bash
export ETHOS_DATA_CONFIG="$PWD/lesson-settings.yaml"
```

Use a shell without `ETHOS_RESTRICTED_DIR`, which would win over the lesson's
settings.

## 1. Look for a hidden dataset

```bash
ethos-data --catalog catalogue/datacatalog.json ls lesson-licensed
```

Expect an unknown-dataset error and exit status `2`. The public practice index
does not list `lesson-licensed`. This is a metadata problem; no download is attempted.

## 2. Select the internal view

```bash
ethos-data --catalog internal-catalogue/datacatalog.json ls lesson-licensed
ethos-data --catalog internal-catalogue/datacatalog.json --root cache fetch lesson-licensed/factor.csv
```

The listing contains `lesson-licensed/factor.csv`. Fetching still fails because
the authorised installation has not been located. It does not try a download.
If you already ran this lesson, run `ethos-data config unset-restricted-cache`
first.

## 3. Locate the practice installation

Print the directory's absolute path:

```bash
python -c "from pathlib import Path; print(Path('restricted-installation').resolve())"
```

Replace `ABSOLUTE_PATH` below with that output:

```bash
ethos-data config set-restricted-cache "ABSOLUTE_PATH"
ethos-data config show
ethos-data --catalog internal-catalogue/datacatalog.json --root cache fetch lesson-licensed/factor.csv
```

The returned path is under `restricted-installation/lesson-licensed`, and the
file contains a factor of `2`. No copy appears under `cache/lesson-licensed`.

Check the installation in Python:

```python
from pathlib import Path
import ethos_data

catalog = ethos_data.catalog(str(Path("internal-catalogue/datacatalog.json").resolve()))
findings = ethos_data.verify(catalog, catalog.resources("lesson-licensed"), deep=True)
assert all(finding.status == "ok" for finding in findings)
```

## 4. End the exercise

```bash
ethos-data config unset-restricted-cache
unset ETHOS_DATA_CONFIG
```

The original CSV remains. The setting located files; it did not grant permissions
or change their metadata. For real data, follow
[Set up your machine](../how-to/data-users/set-up-your-machine.md#cluster-users) using the
locations and permissions supplied by the dataset custodian.
