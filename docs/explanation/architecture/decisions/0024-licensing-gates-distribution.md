# 0024. Let unresolved licensing block distribution, not development

**Status:** proposed · **Date:** 2026-10-06 · **Implemented by:** #21, #25

## Context

Silence about a licence must not read as permission, and it must stay
visible which datasets someone cleared and which nobody looked at. A warning
suits someone who already has the data; handing data to others is where an
unsettled licence must stop it. Development must not wait for a legal
answer.

## Decision

Licensing is settled by a `licenses:` entry or by
`ethos:license_status: resolved`, and by nothing else. While a dataset's
licensing is unsettled:

| Command | Does |
|---|---|
| `fetch`, `verify` | warn, naming the dataset and the licence note |
| `link NAME` | refuses |
| `link --all` | skips the dataset and links the rest |
| `materialize` into a cache | refuses |
| `catalog upload` | refuses, except `--verify-only` |
| `bundle update`, `bundle export`, and reading a bundle that holds the dataset | refuse ([0020](0020-repository-bundles.md)) |
| `staging add` | proceeds |

- The licence status is promoted into the index row, so a reader knows it
  without the descriptor. `ethos:license_note` is never published.
- The guard is part of the lifecycle step ([0022](0022-dataset-status-files.md)),
  so every command that takes a guarded step applies it.

## Alternatives considered

- **Silence as permission.** A question nobody asked would read as an answer.
- **Fail a whole `link --all` over one dataset.** It would block every other
  dataset and teach people to stop asking.
- **Block staging too.** Development would wait for the legal answer.

## Consequences

- Terms are recorded before data is handed to others.
- Staged data stays one person's, on one machine, and is never uploaded.
- See [Licensing and immutability](../../licensing.md#unresolved-licensing-stops-distribution-not-work).

## Related

- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0016. Give one link command two modes](0016-one-link-command-two-modes.md)
- [0020. Keep attributed data in bundles that are authoritative for their package](0020-repository-bundles.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
