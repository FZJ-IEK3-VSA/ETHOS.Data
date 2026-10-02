# Materialize linked data

Replace a cache link with a real, checksum-verified copy that the cache owns,
so the original directory can later be retired. You need the dataset built in
the catalogue, the link or a readable source directory, and room on the
filesystem. Paths are examples.

## 1. Prepare the destination

Set the permissions and default ACLs of the cache root first: copying does not
carry over the source's ownership. Keep the source unchanged while copying.

## 2. Preview, then copy {#materialize-copies}

```bash
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json --root /shared/ethos/public \
    materialize climate-inputs --dry-run
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json --root /shared/ethos/public \
    materialize climate-inputs --catalog-root /shared/ethos/catalogue/source
```

`--catalog-root` records the copy in the dataset's `status.yaml`, in place of
the link it replaces.

Only the files the catalogue describes are copied, each is checked against its
recorded size and hash, and the link is replaced only after the whole copy
passed. The command refuses to fill the filesystem below 2 % free. Leave
checksum verification on. Readers see the link briefly absent at the switch;
pause jobs that read the dataset for that moment.

To seed an entry that does not exist yet, or to copy from somewhere other than
the link target, add `--from DIR`; this form takes one dataset. Without a link
and without `--from`, the dataset's `source_dir` from the source checkout is
used.

`materialize --all` converts every link in the public cache; preview it with
`--dry-run` and expect it to take a while.

## 3. Check the result

```bash
ls -ld /shared/ethos/public/climate-inputs
cat /shared/ethos/public/climate-inputs/.ethos-data-materialized.json
```

Expect a real directory and a provenance record naming the source and the
time. Then follow [Check a whole dataset](../data-users/verify-and-repair.md#verify-complete-dataset)
with `deep=True`.

## 4. Retire the original {#retire-the-original}

While the original directory remains the dataset's `source_dir`, a rebuild
reads it, so the original stays the authority and the copy may fail
verification after an edit there. Before the original is removed:

1. Freeze the dataset, in the source checkout:

    ```bash
    ethos-data catalog record climate-inputs
    ```

    It checks the copy file by file, makes it the authoritative copy and
    retires `source_dir`.
2. Rebuild. The recorded inventory is kept as it is; the copy is not rehashed,
   so the independent baseline that detects later corruption survives.
3. [Release](release-the-catalogue.md) the new internal version.

Ask the owner of the original to check for scripts, links and root overrides
that still read the old path before deleting it. A public copy can afterwards
be [uploaded](upload-a-dataset.md); a restricted copy stays local, see
[Add restricted data](add-restricted-data.md).
