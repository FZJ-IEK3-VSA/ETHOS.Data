# Catalogue and collections

Loading the catalogue, and resolving a collections file against it. Both are
described in [The catalogue format](../../explanation/catalogue-format.md).

Loading is **lazy**: `load_catalog` reads only the index, and a dataset's
descriptor and inventory are read the first time something asks for its files.
A [`Dataset`][ethos_data.catalogs.Dataset] is its row in the index plus its
[`Inventory`][ethos_data.model.inventory.Inventory], read by the one inventory
reader through the metadata source the catalogue was loaded from: the files on
disk for a path, HTTPS with the metadata cache in front for a URL
([`metadata_source`][ethos_data.catalogs.metadata_source]). A sharded dataset
goes further: `inventory.matching(patterns)` reads only the shards the
patterns can reach.

## Catalogue

Three errors say what went wrong:
[`CatalogUnavailable`][ethos_data.errors.CatalogUnavailable] when the index
itself cannot be read — a wrong location, or a release tag that does not
exist; its message names the location and says how to point at another
catalogue — [`UnknownDataset`][ethos_data.errors.UnknownDataset] for
a dataset the catalogue does not describe, and
[`IncompleteCatalog`][ethos_data.errors.IncompleteCatalog] for a dataset the
index lists whose descriptor or shard is missing. A not-found names the
dataset and where it was asked for, and lists no other datasets:
"collection 'onshore_wind': the dataset 'era5-lnd' cannot be found. Maybe it
was mistyped, or it is not published."

`Catalog.path` and `Catalog.resources` answer for a key — one file, a folder,
a dataset or a family — fetching in the first case and only reading in the
second. `ethos_data.catalog()` builds the handle for the configured catalogue;
`Collections.catalog` is the one a tool reads within its file's release
bounds.

::: ethos_data.catalogs
    options:
      members:
        - load_catalog
        - metadata_source
        - Catalog
        - Dataset
        - shard_key
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Collections

A collection may carry `paths` — handles for the inputs a workflow takes — and
a `test` and a `full` variant. `Collections.variants`, `definition`,
`named_keys` and `check_variants` expose them; `resolve(name, test=...)`
selects the variant and runs `check_variants` on every collection it visits
through `extends`, not only the one asked for. `describe` gives a
collection checked through its model, and `definition` the selection a
variant makes. `load_collections` reads the file's release bounds, lets the
settings choose the catalogue within them
([`Settings.choose_catalog`][ethos_data.config.Settings.choose_catalog]) and
refuses one outside them with
[`CatalogVersionError`][ethos_data.errors.CatalogVersionError]. A package's
`show` and `fetch` commands use that same catalogue; `ethos-data fetch`
instead takes a catalogue key against explicit or shared settings or the
public default.
`Collections.fetch`, `paths` and `plan` make a collection available, by key
and by named handle, and `main` runs the collection commands on the file;
`ethos_data.collections()` builds the handle a tool keeps for the life of the
process. The file format is in
[`collections.yaml`](../schemas.md#collectionsyaml).

::: ethos_data.selection
    options:
      members:
        - load_collections
        - Collections
        - variant_name
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
