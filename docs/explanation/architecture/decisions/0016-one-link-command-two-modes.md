# 0016. Give one link command two modes

**Status:** proposed · **Date:** 2026-10-05 · **Implemented by:** a new PR (shared cache)

## Context

Filling a whole cache from a source catalogue and pointing one dataset at a
directory are the same job at two scales, so they must not disagree about the
entries they make. The command line must make plain which invocation prunes,
which writes into a root other than the user's own cache, and what happens to
restricted data. The invocation that writes many entries at once must never
be the accidental one.

## Decision

| Mode | Command | Writes |
|---|---|---|
| Dataset | `ethos-data [--root CACHE] link NAME [DIR] [--force] [--catalog-root C]` | one entry, at once: a link to DIR, or to the dataset's build input; `--force` repoints an entry that is already a link. The global `--root CACHE`, before `link`, names the cache; without it the entry goes into the user's own public cache. |
| Catalogue | `ethos-data link --all --root CACHE [--catalog-root C] [--prune] [--dry-run]` | an entry for every dataset of the source catalogue C that has a build input, all in CACHE, which the run names before it writes |

- `link --all` requires `--root`: the catalogue-wide link tree goes only into
  a cache a maintainer names, in practice the cluster's shared cache.
- A bare `link` prints the usage of both modes and exits 2. A flag of the
  other mode exits 2: `--root` or `--prune` after `link` beside a name, and
  `--force` or a name beside `--all`.
- `--prune` is the only flag that removes anything: links whose names the
  catalogue does not describe. `--dry-run` prints the plan of `--all` and
  writes nothing.
- `unlink NAME` is a command of its own. It removes a link and never a real
  directory.
- A real directory in a cache is never replaced by a link: it is a copy the
  cache owns.
- Each entry goes into the root for its dataset's access class. Catalogue
  mode never links restricted data. Naming a restricted dataset links it into
  the restricted cache, which registers an authorised installation.
- While a dataset's licensing is unsettled, `link NAME` refuses it and
  `link --all` skips it ([0024](0024-licensing-gates-distribution.md)).
- Recording a link in the dataset's status file with `--catalog-root` is
  [0022](0022-dataset-status-files.md). Filling the cluster's shared cache is
  [0028](0028-read-only-shared-cache.md).

## Alternatives considered

- **A bare `link` that means the whole catalogue.** A forgotten dataset name
  would rebuild a whole cache.
- **`link --all` into the public cache in effect when no `--root` is given.**
  A maintainer who forgot `--root` would build the whole link tree in their
  own public cache, and nothing would say that the shared cache was missed.
- **`link --remove` instead of `unlink`.** Removal follows a different safety
  rule: `--force` repoints a link, while nothing overrules the refusal to
  remove a real directory.

## Consequences

- One planner and one entrance: the two modes cannot disagree about an entry.
- A user's public cache gets links one dataset at a time, by name.
- Licensed data reaches a cache only by name, from someone who knows that the
  installation is authorised.
- See [Link existing data into the cache](../../../how-to/catalogue-maintainers/link-existing-data.md)
  and [`ethos-data link`](../../../reference/cli/ethos-data.md#link-dataset-directory).

## Related

- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0024. Let unresolved licensing block distribution, not development](0024-licensing-gates-distribution.md)
- [0028. Serve shared data on the cluster from a read-only shared cache](0028-read-only-shared-cache.md)
- [5. Building Block View](../building-blocks.md)
