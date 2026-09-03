# Uploading a dataset to dCache

For maintainers who have already described a dataset in the catalogue (see
[ADDING-DATA.md](ADDING-DATA.md)) and now need to put its bytes on DESY dCache
InfiniteSpace, at `/Helmholtz/FZJ-ICE2/reskit-data`, served over anonymous
HTTPS. None of this needs the `ice2-data` Python package — just `oidc-agent`,
`rclone` and `curl`.

---

## 1. Credentials (once per machine)

```bash
conda install -c conda-forge oidc-agent rclone
```

**conda-forge's `oidc-agent-service` 4.4.0 has a packaging bug**: it hardcodes
`/bin/oidc-agent`, which doesn't exist. Fix it once per environment:

```bash
mkdir -p "$CONDA_PREFIX/etc/conda/activate.d"
cat > "$CONDA_PREFIX/etc/conda/activate.d/oidc-agent-path.sh" <<'EOF'
export OIDC_AGENT="${CONDA_PREFIX}/bin/oidc-agent"
EOF
conda deactivate && conda activate "$CONDA_DEFAULT_ENV"
```

**Run that last line as shown — do not retype the environment name by
hand.** `$CONDA_DEFAULT_ENV` is set by conda itself to whatever was active
before the `deactivate`. Leaving it as a literal placeholder for "your env
name" (or leaving it unset) makes `conda activate` silently fall back to
`base`, which has none of this installed — `oidc-agent-service` then fails
with a plain `command not found`, not the packaging-bug error below, which
is a confusing way to lose ten minutes.

A *running* agent hides this bug (it only shells out to `$OIDC_AGENT` when
starting a fresh daemon), so if it's ever unclear whether the fix took, test
from cold with `oidc-agent --kill` first.

**Use `conda activate`, not `conda run`**, for everything below — `oidc-gen`
is interactive (it prompts for an encryption password, and waits on a browser
login), and `conda run` gives it no TTY.

Start the agent (every new shell):

```bash
eval $(oidc-agent-service use)
```

A bare number in the output is the daemon PID; `OIDCD_PID=` empty just means
an agent was already running. Neither is an error.

Register a profile (once — you log in with **Helmholtz ID**, federated
through DESY Keycloak; there is no separate dCache password):

```bash
oidc-gen HIFIS --flow=code --client-id=desy-public --client-secret='' \
  --scope="openid profile offline_access" \
  --iss=https://keycloak.desy.de/auth/realms/production/ \
  --redirect-uri=http://localhost:8080
```

Three flags that are not optional:

| Flag | Why |
|:--|:--|
| `--client-secret=''` | `desy-public` is a public client with no secret; omitting this makes `oidc-gen` prompt for one that doesn't exist |
| `--flow=code`, not `--flow=device` | DESY requires PKCE, which oidc-agent 4.4.0 only sends on the code flow. Device flow fails with `Missing parameter: code_challenge_method` |
| `--redirect-uri=http://localhost:8080` | `desy-public` whitelists only `localhost:4242` and `localhost:8080`. If 4242 is free on your machine you can use it instead; anything else is rejected |

It prints an authorization URL — open it, click **"Helmholtz ID"** (not a
DESY account), log in. On a headless machine over VS Code Remote, the port
forwards automatically (check the **Ports** panel for 8080); no `ssh -L`
needed. The encryption password prompt comes *after* login succeeds — that
password protects the refresh token on disk and is asked again by `oidc-add`
after a reboot.

**This encryption password is one you invent on the spot, the first time —
it is not your Helmholtz/DESY password, and there is no "forgot password"
recovery for it.** If `oidc-gen HIFIS` later asks to *decrypt* an existing
config and you don't know the password, the account itself isn't locked —
only the local cached copy of its refresh token is. Delete that copy and
register again from scratch, choosing a new password.

**`oidc-gen -d HIFIS` is not the way** — it tries to decrypt the config
first (to revoke the token cleanly), so it hits the same password prompt.
The config is just a local encrypted file; delete it directly instead, which
needs no password at all:

```bash
rm ~/.config/oidc-agent/HIFIS
oidc-agent --kill               # clear anything already loaded in the running daemon
eval $(oidc-agent-service use)  # start clean

oidc-gen HIFIS --flow=code --client-id=desy-public --client-secret='' \
  --scope="openid profile offline_access" \
  --iss=https://keycloak.desy.de/auth/realms/production/ \
  --redirect-uri=http://localhost:8080
```

The old refresh token at Keycloak isn't a live problem left behind —
it just expires on its own; a fresh browser login mints an independent one.

That's a normal, full re-run of this step — new browser login, new
encryption password. Worth writing the password down somewhere this time;
it's needed again after every reboot.

Check it worked:

```bash
oidc-token HIFIS | head -c 20; echo      # a JWT starts "eyJ"
```

`~/.config/rclone/rclone.conf`:

```ini
[HIFIS]
type = webdav
url = https://hifis-storage-ht.desy.de:2880/Helmholtz/FZJ-ICE2
vendor = other
bearer_token_command = oidc-token HIFIS
```

Uploads use the **high-throughput** door (uncapped, redirects); public
downloads use the compatible door on 443 — that split is recorded in
`catalog.yaml` and doesn't need repeating per machine.

```bash
rclone lsd HIFIS:                        # lists the VO directory
```

After a reboot the agent is gone but the profile survives: `eval
$(oidc-agent-service use)` then `oidc-add HIFIS` (your encryption password,
no browser step).

## 2. Open the publication root (once, before any upload)

dCache applies a directory's permissions to things created **inside it
afterwards**, not retroactively. So: create, open up, *then* upload.

```bash
rclone mkdir HIFIS:reskit-data

curl -H "Authorization: Bearer $(oidc-token HIFIS)" -H "Content-Type: application/json" \
  -X POST "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/reskit-data" \
  -d '{"action":"chmod","mode":493}'    # 493 decimal == 0755
```

Confirm — no credentials in this command, which is the entire point:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/reskit-data/
```

`200` = a stranger can list it. `401` = the chmod didn't take.

## 3. Upload a dataset

```bash
ice2-catalog upload <dataset> --dry-run   # see what would transfer
ice2-catalog upload <dataset>             # do it, then verify
```

`ice2-catalog upload` refuses `restricted` datasets outright, requires
`--allow-internal` for `internal` ones (and never makes those
world-readable), warns on unresolved licensing, sets `0755` on the dataset's
prefix, then **HEADs every file in the manifest with no credentials** and
reports anything unreadable or the wrong size — that check is the point; the
upload itself is one rclone call. Re-run it any time without re-transferring:

```bash
ice2-catalog upload <dataset> --verify-only
```

Want to see:

```
readable       12/12
storage locality of docs/README.md: ONLINE
```

`ONLINE` is disk, `ONLINE_AND_NEARLINE` is disk plus a tape copy (normal
after about a week), `NEARLINE` is tape-only and the first read blocks while
it stages.

**Paths are immutable.** `ice2-catalog upload` passes `rclone --immutable`, which fails
loudly on an attempted overwrite. If a dataset's bytes genuinely change,
publish it at a new path — `datasets/<name>/dataset.yaml` keeps
`ice2:remote_prefix` stable across *unchanged* files, but a changed file must
never land at a path a consumer already has cached and hash-verified.

## 4. Publish the catalogue entry

```bash
ice2-catalog build
ice2-catalog publish ../ice2-data-catalog
```

Inspect the diff in `../ice2-data-catalog` before committing — the failure
that matters is a leak: `source_dir`, `ice2:embargo` and `ice2:license_note`
must not appear, and a `hidden` dataset must not be mentioned at all.

```bash
grep -rn 'source_dir\|ice2:embargo\|ice2:license_note' ../ice2-data-catalog   # want no output
```

Commit and push both repositories. If the dataset was previously served from
a local root (see [GETTING-DATA.md](GETTING-DATA.md) in
`ice2-data`, "until dCache is ready"), drop that override so it downloads for
real:

```bash
ice2-data config unset-root <dataset>
ice2-data plan <collection>      # should now show files to download
```

---

## When something goes wrong

| Symptom | Cause |
|:--|:--|
| `oidc-agent-service: command not found` | wrong conda env active — check `conda env list`; `base` never has this installed |
| `oidc-agent-service: /bin/oidc-agent: No such file` | the packaging bug — set `OIDC_AGENT` (§1); test from cold with `oidc-agent --kill` |
| `oidc-token` prints nothing | agent not loaded into *this* shell — `eval $(oidc-agent-service use)` |
| `oidc-gen HIFIS` asks to decrypt, and you don't know the password | not recoverable, but nothing is locked — `rm ~/.config/oidc-agent/HIFIS` (not `oidc-gen -d`, which also asks for it), `oidc-agent --kill`, then register again |
| `Missing parameter: code_challenge_method` | used `--flow=device` — use `--flow=code` |
| `Ungültiger Parameter: redirect_uri` | the port isn't whitelisted — only `localhost:4242`/`localhost:8080` |
| An issuer list, then `could not connect to url` | ran `oidc-gen HIFIS` bare — pass `--iss`, `--client-id`, `--flow`, `--scope` |
| `rclone: couldn't fetch bearer token` | `bearer_token_command` returned empty — agent not running |
| Anonymous `curl` gives `401` | directory isn't `0755` — chmod the parent, then **re-upload** (mode isn't retroactive) |
| rclone fails with `--immutable` | a published file changed — publish at a new path, never overwrite |
| `ice2-catalog upload` reports `0/N` for a sharded dataset | it couldn't read `manifests/*.json` — run `ice2-catalog build <dataset>` first |
| First read of a file takes minutes | locality is `NEARLINE` — staging from tape |
