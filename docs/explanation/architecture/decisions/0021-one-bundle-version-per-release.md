# 0021. Make a bundle version exactly what one release holds

**Status:** proposed · **Date:** 2026-10-05 · **Implemented by:** #25

## Context

A repository bundle's `bundle.json` records the catalogue release that holds
its version ([0020](0020-repository-bundles.md)). A published version must
mean exactly what that release holds. If a change were recorded in a version
a release already holds, the release would describe files the catalogue does
not have.

## Decision

- A bundle version that no release holds takes changes in.
- A version a release holds is never changed. The first change after that
  release starts the next version, which waits for a release of its own.
- A change is any added, changed, moved or removed file, and any new or gone
  member.
- `bundle update` with nothing changed asks the package's catalogue whether a
  release holds this version byte for byte, and records that release. The
  warning about an unpublished version then stops.
- `catalog add-bundle` publishes the changed members of a new version as their
  next revisions ([0019](0019-revisions-and-successors.md)).

## Alternatives considered

- **Record additions in the published version, and start a new version only
  for changed bytes.** An addition changes no published file, but the
  recorded release would then describe files the catalogue does not have.

## Consequences

- Every extension waits for a release before the warning stops and before the
  download route serves it, because that route refuses a version no release
  holds.
- The package maintainer proposes each new version
  ([0025](0025-handoff-templates.md)) and runs `bundle update` once the release
  is out, which records it.
- See [Keep data in the repository](../../../how-to/package-maintainers/keep-data-in-the-repository.md#update-data).

## Related

- [0018. Number catalogue releases `vYYYY.MM.N` and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0020. Keep a package's test data in a repository bundle that the catalogue publishes](0020-repository-bundles.md)
- [0025. Draft the handoffs between roles from templates](0025-handoff-templates.md)
- [6. Runtime View](../runtime.md)
