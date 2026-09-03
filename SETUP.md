# Setting up a new catalogue on dCache, from scratch

Day-zero bootstrap — before `catalog.yaml` exists, before the dCache folder
exists, before any dataset is described. If the catalogue already exists and
you just want to add or upload a dataset, you don't need this file — see
[ADDING-DATA.md](ADDING-DATA.md) and [UPLOAD.md](UPLOAD.md).

**The real data lives under `ice2-data-files` on dCache** — the folder these
steps create. (The probe/test datasets already running in this repo target
the older `reskit-data` folder; that's a separate, already-live setup and
migrating it isn't part of this doc.)

## 1. Credentials

Same one-time `oidc-agent` + `rclone` setup as everywhere else — see
[UPLOAD.md](UPLOAD.md) §1. Everything below assumes `oidc-token HIFIS` prints
a JWT and `rclone lsd HIFIS:` works.

## 2. Create and open the publication root

```bash
rclone mkdir HIFIS:ice2-data-files

curl -H "Authorization: Bearer $(oidc-token HIFIS)" -H "Content-Type: application/json" \
  -X POST "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/ice2-data-files" \
  -d '{"action":"chmod","mode":493}'    # 493 decimal == 0755
```

Order matters — dCache applies a directory's mode to things created *inside*
it afterwards, not retroactively, so open it up before anything is uploaded
into it.

Confirm — no credentials, which is the whole point:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files/
```

`200` = a stranger can list it (it's empty, but reachable). `401` = the
chmod didn't take.

**Check what you're actually allowed to do first, if this is a new VO or
you're unsure of the access model:**

```bash
ice2-catalog check-access FZJ-ICE2
```

Non-destructive — it uses a throwaway subdirectory and cleans up after
itself. It tells you whether you can chmod at all (self-managed vs.
root-owned "Simple" model — the latter needs a HIFIS ticket before anything
else here will work) and whether permissions inherit to new files.

## 3. Write `catalog.yaml`

The hand-written identity file at the repo root — everything else
(`datacatalog.json`) is generated from it plus `datasets/*/dataset.yaml`:

```yaml
# Hand-maintained catalogue-level metadata.
# ice2-catalog build merges this with the generated dataset list into
# datacatalog.json. Do not edit datacatalog.json by hand.

name: <catalogue-name>
title: <Human-Readable Title>
description: >-
  What this catalogue is, who maintains it, and what it's for.

# Root of the public data store. Every resource URL is
#   <publication_url>/<dataset ice2:remote_prefix>/<resource path>
# This is DESY's compatible door (443, no redirect) -- right for a public
# catalogue. Override per machine with `ice2-data config set-publication-url`
# for the high-throughput door instead (CI, bulk transfers).
ice2:publication_url: https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files

ice2:contact: <team or username>
```

## 4. Repo skeleton

`catalog.yaml` and an empty `datasets/` directory. That is the whole
skeleton — a catalogue repository holds metadata and nothing else.

The tooling is **not** copied into it. `ice2-catalog` ships with the
`ice2-data` package and finds its catalogue by searching upward from the
current directory for `catalog.yaml`, so it works from anywhere inside any
checkout:

```bash
pip install ice2-data      # brings `ice2-data` and `ice2-catalog`
cd /path/to/your-catalogue
ice2-catalog build         # operates on the catalogue it is standing in
```

Nothing in the tooling hardcodes a catalogue name; `ice2-catalog upload
--root` and `catalog.yaml`'s `ice2:publication_url` are the only places the
folder name (`ice2-data-files`) actually appears.

## 5. Add and upload the first dataset

Proves the whole chain end to end:

```bash
# describe it, build its manifest -- see ADDING-DATA.md
ice2-catalog build <name>

# upload it into the new root, then verify anonymous access -- see UPLOAD.md
ice2-catalog upload <name> --dry-run
ice2-catalog upload <name>

# generate and inspect the public subset
ice2-catalog publish ../<public-repo>
```

If `<name>` is the first thing ever uploaded here, the anonymous
verification pass (readable N/N, storage locality) is the real proof the
folder, permissions and catalogue all agree with each other.

## 6. The public counterpart repo

A generated, public GitHub mirror of just the `visibility: public` datasets
— produced by `ice2-catalog publish`, never hand-edited.

> **Start its git history empty. Never clone the internal repo to make it.**
>
> `ice2-catalog publish` rewrites a *worktree*; it cannot rewrite a history.
> A public checkout that began as a copy of the internal repository still
> carries every `ice2:embargo` block, every `source_dir` pointing at a
> maintainer's workstation, and every hidden dataset's `dataset.yaml` — one
> `git log` away from anyone who clones it. Create it as a fresh
> `git init`, and confirm before the first push:
>
> ```bash
> cd ../<public-repo>
> git log --oneline                                   # only commits you made here
> git log --all --diff-filter=A --name-only | sort -u # every file ever added
> git remote -v                                       # the PUBLIC remote, not jugit
> ```

Setting that repo up
(branch protection, the validation/release CI workflows, GitHub release
assets) is its own checklist — see `TODO-catalog-github-release.md` at the
workspace root. Do steps 1–5 above first; the public repo has nothing to
generate until a dataset exists.
