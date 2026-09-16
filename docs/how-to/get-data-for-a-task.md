# Get data by catalogue key

Use a catalogue key to retrieve a dataset, family, folder or individual file.
You need [ETHOS.Data installed](../installation.md) and access to the selected
catalogue. For a package workflow's collections and named inputs, use that
package's API and wrapper; [RESKit's input-data guide](https://ethos-reskit.readthedocs.io/en/latest/how_to/get_input_data.html)
is one example.

## Find a key

```bash
ethos-data ls
ethos-data ls global-wind-atlas-v4
```

The first command lists dataset names, access classes and titles. The second
lists resource keys and sizes. These commands retrieve metadata only.
Copy a key from the output rather than guessing a filename.

## Fetch the file or folder

```bash
ethos-data fetch reskit-test-data/era5
```

Replace the example with your key. `fetch` prints an absolute path after making
the selected data available. Downloaded bytes are checked and cached; later
calls reuse them. A shapefile includes its sidecars. A folder or family fetch
retrieves every file under that key, so inspect the listing before requesting
a large dataset.

In Python:

```python
import ethos_data

catalog = ethos_data.catalog()
for resource in catalog.resources("reskit-test-data/era5"):
    print(resource.key, resource.bytes)

directory = catalog.path("reskit-test-data/era5")
assert directory.is_dir()
```

## Select a particular catalogue

```bash
ethos-data --catalog /path/to/datacatalog.json ls reskit-test-data/era5
ethos-data --catalog /path/to/datacatalog.json fetch reskit-test-data/era5
```

In Python, pass the same location to `ethos_data.catalog(location)`.
The CLI takes no collections file; it uses the explicit/configured catalogue
or the built-in public one. See [Set up your machine](set-up-your-machine.md)
for persistent settings.

To retrieve keys from the catalogue RESKit pins, use `reskit-data path KEY`
or `reskit.data.handle().catalog.path(KEY)`. For its workflow inputs, use
`reskit-data paths COLLECTION` or `reskit.data.paths(COLLECTION)`. The
[package-command reference](../reference/cli/package-data.md) describes their
shared behaviour.

## Check the result

Open the returned path with the reader your workflow uses. Linked, staged and
restricted inputs may be returned from an existing installation. To check
those files against catalogue hashes, follow [Verify and repair](verify-and-repair.md).

An unknown key, unreadable catalogue or unavailable input exits with an error
instead of printing a usable path. See [Diagnose catalogue problems](troubleshoot-catalogue.md).
