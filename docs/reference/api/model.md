# Shared model

The model layer: `ethos_data.formats`, the specification of every file
format, and `ethos_data.model`, the rules every reader of a catalogue shares,
each written once: the digest of a file and how a catalogue spells one,
dataset names and the families they form, catalogue releases, a dataset's
lifecycle, the record a descriptor keeps for each file, the one inventory
reader, and one glob semantics. The catalogue, a bundle, a staging root and
the build all go through it, so a hash, a sidecar, a shard or a family member
means the same to each of them. It reads no settings, makes no network
request and prints nothing; its one input is hashing a file it is handed, and
the inventory reader reads through the metadata source it is handed.

## Formats

One specification per file, as a pydantic model; the JSON Schemas, the
templates and the tables of [File formats](../schemas.md) are made from them.

::: ethos_data.formats.registry
    options:
      members:
        - FORMATS
        - Format
        - schema
        - template
        - placeholders
        - write_schemas
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

The reference tables, rendered when the documentation is built:

::: ethos_data.formats.reference
    options:
      members:
        - table
        - formats
        - states
        - steps
        - render
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

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
        - entry
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Catalogue releases

::: ethos_data.model.versions
    options:
      members:
        - Version
        - Prefix
        - Bounds
        - releases
        - admissible
        - LEVELS
        - FIRST
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Path patterns

One glob semantics for a collection's `files:` and a dataset's
`ethos:include` and `ethos:exclude`: `*` within one path segment, `**` across
any number of them.

::: ethos_data.model.patterns
    options:
      members:
        - path_matches
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## The inventory reader

One dataset's descriptor and inventory, inline or in shards, read on demand:
the descriptor on first access, each shard at most once, one shard for a path
and only the shards patterns can reach. The catalogue, the maintainer
commands (through `maintain.inventory_of`), bundles and staging all read
inventories through it, and the build splits an inventory by its shard rules.
A missing descriptor or shard raises
[`IncompleteCatalog`][ethos_data.errors.IncompleteCatalog], naming the
dataset, the part and its location.

::: ethos_data.model.inventory
    options:
      members:
        - Inventory
        - PartReader
        - shard_key
        - shard_path
        - split_into_shards
        - shard_could_match
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Lifecycle

A dataset's states in its source catalogue, and the step that leads from
each to the next; the commands that take a step ask `step` first. The guards
are part of the step: restricted data is never uploaded, and data with unread
terms is not uploaded, linked or copied into a cache other people read.

::: ethos_data.model.lifecycle
    options:
      members:
        - step
        - refusal
        - guard
        - next_step
        - freezable
        - Step
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Resource records

A [`Resource`][ethos_data.model.resource.Resource] is one file of a dataset,
the same whether the catalogue, a shard or a bundle records it.

::: ethos_data.model.resource
    options:
      members:
        - Resource
        - from_record
        - to_record
        - extras_of
        - checked
        - with_sidecars
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
