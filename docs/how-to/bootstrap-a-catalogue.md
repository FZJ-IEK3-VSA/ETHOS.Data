# Bootstrap a new catalogue

Day zero: before `catalog.yaml` exists, before the dCache folder exists, before
any dataset is described. If the catalogue already exists and you just want to
add or upload a dataset, you do not need this page — see
[Describe a dataset](describe-a-dataset.md) and
[Upload a dataset](upload-a-dataset.md).

## 1. Credentials

The same one-time `oidc-agent` + `rclone` setup as everywhere else — see
[Upload a dataset](upload-a-dataset.md#credentials-once-per-machine).
Everything below assumes `oidc-token HIFIS` prints a JWT and `rclone lsd HIFIS:`
works.

## 2. Check what you are allowed to do

Before anything else, if this is a new VO or the access model is unclear:

```bash
ethos-data catalog check-store FZJ-ICE2
```

Non-destructive — it uses a throwaway subdirectory and cleans up after itself.
It tells you whether you can chmod at all (self-managed vs. root-owned "Simple"
model — the latter needs a HIFIS ticket before anything else here will work)
and whether permissions inherit to new files.

## 3. Create and open the publication root

```bash
rclone mkdir HIFIS:ice2-data-files

curl -H "Authorization: Bearer $(oidc-token HIFIS)" -H "Content-Type: application/json" \
  -X POST "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/ice2-data-files" \
  -d '{"action":"chmod","mode":493}'    # 493 decimal == 0755
```

**Order matters.** dCache applies a directory's mode to things created *inside*
it afterwards, not retroactively — so open it up before anything is uploaded
into it.

Confirm, with no credentials, which is the whole point:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files/
```

`200` = a stranger can list it (it is empty, but reachable). `401` = the chmod
did not take.

## 4. Write `catalog.yaml`

The hand-written identity file at the repository root. Everything else is
generated from it plus `datasets/*/dataset.yaml`:

```yaml
# Hand-maintained catalogue-level metadata.
# ethos-data catalog build merges this with the generated dataset list into
# datacatalog.json. Do not edit datacatalog.json by hand.

name: <catalogue-name>
title: <Human-Readable Title>
description: >-
  What this catalogue is, who maintains it, and what it is for.

# Root of the public data store. Every resource URL is
#   <publication_url>/<dataset ethos:remote_prefix>/<resource path>
# This is DESY's compatible door (443, no redirect) -- right for a public
# catalogue. Override per machine with `ethos-data config set-publication-url`
# for the high-throughput door instead (CI, bulk transfers).
ethos:publication_url: https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files

ethos:contact: <team or username>

# What kind of catalogue this is. Always `source` in a hand-written
# catalog.yaml; `ethos-data catalog publish` stamps `published` into the generated
# copy, which has no catalog.yaml of its own. Tools read this instead of
# guessing, so standing in the wrong one gets you a straight answer rather
# than a missing-file error.
ethos:catalog_role: source
```

## 5. The repository skeleton

`catalog.yaml` and an empty `datasets/` directory. That is the whole skeleton —
a catalogue repository holds metadata and nothing else.

The tooling is **not** copied into it. `ethos-data catalog` ships with the
`ethos-data` package and finds its catalogue by searching upward from the current
directory for `catalog.yaml`, so it works from anywhere inside any checkout:

```bash
pip install ethos_data      # brings `ethos-data` and `ethos-data catalog`
cd /path/to/your-catalogue
ethos-data catalog build         # operates on the catalogue it is standing in
```

Nothing in the tooling hardcodes a catalogue name. `ethos-data catalog upload --root`
and `catalog.yaml`'s `ethos:publication_url` are the only places the folder name
appears at all.

## 6. Add and upload the first dataset

This proves the whole chain end to end:

```bash
# describe it, build its manifest -- see Describe a dataset
ethos-data catalog build <name>

# upload it into the new root, then verify anonymous access -- see Upload
ethos-data catalog upload <name> --dry-run
ethos-data catalog upload <name>

# generate and inspect the public subset
ethos-data catalog publish ../<public-repo>
```

If `<name>` is the first thing ever uploaded here, the anonymous verification
pass — `readable N/N`, plus the storage locality — is the real proof that the
folder, the permissions and the catalogue all agree with each other.

## 7. The public counterpart repository

A generated, public mirror of just the `visibility: public` datasets, produced
by `ethos-data catalog publish` and never hand-edited.

!!! danger "Start its git history empty. Never clone the internal repo to make it."
    `ethos-data catalog publish` rewrites a *worktree*; it cannot rewrite a *history*.
    A public checkout that began as a copy of the internal repository still
    carries every `ethos:embargo` block, every `source_dir` pointing at a
    maintainer's workstation, and every hidden dataset's `dataset.yaml` — one
    `git log` away from anyone who clones it.

    Create it as a fresh `git init`, and confirm before the first push:

    ```bash
    cd ../<public-repo>
    git log --oneline                                   # only commits you made here
    git log --all --diff-filter=A --name-only | sort -u # every file ever added
    git remote -v                                       # the PUBLIC remote, not jugit
    ```

## 8. Build the cache namespace

Optional, and worth doing on a shared machine. If the datasets already exist on
the cluster, build the public cache as a directory of links to them so nothing
has to be downloaded at all:

```bash
ethos-data catalog link-cache --root /shared/ethos/public --dry-run
ethos-data catalog link-cache --root /shared/ethos/public
ethos-data config set-cache /shared/ethos/public --scope site
```

Users then get the whole catalogue with no setup. See
[Link cluster data into the cache](link-cluster-data.md#2-create-the-links).

## See also

- [The catalogue format](../explanation/catalogue-format.md) — what these files
  are, and why they are Frictionless Data Packages.
- [File formats](../reference/schemas.md) — every key in `catalog.yaml`.
