# 0022. Record each dataset's state in a status file

**Status:** proposed · **Date:** 2026-10-02 · **Implemented by:** #21, #22, #23

## Context

A dataset's progress through the catalogue must be recorded explicitly, with
evidence: who did what and when, the upload reports, the release that first
held it. Every command must check that its step is allowed, and a
hand-written claim of an upload must be impossible. `dataset.yaml` is written
by people, and its comments must survive the tools.

## Decision

Every dataset with files in a source catalogue has
`datasets/<name>/status.yaml`. The commands write it, nobody edits it by hand,
and it is never published; a family has none. It holds the `state`; the
absolute `source_dir` while a build input exists; the `revision`; the recorded
`copies` (`uploaded`, `linked` or `materialized`, each with its location and
when it was verified); the `authority`, one of those copies; and an
append-only `history` of steps, each with when, who, the state after it, and
what the step read or made.

| State | Means |
|---|---|
| `draft` | described, not built |
| `built` | inventory built from `source_dir` |
| `available` | bytes reachable for the access class: uploaded, linked or materialized |
| `frozen` | inventory final; an authoritative copy recorded; no build input |
| `withdrawn` | out of the catalogue; bytes kept |
| `purged` | bytes deleted; `status.yaml` stays as a tombstone, so the name is never reused |

- Every command checks its step against the lifecycle while it plans, and
  records the step after it acts. A refused step raises `TransitionError`
  (exit 1), naming what the dataset needs first. Guards that depend on the
  descriptor, such as settled licensing and the access class, are part of the
  step.
- A release changes no state: it adds a `release` step to every dataset with
  steps since its last release, tombstones included.
- `catalog status` shows each dataset's state, access class, last release
  with the steps since (for example `v2026.10.1 +1`) and next step.
  `catalog status --check` compares every record with its evidence: the
  descriptor a build would write, a draft's `source_dir`, and every copy,
  file by file.
- `dataset.yaml` only describes. `source_dir` is a key of a draft, and
  `catalog add` moves it into `status.yaml`.
- `link` and `materialize` record a copy only when given `--catalog-root`, a
  maintainer's own clone of the source catalogue. A user's installation is
  not a catalogue record.
- `catalog record` freezes a dataset: it checks a copy file by file, makes it
  the authority and retires `source_dir` into the history. An upload, a copy
  a cache owns, or for restricted data the registered installation can be
  frozen; a link to public or internal data only when named with `--copy`.
- Withdrawn datasets are left out of builds, the index, `publish` and
  `link --all`.

## Alternatives considered

- **Derive the state from keys in `dataset.yaml`.** There would be no place
  for a history.
- **A state key in `dataset.yaml`.** The tools would rewrite a hand-written
  file and lose its comments.
- **Rebuild a frozen inventory from its authoritative copy.** That would
  record the copy's current bytes as correct and erase the recorded hashes,
  the independent witness that detects a corrupted copy.

## Consequences

- Status files make reruns resumable ([0023](0023-maintenance-pipelines.md)).
- Maintainers commit them in their own clones and merge them by merge request
  ([0026](0026-internal-catalogue-on-the-cluster.md)); `catalog release`
  refuses an unclean checkout.
- A purged name stays taken ([0004](0004-cache-paths-from-resource-identity.md)).
- The states, steps and guards are drawn in
  [6. Runtime View](../runtime.md#dataset-lifecycle). See also
  [Add a dataset](../../../how-to/catalogue-maintainers/add-a-dataset.md).

## Related

- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0023. Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md)
- [0024. Let unresolved licensing block distribution, not development](0024-licensing-gates-distribution.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [5. Building Block View](../building-blocks.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
