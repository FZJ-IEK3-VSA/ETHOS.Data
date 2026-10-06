# 0012. Find every file through one lookup chain

**Status:** implemented · **Date:** 2026-10-06 · **Implemented by:** #15, #39 (the restricted-caches locator), #16, #24, #25

## Context

`plan`, `paths`, `fetch` and `verify` must agree about where a file is read.
Packages need their bundles read first, a download switch and a catalogue
override, without writing any of them. On the cluster, users must read in
place what maintainers provide, and download only what is missing. A refusal
must never fall through to a download.

## Decision

Every file goes through five locators, in this order. A locator that is not
considered for a file, or does not find it, passes. The first that finds the
file decides where it is read; a refusal ends the call before any transfer.

| # | Locator | Considered for | Finds the file | Refuses |
|---|---|---|---|---|
| 1 | Staging | every dataset except restricted ones, once a staging root is set | in the staging root, in place and unchecked; it warns once per dataset per call | never |
| 2 | Bundles | a dataset that a listed bundle holds; with the download switch on, only files whose recorded SHA-256 the catalogue does not hold for the same key | in the bundle, in place, after a size and SHA-256 check | a missing file, or a change `bundle update` has not recorded: `BundleError`, never a download |
| 3 | Restricted caches | restricted data only | in the first listed restricted cache whose entry is readable, in place | no listed cache has a readable entry: `AccessError` ([0013](0013-every-input-is-required.md)) |
| 4 | Public cache | public data | in the public cache: in place when the entry, or a family entry above it, is a link; otherwise a file of the recorded size, hash-checked when fetched | never |
| 5 | Download | public data | at `<publication_url>/<remote_prefix>[@<r>]/<path>`, downloaded into the public cache | a missing publication URL: `AccessError` |

- The chain is built from the handle's settings snapshot
  ([0010](0010-one-settings-file-per-account.md)), and building it touches
  nothing. `config show` prints it, numbered.
- `plan` and `verify` run the chain in describe mode: a refusal becomes "not
  available here", with its reason, and nothing is downloaded.
- Cache entries use the dataset's entry name, `<dataset>` or `<dataset>@<r>`
  ([0019](0019-revisions-and-successors.md)). Staging uses the dataset's name.
- `fetch=False` downloads nothing and contacts no store. A file that would be
  downloaded raises `NotFetched`, naming where it belongs.
- A download goes into the public cache. It never writes through a link, the
  dataset's own or its family's.
- The order follows four rules:
    1. staging first, because it is one person's explicit statement;
    2. bundles before the caches, because a package's bundle is authoritative
       for that package ([0020](0020-repository-bundles.md));
    3. restricted data is found or refused before the public cache and the
       download are consulted;
    4. the public cache before the download, so a file that is there, or
       linked there, is never downloaded again.

## Alternatives considered

- **One long `locate()` function.** Every place and every refusal is a branch
  of one function, describe mode needs a copy of those branches, and no place
  can be tested alone.
- **Bundle reads in each package.** Every package that ships test data writes
  its own bundle-first reads, download switch and catalogue override.

## Consequences

- `bundles=`, the download switch and `fetch=False` are options of the chain.
  RESKit reads its bundles through it, not through code of its own.
- A broken link in the public cache refuses the read: a file read in place
  must be present, and `AccessError` names it. `verify` reports the link, and
  on the cluster a maintainer repairs it
  ([0028](0028-one-public-cache-on-the-cluster.md)).
- See [6. Runtime View](../runtime.md) for the lookup of one file,
  [Fetch, or only resolve the paths](../../../how-to/data-users/use-data-in-a-script.md#fetch-or-path)
  and [Choose the source of bundled data](../../../how-to/package-maintainers/run-in-ci.md#download-switch).

## Related

- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0013. Treat every input as required, and say what is missing](0013-every-input-is-required.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0020. Keep attributed data in bundles that are authoritative for their package](0020-repository-bundles.md)
- [0021. Let a bundle be ahead of the catalogue, and warn until it is realigned](0021-bundles-ahead-of-the-catalogue.md)
- [0028. Share one public cache on the cluster](0028-one-public-cache-on-the-cluster.md)
- [5. Building Block View](../building-blocks.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
