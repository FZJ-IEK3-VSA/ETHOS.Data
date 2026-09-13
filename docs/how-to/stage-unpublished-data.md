# Stage uncatalogued data

Use a dataset that is not in the catalogue yet through the ordinary ETHOS.Data
calls while you develop it.

## 1. Choose a staging directory

```bash
ethos-data config set-staging-cache /scratch/me/ethos-staging
```

## 2. Stage the dataset

```bash
ethos-data staging add my-new-dataset /scratch/me/new-data --note "regenerated 2026-09-04"
ethos-data staging list
```

The directory is linked into the staging directory. Add `--copy` to copy it
instead.

## 3. Use it

In a script, by path:

```python
import ethos_data

table = ethos_data.path("my-new-dataset/results/table.csv")
folder = ethos_data.path("my-new-dataset")
```

In your package, add it to the collections file like any catalogued dataset:

```yaml title="reskit/data/collections.yaml"
collections:
  my_workflow:
    include:
      - dataset: my-new-dataset
```

```bash
ethos-data -p reskit fetch my_workflow
```

```python
files = ethos_data.fetch("my_workflow", package="reskit")
```

Every read from staging warns that the data is staged, and
`ethos-data verify` reports staged files as `unverifiable`.

## 4. Stop staging

After the dataset has been accepted into the catalogue:

```bash
ethos-data staging remove my-new-dataset
ethos-data config unset-staging-cache
```

Run the workflow again and check that no staging warning remains.

## Options

| Flag | |
|---|---|
| `--note "…"` | a description, shown by `staging list` |
| `--copy` | copy the data instead of linking it |
| `--new-only` (on `list`) | only datasets that are not in the public or restricted cache |
| `--force` (on `remove`) | required if the entry is a copy rather than a link |

Restricted datasets cannot be staged.

## See also

- [Propose a dataset](propose-a-dataset.md) — get the dataset into the catalogue.
- [Develop and propose a dataset](../tutorials/develop-and-propose-data.md) —
  a tutorial that stages a tiny dataset on your own machine.
- [Caches, classes and roots](../explanation/caches-and-access.md) — how
  staging relates to the other caches.
