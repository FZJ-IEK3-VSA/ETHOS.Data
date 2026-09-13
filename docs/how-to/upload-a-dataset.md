# Upload a dataset

For maintainers who have already [described a dataset](describe-a-dataset.md)
and now need to put its bytes on DESY dCache InfiniteSpace, served over
anonymous HTTPS.

The upload itself is one `rclone` call. The part that matters is the
verification afterwards: `ethos-data catalog upload` HEADs every file in the manifest
**with no credentials at all** and reports anything unreadable or the wrong
size. That is the only check that actually proves a stranger can download what
you just published.

## Credentials (once per machine)

```bash
conda install -c conda-forge oidc-agent rclone
```

!!! bug "conda-forge's `oidc-agent-service` 4.4.0 hardcodes `/bin/oidc-agent`"
    Which does not exist. Fix it once per environment:

    ```bash
    mkdir -p "$CONDA_PREFIX/etc/conda/activate.d"
    cat > "$CONDA_PREFIX/etc/conda/activate.d/oidc-agent-path.sh" <<'EOF'
    export OIDC_AGENT="${CONDA_PREFIX}/bin/oidc-agent"
    EOF
    conda deactivate && conda activate "$CONDA_DEFAULT_ENV"
    ```

    **Run that last line as shown — do not retype the environment name.**
    `$CONDA_DEFAULT_ENV` is set by conda to whatever was active before the
    `deactivate`. Leaving it as a literal placeholder makes `conda activate`
    fall back to `base`, which has none of this installed, and
    `oidc-agent-service` then fails with a plain `command not found` rather
    than the packaging-bug error — a confusing way to lose ten minutes.

    A *running* agent hides this bug (it only shells out to `$OIDC_AGENT` when
    starting a fresh daemon), so test from cold with `oidc-agent --kill` first.

**Use `conda activate`, not `conda run`**, for everything below: `oidc-gen` is
interactive — it prompts for an encryption password and waits on a browser
login — and `conda run` gives it no TTY.

### Start the agent (every new shell)

```bash
eval $(oidc-agent-service use)
```

A bare number in the output is the daemon PID; an empty `OIDCD_PID=` just means
an agent was already running. Neither is an error.

### Register a profile (once)

You log in with **Helmholtz ID**, federated through DESY Keycloak. There is no
separate dCache password.

```bash
oidc-gen HIFIS --flow=code --client-id=desy-public --client-secret='' \
  --scope="openid profile offline_access" \
  --iss=https://keycloak.desy.de/auth/realms/production/ \
  --redirect-uri=http://localhost:8080
```

Three flags that are not optional:

| Flag | Why |
|:--|:--|
| `--client-secret=''` | `desy-public` is a public client with no secret; omitting this makes `oidc-gen` prompt for one that does not exist |
| `--flow=code`, not `--flow=device` | DESY requires PKCE, which oidc-agent 4.4.0 only sends on the code flow. Device flow fails with `Missing parameter: code_challenge_method` |
| `--redirect-uri=http://localhost:8080` | `desy-public` whitelists only `localhost:4242` and `localhost:8080`. Either is fine; anything else is rejected |

It prints an authorization URL — open it, click **"Helmholtz ID"** (not a DESY
account), log in. On a headless machine over VS Code Remote the port forwards
automatically (check the **Ports** panel for 8080); no `ssh -L` needed.

!!! warning "The encryption password is one you invent on the spot"
    It is **not** your Helmholtz/DESY password, and there is no recovery for
    it. It protects the refresh token on disk, and `oidc-add` asks for it again
    after every reboot — write it down.

    If `oidc-gen HIFIS` later asks to *decrypt* an existing config and you do
    not know the password, the account is not locked — only the local cached
    copy of its refresh token is. Delete that copy and register again.
    `oidc-gen -d HIFIS` is **not** the way: it decrypts first, so it hits the
    same prompt. Delete the file directly, which needs no password:

    ```bash
    rm ~/.config/oidc-agent/HIFIS
    oidc-agent --kill               # clear anything loaded in the running daemon
    eval $(oidc-agent-service use)  # start clean
    # then re-run oidc-gen as above
    ```

Check it worked — a JWT starts `eyJ`:

```bash
oidc-token HIFIS | head -c 20; echo
```

### rclone

`~/.config/rclone/rclone.conf`:

```ini
[HIFIS]
type = webdav
url = https://hifis-storage-ht.desy.de:2880/Helmholtz/FZJ-ICE2
vendor = other
bearer_token_command = oidc-token HIFIS
```

Uploads use the **high-throughput** door (uncapped, redirects); public
downloads use the compatible door on 443. That split is recorded in
`catalog.yaml` and does not need repeating per machine.

```bash
rclone lsd HIFIS:            # lists the VO directory
```

After a reboot the agent is gone but the profile survives:
`eval $(oidc-agent-service use)` then `oidc-add HIFIS` — your encryption
password, no browser step.

## Open the publication root (once, before any upload)

dCache applies a directory's permissions to things created **inside it
afterwards**, not retroactively. So: create, open up, *then* upload.

```bash
rclone mkdir HIFIS:ice2-data-files

curl -H "Authorization: Bearer $(oidc-token HIFIS)" -H "Content-Type: application/json" \
  -X POST "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/ice2-data-files" \
  -d '{"action":"chmod","mode":493}'    # 493 decimal == 0755
```

Confirm — note that this command carries no credentials, which is the entire
point:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files/
```

`200` = a stranger can list it. `401` = the chmod did not take.

## Upload

```bash
ethos-data catalog upload my-dataset --dry-run   # see what would transfer
ethos-data catalog upload my-dataset             # do it, then verify
```

| Flag | |
|---|---|
| `--dry-run` | show what rclone would transfer |
| `--verify-only` | skip the upload, just re-run the anonymous readability check |
| `--allow-internal` | required for an `internal` dataset (never made world-readable) |
| `--no-chmod` | do not set `0755` on the dataset prefix |
| `--transfers N` | parallel transfers (default 8) |
| `--remote`, `--oidc-profile` | rclone remote / oidc-agent profile names (both default `HIFIS`) |
| `--vo-path`, `--root` | the VO namespace path, and the publication root under it |

`upload` refuses `restricted` datasets outright, requires `--allow-internal` for
`internal` ones, and warns on unresolved licensing.

### Uploading a subset of the catalogue

A release usually touches two or three datasets, not one and not all of them.
Name as many as you like — by directory name, or by path, which is what shell
completion gives you:

```bash
ethos-data catalog upload global-wind-atlas-v4 global-solar-atlas --dry-run
ethos-data catalog upload global-wind-atlas-v4 global-solar-atlas
ethos-data catalog upload datasets/global-wind-atlas-v4
```

They are uploaded and verified one at a time, in the order given, and the run
ends with a summary:

```title="Output"
2 datasets, 123 files, 99.39 GB
  global-wind-atlas-v4, global-solar-atlas

---- [1/2] global-wind-atlas-v4 ------------------------------
...
========================================================================
2/2 datasets ok
```

!!! tip "Prefer this over a shell loop"
    Every dataset named is loaded and checked **before any of them is
    uploaded** — so a restricted dataset, an unbuilt manifest or a mistyped
    name stops the run while nothing has been published yet. A
    `for name in ...; do ethos-data catalog upload "$name"; done` checks each
    dataset only when it reaches it, and will happily transfer 70 GB before
    discovering that the next name was one it should have refused.

A path has to point into the *source* catalogue's `datasets/`. Naming a
directory in the published catalogue is refused — it holds descriptors only, so
there are no bytes there to upload — and the message tells you the name to use
instead.

What you want to see:

```title="Output"
readable       12/12
storage locality of docs/README.md: ONLINE
```

`ONLINE` is disk. `ONLINE_AND_NEARLINE` is disk plus a tape copy, which is
normal after about a week. `NEARLINE` is tape-only, and the first read blocks
while it stages.

Re-run the check any time without re-transferring:

```bash
ethos-data catalog upload my-dataset --verify-only
```

!!! danger "Paths are immutable"
    `upload` passes `rclone --immutable`, which fails loudly on an attempted
    overwrite. If a dataset's bytes genuinely change, publish them at a **new**
    path — `ethos:remote_prefix` keeps unchanged files stable, but a changed file
    must never land at a path a consumer already has cached and hash-verified.
    See [Licensing and immutability](../explanation/licensing.md#paths-are-immutable).

## Then publish the catalogue entry

```bash
ethos-data catalog build
ethos-data catalog publish ../ETHOS.Data-Catalogue
```

See [Publish the catalogue](publish-the-catalogue.md) for what to check before
committing.

If the dataset was previously served from a local root, drop that override so
it downloads for real:

```bash
ethos-data config unset-root my-dataset
ethos-data plan <collection>      # should now show files to download
```

## When something goes wrong

| Symptom | Cause |
|:--|:--|
| `oidc-agent-service: command not found` | wrong conda env active — check `conda env list`; `base` never has this installed |
| `oidc-agent-service: /bin/oidc-agent: No such file` | the packaging bug — set `OIDC_AGENT`; test from cold with `oidc-agent --kill` |
| `oidc-token` prints nothing | agent not loaded into *this* shell — `eval $(oidc-agent-service use)` |
| `oidc-gen HIFIS` asks to decrypt, and you do not know the password | not recoverable, but nothing is locked — `rm ~/.config/oidc-agent/HIFIS`, `oidc-agent --kill`, register again |
| `Missing parameter: code_challenge_method` | used `--flow=device` — use `--flow=code` |
| `Ungültiger Parameter: redirect_uri` | the port is not whitelisted — only `localhost:4242` / `localhost:8080` |
| an issuer list, then `could not connect to url` | ran `oidc-gen HIFIS` bare — pass `--iss`, `--client-id`, `--flow`, `--scope` |
| `rclone: couldn't fetch bearer token` | `bearer_token_command` returned empty — agent not running |
| anonymous `curl` gives `401` | directory is not `0755` — chmod the parent, then **re-upload** (mode is not retroactive) |
| rclone fails with `--immutable` | a published file changed — publish at a new path, never overwrite |
| `upload` reports `0/N` for a sharded dataset | it could not read `manifests/*.json` — run `ethos-data catalog build <dataset>` first |
| first read of a file takes minutes | locality is `NEARLINE` — staging from tape |

## Probing what you are allowed to do

If this is a new VO, or the access model is unclear:

```bash
ethos-data catalog check-store FZJ-ICE2
```

Non-destructive: it uses a throwaway subdirectory and cleans up after itself.
It reports whether you can chmod at all (self-managed vs. root-owned "Simple"
model — the latter needs a HIFIS ticket first) and whether permissions inherit
to new files.

## See also

- [Withdraw a dataset](withdraw-a-dataset.md) — deleting, and why the order is
  reversed.
- [Bootstrap a new catalogue](bootstrap-a-catalogue.md) — if the publication
  root does not exist yet.

See [The catalogue lifecycle — ordering and failure boundaries](../explanation/architecture/lifecycle.md) for the system-level explanation.
