# Get data for a task

Get the input data an ETHOS tool or workflow needs, from a script or from the
command line. The examples use ETHOS.RESKit; replace the collection and dataset
names with those of your package. They illustrate the interface and do not imply
those collections are available in every RESKit release. First
[set up the machine](set-up-your-machine.md) and use a released catalogue.

## In a script or notebook

### Feed a workflow by name

A collections file names the inputs a workflow takes. The file is your
project's own, or the one a package ships — its documentation names it.
`ethos_data.collections()` builds a handle on that file; its `paths()` fetches
the collection and returns those names resolved to absolute local paths, ready
to pass to the workflow:

```python
import ethos_data

data = ethos_data.collections("collections.yaml")
inputs = data.paths("onshore_wind", test=True)

era5_path = inputs["era5"]
gwa_100m_path = inputs["gwa_100m"]
height_scaling_data = {50: inputs["gwa_50m"], 200: inputs["gwa_200m"]}
```

`test=True` selects the collection's small test variant, so a first run takes
seconds. Drop it and the same code runs on the full data: both variants offer
the same names. The full data is the default so that a forgotten flag costs a
visible download rather than a silently wrong result — see
[Test and full variants](../explanation/test-data.md#test-and-full-variants-of-a-collection).
`inputs` is a dict; a name the collection does not define raises `KeyError`
listing the ones it does.

### Get a file or folder by key

If you know the resource key, the catalogue handle's `path()` returns one file
or folder; no collections file is needed for this:

```python
import ethos_data

catalog = ethos_data.catalog()
placements = catalog.path("reskit-test-data/placements/turbine_placements.csv")
era5_folder = catalog.path("reskit-test-data/era5")
```

`path()` downloads the data the first time and returns the absolute path of the
copy in the cache. The key is `<dataset>/<file>` for a file, and
`<dataset>/<folder>` or `<dataset>` for a folder. Asking for a `.shp` also
fetches its `.dbf`, `.shx` and other companion files.

`ethos_data.catalog()` reads the configured catalogue, or the public one. To
use the catalogue version a collections file pins, ask the handle's `.catalog`
instead:

```python
data = ethos_data.collections("collections.yaml")
era5_folder = data.catalog.path("reskit-test-data/era5")
```

On the command line, `ethos-data path` reads the configured catalogue — or the
pin of a file named with `-c collections.yaml`, of a configured default
collections file, or of a `collections.yaml` in the current directory.
`--catalog` and `$ETHOS_DATA_CATALOG` win over any pin.

### Get a whole collection

```python
files = data.fetch("onshore_wind")
gwa_100m = files.named["gwa_100m"]
```

`files` maps each key to its path. `files.paths` lists all paths,
`files.named` holds the same `{name: path}` mapping that `paths()` returns
(empty when the collection names none), and `files.one(suffix)` returns the
one file whose key ends with `suffix`. `fetch()` takes `test=True` too.

## Find out what a dataset contains

`path("global-wind-atlas-v4")` returns a folder. To get one file out of it,
list the dataset first; `ls` reads the catalogue and fetches nothing:

```bash
ethos-data ls global-wind-atlas-v4
```

Each line is a resource key with its size. That key is what `path()` takes to
return the one file:

```bash
ethos-data path global-wind-atlas-v4/<resource path>
```

```python
one_file = ethos_data.catalog().path("global-wind-atlas-v4/<resource path>")
```

`ls` also takes `<dataset>/<folder>` and a family name. From Python,
`ethos_data.catalog().resources("global-wind-atlas-v4")` returns the same files as
`Resource` objects, each with a `.key`.

## Which key do I need?

For a collection with named inputs, `info` ends with a `named paths` section
showing each name and the key behind it:

```bash
ethos-data -c collections.yaml info onshore_wind
ethos-data -c collections.yaml info onshore_wind --test
```

Use the name through `paths()` where you can; the key is there for when you
need one file directly. If the collection names no inputs, or not the one you
need, ask the package maintainer to add it under `paths:` — they know which
file the workflow wants, and
[naming it once](write-a-collections-file.md#2-name-the-inputs-a-workflow-takes)
spares every caller.

## On the command line

```bash
ethos-data -c collections.yaml list                        # the file's collections, one row per variant
ethos-data -c collections.yaml info onshore_wind --test    # the files and named inputs of the test variant
ethos-data -c collections.yaml plan onshore_wind           # what a fetch of the full data would download
ethos-data -c collections.yaml fetch onshore_wind          # download it
ethos-data -c collections.yaml paths onshore_wind --test   # fetch the test variant; print name<TAB>path
ethos-data path reskit-test-data/era5                      # the path of a file or folder; no collections file needed
ethos-data ls global-wind-atlas-v4                         # list a dataset's files, fetching nothing
```

`--test` goes before or after the subcommand. `-c collections.yaml` names the
collections file; without it, the collection commands read the configured
default or a `collections.yaml` in the current directory. A package that ships
its collections may also provide a command of its own for them; its
documentation says so. If the file declares an `all` collection for its
combined inputs:

```bash
ethos-data -c collections.yaml fetch all
```

## If a dataset is not available

- Licensed or proprietary data: [Work with restricted data](restricted-data.md).
- Data that is only in the internal catalogue:
  [Add the internal data catalogue](add-internal-catalogue.md).
- Anything else: [Identify and report a problem](report-a-problem.md).
