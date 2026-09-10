# Maintainer tooling

`ethos_data.maintain` is the writing half of the format: the code that produces
the descriptors `ethos_data.catalog` reads. Consumers never import it — the
`ethos_data` package itself stays a read-only library.

Both halves ship in one distribution on purpose. The `ethos:` extensions are a
format, and a format whose writer and reader live in separate repositories
drifts silently.

The command-line entry point is
[`ethos-data catalog`](../cli/catalog.md); this page documents the functions
behind it.

## Locating a catalogue

::: ethos_data.maintain
    options:
      members:
        - find_catalog_root
        - resolve_catalog_root
        - catalogue_role
        - datasets_dir
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Building manifests

::: ethos_data.maintain.manifest
    options:
      members:
        - run
        - render_dataset
        - write_dataset
        - stale_files
        - build_catalog
        - catalog_meta
        - select
        - expand_pattern
        - iter_data_files
        - build_resource
        - split_into_shards
        - shard_path
        - validate_classification
        - validate_provenance
        - validate_licenses
        - apply_resource_licenses
        - slugify
        - mediatype_of
        - sha256_of
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Publishing

::: ethos_data.maintain.publish
    options:
      members:
        - run
        - render
        - public_datasets
        - strip
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## The cache namespace

::: ethos_data.maintain.namespace
    options:
      members:
        - run
        - plan
        - apply
        - Action
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Uploading

::: ethos_data.maintain.upload
    options:
      members:
        - run
        - preflight
        - resources_of
        - remote_manifest_check
        - locality
        - chmod
        - token
        - load
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
