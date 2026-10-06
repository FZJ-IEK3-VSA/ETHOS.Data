# Set up your machine

Point your account at the catalogue and the caches it should use. You need
[ETHOS.Data installed](../../installation.md), usually as a dependency of the
package you work with. Which section applies depends on the machine, not on
who you are:

| | Public installation | Cluster installation |
| --- | --- | --- |
| Machine | A laptop, a workstation or a CI runner, anywhere outside the ICE-2 cluster computer | The ICE-2 cluster computer |
| Catalogue | The public catalogue, built in, or the version a package declares | The internal catalogue on the cluster computer, which includes every public entry |
| Caches | Your own public cache; a restricted cache only if you register a copy of restricted data | The cluster's public cache, which every cluster user shares; restricted caches only if your groups admit them |
| Restricted data | Not reachable, unless you register your own authorised copy | Read in place from the restricted caches you list |

An ICE-2 member working on a laptop is a public installation user: the
internal catalogue, the cluster's public cache and its restricted caches
exist only on the cluster computer.

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

## Check what is in effect

```bash
ethos-data config show
```

The command prints the settings file it read, the catalogue and cache
settings, and where each came from. It numbers the restricted caches and
marks one it cannot reach; if you list none, it says so, which is a normal
set-up. It needs no network and loads no catalogue. Run it before and after
every change below.

## Public installation users {#public-installation-users}

Nothing has to be configured. Without a setting, every ETHOS tool reads the
public catalogue, or the version of it that the package declares, and
downloads into the per-user cache directory (`~/.cache/ethos-data` on Linux,
`%LOCALAPPDATA%\ethos-data\Cache` on Windows).

To put the cache on a disk with room:

```bash
ethos-data config set-public-cache /data/ethos/public
```

Restricted datasets, licensed ones for example, may be described in the
public catalogue, but they are never downloaded. A workflow that needs one
stops before anything is downloaded, with an error that names the dataset and
says how to obtain it, as far as the catalogue records that;
[`--meta`](use-data-in-a-script.md#metadata) prints its full description.
Obtain your own copy under its terms and register it:

```bash
ethos-data config add-restricted-cache /data/ethos/restricted
ethos-data link gadm-3.6 /data/licensed/gadm36_levels_shp
```

The first command lists a restricted cache in your settings, once. The second
links your copy into it, and the copy is read in place.

Every input a workflow names is required; no setting lets it run without one.

!!! warning "Gap: inputs can be left out"
    The code's refusal names the dataset and prints the `ethos:restriction`
    note only, and it offers to carry on without the dataset, through `--skip-unavailable`,
    `skip_unavailable=True`, `config set-skip-unavailable` or
    `ETHOS_SKIP_UNAVAILABLE`. See [every input is
    required](../../explanation/architecture/decisions/0013-every-input-is-required.md).

## Cluster users {#cluster-users}

Work on the ICE-2 cluster computer, in the environment your package is
installed in. Take the locations below from the ICE-2 wiki; the paths here
are placeholders. Every cluster user sets the catalogue and the public cache:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/datacatalog.json
ethos-data config set-public-cache /shared/ethos/cache
```

If your groups admit restricted data, add the restricted cache of each such
group:

```bash
ethos-data config add-restricted-cache /shared/ethos/restricted/<group>
```

| Setting | What it does |
| --- | --- |
| catalogue | Selects the internal catalogue, which describes every dataset, including those the public catalogue hides. It replaces the public catalogue and any version a package declares. |
| public cache | The cluster's public cache, one directory that every cluster user shares and may write. Public data lies there as links into project storage or as copies, and a public file it lacks is downloaded into it, once for everyone. |
| restricted caches | One directory per access combination, for example every member of the institute or one licence group. Retrieval reads them in place and never writes to them. |

A user who works with public data only adds no restricted cache, and every
workflow that needs no restricted data runs. The settings locate data; they
grant no permission. Ask the dataset's owner or a cluster administrator for
access.

A broken link in the cluster's public cache stops every user's read of that
dataset until a catalogue maintainer repairs it; [report it](report-a-problem.md).

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
cluster computer they are usually read in place from the cluster's public
cache, and nothing is downloaded. To force a download, give a new, empty
directory as the cache:

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
    `ethos-data selftest` and `ethos_data.EXAMPLE_COLLECTIONS` do not
    exist, and the example collections file is only in the documentation, as
    [collections.yaml](../../assets/examples/collections.yaml). With the
    code, `ethos-data fetch
    reskit-test-data/placements/turbine_placements.csv` checks a single
    download. See [the self-test
    collection](../../explanation/architecture/decisions/0017-self-test-collection.md).

## Use another settings file {#another-settings-file}

Name a file in `ETHOS_DATA_CONFIG` to use it instead of the one in your
account. ETHOS.Data then reads only that file, and the `config` commands that
change a setting write to it:

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
environment again. The file must exist; only `config set-*` and
`config add-restricted-cache` create it. Every other command stops and names
the missing file.

## Override one shell or one run {#temporary-overrides}

=== "Bash"

    ```bash
    export ETHOS_DATA_CATALOG=/shared/ethos/catalogue/datacatalog.json
    export ETHOS_DATA_DIR=/scratch/me/ethos-public
    export ETHOS_RESTRICTED_DIRS=/shared/ethos/restricted/group-a:/shared/ethos/restricted/group-b
    ```

=== "PowerShell"

    ```powershell
    $env:ETHOS_DATA_CATALOG = "D:/catalogue/datacatalog.json"
    $env:ETHOS_DATA_DIR = "D:/ethos/public"
    $env:ETHOS_RESTRICTED_DIRS = "D:/ethos/restricted;E:/licensed"
    ```

Environment variables win over the settings file. `ETHOS_RESTRICTED_DIRS`
lists restricted caches separated by `:`, on Windows by `;`, and replaces
the list in the settings file; nothing is merged. For one command, put
`--catalog LOCATION` or `--root DIR` before the subcommand of `ethos-data` or of
your package's `<your-tool>-data` command.

## Remove a setting {#check-and-remove-settings}

```bash
ethos-data config unset-catalog
ethos-data config unset-public-cache
ethos-data config remove-restricted-cache /data/ethos/restricted
```

Each command removes a setting from the settings file in effect;
`remove-restricted-cache` removes one directory from the list of restricted
caches. Removing a setting changes configuration only; no data is moved or
deleted. Clear the matching environment variables too. Continue with
[Use data in a script](use-data-in-a-script.md).
