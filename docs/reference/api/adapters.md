# Adapters

`ethos_data.adapters` holds the external systems ETHOS.Data talks to, each
behind a port: dCache for the maintainer who uploads, the downloader every
reader uses, and git for a release. Code that needs one takes it as an
argument, and a test hands it the fake instead:

| Port | Real adapter | Fake |
|---|---|---|
| `Store` | `DcacheStore`: rclone for bytes, the DESY REST interface for chmod and locality | `FakeStore`: records each call, and copies into a directory or a test server |
| `Downloader` | `PoochDownloader`: hash-checked downloads into the cache | `FakeDownloader`: serves the bytes it was given, checking their hashes |
| `Git` | `GitRepository`: the `git` command line in a checkout | `FakeGit`: keeps its commits, tags and pushes in lists |

`ethos-data catalog upload` uses `upload.run(..., store=)`, and
`ethos_data.download` takes `downloader=`. The test suite refuses to run
rclone or `oidc-token` at all, so an upload in a test must be given a fake.

## Ports

::: ethos_data.adapters
    options:
      members:
        - Store
        - Downloader
        - Git
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
