# Run it in CI

Published data is served over plain HTTPS, so CI needs **no credentials**. What
it does need is somewhere to put the data that survives between runs, and a
catalogue pinned to something that does not move.

## GitHub Actions

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/ice2-data
    key: ice2-data-${{ hashFiles('**/collections.yaml') }}

- run: ice2-data -c reskit/data/collections.yaml fetch test_suite
  env:
    ICE2_DATA_DIR: ~/.cache/ice2-data
```

Keying the cache on the collections file is the right granularity: the key
changes exactly when the set of files being asked for changes. Keying on a lock
file or a commit SHA re-downloads everything for changes that have nothing to
do with the data.

## GitLab CI

```yaml
variables:
  ICE2_DATA_DIR: "$CI_PROJECT_DIR/.cache/ice2-data"

cache:
  key:
    files:
      - reskit/data/collections.yaml
  paths:
    - .cache/ice2-data

test:
  script:
    - ice2-data -c reskit/data/collections.yaml fetch test_suite
    - pytest
```

GitLab's cache only covers paths inside the project directory, which is why
`ICE2_DATA_DIR` points there rather than at `~/.cache`.

## Use `$ICE2_DATA_DIR`, not a config file

The environment variable is layer 2 of the
[precedence chain](configure-the-cache.md#six-ways-strongest-first) — above
every config file, below only an explicit `--root`. That makes it exactly right
for CI: it overrides whatever a committed `ice2-data.yaml` says without editing
it, and it is scoped to the one job.

## Know the cost before you pay it

```bash
ice2-data -c collections.yaml plan test_suite
```

`plan` touches no network and reports what would be downloaded. Running it
before the fetch turns "why is CI slow today" into a number in the log:

```title="Output"
public cache:    /builds/project/.cache/ice2-data
already cached:    24 files      2.1 MB
to download:        3 files    140.6 MB
    + reskit-test-data/era5-like/100m_u_component_of_wind.nc
    ...
```

## Pin the catalogue

A collections file pins its own catalogue with a versioned URL:

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ice2-data-catalog/v2026.09/datacatalog.json
```

Use a **tag**, never a branch. A catalogue fetched from a pinned URL is cached
on disk and reused forever, because the bytes behind it cannot change; one
fetched from `main`, `master`, `HEAD`, `latest`, `dev` or `develop` is
recognised as moving and re-fetched every time. A branch URL makes a green
build go red for reasons that are nowhere in your diff.

To force a re-fetch of a catalogue you believe is stale:

```bash
ICE2_CATALOG_NO_CACHE=1 ice2-data -c collections.yaml list
```

## Verify what the cache restored

A restored CI cache is bytes from another machine, another run, possibly
another week. If the job's results matter, check them:

```bash
ice2-data -c collections.yaml verify test_suite      # sizes — cheap enough for every run
```

Add `--deep` for a nightly job; it reads every byte, which is too slow for a
per-commit build.

## If some datasets are not reachable

A CI runner outside the institute cannot reach licensed data at all. Rather
than have the job fail, tell it to carry on and report:

```bash
ice2-data -c collections.yaml fetch test_suite --skip-unavailable
```

Anything unreachable is left out of the result and listed. See
[Work with restricted data](restricted-data.md).

## Catalogue CI

If you maintain a catalogue rather than consume one, the check that belongs in
its CI is the staleness check:

```bash
ice2-data catalog build --check                        # fail if any manifest is out of date
ice2-data catalog publish ../ice2-data-catalog --check  # fail if the public repo is out of date
```

Both are non-destructive. See
[Publish the catalogue](publish-the-catalogue.md).
