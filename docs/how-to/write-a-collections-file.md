# Write a collections file

A `collections.yaml` names *slices* of the shared catalogue using dataset names
and resource-path patterns. It selects inputs without duplicating their
inventory, sizes, hashes, or download URLs. See
[Why one catalogue](../explanation/deduplication.md).

## The shape

```yaml
# The catalogue this file resolves against. A local path or an http(s) URL.
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ethos-data-catalog/v2026.09/datacatalog.json

collections:
  test_suite:
    title: Data required by the pytest suite
    include:
      - dataset: reskit-test-data
        files: ["**"]

  landcover:
    title: Land cover for wind workflows
    include:
      - dataset: landcover
        files: ["*.tif"]

  onshore_wind:
    title: Data for onshore wind workflows
    extends: [landcover]
    include:
      - dataset: reskit-test-data
        files:
          - "era5-like/100m_*_component_of_wind.nc"
          - "gwa*-like.tif"
          - "turbinePlacements.shp"
```

| Key | |
|---|---|
| `catalog:` | where to resolve dataset names. Required unless the caller supplies one. |
| `collections:` | a mapping of collection name to definition. |
| `title:` | a one-line description, shown by `ethos-data list`. |
| `include:` | a list of `{dataset, files}` entries. |
| `extends:` | other collections in this file whose contents are pulled in too. |

## Patterns

Globs are matched against the resource path **with proper directory
semantics** — not plain `fnmatch`:

| Pattern | Matches | Does not match |
|---|---|---|
| `*.tif` | `wind.tif` | `sub/dir/wind.tif` |
| `**` | everything, at any depth | — |
| `**/*.tif` | `wind.tif`, `sub/dir/wind.tif` | — |
| `era5-like/*.nc` | `era5-like/temp.nc` | `era5-like/2020/temp.nc` |
| `era5-like/**` | everything under `era5-like/` | files elsewhere |

`*` matches within one path segment; `**` matches any number of segments,
including zero. Plain `fnmatch` would let `*.tif` match `sub/dir/x.tif`, which
quietly pulls in far more than the file asked for.

Omitting `files` (or writing `["**"]`) takes the whole dataset.

!!! note "The same rule applies on the writing side"
    A dataset's `ethos:include` / `ethos:exclude` in `dataset.yaml` uses this
    identical matcher. A pattern that picks a file in one place cannot miss it
    in the other — that is why both call the same function.

## Sidecars come along automatically

Asking for `turbinePlacements.shp` also gets you `.shx`, `.dbf`, `.prj` and
`.cpg`. A shapefile without its companions is unreadable, and expecting every
collections file to spell that out invites bugs. The companion list comes from
the catalogue, which recorded it when the manifest was built.

## Composing with `extends`

```yaml
collections:
  landcover:
    title: Land-cover rasters
    include:
      - dataset: corine-land-cover
        files: ["**"]

  onshore_wind:
    title: Data for onshore wind workflows
    extends: [landcover]          # everything above, plus:
    include:
      - dataset: reskit-test-data
        files: ["gwa*-like.tif"]
```

`extends` takes a list and composes transitively. A cycle is caught and
reported with the chain that produced it, rather than recursing forever.

The result is deduplicated and sorted by resource key, so a
file selected twice appears once.

To offer all inputs needed by your package, define an aggregate collection:

```yaml
collections:
  all:
    title: All inputs used by this package
    extends: [test_suite, onshore_wind]
```

Add this definition alongside the other collections. `all` is an ordinary
name, not an instruction to include every dataset in the institute catalogue.

## Pinning a catalogue version

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ethos-data-catalog/v2026.09/datacatalog.json
```

Choose an available official release and put its tag or commit directly in the
URL path, as in the example above. Prefer a commit or a tag covered by an
immutability policy: Git tags can otherwise move. Reproducibility also requires
retaining the referenced catalogue tree and immutable data paths.

The metadata cache recognises URLs containing `main`, `master`, `HEAD`,
`latest`, `dev`, or `develop` as moving and refetches them. Other URLs are
treated as pinned and may be reused indefinitely; this heuristic does not
establish that a host cannot change their contents.

Do not append `@v2026.09` to `datacatalog.json` as a way to pin it. The legacy
suffix handling strips the suffix and does not select a Git revision. Use a
real versioned URL or a versioned local catalogue directory instead.

A relative local path is resolved **relative to the collections file**, not the
caller's working directory:

```yaml
catalog: ../ethos-data-catalog-internal/datacatalog.json
```

### Overriding it

Three ways, strongest first:

```python
ethos_data.fetch("onshore_wind", collections=path, catalog="/other/datacatalog.json")
```

```bash
ethos-data --catalog /other/datacatalog.json -c collections.yaml list
ethos-data config set-catalog /other/datacatalog.json --scope project
```

A library should expose the override under its own environment variable name —
`RESKIT_DATA_CATALOG`, say — so two ICE-2 tools in one shell can point at
different catalogues. See
[Use it from your own package](../tutorials/use-from-a-library.md).

## Check it

```bash
ethos-data -c collections.yaml list                # every collection, with sizes
ethos-data -c collections.yaml info onshore_wind   # exactly which files one selects
ethos-data -c collections.yaml plan onshore_wind   # what a fetch would download
```

`info` is the one to run after editing a pattern. A `**` where you meant `*`
shows up immediately as a file count an order of magnitude too large.

If a collection names a dataset the catalogue does not describe, `list` reports
that one as `[unresolvable]` and carries on with the rest — one withdrawn
dataset must not hide every other collection in the file from everybody else.
The likeliest cause is a collections file pinned to a catalogue newer or older
than the one it was written against.

## See also

- [File formats](../reference/schemas.md) — the complete key reference.
- [Describe a dataset](describe-a-dataset.md) — the other side of the same
  pattern grammar.
- [Propose a dataset](propose-a-dataset.md) — when an input is not accepted yet.
- [Catalogue hosting](catalogue-hosting.md) — versioned filesystem trees and
  public metadata releases.
