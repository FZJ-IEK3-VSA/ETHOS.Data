# Release the catalogue

Turn the reviewed source catalogue into a new release: the internal catalogue
on the cluster computer, the public catalogue on GitHub and, for attribution,
on dCache. You need a source checkout with every added dataset built and
every upload verified. Today the steps are manual and the checks are
commands; the intended state is a pipeline that does everything after the
tag.

## 1. Build, check, commit, tag

Set the release in `catalog.yaml` first, `version: v2026.09.2`: the build
writes it into the index, where packages compare it with the versions their
collections files accept.

```bash
ethos-data catalog build
ethos-data catalog build --check
git diff
git commit -am "Add <datasets>"
git tag v2026.09.2
git push origin main v2026.09.2
```

Expect `--check` to pass and the diff to contain only the datasets you added.
Releases are numbered `vYYYY.MM.N`, `N` counting the releases within the
month, and the tag names the release for the internal and the public
catalogue alike.

## 2. Update the internal catalogue {#internal}

Cluster users read one checkout of the source catalogue on the cluster computer,
see [Set up the shared machine](set-up-the-shared-machine.md). It
holds one version, the latest release. Update it when no jobs are reading it
and check it before announcing:

```bash
cd /shared/ethos/catalogue
git pull --ff-only
ethos-data catalog build --check
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json ls
```

Never rebuild inside the served checkout while jobs read it: an index from
one revision paired with inventories from another is exactly what an
`IncompleteCatalog` error reports.

## 3. Generate the public catalogue {#public}

```bash
ethos-data catalog publish ../ETHOS.Data-Catalogue
```

!!! danger "Only ever point `publish` at the public repository"
    It deletes everything in its target except `.git` before regenerating.
    Pointed at the source checkout, it removes every hand-written
    `dataset.yaml` and `catalog.yaml`. Files under Git come back with
    `git checkout HEAD -- <path>`; untracked files do not.

`publish` emits, for every dataset with `ethos:visibility: public`, the index,
the descriptor and shards with `source_dir`, `ethos:embargo`,
`ethos:license_note`, `ethos:uploaded` and `ethos:frozen` stripped, the
licence documents, and the README table. It stamps
`ethos:catalog_role: published` into the index.

### Check for a leak before committing {#leak-check}

`publish` checks the tree it generates before writing any of it. A stripped
key that is still there, or a hidden dataset named anywhere, in a descriptor,
the index or the README, stops it with nothing written, and it names each
finding. Fix the source descriptor or its visibility, rebuild, and publish
again. The check knows names, not meaning, so read the diff:

```bash
cd ../ETHOS.Data-Catalogue && git diff
```

A hidden dataset must not be mentioned at all.

### Commit, tag, push

```bash
git commit -am "Release v2026.09.2: <what changed>"
git tag v2026.09.2
git push origin main v2026.09.2
```

Release the public catalogue only after every downloadable entry it adds has
been [uploaded and verified](upload-a-dataset.md). Never move a released tag
or change metadata behind an existing release.

!!! danger "Never create the public repository by cloning the internal one"
    A public checkout that began as a copy of the source repository carries
    every `source_dir`, every embargo block and every hidden dataset's
    `dataset.yaml` in its history, one `git log` away from anyone who clones
    it. Publishing rewrites a worktree, never a history. Check before the
    first push:

    ```bash
    git log --oneline                                    # only commits made here
    git log --all --diff-filter=A --name-only | sort -u  # every file ever added
    git remote -v                                        # the PUBLIC remote
    ```

### Put the public catalogue beside the data on dCache

Anyone who holds the published bytes should also hold their descriptors and
licence documents, so the current public catalogue is uploaded next to the
data under the publication root, `<publication root>/catalogue/`, replacing
the previous one. Only the latest release lives there; the history stays on
GitHub.

## 4. Release an embargoed dataset {#embargo}

Two edits in `datasets/<name>/dataset.yaml`:

```yaml
ethos:access: public
ethos:visibility: public
# and delete the ethos:embargo block
```

Rebuild, [upload](upload-a-dataset.md) if the bytes are not on dCache yet or
verify the existing upload, then release as above. Resource keys and
checksums stay unchanged; only readers of the new release see the dataset.

## 5. Tell the users

Announce the release on the ICE-2 wiki and to the package maintainers whose
datasets changed, so they can raise their minimum versions.

## Automate it {#in-ci}

The two checks run on every merge request of the source repository; both
compare and never write:

```bash
ethos-data catalog build --check
ethos-data catalog publish ../ETHOS.Data-Catalogue --check
```

`publish --check` runs the [leak check](#leak-check) too, so a merge request
that would leak fails before anybody publishes.

| Dataset state | The runner needs |
| --- | --- |
| Candidate with `source_dir` | Read access to that directory, so a runner on the cluster computer |
| Uploaded or frozen, no `source_dir` | Only the checkout; the recorded inventory is preserved |

The build keeps a size-and-mtime hash cache; for a review that must hash every
byte, start from a checkout without `.ice2-hash-cache.json`. To check that
uploaded bytes are still served without transferring anything:

```bash
ethos-data catalog upload <dataset> --verify-only --no-chmod
```

The intended pipeline lives in the internal catalogue repository and runs on
a tag: it generates the public catalogue, runs the leak check, commits, tags
and pushes the public repository on GitHub, uploads the public catalogue to
dCache, and updates the checkout on the cluster computer. A maintainer then
only reviews and tags. Whether the internal Git host can push to GitHub and
reach dCache from its runners, or whether the public half has to run on
GitHub, is still to be established.

!!! warning "Gap: releases are manual"
    Only the two check commands exist. No pipeline publishes, uploads the
    catalogue to dCache or updates the cluster computer checkout.
