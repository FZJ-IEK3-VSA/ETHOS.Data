# Troubleshoot catalogue access

Start with the same environment, collections file, and catalogue override as
the failing workflow. These diagnostics apply to data users, package
maintainers, and catalogue maintainers.

## Identify the selected metadata and roots

```bash
ethos-data config show
ethos-data -p reskit list
ethos-data -p reskit plan onshore_wind
```

Replace the RESKit names for your package. Include `--catalog` if the workflow
supplies one. `config show` needs no catalogue and names the catalogue in use;
`list` and `plan` may retrieve remote metadata.

## Match the symptom to the next check

| Symptom | Check and action |
|---|---|
| Unknown dataset or `[unresolvable]` collection | Check the catalogue path/version and spelling. Hidden datasets are absent from the public view; an unaccepted dataset may need staging. |
| Catalogue JSON exists but a descriptor or shard is missing | Check that the entire catalogue tree was deployed, not just `datacatalog.json`. A release archive must be extracted before using its local index. |
| Catalogue on the cluster is unreadable | Confirm the supplied path and directory/file read permissions. Use a complete versioned tree if `current` is being updated. |
| Data is looked up in an unexpected directory | Read the configuration origins in `config show`; inspect local roots, environment variables, and namespace links. |
| Licensed data is unavailable | Configure the authorised local root using [Work with restricted data](restricted-data.md); downloading is not a fallback for this access class. |
| A staging warning appears unexpectedly | Inspect `ethos-data staging list`; remove the relevant development entry and any local-root override before verifying an official run. |
| A staged symlink is broken | Restore its target or explicitly remove the staging entry. A broken development entry must not silently select the official data. |
| Cache has wrong size or checksum | Run `verify <collection> --deep`; inspect the findings before using [repair](verify-and-repair.md). Preserve deliberate fixture edits separately. |
| A request fails only outside the cluster | Separate public metadata access from data access; a publicly listed entry may still describe internal or restricted bytes. |
| Upload partly succeeds | Read the per-dataset summary and rerun the failed selection after fixing the cause. Completed uploads are not rolled back. |
| The public catalogue misses accepted data | Check visibility, the generated diff, the deployed public revision, and the consumer's pin; generation alone does not release metadata. |

## Distinguish a stale pin from a stale download

A package pinned to an older catalogue intentionally sees that version. Update
its pin only after reviewing the changed data requirements. For a remote
descriptor suspected of being cached incorrectly, bypass the metadata cache
for a diagnostic request:

```bash
ETHOS_CATALOG_NO_CACHE=1 ethos-data -p reskit list
```

This does not change the pin or fetch dataset bytes. Prefer a commit URL or an
immutable release/tag policy. The URL caching heuristic cannot prove that an
arbitrary tag has never been moved.

## Report a reproducible failure

Include the package and `ethos-data` versions, selected catalogue location and
revision, collection/resource key, full error, and relevant configuration
origins. Include whether staging or a deliberately modified test-data bundle
was active, plus whether the failure occurs with an empty disposable cache.
For maintainers, add the source/public revisions and upload summary. Remove
credentials and private values before posting a report publicly.

The [Architecture](../explanation/architecture/index.md) explains which
components own metadata loading, selection, access, retrieval, and publication;
use it to find the implementation responsible for the failing step.
