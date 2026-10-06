# Remove a dataset

Take a dataset that should not have been added out of the catalogue, the
cluster's caches and dCache. Removal is for data that must stop existing: a
wrongly accepted candidate, a licence that turned out to forbid what was done,
test data nobody needs. A correction is not a removal; it is a new version at
new paths, see [Licensing and immutability](../../explanation/licensing.md).

The order is the reverse of publishing: **metadata first, bytes second**.
A catalogue that points at deleted bytes breaks every reader half-way. The
bytes go only after a major release, because the releases of the current
major made before the withdrawal still describe the dataset.

## 1. Withdraw it and release

In your own clone of the source catalogue:

```bash
ethos-data catalog remove <name> --reason "<why>" --dry-run
ethos-data catalog remove <name> --reason "<why>"
```

`remove` records the dataset as withdrawn in its `status.yaml`, with the
reason, and rebuilds the index without it; a family name withdraws every
member. Its description, its status file, its cache entries and its bytes
stay. Commit, merge on JuGit, then [release](release-the-catalogue.md) the
internal and the public catalogue: a withdrawal needs a minor release. Note
why the dataset was removed and what replaces it in the commit and in the
issue.

If only the public listing was wrong, keep the dataset and hide it instead:
`ethos:visibility: hidden` with an embargo block that says why.

## 2. Purge it after a major release

After the next major release:

```bash
ethos-data catalog remove <name> --purge --dry-run
ethos-data catalog remove <name> --purge
```

Before it deletes anything, `--purge` refuses when no major release is
recorded after the removal, when another dataset's folder on dCache lies in or
around this one, and when a recorded entry lies in a cache your account cannot
write; it names the dataset and the cache. Whoever purges therefore needs
write access to every cache that holds the dataset, the restricted cache of
its group included.

Then it deletes the links and copies recorded in the cluster's public cache
and in the restricted caches, purges the dataset's folders on dCache, which
has no trash area, and deletes the dataset's directory except its
`status.yaml`. That file stays as a tombstone, so `catalog add` refuses the
name for other bytes. Entries nobody recorded, such as downloads in the
cluster's public cache or links made without `--catalog-root`, are reported,
not deleted. Public caches on other machines are never touched. Commit and
merge the deletion.

A purge deletes withdrawn datasets only. Earlier revisions of a dataset that
is still in the catalogue stay as long as the dataset does. If the bytes must
go at once, for example because a licence forbids further distribution, make
an unplanned major release.

## 3. Check and tell people

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ethos-data/<remote prefix>/<one file>
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json ls | grep <name>
```

Expect `404` and no listing. Then tell the maintainers of every package whose
collections name the dataset: the removed name, the reason, the last release
that describes it, and the replacement. Releases before the major release
still describe the dataset, but its bytes are gone, and copies on users' own
machines remain; removal notifies nobody by itself and corrects no earlier
result.

