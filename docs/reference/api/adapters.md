# Adapters

`ethos_data.adapters` holds the external systems ETHOS.Data talks to, each
behind a port: dCache for the maintainer who uploads, the downloader every
reader uses, git for a release, and the metadata sources catalogue files are
read from. Code that needs one takes it as an
argument, and a test hands it the fake instead:

| Port | Real adapter | Fake |
|---|---|---|
| `Store` | `DcacheStore`: rclone for bytes, the DESY REST interface for chmod and locality, an anonymous `HEAD` for the read-back | `FakeStore`: records each call, keeps what it is sent and reads it back |
| `Downloader` | `PoochDownloader`: hash-checked downloads into the cache | `FakeDownloader`: serves the bytes it was given, checking their hashes |
| `Git` | `GitRepository`: the `git` command line in a checkout | `FakeGit`: keeps its commits, tags and pushes in lists |
| `MetadataSource` | `FileSource`: a checkout or a copy on disk; `HttpSource`: HTTPS, asking for gzip; `CachedSource`: the metadata cache in front of another source, keeping every location that names no moving ref | `MemorySource`: a catalogue tree held in memory, recording every read |

A port returns data and raises a typed error when it fails:
[`UploadError`][ethos_data.errors.UploadError] for the store,
[`DownloadError`][ethos_data.errors.DownloadError] for the downloader, naming
the URL, [`MaintenanceError`][ethos_data.errors.MaintenanceError] for git, and
for a metadata source [`IncompleteCatalog`][ethos_data.errors.IncompleteCatalog]
when nothing is at a location and
[`CatalogUnavailable`][ethos_data.errors.CatalogUnavailable] when it cannot be
reached.
The fakes fail the same way.

`ethos-data catalog upload` uses `upload.run(..., store=)` and reads every
uploaded file back through `Store.served`, and `ethos_data.download` takes
`downloader=`. The test suite refuses to run rclone or `oidc-token` at all, so
an upload in a test must be given a fake.

## Ports

::: ethos_data.adapters
    options:
      members:
        - Store
        - Downloader
        - Git
        - MetadataSource
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Real adapters

::: ethos_data.adapters.dcache
    options:
      members:
        - DcacheStore
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

::: ethos_data.adapters.downloads
    options:
      members:
        - PoochDownloader
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

::: ethos_data.adapters.git
    options:
      members:
        - GitRepository
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

::: ethos_data.adapters.metadata
    options:
      members:
        - FileSource
        - HttpSource
        - CachedSource
        - MemorySource
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Fakes

::: ethos_data.adapters.fakes
    options:
      members:
        - FakeStore
        - FakeDownloader
        - FakeGit
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
