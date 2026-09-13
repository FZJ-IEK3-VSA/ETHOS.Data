# Use data already on disk

Read a catalogued dataset from a directory you already have, instead of
downloading it.

## Point the dataset at the directory

```bash
ethos-data config set-root global-wind-atlas-v4 /data/GWA_4.0
```

The directory must have the same layout as the dataset in the catalogue. Add
`--scope project` to set it for one project folder only.

## Check it

```bash
ethos-data config show                           # lists the dataset and its directory
ethos-data -p reskit plan onshore_wind           # reports its files as used in place
ethos-data -p reskit verify onshore_wind --deep  # compares the files with the catalogue
```

## Remove it

```bash
ethos-data config unset-root global-wind-atlas-v4
```

The dataset is downloaded into the public cache the next time it is needed.

## Related tasks

- Licensed or proprietary data: [Work with restricted data](restricted-data.md).
- A shared cache that links to data on disk is set up by a catalogue
  maintainer: [Migrate cluster data](migrate-cluster-data.md).
- Turn a linked dataset into your own copy:
  [Verify and repair](verify-and-repair.md#materialize-turning-a-borrowed-dataset-into-one-you-own).
