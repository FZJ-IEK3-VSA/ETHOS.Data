# Publish the catalogue

The public catalogue is **generated**. `ice2-data catalog publish` regenerates it
from the source catalogue, and anything it no longer generates is deleted from
the target — so the public repository can never drift from what this command
would produce.

```bash
ice2-data catalog build                        # regenerate every manifest first
ice2-data catalog publish ../ice2-data-catalog
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

For every dataset marked `ice2:visibility: public`:

- `datacatalog.json` — the index, with the per-dataset totals, access class,
  remote prefix and licence status that let a consumer answer questions without
  loading any inventory;
- `datasets/<name>/datapackage.json` (and `manifests/*.json` for a sharded
  dataset) — the inventory, with `source_dir`, `ice2:embargo` and
  `ice2:license_note` **stripped**;
- the README table.

It stamps `ice2:catalog_role: published` into the generated index. Tools read
that key rather than guessing from which files happen to be lying around, so
running a maintainer command inside the wrong checkout gets you a straight
answer instead of a confusing missing-file error.

## Check for a leak before committing

This is the failure that matters. `source_dir` points at a maintainer's
workstation, `ice2:embargo` says what is being withheld and until when, and
`ice2:license_note` may name an unresolved legal question:

```bash
grep -rn 'source_dir\|ice2:embargo\|ice2:license_note' ../ice2-data-catalog   # want no output
```

A `hidden` dataset must not be mentioned at all. Then read the actual diff:

```bash
cd ../ice2-data-catalog && git diff
```

Commit and push **both** repositories — the source catalogue and the public
one. They are two commits, and forgetting the second one is the most common way
for a published dataset to be invisible.

## In CI

```bash
ice2-data catalog build --check                         # fail if any manifest is stale
ice2-data catalog publish ../ice2-data-catalog --check  # fail if the public repo is out of date
```

Both are non-destructive; `--check` reports and exits non-zero rather than
writing. The pair is what keeps "generated" from becoming "generated once, in
2026, by someone who has left".

## The public repository's history

`publish` rewrites a *worktree*. It cannot rewrite a *history* — and that
distinction has bitten people:

!!! danger "Never create the public repo by cloning the internal one"
    A public checkout that began as a copy of the internal repository still
    carries every `ice2:embargo` block, every `source_dir`, and every hidden
    dataset's `dataset.yaml`, one `git log` away from anyone who clones it.
    No amount of publishing removes them.

    Create it as a fresh `git init`, and confirm before the first push:

    ```bash
    cd ../ice2-data-catalog
    git log --oneline                                   # only commits you made here
    git log --all --diff-filter=A --name-only | sort -u # every file ever added
    git remote -v                                       # the PUBLIC remote
    ```

See [Bootstrap a new catalogue](bootstrap-a-catalogue.md).

## Releasing an embargoed dataset

Two edits in `datasets/<name>/dataset.yaml`:

```yaml
ice2:access: public
ice2:visibility: public
# and delete the ice2:embargo block
```

Then `ice2-data catalog build && ice2-data catalog publish ../ice2-data-catalog`. The
dataset name and every checksum stay the same, so everything that already
referenced it keeps working — including a collections file pinned to an older
catalogue, which simply did not see it before.

## See also

- [Withdraw a dataset](withdraw-a-dataset.md) — the reverse, in the reverse
  order.
- [Describe a dataset](describe-a-dataset.md).
