# Work with restricted data

Read licensed data from an authorised local installation. You need its dataset
identifier, the catalogue describing it, and permission to read the files.

## Configure an existing copy

If the description is hidden, [select the internal catalogue](add-internal-catalogue.md).

For a root containing one directory per dataset:

```bash
ethos-data config set-restricted-cache /path/to/ethos-restricted
```

For one dataset in another location:

```bash
ethos-data config set-root licensed-example /path/to/licensed-example
```

Use the actual installation paths. The second form points directly to the
dataset's files; do not append its name again.

## Check and use the data

Replace the package and collection below with the workflow requiring the dataset:

```bash
ethos-data config show
ethos-data -p reskit plan onshore_wind
ethos-data -p reskit verify onshore_wind --deep
ethos-data -p reskit fetch onshore_wind
```

The restricted files must be available in place and match the inventory.
Fetching reads them there; it never downloads or repairs restricted bytes.

## Obtain a missing required input

Read the `ethos:restriction` access note in the error/descriptor and contact the
named custodian. Request both permission and the installation location.
Selecting a restricted cache cannot grant access. Report an unreadable or
mismatched installation through the internal support channel.

## Skip an optional input

Only if the workflow explicitly handles omitted data:

```bash
ethos-data --skip-unavailable -p reskit fetch onshore_wind
```

Keep the global option before `fetch`. For Python, first enable the preference
with `ethos-data config set-skip-unavailable true --scope project` in the project
directory. Skipped resources are absent from the result:

```python
import ethos_data

files = ethos_data.fetch("onshore_wind", package="reskit")
if "licensed-example/layer.tif" in files:
    layer = files["licensed-example/layer.tif"]
```

For a persistent preference, use `config set-skip-unavailable true`; undo it with
`config unset-skip-unavailable` in the same scope. Required inputs and tests should fail if absent.

See [Report a problem](report-a-problem.md) or, for administrators,
[Add internal and restricted datasets](add-internal-and-restricted-data.md).
