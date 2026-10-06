# Why one catalogue

A dozen scientific tools at one institute need overlapping input data: ERA5
reanalysis, land cover, wind atlases, bathymetry. The naive arrangement gives
each tool its own downloader and its own copy of the data. `ethos-data` exists
because that arrangement fails in a specific, predictable way — and because the
obvious fixes for it fail worse.

## The problem with per-tool inventories

Suppose each tool ships a list of the files it needs, with URLs and checksums.
It works, on day one.

Then a dataset is revised. Tool A updates its list; tool B does not, because
nobody told its maintainer. Now the two tools disagree about what
"corine-land-cover" means, and there is no place where that disagreement is
visible. Both still run. Both still produce numbers.

Let the tools share one cache to save disk space and it gets worse, not better:
two tools writing different bytes to the same path is a corruption, and two
tools writing the same bytes to different paths is the disk usage you were
trying to avoid.

## The split

`ethos-data` separates the two things that were tangled together:

| | Lives in | Says |
|---|---|---|
| **the catalogue** | one institute-wide repository | what a dataset *is*: paths, sizes, SHA-256 checksums, sources, licences |
| **a collections file** | each tool's own repository | which *slices* of those datasets it needs |

A `collections.yaml` contains **no file paths, no sizes, no checksums and no
URLs**. It names a dataset and a glob:

```yaml
collections:
  onshore_wind:
    include:
      - dataset: reskit-test-data/era5
        files: ["100m_*_component_of_wind.nc"]
```

That omission is the whole design. There is no per-tool inventory to drift,
because there is no per-tool inventory. The two things a collection may add —
`paths:`, naming a workflow's inputs by handle, and a `test:` / `full:` pair —
are references into the catalogue as well.

## What makes the sharing work

The cache layout is derived, not configured:

```
<public cache>/<dataset>/<resource path>
```

Every tool computes that path from the same catalogue entry, so two tools asking
for the same file arrive at the same absolute path. When the second one asks,
the file is simply there.

<figure markdown="span">
  ![One catalogue, two tools, one derived cache path](../assets/diagrams/dedup-light.svg#only-light){ .diagram }
  ![One catalogue, two tools, one derived cache path](../assets/diagrams/dedup-dark.svg#only-dark){ .diagram }
</figure>

**Nothing synchronises.** There is no lock, no index of what has been
downloaded, no daemon, no symlink farm, and no "cache manager" to go wrong. Two
processes racing to fetch the same file both verify it against the same
checksum, and the loser's work is discarded — which is the correct outcome and
costs one redundant download at worst.

## What would break it

Anything that lets two tools compute *different* paths for the same catalogue
entry. That is why `Resource.key` (`"<dataset>/<resource path>"`) and
`local_path` are treated as compatibility surface rather than implementation
detail: a change there does not fail loudly, it just quietly stops the
deduplication and nobody finds out for months.

The same reasoning explains a smaller decision. A collection's `files:` patterns
and a dataset's `ethos:include` patterns are matched by *the same function*,
`path_matches`. If the writer and the reader globbed differently, a pattern
could select a file when a manifest was built and miss it when a collection was
resolved — a difference that shows up as a missing file, far from its cause.

## Why the catalogue is versioned, not live

A collections file names the catalogue releases it accepts:

```yaml
catalog:
  min_version: v1.2.0
```

Each release is a **tag**, `vMAJOR.MINOR.PATCH`, not a branch. A released
version of a tool must resolve to the same bytes, or "reproducible" means
nothing. `ethos-data` enforces the distinction where it matters — a tag's
contents cannot change, so its catalogue is cached on disk indefinitely; a URL
naming `main`, `master`, `HEAD`, `latest`, `dev` or `develop` is recognised as
moving and re-fetched every time.

This is also why a withdrawal need not break a released tool. Within a major
release, dCache keeps every version it published, so a collections file
whose bounds stop before the withdrawal, `exact_version: v1.3` say, keeps
working; the bytes go only after a major release. A collections file that
admits a later release reads a catalogue without the dataset, and the error
says plainly that the dataset cannot be found, as for a mistyped name. Release
notices announce withdrawals.

!!! warning "Gap: `catalog:` takes a URL"
    The code takes only a catalogue path or URL in `catalog:`, such as a
    release tag's `datacatalog.json` on GitHub, and has no release bounds.
    Its error for an unknown dataset lists the datasets the catalogue has
    and, for the public catalogue, suggests that the dataset was withdrawn
    and that an older catalogue would still describe it.

## What a tool gives up

Being told, rather than deciding, what a dataset contains. A tool cannot patch
a checksum locally, or quietly ship a slightly different version of a shared
raster. A package's bundle may hold a change the catalogue has not accepted
yet, but only for that package and never quietly: the package reads it in
place, never through a cache, and warns until the bundle is realigned. If a
dataset needs to change, that change happens in the catalogue, once, where
every consumer sees it.

That is a real constraint and it is the point of the exercise. The alternative
is twelve tools that each believe they are using CORINE Land Cover 2018.

## See also

- [The catalogue format](catalogue-format.md) — what the catalogue actually is.
- [Caches, classes and roots](caches-and-access.md) — where the bytes come from.
- [Write a collections file](../how-to/package-maintainers/write-a-collections-file.md).
