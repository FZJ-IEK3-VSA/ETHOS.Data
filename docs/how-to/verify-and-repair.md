# Check and repair the cache

Check the collection used by your workflow. Replace `collections.yaml` and
`onshore_wind` below with the collections file your workflow uses — your
project's own or one a package ships — and its collection.

## Check the stored files

```bash
ethos-data -c collections.yaml verify onshore_wind
ethos-data -c collections.yaml verify onshore_wind --deep
```

The first command checks sizes; `--deep` checks SHA-256 hashes and reads every
selected byte. Use `verify --all --deep` for every collection in the selected
file. Neither command repairs data.

| Finding | Next action |
|---|---|
| `ok` | Continue; only a deep check establishes a hash match. |
| `wrong size` or `wrong checksum` | Preserve deliberate edits, then repair a downloaded copy or contact the local source owner. |
| `dangling` | Restore the link target or review repair with the cache administrator. |
| `missing` or `unreadable` | Check the expected location and permissions. |
| `unavailable here` | Obtain the authorised installation if the workflow needs it. |
| `unverifiable` | Remove development staging before validating an official run. |

## Preview and perform a repair

For downloadable data:

```bash
ethos-data -c collections.yaml verify onshore_wind --deep --repair --dry-run
ethos-data -c collections.yaml verify onshore_wind --deep --repair
ethos-data -c collections.yaml verify onshore_wind --deep
```

Inspect the preview first. Repair can remove affected dataset links from the
public cache before fetching; other readers see that change. Coordinate with
the cache owner. Restricted and staged data are not repaired.

For a per-dataset root, fix that source or remove the override before expecting a
download. For internal inputs without a working download endpoint, restore the
authorised local copy. The final verification must match every required file.

To replace a healthy link with a verified copy, use
[Move linked data into the cache](move-linked-data-into-the-cache.md).
See [CLI reference](../reference/cli/ethos-data.md#verify-collection) for options
or [Report a problem](report-a-problem.md) if verification still fails.
