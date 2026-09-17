# Your first fetch

Download a tiny CSV from a local practice server, read it in Python, then detect
and replace a damaged cache copy. You need [ETHOS.Data installed](../installation.md),
Python and two terminals in the same environment. Allow about 15 minutes.
The lesson uses no public catalogue release, cluster account or storage credentials.

## 1. Prepare the practice files

Save [create-fetch-lesson.py](../assets/examples/create-fetch-lesson.py) in a new
working directory and run:

```bash
python create-fetch-lesson.py
cd first-fetch-lesson
```

The script refuses to overwrite an existing lesson directory. It creates
metadata in `catalogue/` and synthetic bytes in `server/`. We will fetch into
`cache/`. Its collections files are optional examples for the Python API;
the direct CLI reads catalogue keys.

Use a shell without `ETHOS_PUBLICATION_URL`, staging or dataset-root overrides
from earlier practice. The project config points downloads to the local server.

## 2. Start the server

In the first terminal, from `first-fetch-lesson`:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory server
```

Leave it running. If the port is occupied, stop the earlier lesson server.
Open the second terminal in the same lesson directory for the remaining commands.

## 3. Inspect the catalogue

```bash
ethos-data config show
ethos-data --catalog catalogue/datacatalog.json ls
ethos-data --catalog catalogue/datacatalog.json ls lesson-stations
```

The first listing contains `lesson-stations`; the second contains
`lesson-stations/temperatures.csv` and its size. No data request should appear
in the server terminal. `config show` reports shared settings; the explicit
`--catalog` selects the lesson index for each invocation.

## 4. Fetch twice

```bash
ethos-data --catalog catalogue/datacatalog.json --root cache fetch lesson-stations/temperatures.csv
ethos-data --catalog catalogue/datacatalog.json --root cache fetch lesson-stations/temperatures.csv
```

Both commands print the same absolute local path. The first downloads and checks
the CSV; the second reuses it. The server receives a data request only on the
first fetch. The original stays under `server/data/lesson-stations/`.

## 5. Read the result in Python

Save `read_observations.py` in the lesson directory:

```python
import csv
from pathlib import Path
import ethos_data

catalog = ethos_data.catalog(str(Path("catalogue/datacatalog.json").resolve()))
table = catalog.path("lesson-stations/temperatures.csv", root=Path("cache").resolve())
with table.open() as handle:
    values = [float(row["value"]) for row in csv.DictReader(handle)]
print(table)
print(sum(values) / len(values))
```

```bash
python read_observations.py
```

Expect the cache path and `12.75`. The key identifies the resource; the returned
path lets an ordinary CSV reader open it.

## 6. Detect and replace a changed copy

Change only the cache copy:

```bash
python -c "from pathlib import Path; p = Path('cache/lesson-stations/temperatures.csv'); p.write_bytes(p.read_bytes().replace(b'13.0', b'14.0'))"
```

Save `check_cache.py`:

```python
import sys
from pathlib import Path
import ethos_data

catalog = ethos_data.catalog(str(Path("catalogue/datacatalog.json").resolve()))
resources = catalog.resources("lesson-stations")
deep = "--deep" in sys.argv
findings = ethos_data.verify(catalog, resources, Path("cache").resolve(), deep=deep)
for finding in findings:
    print(finding.status, finding.resource.key)
raise SystemExit(any(finding.status != "ok" for finding in findings))
```

```bash
python check_cache.py
python check_cache.py --deep
```

The size check reports `ok` because the length did not change. The deep check
reports `wrong checksum` and returns a nonzero exit status. This failure is
intentional. Fetch again while the server is running:

```bash
ethos-data --catalog catalogue/datacatalog.json --root cache fetch lesson-stations/temperatures.csv
python check_cache.py --deep
python read_observations.py
```

The fetch replaces the damaged downloaded copy. Verification now reports `ok`
and the calculation again prints `12.75`. Package wrappers also provide
`verify --repair` for collection workflows.

Stop the server with Ctrl+C. All practice files are inside `first-fetch-lesson`.
Continue with [Set up your machine](../how-to/data-users/set-up-your-machine.md) or
[Get data by catalogue key](../how-to/data-users/get-data-for-a-task.md).
