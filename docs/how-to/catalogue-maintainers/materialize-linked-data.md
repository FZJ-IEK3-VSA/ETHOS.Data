# Materialize linked data

Replace a cache link with a real, checksum-verified copy that the cache owns,
so the original directory can later be retired. You need the dataset built in
the catalogue, the link or a readable source directory, and room on the
filesystem. Paths are examples.

## 1. Prepare the destination

Check the permissions and default ACLs of the cache root first; on the
cluster computer the administrators set them. Copying does not carry over the
source's ownership. Keep the source unchanged while copying.

## 2. Preview, then copy {#materialize-copies}

```bash
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json --root /shared/ethos/cache \
    materialize climate-inputs --dry-run
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json --root /shared/ethos/cache \
    materialize climate-inputs --catalog-root <your clone>
```

`--catalog-root` records the copy in your own clone of the source catalogue,
in place of the link it replaces.

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
ls -ld /shared/ethos/cache/climate-inputs
cat /shared/ethos/cache/climate-inputs/.ethos-data-materialized.json
```

Expect a real directory and a provenance record naming the source and the
time. Then follow [Check a whole dataset](../data-users/verify-and-repair.md#verify-complete-dataset)
with `deep=True`.

## 4. Retire the original {#retire-the-original}

While the original directory is the dataset's build input (`source_dir` in
its status file), a rebuild reads it, so the original stays the authority and
the copy may fail verification after an edit there. Before the original is
removed, freeze the dataset on its copy, in your own clone:

```bash
ethos-data catalog --catalog-root <your clone> record climate-inputs     --copy /shared/ethos/cache/climate-inputs
```

`catalog record` checks the copy file by file, makes it the authority and
retires `source_dir`. The recorded inventory is kept as it is; the copy is not
rehashed, so the independent baseline that detects later corruption survives.
Commit the status file on a branch and merge it by merge request on JuGit.

Ask the owner of the original to check for scripts and links that still read
the old path before deleting it. A public copy can afterwards be
[uploaded](upload-a-dataset.md); a restricted copy stays in its restricted
cache, see [Add restricted data](add-restricted-data.md).
