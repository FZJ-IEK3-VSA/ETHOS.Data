# 0016. Give one link command two modes

**Status:** proposed · **Date:** 2026-10-06 · **Implemented by:** a new PR (caches)

## Context

Filling a whole cache from a source catalogue and pointing one dataset at a
directory are the same job at two scales, so they must not disagree about the
entries they make. The command line must make plain which invocation prunes,
which writes into a cache other than the account's public cache, and where
restricted data goes: only into a cache whose permissions admit its readers.
The invocation that writes many entries at once must never be the accidental
one.

## Decision

| Mode | Command | Writes |
|---|---|---|
| Dataset | `ethos-data [--root CACHE] link NAME [DIR] [--force] [--catalog-root C]` | one entry, at once: a link to DIR, or to the dataset's build input; `--force` repoints an entry that is already a link |
| Catalogue | `ethos-data link --all --root CACHE [--catalog-root C] [--prune] [--dry-run]` | an entry for every public dataset of the source catalogue C that has a build input, all in CACHE, which the run names before it writes |

- The global `--root CACHE`, before `link`, `unlink` or `materialize`, names
  the cache that holds the entry. Without it, a public dataset's entry goes
  into the public cache, and a restricted dataset's into the only listed
  restricted cache. With several listed, the command refuses and names them;
  with none, it refuses and names `config add-restricted-cache DIR`
  ([0010](0010-one-settings-file-per-account.md)).
- A restricted dataset's entry goes only into a listed restricted cache, and a
  public dataset's never into one. Naming a restricted dataset links it into
  the restricted cache of its access combination, which registers an
  authorised installation.
- `link --all` requires `--root`: the catalogue-wide link tree goes only into
  a public cache a maintainer names, in practice the cluster's public cache.
  It links public data only, and refuses a listed restricted cache as its
  root.
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
- Where symbolic links cannot be created, as on Windows without that right,
  `link` refuses and offers `ethos-data materialize NAME --from DIR`, a
  verified copy.
- While a dataset's licensing is unsettled, `link NAME` refuses it and
  `link --all` skips it ([0024](0024-licensing-gates-distribution.md)).
- Recording a link in the dataset's status file with `--catalog-root` is
  [0022](0022-dataset-status-files.md). Filling the cluster's public cache is
  [0028](0028-one-public-cache-on-the-cluster.md).

## Alternatives considered

- **A bare `link` that means the whole catalogue.** A forgotten dataset name
  would rebuild a whole cache.
- **`link --all` into the account's public cache when no `--root` is given.**
  A forgotten `--root` would build the whole link tree in whatever public
  cache the account has, on the cluster the one every user reads, without
  anyone naming it.
- **Restricted data in catalogue mode.** One `--root` names one cache, but each
  restricted dataset belongs in the cache of its own access combination.
- **`link --remove` instead of `unlink`.** Removal follows a different safety
  rule: `--force` repoints a link, while nothing overrules the refusal to
  remove a real directory.

## Consequences

- One planner and one entrance: the two modes cannot disagree about an entry.
- A user links one dataset at a time, by name; the catalogue-wide link tree
  is a maintainer's job.
- Restricted data reaches only a listed restricted cache, and only by name,
  from someone who knows that the installation is authorised.
- See [Link existing data into the cache](../../../how-to/catalogue-maintainers/link-existing-data.md)
  and [`ethos-data link`](../../../reference/cli/ethos-data.md#link-dataset-directory).

## Related

- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0011. Let the access class pick the root, and a link mean "read in place"](0011-access-class-picks-the-root.md)
- [0022. Record each dataset's state in a status file](0022-dataset-status-files.md)
- [0024. Let unresolved licensing block distribution, not development](0024-licensing-gates-distribution.md)
- [0028. Share one public cache on the cluster](0028-one-public-cache-on-the-cluster.md)
- [5. Building Block View](../building-blocks.md)
