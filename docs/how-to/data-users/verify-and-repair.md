# Check and repair the cache

Compare the files a workflow uses with the sizes and checksums the catalogue
records, and download again what does not match. Examples use the package's command and
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
| `dangling` | A cache link points nowhere: its target moved. The line names the cache; tell its maintainer. |
| `missing`, `unreadable` | The file is absent or you lack permission. Check the expected location and your group membership. |
| `unavailable here` | A restricted dataset this account cannot read. The output gives the reason and the state of each restricted cache. |
| `unverifiable` | A staged development copy without catalogue checksums: not a failure, but remove the staging entry before an official run. For a catalogue file, the catalogue records no SHA-256 for it: a failure that repair cannot fix. [Report it](report-a-problem.md) to the catalogue maintainers. |
| `note` | About a cache, not the file that was read: an entry passed over in a restricted cache listed before the one read, or a public dataset's entry in a restricted cache. Not a failure; tell that cache's maintainer. |

## Repair downloaded data

```bash
<your-tool>-data verify test_suite --deep --repair --dry-run
<your-tool>-data verify test_suite --deep --repair
<your-tool>-data verify test_suite --deep
```

Read the preview first: repair downloads the listed files again from the
published store, into the public cache. It never removes or replaces a link
and never touches restricted or staged data: a broken link, or a linked or
restricted copy that does not match, is only reported. Its owner repairs it;
on the cluster, [report it](report-a-problem.md) to the catalogue
maintainers. The final check must report every file as `ok`.

## Check a whole dataset fetched by key {#verify-complete-dataset}

A package's `verify` checks only what its collections select. To check every
file of a dataset, use the integrity API against the catalogue and caches in
effect:

```python
import ethos_data

catalog = ethos_data.catalog()
resources = catalog.resources("global-wind-atlas-v4")
findings = ethos_data.verify(catalog, resources, deep=True)
for finding in findings:
    if not finding.ok:
        print(finding.status, finding.resource.key)
```

Remove staging entries first; they would redirect the check away from the
cache.

!!! warning "Gap: `ethos-data` has no `verify`"
    Files fetched by key with `ethos-data fetch` can be checked only through
    the Python API above, or through a package collection that happens to
    select them. An `ethos-data verify <key> [--deep] [--repair]` would close
    the gap.

If verification still fails after a repair, [report the problem](report-a-problem.md).
