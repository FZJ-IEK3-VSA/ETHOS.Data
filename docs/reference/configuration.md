# Configuration

Every setting, where it can be written, and how it is resolved. The
authoritative answer for any given machine is always:

```bash
ethos-data config show
```

which prints the resolved values, the provenance of each, and every file
consulted along the way. A cache path this machine cannot reach, such as a
network drive that is not connected, is marked `NOT REACHABLE` with the reason.

## Precedence

First match wins:

| | Source | |
|---|---|---|
| 1 | an explicit argument | `--root` / `root=` (public cache only) |
| 2 | an environment variable | `$ETHOS_DATA_DIR`, `$ETHOS_RESTRICTED_DIR`, … |
| 3 | project config | `./ethos-data.yaml`, searched upward from the cwd |
| 4 | user config | the per-user config directory, all platforms |
| 5 | environment config | `<sys.prefix>/etc/ethos-data/config.yaml` |
| 6 | site config | the machine-wide config directory |
| 7 | built-in default | the per-user OS cache directory (public cache only) |

Layer 3 is found by walking up from the current directory, the way `git` finds
`.git`. It is for people who want the setting to be **visible**: an ordinary
file sitting next to the work it belongs to, which can be committed so a whole
team shares one answer.

Only the public cache has a layer 7. The restricted and staging roots have no
built-in default on purpose — where licensed bytes land is a decision somebody
has to make out loud, and staging is opt-in.

## Scopes

`--scope` on every `config set-*` / `unset-*` command:

| Scope | File |
|---|---|
| `project` | `./ethos-data.yaml` (created in the current directory; updates the nearest existing one if there is one above) |
| `user` (default) | the per-user config directory, e.g. `~/.config/ethos-data/config.yaml` |
| `environment` | `<sys.prefix>/etc/ethos-data/config.yaml` |
| `site` | the machine-wide config directory, e.g. `/etc/xdg/ethos-data/config.yaml` |

Exact locations are platform-dependent (via
[platformdirs](https://platformdirs.readthedocs.io/)); `config show` prints the
real paths.

## Keys

Written into a config file, or into `ethos-data.yaml` for the project scope.

| Key | Set with | |
|---|---|---|
| `public_cache` | `config set-public-cache` | public and internal data: read from, and downloaded into |
| `cache_dir` | Legacy read fallback | Older spelling of `public_cache`; `config set-cache` now writes `public_cache`. |
| `restricted_cache` | `config set-restricted-cache` | licensed data; retrieval only reads it in place |
| `staging_cache` | `config set-staging-cache` | work in progress that shadows the catalogue |
| `skip_unavailable` | `config set-skip-unavailable` | `true` to carry on without data this machine cannot reach |
| `dataset_roots` | `config set-root <dataset> <dir>` | a mapping of dataset name to directory. Roots from different scopes **combine** rather than clobbering each other |
| `catalog` | `config set-catalog` | the catalogue to use instead of a collections file's pin or the built-in public catalogue |
| `publication_url` | `config set-publication-url` | fetch bytes from a different door than the catalogue declares |

A minimal project file:

```yaml title="ethos-data.yaml"
public_cache: /data/my-analysis/ethos-data
```

A fuller one:

```yaml title="ethos-data.yaml"
public_cache: /shared/ethos/public
restricted_cache: /shared/ethos/restricted
skip_unavailable: false
catalog: /shared/ethos/catalogue/current/datacatalog.json
dataset_roots:
  submarine-cables: /benchtop/shared_data/SubmarineCables
```

## Environment variables

| Variable | Overrides |
|---|---|
| `ETHOS_DATA_DIR` | `public_cache` |
| `ETHOS_RESTRICTED_DIR` | `restricted_cache` |
| `ETHOS_STAGING_DIR` | `staging_cache` |
| `ETHOS_DATA_CATALOG` | `catalog` |
| `ETHOS_SKIP_UNAVAILABLE` | `skip_unavailable` |
| `ETHOS_CATALOG_NO_CACHE` | if set, a fetched catalogue descriptor is never cached on disk |
| `ETHOS_PUBLICATION_URL` | override the dataset download base URL |

`ETHOS_DATA_DIR` is named for the era when there was only one root. It is kept
under that name because it is in scripts, job files and people's shell profiles.

## The three roots

| Root | Holds | Written to |
|---|---|---|
| public | public and internal data — symlinks to data already here, plus real directories for downloads | yes, for downloads into real directories |
| restricted | authorised licensed installations or links | only explicit local administration, such as `link` or `materialize`; never retrieval |
| staging | uncatalogued work in progress | only by `staging add --copy` |

Which root a dataset comes from follows from its access class; whether it is
read in place follows from whether its entry is a symbolic link. See
[Caches, classes and roots](../explanation/caches-and-access.md).

## Catalogue resolution

The catalogue used by `ethos-data` and `ethos_data.catalog()` is the first of:

1. `--catalog` on the command line, or the location passed in Python.
2. `ETHOS_DATA_CATALOG`.
3. The `catalog` setting in configuration.
4. The built-in public catalogue:
   `https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/main/datacatalog.json`.

Package wrappers and collections handles also use the file's `catalog:` pin
before the built-in fallback. A package-specific override, such as
`RESKIT_DATA_CATALOG` passed by RESKit through `catalog=`, ranks below the CLI's
`--catalog` and above `ETHOS_DATA_CATALOG`. To compare a direct fetch with a
package workflow, explicitly select the same catalogue.

Relative pins are resolved relative to the collections file. Pin a revision in
the URL path, for example `.../ETHOS.Data-Catalogue/COMMIT/datacatalog.json`.
A legacy `@ref` suffix is stripped; it does not select a revision.

Metadata fetched from version-pinned URLs is cached indefinitely. URLs naming
`main`, `master`, `HEAD`, `latest`, `dev` or `develop` are treated as moving and
re-fetched. `ETHOS_CATALOG_NO_CACHE=1` bypasses metadata caching.

## Collections resolution

A package command reads the collections file shipped beside its code.
`ethos-data` reads catalogue keys directly and does not discover a collections
file in the working directory or from configuration.

In Python, use `ethos_data.collections(path, tool=...)`, or pass the file to
the one-call `fetch`, `paths` and `resolve` APIs. The handle's `.catalog`
provides access by key against its selected catalogue. See
[Package integration](../how-to/use-from-a-package.md).

## Configuration commands

Prefix these with `ethos-data` or a package wrapper such as `reskit-data`.

| Command | Value |
| --- | --- |
| `config show` | Display shared configuration without network access. |
| `config set-public-cache DIR`, `set-cache DIR` | Public cache; the second spelling is an alias. |
| `config set-restricted-cache DIR` | Authorised restricted installation. |
| `config set-staging-cache DIR` | Shared development overlay. |
| `config set-catalog LOCATION` | Catalogue index path or URL. |
| `config set-root DATASET DIR` | One dataset's existing directory. |
| `config set-skip-unavailable true\|false` | Whether collection results may omit inaccessible inputs. |
| `config set-publication-url URL` | Override the dataset download base URL. |

Each setter accepts `--scope`, as described above. Remove a setting with the
matching `unset-*` command in the same scope; `unset-root` takes the dataset
name. There is no `unset-publication-url` command: remove that key from the
configuration file shown by `config show` and clear `ETHOS_PUBLICATION_URL`
if set. Unsetting configuration does not move or delete data.

`config show` reports shared settings, not a package's pin, package-specific
environment override, or per-command options. `ethos-data ls` and a wrapper's
`list` report the catalogue they actually selected.
