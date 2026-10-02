# Check and repair the cache

Compare the files a workflow uses with the sizes and checksums the catalogue
records, and re-fetch what no longer matches. Examples use the package's command and
its `test_suite` collection; substitute your package's command and collection.

## Check a collection

```bash
<your-tool>-data verify test_suite
<your-tool>-data verify test_suite --deep
```

The first form compares sizes, which is cheap. `--deep` reads every byte and
compares SHA-256 hashes. `verify --all --deep` checks every collection the
package defines. Neither form changes anything.

| Finding | Meaning and next step |
| --- | --- |
| `ok` | The file matches. Only a deep check establishes a hash match. |
| `wrong size`, `wrong checksum` | The bytes differ from the catalogue. Repair a downloaded copy, or tell the owner of a linked copy. |
| `dangling` | A cache link points nowhere: its target moved. Tell the cache maintainer. |
| `missing`, `unreadable` | The file is absent or you lack permission. Check the expected location and your group membership. |
| `unavailable here` | A restricted dataset with no authorised copy on this machine. |
| `unverifiable` | A staged development copy without catalogue checksums. Remove the staging entry before an official run. |

## Repair downloaded data

```bash
<your-tool>-data verify test_suite --deep --repair --dry-run
<your-tool>-data verify test_suite --deep --repair
<your-tool>-data verify test_suite --deep
```

Read the preview first: repair re-fetches the listed files from the published
store and can replace a dataset's cache link with a fresh copy, which every
user of a shared cache sees. Restricted, staged and linked-in-place data are
never repaired; ask the owner of that copy instead. The final check must report
every file as `ok`.

## Check a whole dataset fetched by key {#verify-complete-dataset}

A package's `verify` checks only what its collections select. To check every
file of a dataset, folder or file by its key:

```bash
ethos-data verify global-wind-atlas-v4 --deep
ethos-data verify global-wind-atlas-v4 --deep --repair --dry-run
```

It takes the same `--deep`, `--repair`, `--dry-run` and `--quiet` as a
package's `verify`. The same check from Python, against the catalogue and
caches in effect:

```python
import ethos_data

catalog = ethos_data.catalog()
resources = catalog.resources("global-wind-atlas-v4")
findings = ethos_data.verify(catalog, resources, deep=True)
for finding in findings:
    if not finding.ok:
        print(finding.status, finding.resource.key)
```

Remove staging entries and per-dataset root overrides first; they would
redirect the check away from the cache.

If verification still fails after a repair, [report the problem](report-a-problem.md).
