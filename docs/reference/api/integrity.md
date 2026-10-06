# Integrity and staging

Checking that the data on disk is still the data the catalogue describes, and
the development escape hatch for data that is not in the catalogue yet.

See [Check and repair the cache](../../how-to/data-users/verify-and-repair.md) and
[Stage uncatalogued data](../../how-to/package-maintainers/stage-development-data.md#stage-development-data).

## Verification

`repair` downloads a damaged copy again into the public cache and never
removes or replaces a link; see [one public cache on the
cluster](../../explanation/architecture/decisions/0028-one-public-cache-on-the-cluster.md).

::: ethos_data.verify
    options:
      members:
        - verify
        - repair
        - Finding
        - summarise
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Self-test

::: ethos_data.selftest
    options:
      members:
        - run_selftest
        - EXAMPLE_COLLECTIONS
        - SelfTest
        - FileOutcome
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Cache entries

::: ethos_data.linking
    options:
      members:
        - link
        - unlink
        - source_dir_for
        - LinkReport
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Materialization

::: ethos_data.materialize
    options:
      members:
        - materialize
        - plan_materialize
        - MaterializeReport
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Staging

::: ethos_data.staging
    options:
      members:
        - add
        - remove
        - list_staged
        - classify_staged
        - staged_only
        - staged_names
        - staging_root
        - apply_staging
        - synthesize
        - StagedDataset
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Repository test-data bundles

!!! warning "Gap: a bundle is to be authoritative for its package"
    With [decision
    0020](../../explanation/architecture/decisions/0020-repository-bundles.md)
    and [bundles ahead of the
    catalogue](../../explanation/architecture/decisions/0021-bundles-ahead-of-the-catalogue.md),
    the package's handle reads its bundles before the caches, even where a
    bundle is ahead of the catalogue; such a read warns once per bundle, in
    a warning category of its own exported from `ethos_data`. One
    `bundle.json` format holds public, visible data with settled licensing
    only, and `export_bundle` reads through the package's handle. To be
    implemented separately.

::: ethos_data.bundles
    options:
      members:
        - export_bundle
        - load_bundle
        - Bundle
        - BundleFinding
        - ModifiedBundleWarning
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
