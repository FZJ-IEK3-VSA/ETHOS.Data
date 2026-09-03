# Deleting from dCache

Removing bytes that are already published is a different, more dangerous
operation than uploading — do it deliberately. Needs the same credentials as
[UPLOAD.md](UPLOAD.md) §1.

## Read this first: deleting is not how a dataset changes

**Published paths are immutable.** If a dataset's *content* changed, the fix
is publishing the new bytes at a new path (see UPLOAD.md), never deleting the
old file — someone may already have it cached and hash-verified. Only delete
when you mean to make something **stop existing**: cleaning up test data, or
genuinely withdrawing a dataset.

## Deleting a file or a whole folder

```bash
rclone delete HIFIS:reskit-data/<prefix>/<path/to/file>   # one file
rclone purge  HIFIS:reskit-data/<prefix>                  # a folder, recursively -- irreversible
rclone rmdir  HIFIS:reskit-data/<prefix>                  # an empty folder only
```

`purge` does not ask for confirmation. Run the equivalent `rclone lsf -R
HIFIS:reskit-data/<prefix>` first if you want to see what it's about to take
with it.

Alternative, e.g. for scripting a check into something else — the namespace
API's `DELETE`, which is what `ice2-catalog check-access` uses to clean up
after itself. **Delete the file(s) inside a directory before the directory
itself** — a single `DELETE` on a non-empty directory fails rather than
recursing:

```bash
curl -X DELETE -H "Authorization: Bearer $(oidc-token HIFIS)" \
  "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/reskit-data/<prefix>/<file>"
curl -X DELETE -H "Authorization: Bearer $(oidc-token HIFIS)" \
  "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/reskit-data/<prefix>"
```

Both act on the same tree; there's no separate "trash" — a deleted file is
gone.

## Withdrawing a dataset from publication

Order matters, and it's the opposite of uploading: **unpublish the catalogue
entry before deleting the bytes**, not after. If you delete first, the public
catalogue still points at a path that now 404s — anyone resolving it mid-way
gets a broken reference instead of a clean "dataset not published."

1. In `datasets/<name>/dataset.yaml`, set `ice2:visibility: hidden` (add the
   required `ice2:embargo` block — see [ADDING-DATA.md](ADDING-DATA.md)), or
   delete the dataset directory entirely if it's never coming back.
2. `ice2-catalog build && ice2-catalog publish ../ice2-data-catalog`
   — this removes it from the public `datacatalog.json` and deletes its
   `datasets/<name>/` from the public repo (the tool prunes anything it no
   longer generates). Commit and push both repositories.
3. **Now** delete the bytes:
   ```bash
   rclone purge HIFIS:reskit-data/<ice2:remote_prefix>
   ```
4. Confirm — no credentials, exactly what a public user gets:
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' \
     https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/reskit-data/<prefix>/
   ```
   Want `404`.

## Cleaning up test/probe data

Everything synthetic lives under a `_`-prefixed folder specifically so it can
be wiped in one shot, nowhere near real data:

```bash
rclone purge HIFIS:reskit-data/_probe
curl -s -o /dev/null -w 'gone? %{http_code}\n' \
  https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/reskit-data/_probe/     # want 404
```

Locally, `rm -rf datasets/probe-basic datasets/probe-sharded
_probe-data/probe-basic _probe-data/probe-sharded` — but only once real
datasets are in; see the note in `ADDING-DATA.md` about which probe fixtures
must stay.
