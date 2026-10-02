# Configuration

Every setting, where it is written, and how it is resolved. The authoritative
answer for any given machine is always:

```bash
ethos-data config show
```

which prints the settings file it read, the resolved values and the provenance
of each, and any settings file of an earlier release that it now ignores. A
cache path this machine cannot reach, such as a network drive that is not
connected, is marked `NOT REACHABLE` with the reason.

## Precedence

Each setting is the first of:

| | Source | |
|---|---|---|
| 1 | an explicit argument | `--root` / `root=` (public cache), `--catalog` / `catalog=` |
| 2 | an environment variable | `$ETHOS_DATA_DIR`, `$ETHOS_RESTRICTED_DIR`, … |
| 3 | the settings file | the file `$ETHOS_DATA_CONFIG` names, else the file in the account |
| 4 | the built-in default | the per-user cache directory (public cache only) |

Only the public cache has a built-in default. The restricted and staging roots
have none on purpose: where licensed bytes land is a decision somebody has to
make out loud, and staging is opt-in.

## The settings file {#settings-file}

One file holds every setting. It is the file in the account:

| System | Settings file |
|---|---|
| Linux | `~/.config/ethos-data/config.yaml`, or `$XDG_CONFIG_HOME/ethos-data/config.yaml` |
| Windows | `%LOCALAPPDATA%\ethos-data\config.yaml` |
| macOS | `~/Library/Application Support/ethos-data/config.yaml` |

unless `ETHOS_DATA_CONFIG` names another file. That file then **replaces** the
one in the account: nothing is merged, so a CI job or a test run reads none of
the settings of the account it runs under. A file `ETHOS_DATA_CONFIG` names must
exist; a setter creates it, and every other command stops and names the missing
file.

The `config` setters and unsetters write to the settings file in effect and
create it if need be. Unsetting the last value leaves the file in place, empty.

Earlier releases also read an `ethos-data.yaml` found by searching upward from
the working directory, `<sys.prefix>/etc/ethos-data/config.yaml` and a
machine-wide file. They are ignored now, and `config show` names each one it
finds.

On Windows the file and the default cache moved out of
`%LOCALAPPDATA%\ethos-data\ethos-data\`. For one release, the file at the old
location is still read while there is none at the new one, with a warning that
names the new location, and the first setter writes it there. The old default
cache is used while the new one does not exist, and `config show` says where to
move it.

## Keys

| Key | Set with | |
|---|---|---|
| `public_cache` | `config set-public-cache` | public and internal data: read from, and downloaded into |
| `cache_dir` | Legacy read fallback | Older spelling of `public_cache`; `config set-cache` now writes `public_cache`. |
| `restricted_cache` | `config set-restricted-cache` | licensed data; retrieval only reads it in place |
| `staging_cache` | `config set-staging-cache` | work in progress that shadows the catalogue |
| `dataset_roots` | `config set-root <dataset> <dir>` | a mapping of dataset name to directory |
| `catalog` | `config set-catalog` | the catalogue to use instead of a collections file's pin or the built-in public catalogue |
| `publication_url` | `config set-publication-url` | fetch bytes from a different door than the catalogue declares |

A settings file for a shared machine:

```yaml title="config.yaml"
public_cache: /shared/ethos/public
restricted_cache: /shared/ethos/restricted
catalog: /shared/ethos/catalogue/current/datacatalog.json
dataset_roots:
  submarine-cables: /benchtop/shared_data/SubmarineCables
```

## Environment variables

| Variable | Overrides |
|---|---|
| `ETHOS_DATA_CONFIG` | the settings file: read this one instead of the one in the account |
| `ETHOS_DATA_DIR` | `public_cache` |
| `ETHOS_RESTRICTED_DIR` | `restricted_cache` |
| `ETHOS_STAGING_DIR` | `staging_cache` |
| `ETHOS_DATA_CATALOG` | `catalog` |
| `ETHOS_CATALOG_NO_CACHE` | if set, a fetched catalogue descriptor is never cached on disk |
| `ETHOS_PUBLICATION_URL` | `publication_url` |

Every input a workflow names is required, so nothing leaves one out: a
`skip_unavailable` key and `ETHOS_SKIP_UNAVAILABLE` from an earlier release
are ignored, and `config show` names them.

`ETHOS_DATA_DIR` is named for the era when there was only one root. It is kept
under that name because it is in scripts, job files and people's shell profiles.

## Settings of a handle {#handle-settings}

A handle reads every setting once, when it is built, and uses that snapshot for
every later call. A script that changes directory or environment variables
half-way keeps the catalogue and caches it began with.

```python
data = ethos_data.collections("collections.yaml")
print(data.settings)
```

```text
settings file      /home/me/.config/ethos-data/config.yaml  (your account)
catalogue          https://.../datacatalog.json  (the pin in collections.yaml)
catalogue version  v2026.09.2
public cache       /home/me/.cache/ethos-data  (built-in default, the per-user cache directory)
restricted cache   not set
staging cache      not set
```

`data.catalog.settings` and `ethos_data.catalog().settings` are the same for a
catalogue handle, and `settings.as_dict()` gives the values as plain data for a
results file. `ethos_data.read_settings()` takes the snapshot without a handle.

## Where a file is read {#lookup-order}

Each file is read from the first of these places that has it, and
`config show` prints the list for this machine:

1. a per-dataset root (`config set-root`), read in place;
2. the staging root, never for restricted data, read in place without checksums;
3. the restricted cache, for restricted data only, read in place;
4. a link in the public cache, the dataset's own or its family's, read in place;
5. a copy already in the public cache, of the size the catalogue records;
6. a download from the publication root into the public cache, for public data only.

A place that may not serve a file refuses, and the search stops there. A
restricted dataset without a restricted cache is never read from a copy in the
public cache, and internal data, which is not published, is never downloaded.
With `fetch=False` nothing is downloaded: a file that only the last place could
provide raises `NotFetched`, naming the path it belongs at.

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

Every handle and command chooses the catalogue the same way, the first of:

1. `--catalog` on the command line, or the location passed in Python.
2. `ETHOS_DATA_CATALOG`.
3. The `catalog` setting.
4. For a collections file, its `catalog:` pin, or, when it bounds the
   release instead, the newest public release within the bounds.
5. The built-in public catalogue:
   `https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/main/datacatalog.json`.

`ethos-data` reads no collections file, so it skips step 4. A collections
file that bounds the release refuses whichever catalogue steps 1 to 4 chose
when it is outside the bounds, or records no release. A package-specific override, such as
`<YOUR_TOOL>_DATA_CATALOG` passed by the package through `catalog=`, ranks below the CLI's
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
[Package integration](../how-to/package-maintainers/use-from-a-package.md).

## Configuration commands

Prefix these with `ethos-data` or a package wrapper such as `<your-tool>-data`.

| Command | Value |
| --- | --- |
| `config show` | Display the settings in effect without network access. |
| `config set-public-cache DIR`, `set-cache DIR` | Public cache; the second spelling is an alias. |
| `config set-restricted-cache DIR` | Authorised restricted installation. |
| `config set-staging-cache DIR` | Shared development overlay. |
| `config set-catalog LOCATION` | Catalogue index path or URL. |
| `config set-root DATASET DIR` | One dataset's existing directory. |
| `config set-publication-url URL` | Override the dataset download base URL. |

Every setter writes to the settings file in effect. Remove a setting with the
matching `unset-*` command; `unset-root` takes the dataset name. Unsetting
configuration does not move or delete data.

`config show` reports the settings, not a package's pin, a package-specific
environment override, or per-command options. `ethos-data ls` and a wrapper's
`show` report the catalogue they actually selected, and a handle's `settings`
reports both.
