# Catalogue and collections

Loading the catalogue, and resolving a collections file against it. Both are
described in [The catalogue format](../../explanation/catalogue-format.md).

Loading is **lazy**: `load_catalog` reads only the index, and a dataset's
inventory is fetched the first time something asks for its files. A sharded
dataset goes further — `resources_matching` pulls only the shards a set of
patterns could reach.

## Catalogue

Three errors say what went wrong:
[`CatalogUnavailable`][ethos_data.catalog.CatalogUnavailable] when the index
itself cannot be read — a wrong location, or a pinned revision or repository
that does not exist; its message names the location and says how to point at
another catalogue — [`UnknownDataset`][ethos_data.catalog.UnknownDataset] for
a dataset the catalogue does not describe, and
[`IncompleteCatalog`][ethos_data.catalog.IncompleteCatalog] for a dataset the
index lists whose descriptor or shard is missing.

::: ethos_data.catalog
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
answer `load_collections` uses, and the reason `ethos-data path` and
`ethos-data fetch` given the same `-c` file read the same catalogue. The file
format is in [`collections.yaml`](../schemas.md#collectionsyaml).

::: ethos_data.selection
    options:
      members:
        - load_collections
        - catalog_pin
        - Collections
        - CollectionError
        - UnknownCollection
        - variant_name
        - path_matches
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
