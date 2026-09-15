# Get data for a task

Get the input data an ETHOS tool or workflow needs, from a script or from the
command line. The examples use ETHOS.RESKit; replace `reskit` and the dataset
names with those of your package. They illustrate the interface and do not imply
those collections are available in every RESKit release. First
[set up the machine](set-up-your-machine.md) and use a released catalogue.

## In a script or notebook

Get the path of a file or folder:

```python
import ethos_data

placements = ethos_data.path("reskit-test-data/placements/turbine_placements.csv")
era5_folder = ethos_data.path("reskit-test-data/era5")
```

`path()` downloads the data the first time and returns the absolute path of the
copy in the cache. The key is `<dataset>/<file>` for a file, and
`<dataset>/<folder>` or `<dataset>` for a folder. Asking for a `.shp` also
fetches its `.dbf`, `.shx` and other companion files.

To use the catalogue version the package pins, add the package:

```python
era5_folder = ethos_data.path("reskit-test-data/era5", package="reskit")
```

Get a whole collection the package declares:

```python
files = ethos_data.fetch("onshore_wind", package="reskit")
```

`files` maps each key to its path. `files.paths` lists all paths, and
`files.one("gwa100-like.tif")` returns the one file whose key ends with that
name.

## On the command line

```bash
ethos-data -p reskit list                  # the package's collections
ethos-data -p reskit info onshore_wind     # the files in one collection
ethos-data -p reskit plan onshore_wind     # what a fetch would download
ethos-data -p reskit fetch onshore_wind    # download it
ethos-data path reskit-test-data/era5      # print the path of a file or folder
```

If the package declares an `all` collection for its combined inputs:

```bash
ethos-data -p reskit fetch all
```

## If a dataset is not available

- Licensed or proprietary data: [Work with restricted data](restricted-data.md).
- Data that is only in the internal catalogue:
  [Add the internal data catalogue](add-internal-catalogue.md).
- Anything else: [Identify and report a problem](report-a-problem.md).
