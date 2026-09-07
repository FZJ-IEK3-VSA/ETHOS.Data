# Write a collections file

A `collections.yaml` names *slices* of the shared catalogue. It contains **no
file paths, sizes, checksums or URLs** — only references. That omission is what
makes deduplication work; see
[Why one catalogue](../explanation/deduplication.md).

## The shape

```yaml
# The catalogue this file resolves against. A local path or an http(s) URL.
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ice2-data-catalog/v2026.09/datacatalog.json

collections:
  test_suite:
    title: Data required by the pytest suite
    include:
      - dataset: reskit-test-data
        files: ["**"]

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
| `title:` | a one-line description, shown by `ice2-data list`. |
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
    A dataset's `ice2:include` / `ice2:exclude` in `dataset.yaml` uses this
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

The result is deduplicated by resource key and sorted in catalogue order, so a
file selected twice appears once.

## Pinning a catalogue version

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ice2-data-catalog/v2026.09/datacatalog.json
```

**Use a tag.** A pinned URL's contents cannot change, so the catalogue is
cached on disk and reused forever; a URL containing `main`, `master`, `HEAD`,
`latest`, `dev` or `develop` is recognised as moving and re-fetched every time.
A released version of your package should resolve to the same bytes every time
somebody installs it, which is precisely what a tag buys.

A `@ref` suffix is also understood, and is stripped for a local path:

```yaml
catalog: https://.../ice2-data-catalog/datacatalog.json@v2026.09
```

A relative local path is resolved **relative to the collections file**, not the
caller's working directory:

```yaml
catalog: ../ice2-data-catalog-internal/datacatalog.json
```

### Overriding it

Three ways, strongest first:

```python
ice2_data.fetch("onshore_wind", collections=path, catalog="/other/datacatalog.json")
```

```bash
ice2-data --catalog /other/datacatalog.json -c collections.yaml list
ice2-data config set-catalog /other/datacatalog.json --scope project
```

A library should expose the override under its own environment variable name —
`RESKIT_DATA_CATALOG`, say — so two ICE-2 tools in one shell can point at
different catalogues. See
[Use it from your own package](../tutorials/use-from-a-library.md).

## Check it

```bash
ice2-data -c collections.yaml list                # every collection, with sizes
ice2-data -c collections.yaml info onshore_wind   # exactly which files one selects
ice2-data -c collections.yaml plan onshore_wind   # what a fetch would download
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
