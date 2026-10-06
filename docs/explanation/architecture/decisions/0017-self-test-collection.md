# 0017. Ship a self-test collection with the package

**Status:** implemented · **Date:** 2026-10-02 · **Implemented by:** #18

## Context

Whether a machine can obtain data at all, with the catalogue readable, the
store reachable and the cache writable, must be checkable without a package's
own collections, which may be large, restricted or not installed. A problem
report needs the same check.

## Decision

ETHOS.Data ships `src/ethos_data/examples/collections.yaml`, exposed as
`ethos_data.EXAMPLE_COLLECTIONS`. `ethos-data selftest`, and
`run_selftest(catalog=, root=)` in Python, build a handle on that file and run
three steps, stopping at the first that fails:

| Step | Checks |
|---|---|
| settings | the settings snapshot, with unreachable caches marked |
| catalogue | the catalogue's location and version |
| files | every file of every collection: downloaded, already present or read in place, each checked against the catalogue's checksums |

- The file selects public test data of under 200 KB that both catalogues
  describe. It names no release bounds while no stamped public release
  exists; once one does, it bounds the releases it accepts with
  `min_version` ([0018](0018-numbered-catalogue-releases.md)).
- The self-test ends with `selftest passed` (exit 0) or
  `selftest FAILED at <step>: <why>` (exit 1). The global `--catalog` and
  `--root` apply, so an empty `--root` forces a real download of every file
  that is not read in place.
- A test keeps the documentation's copy, `docs/assets/examples/collections.yaml`,
  identical to the shipped file.
- The problem report runs the self-test first ([0025](0025-handoff-templates.md)).

## Alternatives considered

- **A package's collections.** They may be large, restricted or not
  installed.

## Consequences

- The documentation's examples and the self-test share one file.
- The file must keep naming published public data: a release that drops it
  makes the self-test fail.
- On the cluster computer the files are usually read in place from the
  cluster's public cache ([0028](0028-one-public-cache-on-the-cluster.md)).
- See [Check that a download works](../../../how-to/data-users/set-up-your-machine.md#check-a-download).

## Related

- [0015. Let each package's data command own its collection workflows](0015-package-commands-own-collections.md)
- [0018. Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0025. Draft the handoffs between roles from templates](0025-handoff-templates.md)
- [0028. Share one public cache on the cluster](0028-one-public-cache-on-the-cluster.md)
- [6. Runtime View](../runtime.md)
