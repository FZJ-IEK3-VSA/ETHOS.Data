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

Add a shared cache to save disk space and it gets worse, not better: two tools
writing different bytes to the same path is a corruption, and two tools writing
the same bytes to different paths is the disk usage you were trying to avoid.

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
      - dataset: reskit-test-data
        files: ["era5-like/100m_*_component_of_wind.nc"]
```

That omission is the whole design. There is no per-tool inventory to drift,
because there is no per-tool inventory.

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

A collections file pins its catalogue with a URL:

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ethos-data-catalog/v2026.09/datacatalog.json
```

A **tag**, not a branch. A released version of a tool must resolve to the same
bytes forever, or "reproducible" means nothing. `ethos-data` enforces the
distinction where it matters — a pinned URL's contents cannot change, so the
catalogue is cached on disk indefinitely; a URL naming `main`, `master`, `HEAD`,
`latest`, `dev` or `develop` is recognised as moving and re-fetched every time.

This is also why a withdrawn dataset does not break old pins. A collections file
pointing at `v2026.09` keeps working after the dataset is unpublished; it breaks
only when somebody repoints it at a newer catalogue that no longer describes
what it asks for — and then the error says exactly that, and suggests pinning an
older one.

## What a tool gives up

Being told, rather than deciding, what a dataset contains. A tool cannot patch
a checksum locally, or quietly ship a slightly different version of a shared
raster. If a dataset needs to change, that change happens in the catalogue,
once, where every consumer sees it.

That is a real constraint and it is the point of the exercise. The alternative
is twelve tools that each believe they are using CORINE Land Cover 2018.

## See also

- [The catalogue format](catalogue-format.md) — what the catalogue actually is.
- [Caches, classes and roots](caches-and-access.md) — where the bytes come from.
- [Write a collections file](../how-to/write-a-collections-file.md).
