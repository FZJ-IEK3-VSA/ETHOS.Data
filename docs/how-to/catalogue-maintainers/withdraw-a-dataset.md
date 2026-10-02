# Remove a dataset

Take a dataset that should not have been added out of the catalogue, the
shared caches and dCache. Removal is for data that must stop existing: a
wrongly accepted candidate, a licence that turned out to forbid what was done,
test data nobody needs. A correction is not a removal; it is a
[new version](publish-a-new-version.md).

The order is the reverse of publishing: **metadata first, bytes second**.
A catalogue that points at deleted bytes breaks every reader half-way.

## 1. Withdraw it from the catalogue

In the source checkout:

```bash
ethos-data catalog remove <name> --reason "<why>" --dry-run
ethos-data catalog remove <name> --reason "<why>"
git commit -am "Remove <name>: <why>"
```

`remove` records the dataset as withdrawn in its `status.yaml`, with the
reason, and rebuilds the index without it; a family name withdraws every
member. From now on the build and `publish` leave it out. Its description,
inventory and status file stay in the checkout until its bytes are gone.

If only the public listing was wrong, keep the dataset and hide it instead:
`ethos:visibility: hidden` with an embargo block that says why. Note why the
dataset was removed and what replaces it in the commit and in the issue.

## 2. Release the catalogue without it

[Release](release-the-catalogue.md) the internal and the public catalogue.
Readers keep being served the dataset until then, so nothing of its bytes may
go before.

## 3. Purge its cache entries and bytes

```bash
ethos-data catalog remove <name> --purge --dry-run
ethos-data catalog remove <name> --purge
```

`--purge` refuses until a release since the removal is recorded in the
dataset's `status.yaml`, and refuses a folder on dCache that another
dataset's copy lies in or around. Then it unlinks every link the status file
records and deletes every copy a cache owns, the restricted cache included,
purges the dataset's folder on dCache, which has no trash area, and deletes
the dataset's directory except its `status.yaml`. That file stays as a
tombstone: it records what happened, and `catalog add` refuses to give the
name to other bytes. Commit the deletion. A copy nobody recorded, an entry
made by hand, is not found; check the caches for one, and see
[Manage dCache folders](manage-dcache-folders.md) for the store.

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

