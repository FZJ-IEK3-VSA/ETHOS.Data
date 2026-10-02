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

## Where the settings are stored {#settings-file}

Every setting on this page is written to one file in your account:

| System | Settings file |
| --- | --- |
| Linux, including the ICE-2 cluster computer | `~/.config/ethos-data/config.yaml`, or `$XDG_CONFIG_HOME/ethos-data/config.yaml` if that variable is set |
| Windows | `%LOCALAPPDATA%\ethos-data\config.yaml` |
| macOS | `~/Library/Application Support/ethos-data/config.yaml` |

Every ETHOS tool reads this file, however ETHOS.Data was installed: in a conda
environment, in a virtual environment, with pip outside any environment, or
with pipx. A setting written by `ethos-data` or by any package's
`<your-tool>-data` command therefore applies to every script you run, from
whichever folder you start it. On the ICE-2 cluster computer your home
directory is the same on every node, so the settings also apply in batch jobs.

The settings say where data lies on this machine. Which datasets a workflow
needs, and which catalogue versions it accepts, come from the package's
collections file.

!!! warning "Gap: settings are read from four files"
    The current release reads four files, first match wins: an
    `ethos-data.yaml` found by searching upward from the working directory,
    the file in your account, a file inside the Python environment
    (`<sys.prefix>/etc/ethos-data/config.yaml`) and a machine-wide file. The
    `config` commands take `--scope project|user|environment|site` to choose
    among them, and `ETHOS_DATA_CONFIG` does not exist. On Windows the file
    in your account is `%LOCALAPPDATA%\ethos-data\ethos-data\config.yaml`
    and the default cache is `%LOCALAPPDATA%\ethos-data\ethos-data\Cache`.
    The planned change, [one settings file per
    account](../../explanation/architecture/decisions.md#one-settings-file-per-account-2026-10-02),
    is to be implemented separately.

## Check what is in effect

```bash
ethos-data config show
```

The command prints the settings file it read, the catalogue and cache
settings, and where each came from. It needs no network and loads no
catalogue. Run it before and after every change below.

## Public installation users {#public-installation-users}

Nothing has to be configured. Without a setting, every ETHOS tool reads the
public catalogue, or the version of it that the package declares, and
downloads into the per-user cache directory (`~/.cache/ethos-data` on Linux,
`%LOCALAPPDATA%\ethos-data\Cache` on Windows).

To put the cache on a disk with room:

```bash
ethos-data config set-public-cache /data/ethos/public
```

Licensed datasets are described in the public catalogue but never downloaded.
A workflow that needs one stops with an error that describes the dataset:
what it is, where it came from, its licence and attribution, and how to
obtain a copy, as far as the catalogue records them. Obtain your own copy
under its terms and register it:

```bash
ethos-data config set-restricted-cache /data/ethos/restricted
ethos-data link gadm-3.6 /data/licensed/gadm36_levels_shp
```

Every input a workflow names is required; no setting lets it run without one.

!!! warning "Gap: the error does not describe the dataset, and inputs can be left out"
    The error names the dataset and prints its `ethos:restriction` note
    only. It also offers to carry on without the dataset, through
    `--skip-unavailable`, `skip_unavailable=True`,
    `config set-skip-unavailable` or `ETHOS_SKIP_UNAVAILABLE`. The planned
    change, [every input is
    required](../../explanation/architecture/decisions.md#every-input-is-required-2026-10-02),
    is to be implemented separately.

## Cluster users {#cluster-users}

Work on the ICE-2 cluster computer, in the environment your package is
installed in. Take the three locations below from the ICE-2 wiki; the paths
here are placeholders.


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

The settings locate data; they grant no permission, which have to requested from the owner or a cluster administrator.

Record the catalogue version that `ethos-data config show` and
`<your-tool>-data show` print with your results.

## Check that a download works {#check-a-download}

Once the settings are in place, let ETHOS.Data fetch a small public
collection that ships with it:

```bash
ethos-data selftest
```

The self-test reads the settings and the catalogue they select, then fetches
a few public test files, under 200 KB in total, into your public cache and
checks each against the catalogue's checksums. It reports three steps:

1. the settings file, the catalogue and the caches in effect, and where each
   came from; a cache this machine cannot reach is marked;
2. the catalogue location and its version;
3. for each file, whether it was downloaded, already present or read in
   place, and its local path.

It ends with `selftest passed` and exit status `0`, or names the step that
failed and exits with `1`. A failure in the first two steps points at a
setting or the network; a failure in the third at the store or the cache
directory.

The self-test selects the catalogue the way a package's data command does:
`--catalog`, then `ETHOS_DATA_CATALOG` or the configured catalogue, then the
public one. The internal catalogue includes the same test files, so on the
cluster computer they are usually already in the shared cache and nothing is
downloaded. To force a download, give a new, empty directory as the cache:

```bash
ethos-data --root selftest-download selftest
```

Delete `selftest-download` afterwards. The same check from Python, in the
environment your scripts run in:

```python
import ethos_data

data = ethos_data.collections(ethos_data.EXAMPLE_COLLECTIONS)
print(data.settings)
print(data.paths("offshore_siting"))
```

`EXAMPLE_COLLECTIONS` is the collections file the self-test fetches, and the
same file the examples in [Use data in a script](use-data-in-a-script.md)
work with.

!!! warning "Gap: no self-test"
    `ethos-data selftest`, `ethos_data.EXAMPLE_COLLECTIONS` and the
    `settings` attribute do not exist, and the example collections file is
    only in the documentation, as
    [collections.yaml](../../assets/examples/collections.yaml). Until they
    are implemented, `ethos-data fetch
    reskit-test-data/placements/turbine_placements.csv` checks a single
    download. The [planned
    change](../../explanation/architecture/decisions.md#a-self-test-collection-ships-with-the-package-2026-10-02)
    is to be implemented separately.

## Use another settings file {#another-settings-file}

Name a file in `ETHOS_DATA_CONFIG` to use it instead of the one in your
account. ETHOS.Data then reads only that file, and the `config set-*` and
`unset-*` commands write to it:

=== "Bash"

    ```bash
    export ETHOS_DATA_CONFIG=/data/my-analysis/ethos-data.yaml
    ```

=== "PowerShell"

    ```powershell
    $env:ETHOS_DATA_CONFIG = "D:/my-analysis/ethos-data.yaml"
    ```

This keeps a CI job, a container or a batch job independent of the account
it runs under, and lets a team keep one file for a shared machine. To tie a
file to one conda environment, store the variable in the environment with
`conda env config vars set ETHOS_DATA_CONFIG=PATH` and activate the
environment again. The file must exist; only `config set-*` creates it.
Every other command stops and names the missing file.

!!! warning "Gap: `ETHOS_DATA_CONFIG` is not implemented"
    The variable is ignored. It is part of [one settings file per
    account](../../explanation/architecture/decisions.md#one-settings-file-per-account-2026-10-02),
    which is to be implemented separately.

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

Environment variables win over the settings file. For one command, put
`--catalog LOCATION` or `--root DIR` before the subcommand of `ethos-data` or of
your package's `<your-tool>-data` command.

## Remove a setting {#check-and-remove-settings}

```bash
ethos-data config unset-catalog
ethos-data config unset-public-cache
ethos-data config unset-restricted-cache
```

Each command removes the setting from the settings file in effect. Unsetting
changes configuration only; no data is moved or deleted. Clear the matching
environment variables too. Continue with
[Use data in a script](use-data-in-a-script.md).
