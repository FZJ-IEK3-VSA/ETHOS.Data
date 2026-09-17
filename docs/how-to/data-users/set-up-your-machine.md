# Set up your machine

Choose shared catalogue and cache locations for your account. You need
[ETHOS.Data installed](../../installation.md). All paths below are examples;
obtain deployment paths and restricted-data permission from your administrator.

## Inspect existing settings

```bash
ethos-data config show
```

Keep suitable site defaults. This command reports shared settings and their
origins without loading the catalogue. It does not resolve a package's pin or
per-command overrides.

## Select the catalogue {#select-the-catalogue}

Without an override, `ethos-data` uses the public catalogue and package commands
use their shipped pin. For institute data, select the complete internal index:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/current/datacatalog.json
```

The setting takes an index path or URL. The internal catalogue includes public
entries. Use `versions/REVISION/datacatalog.json` for a reproducible run.
Append `--scope project` for one project; the default is `user`. A package may
supply a stronger override such as `RESKIT_DATA_CATALOG`.

To select metadata for one command:

```bash
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json ls
```

Use the same `--catalog` with `reskit-data show` when comparing RESKit's
selections. If a pin is unreachable, obtain a complete built catalogue from its
maintainer; the [practice lesson](../../tutorials/first-fetch.md) needs no release.

## Select cache locations {#cache-locations}

The per-user public cache works without setup. To use another disk:

```bash
ethos-data config set-public-cache /data/ethos/public --scope environment
```

For licensed inputs you are authorised to read:

```bash
ethos-data config set-restricted-cache /data/ethos/restricted --scope environment
```

Keep public, restricted and development roots separate. Each cache uses
`<root>/<dataset>/<resource path>`. Settings do not move existing files or grant
permissions. Retrieval reads restricted data in place and never downloads or
repairs it. If one dataset lives elsewhere, use the
[local-copy guide](../catalogue-maintainers/link-cluster-data.md#dataset-root-overrides).

Project settings should contain paths usable by the intended team. Administrators
can use `--scope site` for machine defaults. The
[configuration reference](../../reference/configuration.md) defines all scopes and
precedence. Configure a staging root only while
[developing a dataset](../package-maintainers/propose-a-dataset.md#stage-development-data).

## Override one shell or run {#temporary-overrides}

=== "Bash"

    ```bash
    export ETHOS_DATA_DIR=/scratch/me/ethos-public
    export ETHOS_RESTRICTED_DIR=/data/ethos/restricted
    export ETHOS_DATA_CATALOG=/shared/ethos/catalogue/current/datacatalog.json
    ```

=== "PowerShell"

    ```powershell
    $env:ETHOS_DATA_DIR = "D:/ethos/public"
    $env:ETHOS_RESTRICTED_DIR = "D:/ethos/restricted"
    $env:ETHOS_DATA_CATALOG = "D:/catalogue/datacatalog.json"
    ```

Environment variables override stored settings. For one invocation, use
`ethos-data --root /scratch/me/ethos-public fetch KEY`, or put the same option
before a package subcommand. Per-dataset roots and staging can still redirect
individual inputs.

## Handle an unavailable restricted input {#restricted-data}

Read the dataset's access note and ask its custodian for permission and the
installation location. Required inputs must remain errors when absent.
Only if the workflow supports omitted inputs, use:

```bash
reskit-data --skip-unavailable fetch onshore_wind
```

In Python, pass `skip_unavailable=True` to the collections handle's `fetch` or
`paths`. Skipped files and named inputs are absent from the returned mapping;
check for the keys before using them. A project preference can be stored with
`ethos-data config set-skip-unavailable true --scope project`.

## Check and remove settings {#check-and-remove-settings}

```bash
ethos-data config show
ethos-data ls
reskit-data show
reskit-data fetch onshore_wind --test --plan
```

The first listing checks the direct catalogue; the second names RESKit's actual
catalogue and collections. The plan reports transfers and missing inputs without
downloading data. For integrity checks, use [Verify and repair](verify-and-repair.md).

Remove a setting in the scope where it was written:

```bash
ethos-data config unset-catalog
ethos-data config unset-public-cache --scope environment
ethos-data config unset-restricted-cache --scope environment
ethos-data config unset-skip-unavailable --scope project
```

Clear any corresponding environment override too. Unsetting does not delete
data. Continue with [Get data by catalogue key](get-data-for-a-task.md) or
[diagnose a failure](troubleshoot-catalogue.md).
