# Configure the cache

Choose where this machine reads and stores data. For initial catalogue and cache
setup together, use [Set up your machine](set-up-your-machine.md).

## Set persistent locations

Use absolute paths to a public/internal cache and a separate authorised restricted
installation. These are example paths:

```bash
ethos-data config set-public-cache /data/ethos/public
ethos-data config set-restricted-cache /data/ethos/restricted
ethos-data config show
```

These commands change settings; they do not move files, grant permissions, or
download restricted data. Datasets live at `<root>/<dataset>/<path>`.

Append `--scope project` to use the nearest project config (or create one in the
current directory). The default is `user`. Administrators can use `--scope site`;
`--scope environment` applies to a Python environment. Commit project settings
only when their paths work for the intended team.

## Override one run or shell

`--root` goes before the subcommand; `collections.yaml` is the collections file
your project uses or the one a package ships:

```bash
ethos-data --root /scratch/me/ethos-public -c collections.yaml fetch onshore_wind
```

=== "Bash"

    ```bash
    export ETHOS_DATA_DIR=/scratch/me/ethos-public
    export ETHOS_RESTRICTED_DIR=/data/ethos/restricted
    ```

=== "PowerShell"

    ```powershell
    $env:ETHOS_DATA_DIR = "D:\ethos\public"
    $env:ETHOS_RESTRICTED_DIR = "D:\ethos\restricted"
    ```

Environment variables override config files. Per-dataset roots and staging can
still redirect individual datasets; inspect them with `config show`.

## Remove a setting

```bash
ethos-data config unset-public-cache
ethos-data config unset-restricted-cache --scope project
ethos-data config show
```

Use the scope where the setting was written. Also clear any environment variable
that overrides it. Unsetting does not delete data.

See [Configuration reference](../reference/configuration.md) for all precedence
rules and [Work with restricted data](restricted-data.md) for access setup.
