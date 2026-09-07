# Integrity and staging

Checking that the data on disk is still the data the catalogue describes, and
the development escape hatch for data that is not in the catalogue yet.

See [Check and repair the cache](../../how-to/verify-and-repair.md) and
[Stage uncatalogued data](../../how-to/stage-unpublished-data.md).

## Verification

::: ice2_data.verify
    options:
      members:
        - verify
        - repair
        - Finding
        - summarise
        - sha256_of
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Materialization

::: ice2_data.materialize
    options:
      members:
        - materialize
        - plan_materialize
        - MaterializeReport
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Staging

::: ice2_data.staging
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
