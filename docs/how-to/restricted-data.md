# Work with restricted data

Restricted datasets are licensed or proprietary. ETHOS.Data never downloads
them; it reads your own copy in place.

## If you have a copy

Set the restricted cache to the directory that holds your restricted datasets,
one subdirectory per dataset:

```bash
ethos-data config set-restricted-cache /path/to/ethos_data_restricted
```

Each dataset is then read from `<restricted cache>/<dataset>/…`. For other ways
to set it, see [Configure the cache](configure-the-cache.md).

For one dataset stored somewhere else:

```bash
ethos-data config set-root licensed-example /path/to/licensed-example
```

## If you do not have a copy

Leave restricted datasets out instead of stopping:

```bash
ethos-data -p reskit fetch onshore_wind --skip-unavailable   # one command
ethos-data config set-skip-unavailable true                  # every command
```

The datasets that were left out are listed. In Python, their files are missing
from the result and a `UserWarning` names them:

```python
files = ethos_data.fetch("onshore_wind", package="reskit")
if "licensed-example/layer.tif" not in files:
    ...
```

To stop on missing data again: `ethos-data config unset-skip-unavailable`.

## Find out how to obtain a dataset

Without a copy, asking for a restricted dataset stops with a message that
includes the dataset's access note — whom to contact, or where to license it:

```title="Output"
dataset 'licensed-example' is restricted and is never downloaded.
  Licensed from <vendor> under contract <ref>. Redistribution prohibited.
No restricted cache is configured on this machine.

If you have a copy, say where it is:
    ethos-data config set-restricted-cache /path/to/ethos_data_restricted
    ethos-data config set-root licensed-example /path/to/licensed-example    # just this one

If you do not, carry on without it:
    ethos-data ... --skip-unavailable
    ethos-data config set-skip-unavailable true    # once, for this machine
Datasets you cannot reach are then left out of the result and listed, rather than silently missing.
```

## Check your copy

```bash
ethos-data -p reskit verify --all --deep
```

Files you have no copy of are reported as `unavailable here`.

## See also

- [Add internal and restricted datasets](add-internal-and-restricted-data.md) —
  for catalogue maintainers.
- [Caches, classes and roots](../explanation/caches-and-access.md)
