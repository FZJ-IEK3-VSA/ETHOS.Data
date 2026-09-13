# Configure the cache

ETHOS.Data keeps data in two caches:

| Cache | Holds | Default |
|---|---|---|
| **public cache** | everything downloaded from the catalogue | your operating system's per-user cache directory |
| **restricted cache** | your private copy of licensed or proprietary datasets | none |

Public data needs no configuration. Set a cache only to put it somewhere else.

## Four Configuration Options

The first option that is set wins.

| | Option | Public cache | Restricted cache | Applies to |
|---|---|---|---|---|
| 1 | command-line option or Python argument | `--root DIR` / `root=DIR` | — | one command or call |
| 2 | environment variable | `ETHOS_DATA_DIR` | `ETHOS_RESTRICTED_DIR` | one shell or job |
| 3 | project file | `config set-public-cache DIR --scope project` | `config set-restricted-cache DIR --scope project` | one project folder |
| 4 | personal setting | `config set-public-cache DIR` | `config set-restricted-cache DIR` | all your work |

### 1. For one command or call

```bash
ethos-data --root /data/ethos-data -p reskit fetch onshore_wind
```

```python
ethos_data.fetch("onshore_wind", package="reskit", root="/data/ethos-data")
```

### 2. For one shell or job

```bash
export ETHOS_DATA_DIR=/scratch/me/ethos-data
export ETHOS_RESTRICTED_DIR=/data/licensed
```

In PowerShell, use `$env:ETHOS_DATA_DIR = "D:\ethos-data"`.

### 3. For one project

Run in the project folder:

```bash
ethos-data config set-public-cache /data/my-project/ethos-data --scope project
ethos-data config set-restricted-cache /data/licensed --scope project
```

This writes `ethos-data.yaml` into the current folder:

```yaml title="ethos-data.yaml"
public_cache: /data/my-project/ethos-data
restricted_cache: /data/licensed
```

The file applies to this folder and every folder below it. Commit it to share
the setting with your team.

### 4. For all your work

```bash
ethos-data config set-public-cache /data/ethos-data
ethos-data config set-restricted-cache /data/licensed
```

## Check the result

```bash
ethos-data config show
```

The output lists each cache and the option that set it.

## Remove a setting

```bash
ethos-data config unset-public-cache
ethos-data config unset-restricted-cache --scope project
```

Use the same `--scope` you set it with.

## See also

- [Work with restricted data](restricted-data.md)
- [Configuration reference](../reference/configuration.md) — every key, scope
  and default.
