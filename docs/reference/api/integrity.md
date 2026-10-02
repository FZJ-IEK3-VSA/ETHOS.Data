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
        - LinkReport
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

`link` takes the directory it links to. `ethos-data link NAME` without one
reads the dataset's build input from a source checkout with
[`maintain.source_dir_for`][ethos_data.maintain.source_dir_for], as
`materialize` does for an absent entry: reading a checkout is catalogue
maintenance, and no data-access module imports it.

## Data directories

The files of a data directory, as the catalogue records them: the walk, the
`ethos:include` and `ethos:exclude` patterns, shapefile companions and the
record each file gets. The build inventories a `source_dir` with it.

::: ethos_data.files
    options:
      members:
        - iter_data_files
        - expand_pattern
        - select
        - build_resource
        - slugify
        - mediatype_of
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

## Handoffs

The proposal, the problem report, the answer and the notices, drafted from
the templates in `ethos_data/formats/templates/handoffs/`.

::: ethos_data.handoffs
    options:
      members:
        - propose
        - Proposal
        - handoff
        - issue_template
        - scrub
        - names
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Repository test-data bundles

::: ethos_data.bundles
    options:
      members:
        - load_bundle
        - Bundle
        - BundleFinding
        - BundleAlignmentWarning
        - ModifiedBundleWarning
        - create_bundle
        - BundleCreated
        - update_bundle
        - BundleUpdate
        - differs_from_catalog
        - export_bundle
        - with_bundles
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
