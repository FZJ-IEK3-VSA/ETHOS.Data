# 0010. Read settings from one file per account, once per handle

**Status:** proposed · **Date:** 2026-10-02 · **Implemented by:** #14, #15, a new PR (shared cache: the `shared_cache` setting), #19 (the bounds step inside the one resolver), a new PR (inventory reader: the metadata cache from the snapshot), #25 (the download switch in the snapshot)

## Context

Settings must resolve the same way however a script starts (from an editor, a
terminal, a notebook or a batch job, in any folder) and however ETHOS.Data was
installed (conda, a virtual environment, pip, pipx, `uv tool`). The cluster is
configured per account, not per machine. CI jobs and test runs must be
isolated from the account they run under. A script must be able to record
which settings decided its inputs.

## Decision

- Settings say where data lies for one person on one machine. Which data a
  workflow needs, and which catalogue releases it accepts, come from the
  package's collections file.
- Each setting is the first of four sources: an explicit argument (`root=` or
  `--root`, `catalog=` or `--catalog`), an environment variable, the settings
  file, the built-in default.

| Setting | Key in the settings file | Environment variable | Default |
|---|---|---|---|
| Public cache, personal | `public_cache` | `ETHOS_DATA_DIR` | the per-user cache directory: `~/.cache/ethos-data`, `%LOCALAPPDATA%\ethos-data\Cache`, `~/Library/Caches/ethos-data` |
| Shared cache, on the cluster ([0028](0028-read-only-shared-cache.md)) | `shared_cache` | `ETHOS_SHARED_DIR` | none |
| Restricted cache | `restricted_cache` | `ETHOS_RESTRICTED_DIR` | none |
| Staging root | `staging_cache` | `ETHOS_STAGING_DIR` | none |
| Catalogue | `catalog` | `ETHOS_DATA_CATALOG` | chosen from the release bounds, else the public `main` index |
| Publication URL | `publication_url` | `ETHOS_PUBLICATION_URL` | the URL the catalogue declares |
| Per-dataset roots | `dataset_roots` | — | none |

- `config set-…` writes a setting and `config unset-…` removes it, one pair
  per setting: `public-cache`, `shared-cache`, `restricted-cache`,
  `staging-cache`, `catalog` and `publication-url`, for example
  `config set-shared-cache DIR` and `config unset-shared-cache`. A
  per-dataset root is set with `config set-root DATASET DIR` and removed with
  `config unset-root DATASET`.
- The settings file is the file `ETHOS_DATA_CONFIG` names, which replaces the
  account's file; nothing is merged. Otherwise it is the account's file:
  `~/.config/ethos-data/config.yaml` on Linux (`$XDG_CONFIG_HOME` respected),
  `%LOCALAPPDATA%\ethos-data\config.yaml` on Windows, and
  `~/Library/Application Support/ethos-data/config.yaml` on macOS.
- Only `config set-*` creates a settings file. A file `ETHOS_DATA_CONFIG` names
  must exist, and every other command stops and names it. Unsetting the last
  value leaves the file empty.
- A handle or a command reads the settings once, into one snapshot that names
  each value's source. The snapshot also holds the download switch
  (`download=`, `ETHOS_DATA_DOWNLOAD`) and the metadata cache's policy and
  location (`<public cache>/.catalog`, `ETHOS_CATALOG_NO_CACHE`). Every later
  read of a setting goes through the snapshot, so a change to the environment
  or the file after a handle was built does not change what the handle reads.
- `print(handle.settings)` and `handle.settings.as_dict()` give every value
  and its source, for a results file.
- One catalogue resolver, `Settings.choose_catalog`, takes the first of:
    1. an explicit `--catalog` or `catalog=`, then a package's own `catalog=`
       given to `tool_main`;
    2. `ETHOS_DATA_CATALOG`, or the `catalog` setting;
    3. with release bounds, the newest public release they admit, read from
       its tag ([0018](0018-numbered-catalogue-releases.md));
    4. the public `main` index.
- `config show` prints the snapshot, the shared cache included, with
  unreachable roots marked, then the precedence and the numbered lookup chain
  ([0012](0012-one-lookup-chain.md)).
- Lessons name a lesson settings file in `ETHOS_DATA_CONFIG`, so they never
  touch the reader's own settings.

## Alternatives considered

- **Four files with a fixed lookup:** one in the project, one in the account,
  one in the environment and one for the machine. A committed project file
  carries one machine's paths, the release bounds already live in the
  collections file, four places to look confuse, and a machine-wide file
  contradicts the per-account configuration of the cluster.
- **An environment file beside the account's.** With pipx, `uv tool` or several
  environments, the command that writes a setting and the script that reads
  it run in different interpreters. `conda env config vars set
  ETHOS_DATA_CONFIG=…` gives an environment its own file instead.
- **Merging `ETHOS_DATA_CONFIG` over the account's file.** A CI job or a test
  run would inherit whatever the account has set.

## Consequences

- The same settings apply from an editor, a terminal, a notebook or a batch
  job, in any folder. Any package's data command writes the one file all of
  them read.
- A results file can record every setting and where it came from.
- A CI job or a test run names its own file in `ETHOS_DATA_CONFIG` and is
  isolated from its account.
- On the cluster each user sets the served checkout, the shared cache and the
  restricted cache in their own file, with the values the ICE-2 wiki gives,
  and may move their public cache to a place the wiki recommends, such as
  scratch storage. There is no machine-wide setting
  ([0026](0026-internal-catalogue-on-the-cluster.md),
  [0028](0028-read-only-shared-cache.md)).
- See [Where the settings are stored](../../../how-to/data-users/set-up-your-machine.md#settings-file),
  [Use another settings file](../../../how-to/data-users/set-up-your-machine.md#another-settings-file)
  and [Configuration](../../../reference/configuration.md).

## Related

- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0018. Number catalogue releases `vYYYY.MM.N` and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [0028. Serve shared data on the cluster from a read-only shared cache](0028-read-only-shared-cache.md)
- [5. Building Block View](../building-blocks.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
