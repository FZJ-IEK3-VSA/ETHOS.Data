# API Reference

`ethos_data`'s public API. Most callers need only [`path`][ethos_data.path] and
[`fetch`][ethos_data.fetch]. The rest is here for completeness.

| Topic | Contents |
|-------|----------|
| [Catalogue and collections](catalog.md) | `Catalog`, `Dataset`, `Resource`, `Collections`, `load_catalog`, `load_collections` |
| [Configuration and access](configuration.md) | cache roots, scopes, provenance, `Location`, `locate`, `AccessError` |
| [Integrity and staging](integrity.md) | `verify`, `repair`, `Finding`, `materialize`, the staging root |
| [Maintainer tooling](maintain.md) | `ethos_data.maintain` — building, publishing, uploading |

Consumers never import `ethos_data.maintain`; `ethos_data` itself is a read-only
library.

## Getting data

::: ethos_data
    options:
      members:
        - path
        - fetch
        - fetch_one
        - resolve
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

## Downloading

The module behind `fetch`. It is called `retrieval`, not `fetch`, so that it
can never shadow the function above — the same reason `selection` is not called
`collections`.

::: ethos_data.retrieval
    options:
      members:
        - DataFiles
        - download
        - plan
        - cache_dir
        - local_path
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
