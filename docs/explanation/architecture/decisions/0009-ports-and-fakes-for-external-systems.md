# 0009. Reach dCache, downloads, metadata sources and git through ports with fakes

**Status:** implemented · **Date:** 2026-10-02 · **Implemented by:** #20, #40 (the metadata-source port), #23

## Context

Pipelines and lookup must run in tests without the network, rclone or
credentials. External systems must be replaceable, and every check a pipeline
makes, the read-back of a published file included, must run against one fake.
Downstream packages need the same fakes for their own tests.

## Decision

Four ports, each a `typing.Protocol` with its real adapters and a fake, all
shipped in the package:

| Port | Answers | Real adapter | Fake |
|---|---|---|---|
| `Store` | copies files into the publication root and never overwrites; syncs a tree, leaving out `.git`; purges a folder; gets a token; sets permissions; reports locality (online, nearline); says whether an object exists; reports the size the anonymous download door serves for a URL | `DcacheStore`: rclone, `oidc-token` and the DESY REST frontend | `FakeStore` |
| `Downloader` | fetches files from a base URL into a directory, keeping a present file whose hash matches and checking each against its recorded hash; a failure raises `DownloadError`, naming the URL | `PoochDownloader` | `FakeDownloader` |
| Metadata source | reads one catalogue part at a location: a file or a checkout, an HTTPS URL, the metadata cache in front of HTTPS, or a tree in memory. A missing part and an unreachable location fail differently: the inventory reader words the first as `IncompleteCatalog`, and the second raises `CatalogUnavailable`, naming the location. | the file, HTTPS and caching sources | the in-memory source |
| `Git` | whether a checkout is clean, its tags and head; fetch, fast-forward, commit, tag and push | `GitRepository` | `FakeGit` |

- The anonymous read-back of published files belongs to the store port, so one
  fake answers every check of the upload, record, release and purge pipelines
  and of `catalog status --check`.
- Adapters read no settings. Services pass them the store settings from
  `catalog.yaml`'s `ethos:store` and the cache directory from the settings
  snapshot. Adapters raise typed errors and return data, not exit codes.
- Services default to the real adapters, and tests pass fakes. Tests never use
  the network (loopback only), never run rclone or `oidc-token`, and never read
  the developer's settings.
- `check-store` stays a diagnostic script, outside the ports.

## Alternatives considered

- **Patching `subprocess` and `urllib` in tests.** Tests then depend on how an
  adapter calls its tools, and downstream packages get nothing to reuse.
- **Keeping the read-back outside the store port.** Every check of a published
  file needs an HTTP server in its tests, beside the fake store.

## Consequences

- Pipelines and lookup are tested without the network, rclone or credentials.
- Downstream packages can use the fakes in their own tests.
- The store defaults (remote `HIFIS`, VO path `Helmholtz/FZJ-ICE2`, OIDC
  profile `HIFIS`, REST frontend `https://hifis-storage-web.desy.de/api/v1`)
  are written once, in `formats.catalogue`, and a catalogue's `ethos:store`
  overrides them.
- See [5. Building Block View](../building-blocks.md) and
  [7. Deployment View](../deployment.md).

## Related

- [0007. Read every generated catalogue through one inventory reader](0007-one-inventory-reader.md)
- [0008. Build the package in four layers: model, adapters, services, presentation](0008-four-layers.md)
- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0023. Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md)
- [5. Building Block View](../building-blocks.md)
- [7. Deployment View](../deployment.md)
