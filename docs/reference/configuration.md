# Configuration

Every setting, where it is written, and how it is resolved. The authoritative
answer for any given machine is always:

```bash
ethos-data config show
```

which prints the settings file it read, the resolved values and the provenance
of each. A cache path this machine cannot reach, such as a network drive that is
not connected, is marked `NOT REACHABLE` with the reason.

## Precedence

Each setting is the first of:

| | Source | |
|---|---|---|
| 1 | an explicit argument | `--root` / `root=` (public cache), `--catalog` / `catalog=` |
| 2 | an environment variable | `$ETHOS_DATA_DIR`, `$ETHOS_RESTRICTED_DIRS`, … |
| 3 | the settings file | the file `$ETHOS_DATA_CONFIG` names, else the file in the account |
| 4 | the built-in default | the per-user cache directory (public cache only) |

The restricted caches are a list with no explicit argument:
`$ETHOS_RESTRICTED_DIRS` holds directories separated by `:`, on Windows by `;`,
and replaces the file's list; nothing is merged.

Only the public cache has a built-in default. The restricted caches and the
staging root have none on purpose: where restricted bytes are read is a
decision somebody has to make out loud, and staging is opt-in. An account that
lists no restricted cache reads public data only, which is a valid set-up
everywhere, the cluster included.

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

The file is checked against its specification, `ethos_data.formats.SettingsFile`,
when it is read, and every problem is reported at once, naming the key.

## Keys

| Key | Set with | |
|---|---|---|
| `public_cache` | `config set-public-cache` | public data: read from, and downloaded into |
| `restricted_caches` | `config add-restricted-cache`, `remove-restricted-cache` | a list of directories, read in order for restricted data, in place; none by default |
| `staging_cache` | `config set-staging-cache` | work in progress that shadows the catalogue |
| `catalog` | `config set-catalog` | the catalogue to use instead of the public one; a package checks it against its release bounds |
| `publication_url` | `config set-publication-url` | fetch bytes from a different door than the catalogue declares |

A settings file on the cluster, for a user whose groups admit one restricted
cache:

```yaml title="config.yaml"
public_cache: /shared/ethos/cache
restricted_caches:
  - /shared/ethos/restricted/<group>
catalog: /shared/ethos/catalogue/datacatalog.json
```

## Environment variables

| Variable | Overrides |
|---|---|
| `ETHOS_DATA_CONFIG` | the settings file: read this one instead of the one in the account |
| `ETHOS_DATA_DIR` | `public_cache` |
| `ETHOS_RESTRICTED_DIRS` | `restricted_caches`: directories separated by `:`, on Windows by `;` |
| `ETHOS_STAGING_DIR` | `staging_cache` |
| `ETHOS_DATA_CATALOG` | `catalog` |
| `ETHOS_CATALOG_NO_CACHE` | if set, a fetched catalogue descriptor is never cached on disk |
| `ETHOS_PUBLICATION_URL` | `publication_url` |
| `ETHOS_DATA_DOWNLOAD` | the download switch: `1` reads a bundled file whose bytes the catalogue holds under the same key through the catalogue route, as `download=True` does; `config show` reports it |

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
catalogue          https://.../v1.2.0/datacatalog.json  (the public release v1.2.0, the newest within min_version v1.2)
catalogue version  v1.2.0
public cache       /home/me/.cache/ethos-data  (built-in default, the per-user cache directory)
restricted caches  none listed: public data only
staging cache      not set
```

`data.catalog.settings` and `ethos_data.catalog().settings` are the same for a
catalogue handle, and `settings.as_dict()` gives the values as plain data for a
results file. `ethos_data.read_settings()` takes the snapshot without a handle.

## Where a file is read {#lookup-order}

Each file is read from the first of these places that has it. The chain of
places is built from the settings snapshot of the handle or the command, and
`config show` prints it for this machine:

1. the staging root, never for restricted data, read in place without checksums;
2. the bundles a package's handle lists, for what they hold: in place,
   hash-checked once per process;
3. the restricted caches, for restricted data only: in place, from the first
   listed cache whose entry is readable;
4. the public cache: in place where the dataset's entry, or its family's, is a
   link; otherwise a copy of the size the catalogue records, hash-checked when
   it is fetched;
5. a download from the publication root into the public cache, for public data
   only.

A place that may not serve a file refuses, and the search stops there. A
restricted dataset that no listed cache holds readable is refused before
anything is downloaded, and the refusal names what is wrong besides a missing
copy: that the account lists no restricted cache, an entry that is dangling or
cannot be read, or a cache that cannot be reached. It is never read from a copy
in the public cache, and never downloaded.
With `fetch=False` nothing is downloaded: a file that only the last place could
provide raises `NotFetched`, naming the path it belongs at.

## The roots

| Root | Holds | Written to |
|---|---|---|
| public cache | public data — symbolic links to data already here, plus real directories for downloads and materialized copies | by downloads, into real directories; by `link` and `materialize` |
| restricted caches | restricted data, one cache per access combination — authorised installations, linked or copied | only by `link` and `materialize`; never by retrieval |
| staging root | uncatalogued work in progress | only by `staging add --copy` |

Which root a dataset comes from follows from its access class, `public` or
`restricted`; whether it is read in place follows from whether its entry is a
symbolic link. On the cluster every user sets the same public cache, the
cluster's public cache. See
[Caches, classes and roots](../explanation/caches-and-access.md) and [one public
cache on the cluster](../explanation/architecture/decisions/0028-one-public-cache-on-the-cluster.md).

No root contains another: `config` refuses a public cache, staging root or
restricted cache that is, contains or lies inside another root.

## Catalogue resolution

Every handle and command chooses the catalogue the same way, the first of:

1. `--catalog` on the command line, or the location passed in Python.
2. `ETHOS_DATA_CATALOG`.
3. The `catalog` setting.
4. The public catalogue. For a collections file with release bounds, the
   release they select: a full `exact_version` reads that release's tag, any
   other bounds the newest release they admit among those the public
   catalogue lists. Without bounds, the built-in public catalogue:
   `https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/main/datacatalog.json`.

`ethos-data` reads no collections file, so step 4 is the built-in public
catalogue for it. A collections file refuses whichever catalogue steps 1 to 3
chose when it is outside the file's bounds, or records no release, with
`CatalogVersionError`. A package-specific override, such as
`<YOUR_TOOL>_DATA_CATALOG` passed by the package through `catalog=`, ranks below the CLI's
`--catalog` and above `ETHOS_DATA_CATALOG`. To compare a direct fetch with a
package workflow, explicitly select the same catalogue.

Every release of the current major stays readable: data is purged only after
a major release, so a package bounded to an older release keeps resolving the
same bytes.

Metadata fetched from URLs naming a release tag or a commit is cached
indefinitely. URLs naming
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
| `config set-public-cache DIR` | Public cache. |
| `config add-restricted-cache DIR` | Append a restricted cache to the list; refuses one already listed. |
| `config remove-restricted-cache DIR` | Remove a restricted cache from the list. |
| `config set-staging-cache DIR` | Development overlay. |
| `config set-catalog LOCATION` | Catalogue index path or URL. |
| `config set-publication-url URL` | Override the dataset download base URL. |

Every setter writes to the settings file in effect. Remove a setting with the
matching `unset-*` command, and a restricted cache with
`remove-restricted-cache`. Removing a setting does not move or delete data.

`config show` reports the settings, not a package's release bounds, a
package-specific environment override, or per-command options. `ethos-data ls` and a wrapper's
`show` report the catalogue they actually selected, and a handle's `settings`
reports both.
