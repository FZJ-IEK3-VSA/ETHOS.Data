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
| `UnknownDataset`, unknown key | The dataset or key cannot be found: the name is mistyped, or the catalogue in use does not publish it. | Check the spelling and which catalogue is selected. A hidden dataset is not in the public catalogue. |
| `CollectionError` | The collection has no test (or full) variant, or a named path is in one variant only; the message names the collection and the variant or the named path. | Ask for a variant the collection defines; otherwise report it to the package maintainer. |
| `AccessError` | A restricted dataset has no copy this account may read: the error says how to obtain and register one. Or a file read in place is missing, for example behind a broken link. | Obtain a copy under its terms and [register it](set-up-your-machine.md#public-installation-users); on the cluster computer, ask the dataset's custodian for access and [add your group's restricted cache](set-up-your-machine.md#cluster-users). Report a broken link. |
| Hash mismatch, `wrong checksum` | The downloaded or linked bytes differ from the catalogue. | [Verify and repair](verify-and-repair.md). If a repair fails again, report it. |
| Download error, 404, 403 | The published store does not serve a file the catalogue lists. | Report it with the URL from the error. |
| Unresolved-licence warning | The dataset's terms have not been reviewed yet. | Not an error. Tell the catalogue maintainer if you know the terms. |

## 2. Collect the facts

```bash
<your-tool>-data report <collection>
ethos-data report <key>
```

`report` runs the checks below and prints their output in the report
template of step 3, with tokens, credentials in URLs, your home directory and
your account name removed, and names the tracker to post it at. `--no-selftest`
leaves out the self-test's small download. The checks one by one:

```bash
ethos-data selftest
ethos-data config show
<your-tool>-data show
<your-tool>-data fetch <collection> --plan
<your-tool>-data verify <collection>
```

The [self-test](set-up-your-machine.md#check-a-download) fetches a small
public collection that ships with ETHOS.Data. If it fails too, the cause is
the machine, its settings or the store rather than the package, and its
output names the failing step. `config show` prints every setting and its
origin. `show` names the catalogue the package actually reads and marks
unresolvable collections. The plan says what a fetch would download and what
is missing, without downloading, and the state of every listed restricted
cache for the collection's restricted data. `verify` compares sizes, which
reads no file, and names a broken link in the public cache.

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

`report` printed the template with the facts filled in; add what only you
know. Without it, copy and fill this template:

```text
Expected result:
Actual result and full error text:
Smallest command or Python snippet that reproduces it:
Versions: ETHOS.Data, the package, Python, operating system:
Output of `ethos-data selftest`:
Catalogue location and version (from `config show` and `show`):
Collection or catalogue key:
Cache settings and their origins (from `config show`):
Staging entries or bundles in use:
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
| Restricted data, from any installation; the internal catalogue, the cluster's public cache or a restricted cache, from a cluster installation | [ethos-data-catalog-internal on JuGit](https://jugit.fz-juelich.de/iek-3/shared-code/ethos-data-catalog-internal) |
| A package's collection or workflow | That package's issue tracker |

If ownership is unclear, start with the catalogue maintainer named on the
ICE-2 wiki and include the checks you already ran. The maintainer continues
with [Diagnose a report](../catalogue-maintainers/diagnose-a-report.md).
