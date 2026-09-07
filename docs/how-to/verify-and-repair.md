# Check and repair the cache

Existence is not integrity. A cache entry that links into shared project
storage is only as stable as that storage: the target can be moved,
regenerated, truncated or replaced by a well-meaning colleague, and **nothing
about the path changes when it happens**. Downloads are verified as they
arrive; data read in place has never been checked at all.

`ice2-data verify` is the one place where the promise "these bytes are the ones
in the manifest" is actually tested.

## Verify

```bash
ice2-data verify onshore_wind            # sizes: cheap, run it often
ice2-data verify onshore_wind --deep     # checksums: slow, run it before you publish
ice2-data verify --all                   # every collection in the file
ice2-data verify --all --deep -q         # only report problems
```

```title="Output"
verifying 7 files from probe-small (sizes)

ok: 7

7 file(s) match the catalogue.
```

Without `--deep` it compares sizes, which catches truncation, replacement and
regeneration for a few milliseconds of `stat` calls. With `--deep` it reads
every byte and compares SHA-256 — the check to run before publishing a result,
not the one to run every morning.

`verify` never writes anything.

### What it can find

| Status | Means |
|---|---|
| `dangling` | a symbolic link whose target is gone |
| `wrong checksum` | the bytes changed (`--deep` only) |
| `wrong size` | the file was replaced or truncated |
| `missing` | expected here, not here |
| `unreadable` | present, but could not be read |
| `unavailable here` | restricted data this machine has no access to — not a fault |
| `unverifiable` | [staged](stage-unpublished-data.md) data, which has no checksums by design |
| `ok` | matches the catalogue |

They are reported worst-first, because the first line is the one people read.

It is deliberately **link-agnostic**: a symbolic link, a hard link, a configured
root and an ordinary downloaded directory are all just paths by the time they
reach it. That is what makes it useful during a migration, when a dataset may
be any of those on any given day.

## Repair

```bash
ice2-data verify --all --deep --repair --dry-run   # say what would be re-fetched
ice2-data verify --all --deep --repair            # do it
```

`--repair` re-fetches from dCache whatever no longer matches the manifest.

**It cannot repair what was never downloadable**, and says so per file rather
than failing:

| Skipped | Because |
|---|---|
| restricted data | never downloaded, by definition — there is nothing to fetch it from |
| staged data | the whole point of a staging entry is that it is *not* the catalogue's version — fix the entry yourself |
| data this machine cannot reach | nothing to fetch, and nowhere to put it |

**A dangling link is removed so the download has somewhere to land.** That is a
change other people sharing the cache will see — they will be re-fetching too —
so the links are listed explicitly *before* anything happens:

```title="Output"
these links will be removed so a download has somewhere to land
(other people share this cache -- they will be re-fetching too):
    /projects5/ice2_data_cache_public/global-wind-atlas -> /fast/central/shared_data/GWA_4.0
```

Which is what `--dry-run` is for. Run it first.

## `materialize`: turning a borrowed dataset into one you own

A dataset that appears in the cache as a symbolic link costs no disk space, but
it is only as durable as whatever it points at. Sooner or later you want a real
copy:

- the storage behind the link is about to be reorganised or deleted, and the
  data is not on dCache yet;
- a long run must be insulated from anybody editing the shared original halfway
  through;
- the link crosses to a filesystem that is slow, full, or about to be
  unmounted.

```bash
ice2-data materialize global-wind-atlas          # one dataset
ice2-data materialize --all --dry-run            # what it would cost
ice2-data materialize --all                      # every entry that is a link
```

`materialize` replaces the link with a real directory holding real files. Every
copy is checksummed against the manifest before it is put in place, and the old
link target is recorded in `.ice2-materialized.json` inside the directory, so a
copy can always be traced back to where it came from.

| Flag | Effect |
|---|---|
| `--dry-run` | report the cost, copy nothing |
| `--force` | do not stop at entries that are already real directories |
| `--no-verify` | skip checksum verification of each copied file (not advised) |

Two refusals worth knowing about:

**Only files the catalogue describes are copied.** A cache is not a backup of
somebody's project directory. Copying the strays as well would quietly make the
cache a second, divergent source of truth.

**It stops before filling the disk.** If the copy would leave less than 2% of
the filesystem free, it refuses — a cache that fills the volume it lives on
takes everyone else down with it.

Restricted datasets are refused outright: they may not be copied at all.

## Which one do I want?

| Symptom | Command |
|---|---|
| "is my data still right?" | `ice2-data verify --all` |
| "is my data *really* still right?" | `ice2-data verify --all --deep` |
| "something drifted, fix it" | `ice2-data verify --all --deep --repair` |
| "this link is about to break" | `ice2-data materialize <dataset>` |
| "where is this even coming from?" | `ice2-data config show` |

## See also

- [Use data already on disk](use-data-already-on-disk.md) — where links come
  from in the first place.
- [Caches, classes and roots](../explanation/caches-and-access.md).
