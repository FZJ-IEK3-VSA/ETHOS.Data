# Withdraw a dataset

Removing bytes that are already published is a different, more dangerous
operation than uploading. Do it deliberately. It needs the same credentials as
[Upload a dataset](upload-a-dataset.md#credentials-once-per-machine).

## Read this first: deleting is not how a dataset changes

**Published paths are immutable.** If a dataset's *content* changed, the fix is
publishing the new bytes at a new path — never deleting the old file. Somebody
may already have it cached and hash-verified, and a file that changes under a
fixed path breaks every reproducible run that referenced it.

Delete only when you mean to make something **stop existing**: cleaning up test
data, or genuinely withdrawing a dataset.

## The order is the opposite of publishing

**Unpublish the catalogue entry before deleting the bytes.** If you delete
first, the public catalogue still points at a path that now 404s, and anyone
resolving it mid-way gets a broken reference instead of a clean "not published".

### 1. Take it out of the catalogue

In `datasets/<name>/dataset.yaml`, either set `ethos:visibility: hidden` and add
the required `ethos:embargo` block (see
[Describe a dataset](describe-a-dataset.md#datasets-that-are-not-ready-to-publish)),
or delete the dataset directory entirely if it is never coming back.

### 2. Republish

```bash
ethos-data catalog build
ethos-data catalog publish ../ETHOS.Data-Catalogue
```

This removes it from the public `datacatalog.json` and deletes its
`datasets/<name>/` from the public repository — `publish` prunes anything it no
longer generates. Commit and push both repositories.

A consumer whose collections file still names the dataset now gets a clear
message rather than a mystery: `list` reports that one collection as
`[unresolvable]`, with the explanation that it has been withdrawn and the
suggestion to pin an older catalogue.

### 3. Now delete the bytes

```bash
rclone delete HIFIS:ice2-data-files/<prefix>/<path/to/file>   # one file
rclone purge  HIFIS:ice2-data-files/<prefix>                  # a folder, recursively — irreversible
rclone rmdir  HIFIS:ice2-data-files/<prefix>                  # an empty folder only
```

!!! warning "`purge` does not ask"
    Run `rclone lsf -R HIFIS:ice2-data-files/<prefix>` first if you want to see
    what it is about to take with it. There is no trash: a deleted file is gone.

### 4. Confirm

Exactly what a public user gets, with no credentials:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files/<prefix>/
```

Want `404`.

## The namespace API alternative

Useful for scripting a deletion into something else — this is what
`ethos-data catalog check-store` uses to clean up after itself. **Delete the files
inside a directory before the directory itself**: a single `DELETE` on a
non-empty directory fails rather than recursing.

```bash
curl -X DELETE -H "Authorization: Bearer $(oidc-token HIFIS)" \
  "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/ice2-data-files/<prefix>/<file>"
curl -X DELETE -H "Authorization: Bearer $(oidc-token HIFIS)" \
  "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/ice2-data-files/<prefix>"
```

Both act on the same tree as `rclone`.

## Cleaning up test and probe data

Everything synthetic lives under a `_`-prefixed folder specifically so it can be
wiped in one shot, nowhere near real data:

```bash
rclone purge HIFIS:ice2-data-files/_probe
curl -s -o /dev/null -w 'gone? %{http_code}\n' \
  https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files/_probe/     # want 404
```

Locally, remove the corresponding `datasets/probe-*` directories and their
source data — but only once real datasets are in the catalogue. The probe
fixtures are what prove the upload/download round trip still works.

## What about users who already have it?

Nothing on their machines changes. A withdrawn dataset that is already in
somebody's cache stays there and stays valid — the checksums in their pinned
catalogue still describe the bytes they hold. Withdrawal stops new resolutions,
not old ones.

If the data is being withdrawn because it is *wrong* rather than because it is
finished, say so somewhere people will read it. Deletion is not a notification.

## See also

- [Publish the catalogue](publish-the-catalogue.md).
- [Licensing and immutability](../explanation/licensing.md).
