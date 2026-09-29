# Set up your machine

Point your account at the catalogue and the caches it should use. You need
[ETHOS.Data installed](../../installation.md), usually as a dependency of the
package you work with. Which section applies depends on the machine, not on
who you are:

| | Public installation | Cluster installation |
| --- | --- | --- |
| Machine | A laptop, a workstation or a CI runner, anywhere outside the ICE-2 cluster computer | The ICE-2 cluster computer |
| Catalogue | The public catalogue, built in, or the version a package declares | The internal catalogue on the cluster computer, which includes every public entry |
| Caches | Your own public cache; no restricted cache | The shared public and restricted caches |
| Restricted data | Not reachable, unless you register your own authorised copy | Read in place, if you are in the dataset's group |

An ICE-2 member working on a laptop is a public installation user: the
internal catalogue and the shared caches exist only on the cluster computer.

## Check what is in effect

```bash
ethos-data config show
```

The command prints the catalogue and cache settings, where each came from, and
every configuration file it read. It needs no network and loads no catalogue.
Run it before and after every change below.

## Public installation users {#public-installation-users}

Nothing has to be configured. Without a setting, every ETHOS tool reads the
public catalogue, or the version of it that the package declares, and
downloads into the per-user cache directory (`~/.cache/ethos-data` on Linux).

To put the cache on a disk with room:

```bash
ethos-data config set-public-cache /data/ethos/public
```

Licensed datasets are described in the public catalogue but never downloaded.
If a workflow you run names one, either obtain your own copy under its terms
and register it:

```bash
ethos-data config set-restricted-cache /data/ethos/restricted
ethos-data link gadm-3.6 /data/licensed/gadm36_levels_shp
```

or, when the workflow can run without it, carry on and have it left out:

```bash
ethos-data config set-skip-unavailable true
```

`link` puts a dataset whose access class is `restricted` into the restricted
cache; the entry is read in place and never copied. See
[Add restricted data](../catalogue-maintainers/add-restricted-data.md) for what a
link does and does not do.

## Cluster users {#cluster-users}

Work on the ICE-2 cluster computer, in the environment your package is
installed in. Take the three locations below from the ICE-2 wiki; the paths
here are placeholders.

!!! note "Data on the cluster computer may not be shared"
    The shared caches hold datasets the institute is not permitted to pass
    on. Do not copy data out of them, and do not put cluster paths or
    restricted dataset details into public repositories or issue trackers.

```bash
ethos-data config set-catalog /shared/ethos/catalogue/datacatalog.json
ethos-data config set-public-cache /shared/ethos/public
ethos-data config set-restricted-cache /shared/ethos/restricted
```

| Setting | What it does |
| --- | --- |
| catalogue | Selects the internal catalogue, which includes every public entry plus the internal and restricted ones. It replaces the public catalogue and any version a package declares. |
| public cache | The shared directory where public and internal data already lies, as links or copies, and where downloads land. |
| restricted cache | The shared directory holding the licensed datasets the institute may use. Retrieval reads it in place and never writes to it. |

Every user runs these three commands for their own account; there is no
machine-wide default. The settings locate data; they grant no permission.
Reading a restricted dataset still needs the filesystem permission its
custodian gives you, and asking for a dataset you are not in the group of
fails with an explanation.

Use `--scope environment` to store a setting inside one conda environment, or
`--scope project` to write an `ethos-data.yaml` next to your work that a team
can commit. The default scope, `user`, is your account. Record the catalogue
version that `ethos-data config show` and `<your-tool>-data show` print with
your results.

## Override one shell or one run {#temporary-overrides}

=== "Bash"

    ```bash
    export ETHOS_DATA_CATALOG=/shared/ethos/catalogue/datacatalog.json
    export ETHOS_DATA_DIR=/scratch/me/ethos-public
    export ETHOS_RESTRICTED_DIR=/shared/ethos/restricted
    ```

=== "PowerShell"

    ```powershell
    $env:ETHOS_DATA_CATALOG = "D:/catalogue/datacatalog.json"
    $env:ETHOS_DATA_DIR = "D:/ethos/public"
    $env:ETHOS_RESTRICTED_DIR = "D:/ethos/restricted"
    ```

Environment variables win over stored settings. For one command, put
`--catalog LOCATION` or `--root DIR` before the subcommand of `ethos-data` or of
your package's `<your-tool>-data` command.

## Remove a setting {#check-and-remove-settings}

Unset in the scope where the setting was written:

```bash
ethos-data config unset-catalog
ethos-data config unset-public-cache --scope environment
ethos-data config unset-restricted-cache
ethos-data config unset-skip-unavailable
```

Unsetting changes configuration only; no data is moved or deleted. Clear the
matching environment variables too. Continue with
[Use data in a script](use-data-in-a-script.md).
