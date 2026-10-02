# Report a problem

Work out whether a failure is on your machine or in the catalogue and its
storage, then send a report the maintainer can act on. Run everything in the
same environment and working directory as the failing script or command.

## 1. Read the error

Every error names what failed and, where there is one, the setting or command
that fixes it. The common ones:

| Error | Meaning | What to do |
| --- | --- | --- |
| `CatalogUnavailable` | The catalogue location cannot be read: wrong path or URL, no network, or a version that does not exist yet. | Run `ethos-data config show`; check the location and, on the cluster computer, your read permission. |
| `IncompleteCatalog` | The catalogue index lists a dataset whose descriptor is missing from the served copy. | Not yours to fix: report it. A copy of only the index is not a catalogue. |
| `UnknownDataset`, unknown key | The selected catalogue does not describe that name. | Check the spelling and which catalogue is selected. An internal dataset is invisible through the public catalogue. |
| `AccessError` | A licensed dataset has no copy on this machine that you may read. The error describes the dataset and how to obtain it. | Obtain a copy under its terms and [register it](set-up-your-machine.md#public-installation-users); on the cluster computer, ask the dataset's custodian for access. |
| Hash mismatch, `wrong checksum` | The downloaded or linked bytes differ from the catalogue. | [Verify and repair](verify-and-repair.md). If a repair fails again, report it. |
| Download error, 404, 403 | The published store does not serve a file the catalogue lists. | Report it with the URL from the error. |
| Unresolved-licence warning | The dataset's terms have not been reviewed yet. | Not an error. Tell the catalogue maintainer if you know the terms. |

## 2. Collect the facts

```bash
ethos-data selftest
ethos-data config show
<your-tool>-data show
<your-tool>-data fetch <collection> --plan
```

The [self-test](set-up-your-machine.md#check-a-download) fetches a small
public collection that ships with ETHOS.Data. If it fails too, the cause is
the machine, its settings or the store rather than the package, and its
output names the failing step. `config show` prints every setting and its
origin. `show` names the catalogue the package actually reads and marks
unresolvable collections. The plan says what a fetch would download and what
is missing, without downloading.

To rule out a stale metadata cache without changing settings:

=== "Bash"

    ```bash
    ETHOS_CATALOG_NO_CACHE=1 <your-tool>-data show
    ```

=== "PowerShell"

    ```powershell
    $env:ETHOS_CATALOG_NO_CACHE = "1"
    <your-tool>-data show
    Remove-Item Env:ETHOS_CATALOG_NO_CACHE
    ```

If needed, repeat the failing command with a fresh, empty `--root DIR` to
separate cache state from catalogue state. Do not download a large collection
only to complete a report.

## 3. Write the report {#report-a-problem}

Copy and fill this template:

```text
Expected result:
Actual result and full error text:
Smallest command or Python snippet that reproduces it:
Versions: ETHOS.Data, the package, Python, operating system:
Output of `ethos-data selftest`:
Catalogue location and version (from `config show` and `show`):
Collection or catalogue key:
Cache settings and their origins (from `config show`):
Staging entries, dataset-root overrides or bundles in use:
Output of `fetch --plan` and `verify`:
When it last worked and what changed since:
```

Remove tokens, credential-bearing URLs and personal paths before posting in a
public tracker. Cluster paths and details of restricted datasets go to the
internal tracker only.

## 4. Send it to the right place

| Problem | Where |
| --- | --- |
| The `ethos-data` command, the Python API or this documentation | [ETHOS.Data issues](https://github.com/FZJ-IEK3-VSA/ETHOS.Data/issues) |
| A public dataset's contents, licence or published catalogue entry, from a public installation | [ETHOS.Data-Catalogue issues](https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/issues) |
| Anything about the internal catalogue, restricted data or the shared caches, from a cluster installation | [ethos-data-catalog-internal on JuGit](https://jugit.fz-juelich.de/iek-3/shared-code/ethos-data-catalog-internal) |
| A package's collection or workflow | That package's issue tracker |

If ownership is unclear, start with the catalogue maintainer named on the
ICE-2 wiki and include the checks you already ran. The maintainer continues
with [Diagnose a report](../catalogue-maintainers/diagnose-a-report.md).
