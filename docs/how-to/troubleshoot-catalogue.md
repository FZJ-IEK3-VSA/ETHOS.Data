# Diagnose catalogue problems

Trace a reported failure through the selected metadata, local files, and remote
storage. You need the reporter's catalogue revision, collection/resource keys,
and error. For the initial user checks and report template, see
[Identify and report a problem](report-a-problem.md).

## 1. Confirm the reader's inputs

```bash
ethos-data config show
ethos-data --catalog /path/to/reported/datacatalog.json -c collections.yaml list
ethos-data --catalog /path/to/reported/datacatalog.json -c collections.yaml plan affected_collection
```

Use the reporter's actual pin, collection, and cache selection. `config show`
reports configuration origins; `list` prints the chosen catalogue.
Both `list` and `plan` may retrieve remote metadata.

| Symptom | Check and action |
|---|---|
| Unknown dataset or unresolvable collection | Check spelling, catalogue revision, staging, and whether the entry is hidden. |
| Index exists, descriptor/shard is missing | Deploy the complete tree for that revision; copying only the index is insufficient. |
| Cluster catalogue unreadable | Check filesystem permissions and the target of the `current` alias. |
| Unexpected data location | Inspect per-dataset roots, staging, and cache links. |
| Unexpected download host | Check `ETHOS_PUBLICATION_URL` and `publication_url` in the config files reported by `config show`. |
| Hash mismatch | Compare with accepted inventory; preserve evidence before repairing or rebuilding. |
| Public view misses accepted data | Check visibility, generated diff, released commit, and consumer pin. |

To diagnose remote metadata caching without changing the pin:

=== "Bash"

    ```bash
    ETHOS_CATALOG_NO_CACHE=1 ethos-data -p reskit list
    ```

=== "PowerShell"

    ```powershell
    $env:ETHOS_CATALOG_NO_CACHE = "1"
    ethos-data -p reskit list
    Remove-Item Env:ETHOS_CATALOG_NO_CACHE
    ```

Replace `reskit` with the affected package and retain its catalogue override.
This bypasses metadata caching, not dataset storage.

## 2. Check source and generated metadata

In the source checkout:

```bash
ethos-data catalog build --check
ethos-data catalog publish ../ETHOS.Data-Catalogue --check
```

| Failure | Action |
|---|---|
| Missing candidate `source_dir` | Restore access to the reviewed source; do not substitute an unrelated cache copy. |
| Inventory stale before upload | Inspect changed source files and filters, rebuild, and review the diff. |
| Include matches nothing | Correct the pattern or source path; do not accept an empty inventory accidentally. |
| Uploaded/frozen inventory needs changed bytes | Create a deliberate dataset/resource revision; rebuilding preserves recorded hashes. |
| Public generation differs | Review visibility and stripped fields, regenerate the dedicated public checkout, then release it. |
| Command refuses a published checkout | Select the source checkout containing `catalog.yaml` with `catalog --catalog-root`. |

## 3. Check the public store

```bash
ethos-data catalog upload affected-dataset --verify-only --no-chmod
```

| Failure | Action |
|---|---|
| rclone cannot obtain a token | Check the active environment and loaded profile using [Set up dCache access](set-up-dcache-access.md). |
| Anonymous 401/403 for public data | Check the intended publication root and object permissions with the storage administrator. |
| 404 or wrong size | Compare the exact manifest path, remote prefix, transfer summary, and publication URL. |
| Immutable transfer conflict | Use new published paths; do not remove a released object to retry. |
| Internal transfer succeeded, verification failed | Verification is still anonymous; use the agreed private-storage procedure, not public chmod. |
| Long first read, locality `NEARLINE` | Allow for tape staging; report persistent storage failures with the resource path and time. |

Rerun only the failed upload selection after fixing the cause. Earlier completed
transfers are not rolled back. For an unknown VO permission model,
`catalog check-store` probes with temporary remote objects and cleans up.

Keep source/public revisions, validation results, and the resolution with the
issue. See [Catalogues and storage](../explanation/catalogues-and-storage.md) for
the boundaries each check establishes.
