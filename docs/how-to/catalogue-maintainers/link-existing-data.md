# Link existing data into the cache

Make public data that already lies on the cluster computer available through
the cluster's public cache without copying it. A link is the bridge for
datasets that cannot be moved yet: existing scripts keep reading the original path,
ETHOS.Data readers find the same bytes under the catalogue's name. You need a described and built dataset
and a directory with the catalogue's relative layout. Paths are examples.

## Choose the mechanism

| Need | Use |
| --- | --- |
| Share an existing directory with every cluster user through the cache | A cache link, below |
| Make the cache own an independent copy | [Materialize](materialize-linked-data.md) |
| Restricted data | [Add restricted data](add-restricted-data.md): a link by name into the restricted cache of its access combination; `link --all` skips it |
| Data that is not catalogued yet | [Staging](../package-maintainers/stage-development-data.md) |
| A copy on a workstation | A link into that machine's own caches, see [below](#workstation-copy) |

## Link one dataset {#cache-links}

On the cluster computer, with the catalogue and cache the users read:

```bash
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json --root /shared/ethos/cache \
    link climate-inputs /projects/climate/climate-inputs --catalog-root <your clone>
```

The entry `/shared/ethos/cache/climate-inputs` points at the directory, and
every reader of that cache uses it in place. The link keeps the directory as
given, not resolved. If the catalogue's first file is not found under it, the
link is still made and a warning names the file; the usual cause is naming a
level too high. `--catalog-root` records the link in your own clone of the
source catalogue, so that a purge finds it later. Commit the dataset's status
file on a branch and merge it by merge request on JuGit.

Without a directory, `link` reads the dataset's `source_dir` from your clone:

```bash
ethos-data --root /shared/ethos/cache link climate-inputs --catalog-root <your clone>
```

A restricted dataset is refused here, and so is a dataset with unresolved
licensing: a cache entry hands it to everyone. A real directory in the cache
is never replaced by a link; that is data the cache owns. `--force` repoints
an entry that is already a link.

## Link every public dataset the source catalogue describes

Run this from your own clone, at the merged state of the release the cluster
serves, so that the links match what users read:

```bash
ethos-data link --all --root /shared/ethos/cache --catalog-root <your clone> --dry-run
ethos-data link --all --root /shared/ethos/cache --catalog-root <your clone>
```

Review the preview: it names the root and the checkout before anything is
written. It links public data only, and refuses a restricted cache your
account lists as its root. Restricted datasets, datasets with unresolved
licensing, datasets without `source_dir` and entries that are already real
directories are left alone and reported as such. A `source_dir` that does not
exist on this machine is reported as `missing` and gives exit status `1`
without stopping the rest.

Avoid `--prune` while the catalogue is still behind the filesystem: it also
removes links for datasets the catalogue no longer lists. It never removes a
real directory.

## Remove a link

```bash
ethos-data --root /shared/ethos/cache unlink climate-inputs
```

Only a link is removed; the directory it pointed at is untouched, and a real
directory is refused.

## Check

```bash
ls -l /shared/ethos/cache/climate-inputs
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json fetch climate-inputs/<one file>
```

Expect the link and a path under the original directory, with no download.
For a hash check of the whole dataset, follow
[Check a whole dataset](../data-users/verify-and-repair.md#verify-complete-dataset).

## A copy on a workstation {#workstation-copy}

A copy that already lies on a workstation is linked the same way, into that
machine's own caches: `ethos-data link NAME DIR` makes a public dataset's
entry in your public cache a link to DIR, and a restricted dataset's entry in
a restricted cache you list, as under
[Set up your machine](../data-users/set-up-your-machine.md#public-installation-users).
There is no setting per dataset.

Windows needs Developer Mode or elevation for symbolic links. Without either,
`link` refuses and offers `ethos-data materialize NAME --from DIR`, a
verified copy. Directory junctions are unsuitable, because the cache would
treat them as directories it owns.
