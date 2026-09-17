# Create, rename, and delete dCache folders

Use an authorised rclone remote from [Set up dCache access](set-up-dcache-access.md).
The examples use `HIFIS:ice2-data-files`; confirm the VO and publication root
before substituting your own folder names. ETHOS.Data has no `catalog mkdir`,
`rename`, or `delete` command.

## Create a folder

```bash
rclone lsd HIFIS:ice2-data-files
rclone mkdir HIFIS:ice2-data-files/_practice
rclone lsd HIFIS:ice2-data-files
```

Expect `_practice` in the listing. [mkdir](https://rclone.org/commands/rclone_mkdir/)
creates a missing directory. A folder alone is not a catalogue entry.
For a new public publication root, establish its permissions before uploading;
see [Bootstrap a catalogue](bootstrap-a-catalogue.md#2-prepare-the-publication-root).

## Rename an unpublished folder

Use this only for unpublished scratch/candidate data. Confirm the destination
does not already exist; `moveto` can merge directories and overwrite files.

```bash
rclone lsf -R HIFIS:ice2-data-files/_candidate-old
rclone lsd HIFIS:ice2-data-files
rclone moveto HIFIS:ice2-data-files/_candidate-old HIFIS:ice2-data-files/_candidate-new --dry-run
rclone moveto HIFIS:ice2-data-files/_candidate-old HIFIS:ice2-data-files/_candidate-new
rclone lsf -R HIFIS:ice2-data-files/_candidate-new
```

Inspect the preview before the real command and check the destination contents
afterwards. See [moveto](https://rclone.org/commands/rclone_moveto/).
Update any unpublished descriptor's `ethos:remote_prefix`, rebuild, and check
the intended URLs before releasing it.

For released datasets, retain the old path for existing pins. Publish a new
version at a new path rather than rename its storage. See
[Licensing and immutability](../../explanation/licensing.md#paths-are-immutable).

## Delete an empty folder

```bash
rclone rmdir HIFIS:ice2-data-files/_practice --dry-run
rclone rmdir HIFIS:ice2-data-files/_practice
```

[rmdir](https://rclone.org/commands/rclone_rmdir/) refuses a non-empty directory.

## Delete a file or an entire folder

For an actual published withdrawal, first
[remove the current catalogue entry](withdraw-a-dataset.md). For scratch data,
inspect exactly what you will delete:

```bash
rclone lsf -R HIFIS:ice2-data-files/_candidate-new
rclone deletefile HIFIS:ice2-data-files/_candidate-new/obsolete.csv --dry-run
rclone deletefile HIFIS:ice2-data-files/_candidate-new/obsolete.csv
```

[deletefile](https://rclone.org/commands/rclone_deletefile/) deletes one file.
To remove the entire selected directory and its contents:

```bash
rclone purge HIFIS:ice2-data-files/_candidate-new --dry-run
rclone purge HIFIS:ice2-data-files/_candidate-new
rclone lsd HIFIS:ice2-data-files
```

[purge](https://rclone.org/commands/rclone_purge/) recursively removes the folder;
it does not use a trash area. Never target the publication root to clean one
dataset. Confirm the removed folder is absent from the final listing.
