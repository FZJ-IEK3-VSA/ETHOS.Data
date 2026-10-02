# Diagnose a report

Trace a data user's [report](../data-users/report-a-problem.md) through the
served metadata, the caches and the published store, and decide which side has
to change. You need the report with its catalogue revision, key or collection
and full error, a source checkout, and dCache credentials for the storage
checks.

## 1. Reproduce with the reporter's selection

```bash
ethos-data --catalog <reported location> ls <dataset>
<your-tool>-data --catalog <reported location> show <collection>
<your-tool>-data --catalog <reported location> fetch <collection> --plan
```

Use the reporter's catalogue, collection and cache settings, not yours.

| Symptom | Check and action |
| --- | --- |
| `CatalogUnavailable` | The location is wrong or the pinned revision does not exist yet. Check the pin in the package's `collections.yaml` and the served path. |
| `IncompleteCatalog`, descriptor or shard missing | The served copy is stale or partial: an index from one revision beside inventories from another. [Release](release-the-catalogue.md#internal) the complete version again; copying only the index is not a fix. |
| Unknown dataset or unresolvable collection | Spelling, revision, a hidden dataset seen through the public catalogue, or a staging entry gone. |
| Cluster catalogue unreadable | Filesystem permissions, or a checkout that was moved or is half-way through an update. |
| Data read from an unexpected place | A staging entry, a bundle, or a link in one of the reporter's caches. `config show` and the plan name them. |
| Download from an unexpected host | `ETHOS_PUBLICATION_URL`, or `publication_url` in the settings file `config show` names. |
| Hash mismatch | Compare with the recorded inventory and keep the evidence before repairing. A linked copy was edited at its source; a downloaded copy was damaged; or the published object was replaced, which must never happen. |
| Public view misses an accepted dataset | Visibility, the generated diff, whether the public revision was released, and which revision the package pins. |

To rule out the metadata cache without changing the reporter's pin, set
`ETHOS_CATALOG_NO_CACHE=1` for one command.

## 2. Check the source and generated metadata

In the source checkout:

```bash
ethos-data catalog build --check
ethos-data catalog publish ../ETHOS.Data-Catalogue --check
```

| Failure | Action |
| --- | --- |
| Candidate `source_dir` missing | Restore access to the reviewed source; do not substitute another copy. |
| Inventory stale before upload | Inspect the changed files and filters, rebuild, review the diff. |
| An include pattern matches nothing | Fix the pattern or the source path; never accept an empty inventory. |
| Uploaded or frozen inventory needs changed bytes | A deliberate new version at new paths; rebuilding preserves the recorded hashes. |
| Public generation differs | Review visibility and stripped fields, regenerate the public checkout, release it. |
| Command refuses a published checkout | Point `catalog --catalog-root` at the source checkout, the one with `catalog.yaml`. |

## 3. Check the published store

```bash
ethos-data catalog upload <dataset> --verify-only --no-chmod
```

| Failure | Action |
| --- | --- |
| rclone cannot obtain a token | The agent or profile is not loaded; see [Set up dCache access](set-up-dcache-access.md). |
| Anonymous 401 or 403 on public data | The prefix lost its public mode; check the object permissions with the storage administrator. |
| 404 or wrong size | Compare the manifest path, remote prefix, transfer summary and publication URL. |
| Immutable-transfer conflict | Somebody tried to overwrite a released object. New paths; never delete to retry. |
| Long first read, locality `NEARLINE` | Tape staging; report persistent failures with the path and time. |

Rerun only the failed selection after fixing the cause; earlier transfers are
not rolled back. For an unfamiliar permission model, `catalog check-store`
probes with temporary objects and cleans up.

## 4. Fix and record

| Cause | Fix |
| --- | --- |
| Stale served copy | Run `catalog update-checkout` on the cluster computer, as under [Update the internal catalogue](release-the-catalogue.md#internal). |
| Broken or moved link | Repoint it with `link --force`, or materialize, each with `--catalog-root <your clone>`. |
| Damaged download on the reporter's machine | The reporter runs `verify --repair`. |
| Wrong or missing metadata | Correct `dataset.yaml`, rebuild, release. |
| Missing or unreadable bytes on dCache | Upload again or fix permissions, then verify. |

Record the revisions checked, the findings and the resolution in the issue,
so the next report with the same symptom starts from the answer.
