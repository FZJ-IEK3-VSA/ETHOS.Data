# Link existing data into the cache

Make data that already lies on the cluster computer available through the
shared public cache without copying it. A link is the bridge for datasets
that cannot be moved yet: old code keeps reading the original path,
ETHOS.Data readers find the same bytes under the catalogue's name. You need a described and built dataset
and a directory with the catalogue's relative layout. Paths are examples.

## Choose the mechanism

| Need | Use |
| --- | --- |
| Share an existing directory with everyone through the cache | A cache link, below |
| Make the cache own an independent copy | [Materialize](materialize-linked-data.md) |
| Use one dataset from a private directory, for your account only | A dataset-root override, at the end of this page |
| A licensed dataset | [Add restricted data](add-restricted-data.md); `link --all` skips it on purpose |
| Data that is not catalogued yet | [Staging](../package-maintainers/stage-development-data.md) |

## Link one dataset {#cache-links}

On the cluster computer, with the catalogue and cache the users read:

```bash
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json --root /shared/ethos/public \
    link climate-inputs /projects/legacy/climate-inputs
```

The entry `/shared/ethos/public/climate-inputs` now points at the directory,
and every reader of that cache uses it in place. The directory is recorded as
given, not resolved. If the catalogue's first file is not found under it, the
link is still made and a warning names the file; the usual cause is naming a
level too high.

Without a directory, `link` reads the dataset's `source_dir` from the source
checkout:

```bash
ethos-data --root /shared/ethos/public link climate-inputs --catalog-root /shared/ethos/catalogue/source
```

A dataset with unresolved licensing is refused: a cache entry hands it to
everyone. A real directory in the cache is never replaced by a link; that is
data the cache owns. `--force` repoints an entry that is already a link.

## Link every dataset the source catalogue describes

```bash
ethos-data link --all --catalog-root /shared/ethos/catalogue/source --root /shared/ethos/public --dry-run
ethos-data link --all --catalog-root /shared/ethos/catalogue/source --root /shared/ethos/public
```

Review the preview: it names the root and the checkout before anything is
written. Restricted datasets, datasets with unresolved licensing, datasets
without `source_dir` and entries that are already real directories are left
alone and reported as such. A `source_dir` that does not exist on this
machine is reported as `missing` and gives exit status `1` without stopping
the rest.

Avoid `--prune` while the catalogue is still behind the filesystem: it also
removes links for datasets the catalogue no longer lists. It never removes a
real directory.

## Remove a link

```bash
ethos-data --root /shared/ethos/public unlink climate-inputs
```

Only a link is removed; the directory it pointed at is untouched, and a real
directory is refused.

## Check

```bash
ls -l /shared/ethos/public/climate-inputs
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json fetch climate-inputs/<one file>
```

Expect the link and a path under the original directory, with no download.
For a hash check of the whole dataset, follow
[Check a whole dataset](../data-users/verify-and-repair.md#verify-complete-dataset).

Create links on the cluster computer. A Windows workstation needs
Developer Mode or elevation for symbolic links, and directory junctions are
unsuitable because the cache would treat them as directories it owns.

## Dataset-root override, for one account {#dataset-root-overrides}

To read one dataset from a directory of your own without touching the shared
cache:

```bash
ethos-data config set-root global-wind-atlas-v4 /data/GWA_4.0
ethos-data config unset-root global-wind-atlas-v4
```

The override wins over every cache and applies to your configuration scope
only. It does not make a restricted dataset downloadable and it does not
change the catalogue.
