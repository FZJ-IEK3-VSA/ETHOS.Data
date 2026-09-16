# Withdraw a dataset

Remove an entry from the current public catalogue, and only delete remote bytes
if withdrawal requires it. For a correction, publish a new version while
retaining the old paths; see [Licensing and immutability](../explanation/licensing.md).

## 1. Remove the current public entry

In the source catalogue, set `ethos:visibility: hidden` and add the required
`ethos:embargo` block, or remove the dataset's metadata directory if the entry
is being removed entirely.

```bash
ethos-data catalog build
ethos-data catalog publish ../ETHOS.Data-Catalogue
```

Review the generated diff. Release the source/public revisions and deploy the
updated internal tree as appropriate. Record why the dataset was withdrawn and
which replacement, if any, consumers should use.

## 2. Check old consumers before deleting bytes

An older pinned catalogue still describes the dataset. Hiding today's entry does
not revoke those pins, erase existing caches, or prevent access through a known
URL. Prefer retaining bytes needed for reproduction.

If withdrawal requires removing bytes, identify the exact remote prefix and
check whether other datasets share it. Follow
[Delete a file or folder](manage-dcache-folders.md#delete-a-file-or-an-entire-folder)
with a preview first. Do not delete the publication root.

## 3. Verify and communicate the withdrawal

Confirm the entry is absent from the newly published index. If bytes were deleted,
check the exact former resource URL without credentials and confirm it is no
longer retrievable.

Tell affected package maintainers the withdrawn identifiers, reason, last usable
revision, and replacement. Ask them to update their collections or document why
an old pin is retained. Existing copies remain on users' machines; deletion does
not notify users or correct their previous results.

See [Publish the catalogue](publish-the-catalogue.md) and
[Report a problem](troubleshoot-catalogue.md#report-a-problem).
