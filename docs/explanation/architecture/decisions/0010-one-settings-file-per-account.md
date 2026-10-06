# 0010. Read settings from one file per account, once per handle

**Status:** proposed · **Date:** 2026-10-06 · **Implemented by:** #14 (the settings file and the snapshot, with no per-dataset roots), #15, #39 (the `restricted_caches` list), #19 (the bounds step inside the one resolver), a new PR (inventory reader: the metadata cache from the snapshot), #25 (the download switch in the snapshot)

## Context

Settings must resolve the same way however a script starts (from an editor, a
terminal, a notebook or a batch job, in any folder) and however ETHOS.Data was
installed (conda, a virtual environment, pip, pipx, `uv tool`). The cluster is
configured per account, not per machine. An account may read restricted data
from several caches, or from none. CI jobs and test runs must be isolated from
the account they run under. A script must be able to record which settings
decided its inputs.

## Decision

- Settings say where data lies for one person on one machine. Which data a
  workflow needs, and which catalogue releases it accepts, come from the
  package's collections file.
- Every setting except the restricted caches is the first of four sources:
  an explicit argument (`root=` or `--root` for the public cache, `catalog=`
  or `--catalog`), an environment variable, the settings file, the built-in
  default.
- The restricted caches are a list with no explicit argument and no default.
  `ETHOS_RESTRICTED_DIRS` replaces the file's list; nothing is merged.

| Setting | Key in the settings file | Environment variable | Default |
|---|---|---|---|
| Public cache; on the cluster, the shared directory the ICE-2 wiki names ([0028](0028-one-public-cache-on-the-cluster.md)) | `public_cache` | `ETHOS_DATA_DIR` | the per-user cache directory: `~/.cache/ethos-data`, `%LOCALAPPDATA%\ethos-data\Cache`, `~/Library/Caches/ethos-data` |
| Restricted caches, in order ([0011](0011-access-class-picks-the-root.md)) | `restricted_caches`, a list | `ETHOS_RESTRICTED_DIRS`: paths separated by `:`, on Windows by `;` | none |
| Staging root | `staging_cache` | `ETHOS_STAGING_DIR` | none |
| Catalogue | `catalog` | `ETHOS_DATA_CATALOG` | chosen from the release bounds, else the public `main` index |
| Publication URL | `publication_url` | `ETHOS_PUBLICATION_URL` | the URL the catalogue declares |

- `config set-…` writes a single value and `config unset-…` removes it:
  `public-cache`, `staging-cache`, `catalog` and `publication-url`, for
  example `config set-public-cache DIR` and `config unset-public-cache`.
  `config add-restricted-cache DIR` appends a restricted cache and refuses one
  that is already listed; `config remove-restricted-cache DIR` removes one.
  `config` refuses a root that is, contains or lies inside another
  ([0011](0011-access-class-picks-the-root.md)).
- The settings file is the file `ETHOS_DATA_CONFIG` names, which replaces the
  account's file; nothing is merged. Otherwise it is the account's file:
  `~/.config/ethos-data/config.yaml` on Linux (`$XDG_CONFIG_HOME` respected),
  `%LOCALAPPDATA%\ethos-data\config.yaml` on Windows, and
  `~/Library/Application Support/ethos-data/config.yaml` on macOS.
- Only `config set-…` and `config add-restricted-cache` create a settings
  file. A file `ETHOS_DATA_CONFIG` names must exist, and every other command
  stops and names it. Removing the last value leaves the file empty.
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
- `config show` prints the snapshot, with unreachable roots marked and the
  restricted caches numbered; for an account that lists none, it says so, as
  a normal state. Then it prints the precedence and the numbered lookup chain
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
- **A root per dataset.** It is a table someone keeps per dataset, which goes
  out of step with what is on disk ([0011](0011-access-class-picks-the-root.md)).
  A local copy is linked into a cache instead
  ([0016](0016-one-link-command-two-modes.md)).

## Consequences

- The same settings apply from an editor, a terminal, a notebook or a batch
  job, in any folder. Any package's data command writes the one file all of
  them read.
- A results file can record every setting and where it came from.
- A CI job or a test run names its own file in `ETHOS_DATA_CONFIG` and is
  isolated from its account.
- On the cluster each user sets the served checkout, the cluster's public
  cache and the restricted caches their groups admit in their own file, with
  the values the ICE-2 wiki gives. There is no machine-wide setting
  ([0026](0026-internal-catalogue-on-the-cluster.md),
  [0028](0028-one-public-cache-on-the-cluster.md)).
- An account that reads public data only lists no restricted cache, on the
  cluster too, and every workflow that needs no restricted data runs.
- See [Where the settings are stored](../../../how-to/data-users/set-up-your-machine.md#settings-file),
  [Use another settings file](../../../how-to/data-users/set-up-your-machine.md#another-settings-file)
  and [Configuration](../../../reference/configuration.md).

## Related

- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0012. Find every file through one lookup chain](0012-one-lookup-chain.md)
- [0016. Give one link command two modes](0016-one-link-command-two-modes.md)
- [0018. Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [0028. Share one public cache on the cluster](0028-one-public-cache-on-the-cluster.md)
- [5. Building Block View](../building-blocks.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
