# Configuration

Every setting, where it can be written, and how it is resolved. The
authoritative answer for any given machine is always:

```bash
ethos-data config show
```

which prints the resolved values, the provenance of each, and every file
consulted along the way.

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
| `cache_dir` | `config set-cache` | what `public_cache` used to be called. Still read and still writable, so existing files keep working |
| `restricted_cache` | `config set-restricted-cache` | licensed data; retrieval only reads it in place |
| `staging_cache` | `config set-staging-cache` | work in progress that shadows the catalogue |
| `skip_unavailable` | `config set-skip-unavailable` | `true` to carry on without data this machine cannot reach |
| `dataset_roots` | `config set-root <dataset> <dir>` | a mapping of dataset name to directory. Roots from different scopes **combine** rather than clobbering each other |
| `catalog` | `config set-catalog` | the catalogue to use instead of a collections file's pin or the built-in public catalogue |
| `collections` | `config set-collections` | a default collections file, so `-c` is not needed every time |
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

Strongest first:

1. `--catalog` on the command line, or `catalog=` in Python
2. `$ETHOS_DATA_CATALOG`
3. the `catalog:` key in a config file (`config set-catalog`)
4. the `catalog:` key at the top of the collections file — for `-p` /
   `package=`, the file the package ships
5. the built-in public catalogue,
   `https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/main/datacatalog.json`

A local relative path in a collections file is resolved **relative to that
file**, not to the caller's working directory. Pin a GitHub revision in the URL
path, for example `.../ETHOS.Data-Catalogue/COMMIT/datacatalog.json`.
The legacy `@ref` suffix is stripped while loading a collections file; it does
not select a remote revision.

A catalogue fetched from a version-pinned URL is cached on disk indefinitely.
One whose URL names `main`, `master`, `HEAD`, `latest`, `dev` or `develop` is
recognised as moving and re-fetched every time.

## Collections resolution

Strongest first:

1. `-c` / `--collections` on the command line, or `-p` / `--package` for the
   file an installed package registers
2. the `collections:` key in a config file (`config set-collections`)
3. `collections.yaml` in the current directory

In Python, `fetch()`, `paths()` and `resolve()` take either `collections=` (a
path) or `package=` (a registered package name). `path()` and
`list_resources()` need neither, but accept either to read the catalogue that
file pins.

A package registers its collections file with an entry point in the
`ethos_data.collections` group; the entry point's value names the module whose
directory holds `collections.yaml`:

```toml title="pyproject.toml"
[project.entry-points."ethos_data.collections"]
reskit = "reskit.data"
```

!!! warning
    A project-scope `collections` setting applies everywhere the project config
    is found — the same walk-up rule as `cache_dir` — not just in the directory
    where you set it.
