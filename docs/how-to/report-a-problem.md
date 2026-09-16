# Identify and report a data problem

Use the same Python environment and working directory as the failing workflow.
`collections.yaml` is the collections file your project uses or the one a
package ships; replace it and `onshore_wind` with yours.

## 1. Locate the failure

```bash
python -c "import sys, ethos_data; print(sys.version); print(ethos_data.__version__); print(ethos_data.__file__)"
ethos-data config show
ethos-data -c collections.yaml list
ethos-data -c collections.yaml plan onshore_wind
ethos-data -c collections.yaml verify onshore_wind --deep
```

Repeat any `--catalog` and `--root` options used by the failing command **before**
the subcommand. `config show` reports persistent/environment settings; it does
not resolve those per-command overrides or inspect the collections file's pin.
`list` prints the actual selected catalogue. Verification reads data without
repairing it.

| Finding | Next action |
|---|---|
| Collections file cannot be found | Pass `-c /path/to/collections.yaml`, or check the default set with `config set-collections` and the `collections.yaml` in the working directory. |
| Catalogue index cannot be read (`CatalogUnavailable`) | The message names the location. Check `config show` and the collections file's `catalog:` pin — a revision nobody has released yet, or a moved repository — and select another catalogue with `--catalog`, `$ETHOS_DATA_CATALOG` or `config set-catalog`. |
| Unknown dataset or missing metadata | Check the spelling and catalogue version; for hidden data, select the internal catalogue. |
| Restricted data unavailable | [Configure an authorised copy](restricted-data.md) or contact its custodian. |
| Cache path marked `NOT REACHABLE` by `config show` | Reconnect the network drive or mount it, or point at another cache with `--root` / `ETHOS_DATA_DIR` for this run. |
| Unexpected local path or staging warning | Inspect configuration origins and `ethos-data staging list`; remove obsolete overrides. |
| Wrong size/hash in a downloaded cache entry | [Preview a repair](verify-and-repair.md); preserve intentional edits first. |
| Broken shared link or unreadable cluster path | Send the path and finding to the cluster/cache administrator. |
| Data passes verification but gives a wrong scientific result | Provide the smallest input and calculation demonstrating the problem to the package or dataset maintainer. |

For descriptor, deployment, and upload failures, use
[Diagnose catalogue problems](troubleshoot-catalogue.md).

## 2. Prepare a reproducible report

Copy and fill this template:

```text
Expected result:
Actual result and full error:
Smallest command or Python example:
ETHOS.Data, consuming-package, Python and OS versions:
Catalogue location and exact revision:
Collection and resource key:
Relevant config origins and actual data path:
Staging, local-root overrides, or modified bundle in use:
plan / verify findings:
When it last worked and what changed:
```

If needed, retry `plan` with a new disposable `--root` to isolate downloaded
metadata/cache state. A different root does not disable staging, per-dataset
roots, or catalogue overrides. Do not download a large collection just to
complete the report.

## 3. Send it to the responsible maintainer

| Problem | Where to report |
|---|---|
| ETHOS.Data CLI/API or documentation | [ETHOS.Data issues](https://github.com/FZJ-IEK3-VSA/ETHOS.Data/issues) |
| Public dataset contents, licence metadata, or published catalogue | [Catalogue issues](https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/issues) |
| A package's collection or calculation | That package's issue tracker |
| Internal metadata, restricted files, cluster permissions, or dCache credentials | The internal catalogue maintainer, dataset custodian, or cluster support channel supplied by your administrator |

Remove tokens, credential-bearing URLs, personal paths, and confidential
metadata before posting publicly. Share restricted examples through the agreed
internal channel. If ownership is unclear, start with the catalogue maintainer
and include the checks already completed.

