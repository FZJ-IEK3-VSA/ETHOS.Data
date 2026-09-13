# Publish the catalogue

The public catalogue is **generated**. `ethos-data catalog publish` regenerates it
from the source catalogue, and anything it no longer generates is deleted from
the target. This guide covers metadata generation for catalogue maintainers.
Before releasing new downloadable entries, complete the upload and verification
steps in [Accept a dataset proposal](accept-a-dataset.md). `publish` does not
test storage readiness or push a repository.

```bash
ethos-data catalog build                        # regenerate every manifest first
ethos-data catalog publish ../ETHOS.Data-Catalogue
```

!!! danger "Only ever point `publish` at the public repo"
    It wipes everything in its target except `.git` before regenerating. Run it
    against the source catalogue, or with the wrong path, and it deletes every
    hand-written `dataset.yaml`, `catalog.yaml` and working file the repository
    is not generated from.

    If that happens: anything git-tracked comes back with
    `git checkout HEAD -- <path>`. Anything that was only ever a working-tree
    file does not.

## What it emits

For every dataset marked `ethos:visibility: public`:

- `datacatalog.json` — the index, with the per-dataset totals, access class,
  remote prefix and licence status that let a consumer answer questions without
  loading any inventory;
- `datasets/<name>/datapackage.json` (and `manifests/*.json` for a sharded
  dataset) — the inventory, with `source_dir`, `ethos:embargo` and
  `ethos:license_note` and `ethos:uploaded` **stripped**;
- the README table.

It stamps `ethos:catalog_role: published` into the generated index. Tools read
that key rather than guessing from which files happen to be lying around, so
running a maintainer command inside the wrong checkout gets you a straight
answer instead of a confusing missing-file error.

## Check for a leak before committing

This is the failure that matters. `source_dir` points at a maintainer's
workstation, `ethos:embargo` says what is being withheld and until when, and
`ethos:license_note` may name an unresolved legal question:

```bash
rg -n 'source_dir|ethos:embargo|ethos:license_note|ethos:uploaded' ../ETHOS.Data-Catalogue   # expect no output
```

A `hidden` dataset must not be mentioned at all. Then read the actual diff:

```bash
cd ../ETHOS.Data-Catalogue && git diff
```

Commit the source and generated public revisions as a reviewed pair. The
internal catalogue is deployed as a complete filesystem tree on the cluster,
with its source history synchronized with JuGit; the public view is released
on GitHub. See [Catalogue hosting](catalogue-hosting.md) for versioned trees,
consumer pins, and release distribution. These deployment actions are separate
from `publish`.

## In CI

```bash
ethos-data catalog build --check                         # fail if any manifest is stale
ethos-data catalog publish ../ETHOS.Data-Catalogue --check  # fail if the public repo is out of date
```

Both are non-destructive; `--check` reports and exits non-zero rather than
writing. Candidate datasets with a `source_dir` need a runner that can read the
candidate bytes; uploaded datasets retain their recorded inventory. See
[Run catalogue checks in CI](catalogue-ci.md).

## The public repository's history

`publish` rewrites a *worktree*. It cannot rewrite a *history* — and that
distinction has bitten people:

!!! danger "Never create the public repo by cloning the internal one"
    A public checkout that began as a copy of the internal repository still
    carries every `ethos:embargo` block, every `source_dir`, and every hidden
    dataset's `dataset.yaml`, one `git log` away from anyone who clones it.
    No amount of publishing removes them.

    Create it as a fresh `git init`, and confirm before the first push:

    ```bash
    cd ../ETHOS.Data-Catalogue
    git log --oneline                                   # only commits you made here
    git log --all --diff-filter=A --name-only | sort -u # every file ever added
    git remote -v                                       # the PUBLIC remote
    ```

See [Bootstrap a new catalogue](bootstrap-a-catalogue.md).

## Releasing an embargoed dataset

Two edits in `datasets/<name>/dataset.yaml`:

```yaml
ethos:access: public
ethos:visibility: public
# and delete the ethos:embargo block
```

Rebuild, establish that the bytes are publicly readable, and generate the
public view. If the bytes have not been uploaded, follow
[Upload a dataset](upload-a-dataset.md) first; otherwise verify the existing
upload before releasing the metadata. The dataset's resource keys and checksums
can remain unchanged when only access and visibility change. Consumers need a
catalogue version that includes the newly public entry; an older public pin
which omitted the dataset will continue to omit it.

## See also

- [Withdraw a dataset](withdraw-a-dataset.md) — the reverse, in the reverse
  order.
- [Describe a dataset](describe-a-dataset.md).
