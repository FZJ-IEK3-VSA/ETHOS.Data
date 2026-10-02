# Release the catalogue

Turn the reviewed source catalogue into a new release: the internal catalogue
on the cluster computer, the public catalogue on GitHub and, for attribution,
on dCache. You need a source checkout with every added dataset built and
committed, every upload verified, and a checkout of the public repository.

## 1. Check and release

```bash
ethos-data catalog status --check
ethos-data catalog release v2026.09.2 --public ../ETHOS.Data-Catalogue --dry-run
ethos-data catalog release v2026.09.2 --public ../ETHOS.Data-Catalogue
```

`release` checks before it writes anything: the version follows the last
release, both checkouts are clean, every manifest is current, every public
dataset the public catalogue lists has a verified upload recorded, and the
public catalogue does not [leak](#leak-check). Then it writes the version into
`catalog.yaml` and the index, where packages compare it with the versions
their collections files accept, records the release in the status file of
every dataset that changed since the last one, commits and tags the source
checkout, and generates, commits and tags the public catalogue. Review both
with `git show`, then finish the release:

```bash
ethos-data catalog release v2026.09.2 --public ../ETHOS.Data-Catalogue --push --upload
```

`--push` pushes both checkouts and the tag; `--upload` puts the public
catalogue on dCache. A run with the same version does only what is left, so
an interrupted release is finished by running it again. Releases are numbered
`vYYYY.MM.N`, `N` counting the releases within the month, and the tag names
the release for the internal and the public catalogue alike.

## 2. Update the internal catalogue {#internal}

Cluster users read one checkout of the source catalogue on the cluster computer,
see [Set up the shared machine](set-up-the-shared-machine.md). It
holds one version, the latest release. Update it there, when no jobs are
reading it, and check it before announcing:

```bash
ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout --dry-run
ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json ls
```

`update-checkout` fetches, moves the checkout to the latest release tag by
fast-forward only, refusing a checkout with local changes, and checks every
manifest against its files; `--to` names an earlier release.

Never rebuild inside the served checkout while jobs read it: an index from
one revision paired with inventories from another is exactly what an
`IncompleteCatalog` error reports.

## 3. The public catalogue {#public}

`release` generates it with `publish`, which you can also run on its own to
look at the result:

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
licence documents, and the README table; status files are never published.
It stamps `ethos:catalog_role: published` into the index.

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

### Committed and tagged with the source

`release` commits the public checkout as `Release v2026.09.2` and tags it
with the release, and `--push` pushes it. It refuses a public dataset whose
upload is not recorded as verified, so the public catalogue never offers
bytes nobody can download; [upload](upload-a-dataset.md) it first, or keep
it hidden. Never move a released tag or change metadata behind an existing
release.

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
licence documents, so `release --upload` puts the current public catalogue
next to the data under the publication root, `<publication root>/catalogue/`,
replacing the previous one, and makes it world-readable. Only the latest
release lives there; the history stays on GitHub. The store it writes is the
one `catalog.yaml` names under `ethos:store`, today's dCache by default.

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

`release` drafts the notice, the datasets the release adds, revises,
supersedes and withdraws, and an answer to every proposal it accepted, and
prints them; `--notices DIR` writes them into files as well. Announce the
release on the ICE-2 wiki and to the package maintainers whose datasets
changed, so they can raise their minimum versions, and post each answer in
its proposal's issue.

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
| `draft`, `built` or `available`, with a `source_dir` | Read access to that directory, so a runner on the cluster computer |
| `frozen`, no `source_dir` | Only the checkout; the recorded inventory is preserved |

`ethos-data catalog status` lists the state of every dataset, and
`catalog status --check` compares each record with the evidence before a
release.

The build keeps a size-and-mtime hash cache; for a review that must hash every
byte, start from a checkout without `.ice2-hash-cache.json`. To check that
uploaded bytes are still served without transferring anything:

```bash
ethos-data catalog upload <dataset> --verify-only --no-chmod
```

`catalog release` is the release pipeline, and `catalog update-checkout`
updates the checkout on the cluster computer, which a runner elsewhere cannot
reach. The intended deployment runs the release in the internal catalogue
repository's CI on a tag, so that a maintainer only reviews and tags.

!!! warning "Gap: no CI runs the release"
    A maintainer runs `catalog release` on their own machine. Whether the
    internal Git host can push to GitHub and reach dCache from its runners, or
    whether the public half has to run on GitHub, is still to be established.
