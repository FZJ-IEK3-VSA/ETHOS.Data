# Catalogue and collections

Loading the catalogue, and resolving a collections file against it. Both are
described in [The catalogue format](../../explanation/catalogue-format.md).

Loading is **lazy**: `load_catalog` reads only the index, and a dataset's
inventory is fetched the first time something asks for its files. A sharded
dataset goes further — `resources_matching` pulls only the shards a set of
patterns could reach.

## Catalogue

Three errors say what went wrong:
[`CatalogUnavailable`][ethos_data.catalogs.CatalogUnavailable] when the index
itself cannot be read — a wrong location, or a pinned revision or repository
that does not exist; its message names the location and says how to point at
another catalogue — [`UnknownDataset`][ethos_data.catalogs.UnknownDataset] for
a dataset the catalogue does not describe, and
[`IncompleteCatalog`][ethos_data.catalogs.IncompleteCatalog] for a dataset the
index lists whose descriptor or shard is missing.

`Catalog.path` and `Catalog.resources` answer for a key — one file, a folder,
a dataset or a family — fetching in the first case and only reading in the
second. `ethos_data.catalog()` builds the handle for the configured catalogue;
`Collections.catalog` is the one a tool's file pins.

::: ethos_data.catalogs
    options:
      members:
        - load_catalog
        - Catalog
        - Dataset
        - Resource
        - CatalogUnavailable
        - UnknownDataset
        - IncompleteCatalog
        - shard_key
        - describe_catalog
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Collections

A collection may carry `paths` — handles for the inputs a workflow takes — and
a `test` and a `full` variant. `Collections.variants`, `definition`,
`named_keys` and `check_variants` expose them; `resolve(name, test=...)`
selects the variant and runs `check_variants` on every collection it visits
through `extends`, not only the one asked for. `catalog_pin` answers which
catalogue a collections file pins for itself, resolved against the file — the
answer `load_collections` uses. A package's `show` and `fetch` commands use
that same selected catalogue; `ethos-data fetch` instead takes a
catalogue key against explicit/shared settings or the public default.
`Collections.fetch`, `paths` and `plan` make a collection available, by key
and by named handle, and `main` runs the collection commands on the file;
`ethos_data.collections()` builds the handle a tool keeps for the life of the
process. The file format is in
[`collections.yaml`](../schemas.md#collectionsyaml).

::: ethos_data.selection
    options:
      members:
        - load_collections
        - catalog_pin
        - Collections
        - CollectionError
        - UnknownCollection
        - CollectionsNotFound
        - variant_name
        - path_matches
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
