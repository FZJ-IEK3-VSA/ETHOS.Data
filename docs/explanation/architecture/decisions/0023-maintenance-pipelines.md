# 0023. Run every catalogue workflow that writes as a pipeline that plans before it acts

**Status:** implemented · **Date:** 2026-10-06 · **Implemented by:** #20, #22, #42 (pipelines: build, upload, publish and the cache copies), #23, #26

## Context

Accepting, releasing and removing a dataset take several steps, and their
order must not depend on a maintainer's memory: bytes are deleted only after
a major release recorded after their removal, a release waits for verified
uploads, and its version must match what changed. Each workflow needs a dry
run, a refusal before its first side effect, and a way to resume after an
interruption. Library code must be testable without the command line or the
network.

## Decision

Every catalogue workflow that writes runs on `maintain.pipeline`, as a
pipeline of stages:

| Command | Stages |
|---|---|
| `catalog add SOURCE` | intake, place, build |
| `catalog add-bundle DIR` | update |
| `catalog build [NAMES]` | check, render, write, record |
| `catalog build NAME --revision` | compare, revise |
| `catalog upload NAMES` | check, transfer, permissions, verify, record |
| `ethos-data [--root S] link NAME [DIR] --catalog-root C` | check, link, record |
| `ethos-data [--root S] materialize NAMES --catalog-root C` | check, copy, verify, record |
| `ethos-data link --all --root S [--catalog-root C] [--prune]` | plan, apply, record |
| `catalog record NAME` | check, freeze |
| `catalog check-source NAME DIR` | compare, record |
| `catalog publish TARGET` | render, check, write |
| `catalog release VERSION` | check, stamp, commit, public, push, store, notices |
| `catalog update-checkout` | fetch, advance, check |
| `catalog remove NAMES` | withdraw, index, notices |
| `catalog remove NAMES --purge` | check, cache, store, tombstone |

S is a cache a maintainer names with `--root`, in practice the cluster's
public cache or a restricted cache ([0016](0016-one-link-command-two-modes.md)),
and C is the maintainer's own clone of the source catalogue. `catalog status`,
`build --check` and `publish --check` only read and compare, `check-store` is
a diagnostic script, and the one-time `catalog migrate` is not a pipeline.

- Every stage plans before any stage acts. A plan may read anything, such as
  hashes or the store, and writes nothing; `--dry-run` prints the plan.
- A refusal comes before the first write, so a batch is checked as a whole
  before its first transfer.
- Every action with an external effect (the store, a git push, deleting
  entries) carries a check of its result.
- A stage plans nothing for work already done, judged from the evidence
  (status files, tags, the store), so a rerun finishes the job. A batch is
  not a transaction: completed transfers stay.
- Steps are checked and recorded in the dataset's status file
  ([0022](0022-dataset-status-files.md)). Every pipeline records in the
  maintainer's own clone, and none commits or pushes a record; `catalog release`
  commits and tags the release it makes ([0026](0026-internal-catalogue-on-the-cluster.md)).
- Uploading bytes and releasing metadata are separate commands. The release's
  `check` stage refuses a public dataset whose upload was not verified after
  its last inventory change. It also computes the smallest level the changes
  since the last release require, from the steps recorded in the status
  files, the index rows of both catalogues compared with the last release
  (access and visibility) and a git diff of the clone against the last tag
  (metadata), and refuses a version that is not the next patch, minor or
  major of the last release at or above that level
  ([0018](0018-numbered-catalogue-releases.md)). A release's `--push` and
  `--upload` are opt-in, and a rerun with them finishes the release.
- The purge's `check` stage requires a major release recorded after the
  removal ([0018](0018-numbered-catalogue-releases.md)). It also refuses,
  before any deletion, when a recorded entry lies in a cache this account
  cannot write, naming the dataset and the cache. Its `cache` stage deletes
  the recorded links and copies in the cluster's public cache and in the
  restricted caches. Entries nobody recorded, such as downloads, are
  reported, not deleted, and public caches on other machines are never
  touched.
- The store settings come from `catalog.yaml`'s `ethos:store` (`remote`,
  `vo_path`, `oidc_profile`, `frontend`), are never published, and upload
  flags override them.

## Alternatives considered

- **Documented manual sequences.** The order would rest on the maintainer's
  memory, with no dry run, no refusal before the first change and no
  resumption.

## Consequences

- Removal and release are commands, and their order is enforced.
- A batch upload is not atomic; it is checked before the first transfer, and
  a rerun finishes it.
- Pipelines run in tests through the fakes of the ports, without the network
  ([0009](0009-ports-and-fakes-for-external-systems.md)).
- The re-download that `catalog check-source` compares stays manual.
- See [Add a dataset](../../../how-to/catalogue-maintainers/add-a-dataset.md),
  [Release the catalogue](../../../how-to/catalogue-maintainers/release-the-catalogue.md)
  and [Remove a dataset](../../../how-to/catalogue-maintainers/withdraw-a-dataset.md).

## Related

- [0009. Reach dCache, downloads, metadata sources and git through ports with fakes](0009-ports-and-fakes-for-external-systems.md)
- [0016. Give one link command two modes](0016-one-link-command-two-modes.md)
- [0018. Number catalogue releases `vMAJOR.MINOR.PATCH`, purge data only after a major release, and let collections files bound them](0018-numbered-catalogue-releases.md)
- [0019. Publish new versions as revisions or successors; published objects never change](0019-revisions-and-successors.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [5. Building Block View](../building-blocks.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
