# Maintainer tooling

`ethos_data.maintain` is the writing half of the format: the code that produces
the descriptors `ethos_data.catalogs` reads. Consumers usually need no maintainer
imports; ordinary APIs also manage downloads, caches, and local development data.

Both halves ship in one distribution on purpose. The `ethos:` extensions are a
format, and a format whose writer and reader live in separate repositories
drifts silently.

Two commands lead here. [`ethos-data catalog`](../cli/catalog.md) drives the
manifest builder, the publisher and the uploader below — the work that writes
and ships metadata about the data. The cache namespace builder is the exception:
it is reached from
[`ethos-data link --all`](../cli/ethos-data.md#link-dataset-directory), because
building a namespace is site administration on the machine that holds the data
rather than catalogue maintenance. It writes symbolic links into one machine's
cache and never a descriptor, and filling a whole cache from a checkout is the
same job as pointing one dataset at a directory, only at a larger scale. That is
exactly why its command sits with the user-facing `link` rather than under
`catalog`.

The catalogue-locating helpers below serve both entry points: `link --all` reads
`source_dir` from the hand-written `dataset.yaml` of a source checkout, and it
finds that checkout the same way the maintainer commands find theirs.

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

Built by [`ethos-data link --all`](../cli/ethos-data.md#link-dataset-directory).
`run` takes the catalogue checkout and the namespace root as plain arguments,
neither of them optional, because the command decides which cache it means once
and hands the answer down: a planner that looked the cache up for itself could
answer differently from the caller that had already looked, and the result would
be a whole link tree built somewhere nobody named.

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
