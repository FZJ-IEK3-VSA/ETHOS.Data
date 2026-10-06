# Publish a new version of a dataset

Replace the bytes of a dataset whose bytes were uploaded or materialized:
corrected files, or a new delivery from its source. Published objects never
change, so a new version is made beside the old one, in one of two ways:

| | Revision | Successor |
| --- | --- | --- |
| For | the same layout: files changed at the byte level, perhaps a few added | a changed layout: folders added, files moved, mostly new files |
| Keys | unchanged | new |
| On dCache | changed and new files under `<remote_prefix>@<revision>/`; unchanged ones stay where they are | a folder of its own |
| Collections files | unchanged | new keys under the same handles |
| The version before | readable through older catalogue releases | stays a dataset of its own, shown as superseded |

Choose a revision when the keys keep meaning the same files. A dataset that
is only linked has neither: it changes in place with its source, and a
rebuild follows it. Work in your own clone of the source catalogue.

## Make a revision {#revision}

Put the corrected files in a directory with the dataset's layout, then:

```bash
ethos-data catalog build my-dataset --revision --from /projects/shared/candidates/my-dataset-fix --dry-run
ethos-data catalog build my-dataset --revision --from /projects/shared/candidates/my-dataset-fix
```

The build compares the corrected files with the recorded inventory and names
every file that changed, is new, or is gone. A file that is gone takes its key
with it, and every collection that names the key breaks, so that is refused
unless `--remove-missing` says it is meant; a change that large is usually a
[successor](#successor). Without `--from`, the dataset's `source_dir` is the
input. Afterwards the dataset is built again, as revision 2, with the
corrected directory as its `source_dir`.

Make its bytes available and freeze it as for the first version:

```bash
ethos-data catalog upload my-dataset
ethos-data catalog record my-dataset
```

`upload` puts the changed and new files under `<remote_prefix>@2/`, leaves the
objects of the unchanged files where they are, and verifies every file at the
address it is served from. Commit the dataset's directory on a branch and
merge it by merge request on JuGit, then [release](release-the-catalogue.md):
a revision changes data, so it needs at least a minor release, and the
release refuses it until the upload of its new folder is verified. A release
names one revision of each dataset. A reader of the new release keeps it in
its own cache entry, `my-dataset@2/`, beside `my-dataset/`, and takes each
unchanged file from the earlier entry instead of downloading it again; a
workflow pinned to an older release keeps reading the revision it names.

A plain `catalog build` refuses other bytes for a dataset whose bytes were
uploaded or materialized. That refusal is how a change that needs a revision
announces itself.

## Make a successor {#successor}

A successor is a new dataset under a name you choose, `my-dataset-v2`, added
as any new dataset is, see [Add a dataset](add-a-dataset.md), whose
description names the dataset it replaces:

```yaml
ethos:supersedes: my-dataset
```

The build writes `ethos:superseded_by` into the replaced dataset's entry,
`ethos-data ls` marks it as superseded, and a collection that still reads it
warns. Commit both on a branch and merge them by merge request on JuGit.
Tell the package maintainers who use it: their collections files map the same
named paths to the new keys, so their workflow code does not change. The
replaced dataset stays until it is [removed](withdraw-a-dataset.md).
