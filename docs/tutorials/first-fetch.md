# Your first fetch

In this lesson we will download a tiny CSV, read it from Python, and detect and
repair a damaged cache copy. You need [ETHOS.Data installed](../installation.md),
Python, and two terminals in the same environment. The exercise takes about
15 minutes and works on Windows, macOS, and Linux.

We use a local practice server so the lesson does not depend on a public catalogue
release, package-specific collections, cluster access, or dCache credentials.

## 1. Prepare the practice files

Save [create-fetch-lesson.py](../assets/examples/create-fetch-lesson.py) in a new
working directory and run:

```bash
python create-fetch-lesson.py
cd first-fetch-lesson
```

The script creates one synthetic dataset, its catalogue, and a collection called
`observations`. It refuses to overwrite an existing lesson directory.
Its project config selects the practice download server. Use a terminal without
an `ETHOS_PUBLICATION_URL` environment override, which would take precedence.

We will read metadata from `catalogue/`, download bytes from `server/`, and keep
the fetched copy in `cache/`. Open `collections.yaml`: it selects the dataset
by name and carries no storage-machine path.

## 2. Start the server

In the first terminal, from `first-fetch-lesson`:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory server
```

Leave it running. It should say it is serving HTTP on port 8765. If that port is
occupied, stop the previous lesson server before continuing.

Open the second terminal in the same `first-fetch-lesson` directory. Run all
remaining commands there.

## 3. Inspect the configuration and collection

```bash
ethos-data config show
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml list
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml info observations
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml plan observations
```

`config show` describes your ordinary settings; our explicit `--catalog` and
`--root` choose lesson locations for each subsequent command. The list should
contain `observations` and the info output one file,
`lesson-stations/temperatures.csv`. The plan should show **one file to download**.

If the plan instead reports staged data or a per-dataset root for
`lesson-stations`, remove that earlier lesson override before continuing.

## 4. Fetch twice

```bash
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml fetch observations
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml fetch observations
```

The first fetch downloads the CSV and checks its hash. The second reuses the
same file. Notice the HTTP request in the server terminal on the first fetch,
and no new data request on the second.

There are now two CSV files: the server's original and the copy at
`cache/lesson-stations/temperatures.csv`.

## 5. Read the result in Python

Save this as `read_observations.py` in the lesson directory:

```python
import csv
from pathlib import Path
from ethos_data import fetch

files = fetch(
    "observations",
    collections="collections.yaml",
    catalog=Path("catalogue/datacatalog.json").resolve(),
    root=Path("cache").resolve(),
)
table = files.one("temperatures.csv")
with table.open() as handle:
    values = [float(row["value"]) for row in csv.DictReader(handle)]
print(table)
print(sum(values) / len(values))
```

```bash
python read_observations.py
```

You should see an absolute cache path and `12.75`. The resource key identifies
the data; the returned path is how a library such as a CSV reader opens it.

## 6. Detect and repair a changed copy

Change only the **cache copy** from `B,13.0` to `B,14.0`:

```bash
python -c "from pathlib import Path; p = Path('cache/lesson-stations/temperatures.csv'); p.write_bytes(p.read_bytes().replace(b'13.0', b'14.0'))"
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml verify observations
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml verify observations --deep
```

The size check still passes: the edit changed no file length. The deep check
reports `wrong checksum` and exits unsuccessfully. This failure is intentional.

Keep the server running and repair:

```bash
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml verify observations --deep --repair --dry-run
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml verify observations --deep --repair
ethos-data --catalog catalogue/datacatalog.json --root cache -c collections.yaml verify observations --deep
python read_observations.py
```

The final verification reports one matching file and Python again prints
`12.75`. Stop the server with Ctrl+C. All practice files are confined to
`first-fetch-lesson`, which you can remove when finished.

You have followed an input from a collection through download, reuse, a Python
calculation, and integrity repair. For real work, continue with
[Set up your machine](../how-to/set-up-your-machine.md) and
[Get data for a task](../how-to/get-data-for-a-task.md). For the reasons behind the
separate metadata and storage locations, read
[Catalogues and storage](../explanation/catalogues-and-storage.md).
