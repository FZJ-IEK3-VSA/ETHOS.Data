# Set up your machine

Configure catalogue metadata and data storage for your account. You need an
[installed ETHOS.Data](../installation.md) and, on the cluster, the locations
supplied by your administrator. All `/shared/ethos/...` paths below are examples.

## 1. Inspect existing settings

```bash
ethos-data config show
```

Keep working site defaults. Use absolute paths when changing persistent settings.

## 2. Select the catalogue

For public data, use the catalogue pinned by your package or the built-in
[public catalogue](https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue).
No catalogue setting is needed. The CLI reads `datacatalog.json`, not the
GitHub repository's web page.

On the cluster, select the administrator's complete internal catalogue:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/current/datacatalog.json
```

The internal catalogue includes public entries too. Use
`versions/<revision>/datacatalog.json` for a reproducible run. This setting
overrides package pins; see [Add the internal catalogue](add-internal-catalogue.md)
to limit it to a project or remove it.

If the public repository has no released `datacatalog.json` yet, obtain a
complete built catalogue from its maintainer. The
[first-fetch lesson](../tutorials/first-fetch.md) works independently of a release.

## 3. Select the caches

For public downloads on a workstation, the per-user default works. To use
another disk or the cluster cache:

```bash
ethos-data config set-public-cache /shared/ethos/public
```

For licensed data you are authorised to read:

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted
```

Use separate roots. The restricted directory contains
`<dataset>/<resource path>`; selecting it grants no permissions and downloads
nothing. Leave it unset if you have no licensed data. Request access from the
dataset custodian when a required workflow needs it.

These commands set account defaults. Append `--scope project` for one project;
an administrator can use `--scope site` for a machine default.
See [Configure the cache](configure-the-cache.md) for temporary overrides.

## 4. Check the workflow

Replace `reskit` and `onshore_wind` with your installed package and collection:

```bash
ethos-data config show
ethos-data -p reskit list
ethos-data -p reskit plan onshore_wind
```

Check the catalogue printed by `list`, download size, and any missing inputs.
`plan` can retrieve metadata but does not download data files.

Continue with [Get data for a task](get-data-for-a-task.md). If the checks fail,
[identify and report the issue](report-a-problem.md).

