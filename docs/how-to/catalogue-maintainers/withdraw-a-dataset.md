# Remove a dataset

Take a dataset that should not have been added out of the catalogue, the
shared caches and dCache. Removal is for data that must stop existing: a
wrongly accepted candidate, a licence that turned out to forbid what was done,
test data nobody needs. A correction is not a removal; it is a new version at
new paths, see [Licensing and immutability](../../explanation/licensing.md).

The order is the reverse of publishing: **metadata first, bytes second**.
A catalogue that points at deleted bytes breaks every reader half-way.

## 1. Remove the catalogue entry

In the source checkout, delete the dataset's directory and rebuild:

```bash
git rm -r datasets/<name>
ethos-data catalog build
ethos-data catalog publish ../ETHOS.Data-Catalogue
```

If only the public listing was wrong, keep the dataset and hide it instead:
`ethos:visibility: hidden` with an embargo block that says why. Review both
diffs, then [release](release-the-catalogue.md) the internal version and the
public revision. Note why the dataset was removed and what replaces it in the
commit and in the issue.

## 2. Remove the cache entries

```bash
ethos-data --root /shared/ethos/public unlink <name>
```

`unlink` removes a link and leaves its target alone. A materialized entry is a
real directory the cache owns; `unlink` refuses it, so remove it by hand after
checking that nothing else reads it:

```bash
ls -ld /shared/ethos/public/<name>
rm -r /shared/ethos/public/<name>
```

A restricted entry lives in the restricted cache; treat it the same way.

## 3. Delete the bytes on dCache

Only after the new catalogue is released. Find the exact remote prefix from
the removed descriptor and check that no other dataset shares it:

```bash
rclone lsf -R HIFIS:ethos-data/<remote prefix>
rclone purge HIFIS:ethos-data/<remote prefix> --dry-run
rclone purge HIFIS:ethos-data/<remote prefix>
```

`purge` removes the folder and everything in it without a trash area. Never
target the publication root to clean one dataset. See
[Manage dCache folders](manage-dcache-folders.md).

## 4. Check and tell people

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ethos-data/<remote prefix>/<one file>
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json ls | grep <name>
```

Expect `404` and no listing. Then tell the maintainers of every package that
pinned the dataset: the removed name, the reason, the last revision that
still describes it, and the replacement. Older pinned catalogue revisions
still describe the dataset, and copies on users' machines remain; removal
notifies nobody and corrects no earlier result.

!!! warning "Gap: removal is four manual steps"
    No command removes a dataset from the catalogue, the caches and dCache
    together, and nothing checks the order. A `catalog remove <dataset>` that
    refuses to delete bytes while a released catalogue still lists them would
    encode the rule above.
