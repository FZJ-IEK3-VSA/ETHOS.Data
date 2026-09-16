# Check and repair the cache

Check the collection used by your workflow. Examples use RESKit's wrapper and
`onshore_wind`; substitute your package command and collection. To verify a
complete dataset beyond a package's selection, use the
[integrity API example](link-cluster-data.md#verify-complete-dataset).

## Check the stored files

```bash
reskit-data verify onshore_wind
reskit-data verify onshore_wind --deep
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
reskit-data verify onshore_wind --deep --repair --dry-run
reskit-data verify onshore_wind --deep --repair
reskit-data verify onshore_wind --deep
```

Inspect the preview first. Repair can remove affected dataset links from the
public cache before fetching; other readers see that change. Coordinate with
the cache owner. Restricted and staged data are not repaired.

For a per-dataset root, fix that source or remove the override before expecting a
download. For internal inputs without a working download endpoint, restore the
authorised local copy. The final verification must match every required file.

To replace a healthy link with a verified copy, use
[Move linked data into the cache](link-cluster-data.md#materialize-copies).
See [CLI reference](../reference/cli/package-data.md#verify-collection) for options
or [Report a problem](troubleshoot-catalogue.md#report-a-problem) if verification still fails.
