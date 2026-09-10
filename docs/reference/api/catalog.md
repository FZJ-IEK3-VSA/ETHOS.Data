# Catalogue and collections

Loading the catalogue, and resolving a collections file against it. Both are
described in [The catalogue format](../../explanation/catalogue-format.md).

Loading is **lazy**: `load_catalog` reads only the index, and a dataset's
inventory is fetched the first time something asks for its files. A sharded
dataset goes further — `resources_matching` pulls only the shards a set of
patterns could reach.

## Catalogue

::: ethos_data.catalog
    options:
      members:
        - load_catalog
        - Catalog
        - Dataset
        - Resource
        - UnknownDataset
        - shard_key
        - describe_catalog
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Collections

::: ethos_data.selection
    options:
      members:
        - load_collections
        - Collections
        - path_matches
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
