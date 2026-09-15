# API Reference

`ethos_data`'s public API. Most callers need only [`paths`][ethos_data.paths],
[`path`][ethos_data.path] and [`fetch`][ethos_data.fetch]. The rest is here for
completeness.

| Topic | Contents |
|-------|----------|
| [Catalogue and collections](catalog.md) | `Catalog`, `Dataset`, `Resource`, `Collections`, `load_catalog`, `load_collections`, `catalog_pin`; the errors `CatalogUnavailable`, `UnknownDataset`, `IncompleteCatalog`, `CollectionError`, `UnknownCollection` |
| [Configuration and access](configuration.md) | cache roots, scopes, provenance, `Location`, `locate`, `AccessError` |
| [Integrity and staging](integrity.md) | `verify`, `repair`, `Finding`, `materialize`, the staging root |
| [Maintainer tooling](maintain.md) | `ethos_data.maintain` — building, publishing, uploading |

Consumers usually need no `ethos_data.maintain` imports. The public API includes
local download, cache, staging, and configuration operations as well as reads.

## Getting data

`paths()`, `fetch()` and `resolve()` name the collections file with
`package=` — the file an installed package registers — or `collections=`, a
path. `path()` and `list_resources()` need neither, but accept either: the
file then contributes its `catalog:` pin, below an explicit `catalog=`,
`$ETHOS_DATA_CATALOG` and a configured catalogue — the order `fetch()` applies,
so `path()` and `fetch()` given the same file read the same catalogue. Giving
both `package=` and `collections=` is a `TypeError`. `list_resources()`
returns resources in key order. A catalogue index that cannot be read raises
[`CatalogUnavailable`][ethos_data.catalog.CatalogUnavailable].

::: ethos_data
    options:
      members:
        - paths
        - path
        - fetch
        - fetch_one
        - resolve
        - list_resources
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Collections shipped by packages

::: ethos_data.selection
    options:
      members:
        - package_collections
        - registered_packages
        - CollectionsNotFound
        - ENTRY_POINT_GROUP
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

A collection defined in a way that cannot be resolved raises
[`CollectionError`][ethos_data.selection.CollectionError]; a name the file does
not define raises [`UnknownCollection`][ethos_data.selection.UnknownCollection].
Both are documented with [`Collections`](catalog.md#collections).

## Downloading

The module behind `fetch`. It is called `retrieval`, not `fetch`, so that it
can never shadow the function above — the same reason `selection` is not called
`collections`.

`fetch()` and `paths()` take `skip_unavailable=`, forwarded to `download()`:
under it, a `paths` handle whose data this machine cannot reach is left out
of the result's `.named`, recorded in `NamedPaths.omitted` and named in a
`UserWarning`, and asking the mapping for it raises a `KeyError` that says it
was left out here rather than never defined.

::: ethos_data.retrieval
    options:
      members:
        - DataFiles
        - NamedPaths
        - download
        - plan
        - cache_dir
        - local_path
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
