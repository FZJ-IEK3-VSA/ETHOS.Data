# Shared model

`ethos_data.model` holds the rules every reader of a catalogue shares, each
written once: the digest of a file and how a catalogue spells one, dataset
names and the families they form, and the record a descriptor keeps for each
file. The catalogue, a bundle, a staging root and the build all go through it,
so a hash, a sidecar or a family member means the same to each of them. It
reads no settings, makes no network request and prints nothing; its one input
is hashing a file it is handed.

[`Resource`][ethos_data.catalogs.Resource], the file these records describe,
is documented with the [catalogue](catalog.md).

## Digests

A resource's `hash` is recorded as `sha256:<hex>`. A bare digest, as the
Data Package standard allows and as `ethos:document_sha256` is usually written,
names the same file, in either case.

::: ethos_data.model.digest
    options:
      members:
        - of_file
        - of_bytes
        - recorded
        - expected
        - matches
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Names and families

A dataset's name is its path under `datasets/`, so `reskit-test-data/era5` is a
member of the `reskit-test-data` family, and the same rule decides which paths a
dataset or bundle may hold.

::: ethos_data.model.names
    options:
      members:
        - relative
        - ancestors
        - within
        - nested
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Catalogue releases

::: ethos_data.model.versions
    options:
      members:
        - Version
        - Bounds
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Resource records

::: ethos_data.model.resource
    options:
      members:
        - from_record
        - to_record
        - extras_of
        - checked
        - with_sidecars
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
