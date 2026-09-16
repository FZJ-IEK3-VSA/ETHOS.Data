# Add the internal data catalogue

ETHOS.Data uses the public catalogue unless you name another one. Point it at
the internal catalogue to also get datasets that are not public. The internal
catalogue lists the public datasets too.

Ask your administrator for the location of the internal catalogue. The examples
use `/shared/ethos/catalogue/current/datacatalog.json`.

## For all your work

```bash
ethos-data config set-catalog /shared/ethos/catalogue/current/datacatalog.json
```

## For one project

Run in the project folder:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/current/datacatalog.json --scope project
```

## For one shell or job

```bash
export ETHOS_DATA_CATALOG=/shared/ethos/catalogue/current/datacatalog.json
```

## For one command or call

```bash
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json -c collections.yaml list
```

`collections.yaml` is the collections file your project uses or the one a
package ships.

```python
ethos_data.catalog("/shared/ethos/catalogue/current/datacatalog.json").path(
    "my-internal-dataset/table.csv")
```

Each of these replaces the catalogue version a collections file pins. To reproduce a
result later, use a versioned directory such as
`/shared/ethos/catalogue/versions/<revision>/datacatalog.json` instead of
`current`.

## Check it

```bash
ethos-data config show
```

The output names the configured catalogue override and where it was set.
Run `ethos-data -c collections.yaml list` to check the actual selected
catalogue and confirm its descriptors are readable.

## Go back to the public catalogue

```bash
ethos-data config unset-catalog
```

Use `--scope project` if you set it for a project, and `unset ETHOS_DATA_CATALOG`
for the environment variable.

## See also

- [Use data already on disk](use-data-already-on-disk.md) — if an internal
  dataset is reported as not available.
- [Troubleshoot catalogue access](troubleshoot-catalogue.md)
