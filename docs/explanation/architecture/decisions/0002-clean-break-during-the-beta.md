# 0002. Make a clean break during the beta; `catalog migrate` converts the internal catalogue once

**Status:** proposed · **Date:** 2026-10-05 · **Implemented by:** #10–#27, each removing the compatibility code of its area, and #21 (`catalog migrate`); implemented once `catalog migrate` is removed, after the internal catalogue is converted

## Context

ETHOS.Data is a beta with few installations. Every reader of a superseded
format, every renamed key and every second spelling multiplies code paths,
tests and documentation, and keeps two concepts alive where the target has
one. The internal catalogue must be converted to the target formats exactly
once, in a diff that a maintainer can review.

## Decision

- No compatibility fallback exists. The package reads and writes only the
  formats, keys, settings, commands and import paths this architecture
  describes. There is:
    - no settings file or default cache in a location other than those of
      [0010](0010-one-settings-file-per-account.md), and no `cache_dir` key;
    - no `manifests/` shard directory;
    - no `source_dir`, `ethos:uploaded` or `ethos:frozen` in a catalogue's
      `dataset.yaml` ([0022](0022-dataset-status-files.md));
    - no string `catalog:` location in a collections file, and no stripping of
      an `@ref` suffix ([0018](0018-numbered-catalogue-releases.md));
    - no second spelling: no `config set-cache` or `unset-cache`, no
      `materialize --force`, no hint for a command name outside the target,
      no `locate(dataset_roots=)`, no `resolve_cache_dir`, and no import of an
      error class or of `Resource` from a service module;
    - no `config show` row about a file or a key outside the target;
    - no test marker, and no test, for behaviour outside the target.
- `Catalog.role` is `None` when `ethos:catalog_role` is absent.
- An error class keeps a standard base, such as `KeyError`, only where that
  base describes it.
- `catalog migrate [NAMES] [--dry-run]` is the one converter. It:
    - writes each dataset's `status.yaml` from `source_dir`, `ethos:uploaded`
      and `ethos:frozen`;
    - removes those keys from `dataset.yaml` line by line, keeping comments,
      and refuses a file it cannot edit that way or a combination of keys the
      build would refuse;
    - moves `manifests/` to `shards/` and rewrites the `ethos:shards` paths;
    - writes `source_dir` as an absolute path;
    - turns `ethos:uploaded: true` into the state `frozen`, with the store
      copy as its authority, which `catalog upload --verify-only` verifies.
- `catalog migrate` is removed once the internal catalogue is converted,
  together with the refusals that name it.

## Alternatives considered

- **Readers of the superseded formats for a transition period.** Each reader
  is code, tests and documentation for two formats, kept for installations
  that can convert in one step.
- **Permanent shims.** Two concepts stay alive in every layer, and the
  documentation has to describe both.
- **Versioned formats with migration chains.** A chain of converters is kept
  forever for a catalogue that is converted once.

## Consequences

- Each key, command and import path has one spelling, so the reference, the
  code and the tests describe the same thing.
- A settings file outside the locations of
  [0010](0010-one-settings-file-per-account.md) is not read; its owner moves
  it.
- Packages, RESKit among them, call the target API. Nothing translates another
  spelling.
- The internal catalogue is converted in a maintainer's own clone:
  `catalog migrate --dry-run`, then `catalog migrate`, then
  `catalog status --check`. The diff is reviewed and merged by merge request
  ([0026](0026-internal-catalogue-on-the-cluster.md)).
- See [2. Architecture Constraints](../constraints.md) and
  [11. Risks and Technical Debt](../risks-and-technical-debt.md).

## Related

- [0001. Describe the target architecture in arc42, with C4 views and one file per decision](0001-arc42-c4-one-file-per-decision.md)
- [0006. Specify every file format once](0006-every-file-format-specified-once.md)
- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0018. Number catalogue releases `vYYYY.MM.N` and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
