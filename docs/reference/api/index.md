# API Reference

`ethos_data`'s public API. Most callers need only the two handles:
[`collections`][ethos_data.collections] for what a tool's workflows need, by
name, and [`catalog`][ethos_data.catalog] for a dataset, folder or file by
key. The rest is here for completeness.

| Topic | Contents |
|-------|----------|
| [Catalogue and collections](catalog.md) | `Catalog`, `Dataset`, `Resource`, `Collections`, `load_catalog`, `load_collections`; the errors `CatalogUnavailable`, `CatalogVersionError`, `UnknownDataset`, `IncompleteCatalog`, `CollectionError`, `UnknownCollection` |
| [Configuration and access](configuration.md) | the settings snapshot, cache roots, provenance, `Location`, `locate`, `AccessError` |
| [Integrity and staging](integrity.md) | `verify`, `repair`, `Finding`, `run_selftest`, `materialize`, the staging root |
| [Shared model](model.md) | `ethos_data.model` — digests, dataset names and families, resource records |
| [Maintainer tooling](maintain.md) | `ethos_data.maintain` — building, publishing, uploading |
| [Adapters](adapters.md) | `ethos_data.adapters` — dCache, downloads and git behind ports, each with a fake |
| [Errors](errors.md) | `EthosDataError` and every refusal the library raises, with the exit status the command line gives each |

Consumers usually need no `ethos_data.maintain` imports. The public API includes
local download, cache, staging, and configuration operations as well as reads.

## Getting data

Two kinds of name, two handles. A **collection** is what a tool's workflow
needs, named once by its maintainer in the tool's `collections.yaml`;
`collections(path, tool=...)` loads that file into a
[`Collections`](catalog.md#collections) handle whose `paths()`, `fetch()`,
`resolve()` and `plan()` answer by collection name, and whose `main()` runs
the collection commands. `tool_main()` is the body of a tool's own console
script: it builds the handle only for the commands that need one. A **key**
(`<dataset>/<path>`) names one dataset, folder or file; `catalog()` loads the
configured or public catalogue into a [`Catalog`](catalog.md#catalogue) whose
`path()` and `resources()` answer by key, and a handle's `.catalog` does the
same for the catalogue it reads within the file's release bounds — so
`fetch()` and `.catalog.path()` on
one handle read the same catalogue. The one-call forms `fetch()`, `paths()`
and `resolve()` take the file's path and build a handle each time. A catalogue
index that cannot be read raises
[`CatalogUnavailable`][ethos_data.errors.CatalogUnavailable].

::: ethos_data
    options:
      members:
        - collections
        - catalog
        - tool_main
        - fetch
        - paths
        - resolve
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

A collection defined in a way that cannot be resolved raises
[`CollectionError`][ethos_data.errors.CollectionError]; a name the file does
not define raises [`UnknownCollection`][ethos_data.errors.UnknownCollection].
Both are documented with the other [errors](errors.md).

## Downloading

The module behind `fetch`. It is called `retrieval`, not `fetch`, so that it
can never shadow the function above — the same reason `selection` is not called
`collections`.

Every input a collection names is required: `fetch()`, `paths()` and
`download()` raise [`AccessError`][ethos_data.errors.AccessError] for restricted
data this account cannot read, before anything is downloaded, naming the
dataset, how to obtain it as far as the catalogue records that, and the
commands that register a copy. `plan()` and `verify()` only describe, and
report such data as not available here, with the state of every listed
restricted cache; they report a file with no publication URL to download it
from the same way. A file that cannot be downloaded, or whose bytes do not
match the recorded hash, raises
[`DownloadError`][ethos_data.errors.DownloadError], an `AccessError` that
names the URL.

::: ethos_data.retrieval
    options:
      members:
        - DataFiles
        - NamedPaths
        - download
        - plan
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
