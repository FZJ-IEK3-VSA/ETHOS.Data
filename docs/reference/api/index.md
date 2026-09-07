# API Reference

`ice2_data`'s public API. Most callers need only [`fetch`][ice2_data.fetch] —
and, if they are wrapping it in a package of their own, `load_collections` and
`download`. The rest is here for completeness.

| Topic | Contents |
|-------|----------|
| [Catalogue and collections](catalog.md) | `Catalog`, `Dataset`, `Resource`, `Collections`, `load_catalog`, `load_collections` |
| [Configuration and access](configuration.md) | cache roots, scopes, provenance, `Location`, `locate`, `AccessError` |
| [Integrity and staging](integrity.md) | `verify`, `repair`, `Finding`, `materialize`, the staging root |
| [Maintainer tooling](maintain.md) | `ice2_data.maintain` — building, publishing, uploading |

Consumers never import `ice2_data.maintain`; `ice2_data` itself is a read-only
library.

## Fetching

::: ice2_data
    options:
      members:
        - fetch
        - fetch_one
        - resolve
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Downloading

The module behind `fetch`. It is called `retrieval`, not `fetch`, so that it
can never shadow the function above — the same reason `selection` is not called
`collections`.

::: ice2_data.retrieval
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
