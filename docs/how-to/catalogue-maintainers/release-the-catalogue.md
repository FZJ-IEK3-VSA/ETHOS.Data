# Release the catalogue

Turn the reviewed source catalogue into a new release: the internal catalogue
on the cluster computer, the public catalogue on GitHub and, for attribution,
on dCache. You need your own clone of the source catalogue at the merged state
of JuGit, with every added dataset built and every public upload verified, and
beside it your clone of the public catalogue. While any dataset is not frozen,
run the release on the cluster computer, where its build input is readable.

## 1. Release {#release}

```bash
ethos-data catalog release v1.2.0 --public ../ETHOS.Data-Catalogue --dry-run
ethos-data catalog release v1.2.0 --public ../ETHOS.Data-Catalogue
ethos-data catalog release v1.2.0 --public ../ETHOS.Data-Catalogue --push --upload
```

The dry run prints the plan and writes nothing. Its `check` stage refuses an
unclean checkout, a version that is not admissible (see below), a stale build,
a public dataset without a verified upload, and a leak into the public
catalogue. The release then stamps the version into `catalog.yaml`, commits
and tags it, generates the public catalogue into `--public`, commits and tags
that too, and drafts the release notice and the answers. `--push` pushes both
tags, `--upload` puts the public catalogue beside the data on dCache. A rerun
with the same version does only what is left; a merge that lands on JuGit
before the push makes the push fail, and the release is rerun from the
updated branch.

!!! warning "Gap: releases are manual"
    The code has no `catalog release`. Set the release in `catalog.yaml`,
    `version: v1.2.0`, which the build writes into the index, where packages
    compare it with their release bounds. Then build, check and tag by hand,
    in the source checkout:

    ```bash
    ethos-data catalog build
    ethos-data catalog build --check
    git diff
    git commit -am "Add <datasets>"
    git tag v1.2.0
    git push origin main v1.2.0
    ```

    then generate, check and tag the public catalogue as in
    [step 3](#public), and update the cluster's checkout as in
    [step 2](#internal).

### Choose the version {#version}

A release is named `vMAJOR.MINOR.PATCH`: three numbers without leading zeros
or a suffix, compared part by part, so `v1.10.0` follows `v1.9.0`. The first
release is `v1.0.0`. Every release tags both catalogues, even when only
restricted or hidden data changed. The level says what changed since the
release before:

| Level | After `v1.2.0` | Means |
| --- | --- | --- |
| Patch | `v1.2.1` | Metadata only: descriptions, attribution, contacts, homepages, licence notes or licence status. Every key of both catalogues resolves to the same bytes under the same access class. |
| Minor | `v1.3.0` | Data changed: datasets added, revised, superseded, changed in place, withdrawn, reclassified, or made visible or hidden. |
| Major | `v2.0.0` | A retention epoch that the catalogue maintainers plan and announce. Datasets withdrawn before it may be purged once it is recorded. |

The version is the next patch, minor or major of the last release, at or
above the smallest level your changes need. `ethos-data catalog status` and
`ethos-data catalog release VERSION --dry-run` name the smallest admissible
version: the release check works it out from the steps recorded since the
last release, the index rows of both catalogues and a diff against the last
tag. It refuses a smaller version, and a release that changes nothing.

No change requires a major release. Data is purged only after one: until
then, the uploads on dCache and the copies the caches own keep everything that
any release of the current major describes. An urgent deletion, for example
under a licence that forbids further distribution, needs an unplanned major
release; see [Remove a dataset](withdraw-a-dataset.md).

!!! warning "Gap: nothing checks the version"
    The code has no `catalog status` and no `catalog release`. Work the level
    out from the table above, and check that the tag follows the last one.

## 2. Update the internal catalogue {#internal}

Cluster users read one checkout of the source catalogue on the cluster
computer, see [Set up the shared machine](set-up-the-shared-machine.md). It
holds one version, the latest release. Update it on the cluster computer when
no jobs are reading it, and check it before announcing:

```bash
ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json ls
```

`update-checkout` refuses local changes, fast-forwards to the newest release
tag and runs `build --check`, which writes nothing. Never rebuild inside the
served checkout while jobs read it: an index from one revision paired with
inventories from another is exactly what an `IncompleteCatalog` error reports.

!!! warning "Gap: no `update-checkout`"
    The code has no `catalog update-checkout`. In the served checkout, run
    `git pull --ff-only`, then `ethos-data catalog build --check`.

## 3. Generate the public catalogue {#public}

`catalog release` generates the public catalogue with `catalog publish`; run
it alone to look at the result before a release:

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

### Commit, tag, push

`catalog release` commits and tags the public catalogue with the same version,
and `--push` pushes it. Its check refuses a public dataset whose upload was
not [verified](upload-a-dataset.md) after its last inventory change. Never
move a released tag or change metadata behind an existing release.

!!! warning "Gap: the public catalogue is tagged by hand"
    Without `catalog release`, commit, tag and push the public checkout
    yourself, once every downloadable entry it adds has been uploaded and
    verified:

    ```bash
    git commit -am "Release v1.2.0: <what changed>"
    git tag v1.2.0
    git push origin main v1.2.0
    ```

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
licence documents, so `catalog release --upload` puts the current public
catalogue next to the data under the publication root,
`<publication root>/catalogue/`, replacing the previous one. Only the latest
release lives there; the history stays on GitHub.

## 4. Release an embargoed dataset {#embargo}

Two edits in `datasets/<name>/dataset.yaml`:

```yaml
ethos:access: public
ethos:visibility: public
# and delete the ethos:embargo block
```

Rebuild, [upload](upload-a-dataset.md) if the bytes are not on dCache yet or
verify the existing upload, then release as above; a change of access or
visibility needs a minor release. Resource keys and checksums stay unchanged;
only readers of the new release see the dataset. If it was restricted, then
remove its entry from the restricted cache, where public data is never read;
`verify` reports the entry until it is gone:

```bash
ethos-data --root <restricted cache> unlink <name>
```

## 5. Tell the users

Announce the release on the ICE-2 wiki and to the package maintainers whose
datasets changed, so they can raise their minimum versions.

Announce a major release before you make it, and name the withdrawn datasets
that may be purged after it. A purge never touches what the latest release
describes, so a package bounded with `min_version` only, as every package on
the cluster is, does not notice a major release. A package whose bounds end
before that major release loses the purged datasets.

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
byte, start from a checkout without `.ethos-data-hash-cache.json`. To check that
uploaded bytes are still served without transferring anything:

```bash
ethos-data catalog upload <dataset> --verify-only --no-chmod
```

A maintainer runs the release itself. Running it in CI is a feature request
(GitHub issue #34): such a runner needs a token that does not depend on a
person's oidc-agent session, and every build input that is not frozen.

