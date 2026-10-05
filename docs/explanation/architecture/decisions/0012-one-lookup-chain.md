# 0012. Find every file through one lookup chain

**Status:** proposed · **Date:** 2026-10-02 · **Implemented by:** #15, a new PR (shared cache: the shared-cache locator), #16, #24, #25

## Context

`plan`, `paths`, `fetch` and `verify` must agree about where a file is read.
Packages need their bundles read first, a download switch and a catalogue
override, without writing any of them. On the cluster, users must read in
place what maintainers provide, and download only what is missing. A refusal
must never fall through to a download.

## Decision

Every file goes through eight locators, in this order. A locator that is not
considered for a file, or does not find it, passes.

| # | Locator | Considered for | Finds the file | Refuses |
|---|---|---|---|---|
| 1 | Dataset roots | a dataset with a root set for it | in that root, in place | never |
| 2 | Staging | every class except restricted, once a staging root is set | in the staging root, in place and unchecked; it warns once per dataset per call | never |
| 3 | Bundles | a dataset that a listed bundle holds, unless the download switch is on | in the bundle, in place, after a size and SHA-256 check | a missing or altered file, with `BundleError`, never a download |
| 4 | Restricted cache | restricted data only | in the restricted cache, in place | no restricted cache, no entry, a dangling or an unreadable entry, with `AccessError` describing the dataset ([0013](0013-every-input-is-required.md)) |
| 5 | Shared cache | public and internal data, once a shared cache is set; never restricted data | in the shared cache, in place, when the file is there | never |
| 6 | Public-cache link | public data | in the user's public cache, in place, when the entry or a family above it is a link | never |
| 7 | Public-cache copy | public data | in the user's public cache, as a file of the recorded size, hash-checked when fetched | never |
| 8 | Download | public and internal data | at `<publication_url>/<remote_prefix>[@<r>]/<path>`, downloaded into the user's public cache | internal data, which is never downloaded and is read on the cluster from the shared cache; a missing publication URL. Both with `AccessError`. |

- The first locator that finds a file decides where it is read. A refusal
  ends the call before any transfer.
- The chain is built from the handle's settings snapshot
  ([0010](0010-one-settings-file-per-account.md)), and building it touches
  nothing. `config show` prints it, numbered.
- `plan` and `verify` run the chain in describe mode: a refusal becomes "not
  available here", with its reason, and nothing is downloaded.
- Cache entries use the dataset's entry name, `<dataset>` or `<dataset>@<r>`
  ([0019](0019-revisions-and-successors.md)). Staging and per-dataset roots
  use the dataset's name.
- `fetch=False` downloads nothing and contacts no store. A file that would be
  downloaded raises `NotFetched`, naming where it belongs.
- A download never writes through a link, the dataset's own or its family's,
  and never into the shared cache.
- The order follows four rules:
    1. overrides first, because they are one person's explicit statements;
    2. bundles before the caches, because the repository is the source of
       truth for its test data ([0020](0020-repository-bundles.md));
    3. restricted data refuses before the shared cache and the public cache
       are consulted;
    4. the shared cache before the user's own public cache, so that cluster
       users read in place what maintainers provide and download only what it
       lacks ([0028](0028-read-only-shared-cache.md)).

## Alternatives considered

- **One long `locate()` function.** Every place and every refusal is a branch
  of one function, describe mode needs a copy of those branches, and no place
  can be tested alone.
- **Bundle reads in each package.** Every package that ships test data writes
  its own bundle-first reads, download switch and catalogue override.

## Consequences

- `bundles=`, the download switch and `fetch=False` are options of the chain.
  RESKit reads its bundles through it, not through code of its own.
- A broken entry in the shared cache passes. A public file is then read from,
  or downloaded into, the user's own public cache, an internal one is refused
  at the download, and `verify` reports the entry for the maintainers
  ([0028](0028-read-only-shared-cache.md)).
- See [6. Runtime View](../runtime.md) for the lookup of one file,
  [Fetch, or only resolve the paths](../../../how-to/data-users/use-data-in-a-script.md#fetch-or-path)
  and [Choose the source of bundled data](../../../how-to/package-maintainers/run-in-ci.md#download-switch).

## Related

- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0013. Treat every input as required, and describe what is missing](0013-every-input-is-required.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0020. Keep a package's test data in a repository bundle that the catalogue publishes](0020-repository-bundles.md)
- [0028. Serve shared data on the cluster from a read-only shared cache](0028-read-only-shared-cache.md)
- [5. Building Block View](../building-blocks.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
