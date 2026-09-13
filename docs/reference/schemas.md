# File formats

Four files matter. Two are hand-written, two are generated and must never be
edited by hand.

| File | Written by | Lives in |
|---|---|---|
| [`collections.yaml`](#collectionsyaml) | you, in your tool | the consuming package |
| [`dataset.yaml`](#datasetyaml) | a maintainer | `datasets/<name>/` in the source catalogue |
| [`catalog.yaml`](#catalogyaml) | a maintainer, once | the catalogue root |
| [`datapackage.json` / `datacatalog.json`](#generated-descriptors) | `ethos-data catalog build` | generated |

Institute-specific keys use the `ethos:` prefix — the
[Data Package](https://datapackage.org/) standard's extension mechanism.

---

## `collections.yaml`

Lives in the consuming package. Names *slices* of the catalogue, and contains
no file paths, sizes, checksums or URLs.

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/v2026.09/datacatalog.json

collections:
  onshore_wind:
    title: Data for onshore wind workflows
    extends: [landcover]
    include:
      - dataset: reskit-test-data
        files:
          - "era5-like/100m_*_component_of_wind.nc"
          - "turbinePlacements.shp"
```

| Key | Type | |
|---|---|---|
| `catalog` | string | local path or `http(s)` URL to a `datacatalog.json`. A relative path is resolved against **this file**. An `@ref` suffix pins a version (a git tag; stripped for local paths). Required unless the caller supplies one. |
| `collections` | mapping | collection name → definition |
| `collections.<name>.title` | string | one line, shown by `ethos-data list` |
| `collections.<name>.include` | list | `{dataset, files}` entries |
| `collections.<name>.include[].dataset` | string | a dataset name in the catalogue |
| `collections.<name>.include[].files` | list of globs | omit, or use `["**"]`, for everything |
| `collections.<name>.extends` | list of names | other collections in this file, composed transitively; a cycle is reported with its chain |

Glob semantics: `*` matches within one path segment, `**` matches any number of
segments including zero. Shapefile companions are added automatically.

See [Write a collections file](../how-to/write-a-collections-file.md).

---

## `dataset.yaml`

One per dataset, in the **source** catalogue only. Hand-written.

Only three things are mandatory. This builds:

```yaml
name: my-dataset
source_dir: /benchtop/shared_data/MyDataset
licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
```

`licenses` is not enforced by the build — a dataset without one still builds, and
is marked `license_status: unknown` for somebody to come back to. It is in the
minimum anyway because a mirror whose terms nobody has read is not finished.

Everything else is optional, defaulted, or required only in a specific
situation. The full set, annotated:

```yaml
#  required      the build fails without it
#  default: x    omit it and you get x
#  if ...        required only in that case
#  repeatable    a list; add as many entries as you need
#  (unmarked)    optional

# ---- identity ----------------------------------------------------------
name: my-dataset                              # required
title: A short human-readable title
description: >-
  What this is, and what it is used for.
homepage: https://example.org/the-product
id: https://doi.org/10.5281/zenodo.1234567
version: "2.0.7"                              # the publisher's own release string

sources:                                      # repeatable
  - title: Where the data originally came from
    path: https://doi.org/10.5281/zenodo.1234567
  - title: A second source, when it had more than one
    path: https://example.org/methodology.pdf

contributors:                                 # repeatable
  - title: A Researcher                       # required within an entry
    roles: [author]                           # repeatable; see below for the vocabulary
    organization: Forschungszentrum Jülich, ICE-2
    path: https://orcid.org/0000-0000-0000-0000
    email: a.researcher@fz-juelich.de

licenses:                                     # repeatable
  - name: CC-BY-4.0                           # `name` and/or `path` -- at least one
    path: https://creativecommons.org/licenses/by/4.0/
    ethos:applies_to: ["originals/**"]         # repeatable; omit to cover every file
  - name: CC0-1.0
    path: https://creativecommons.org/publicdomain/zero/1.0/

ethos:retrieved: "2026-09-01"
ethos:contact: your-username
ethos:attribution: >-
  The statement anyone redistributing this data has to reproduce.
ethos:coverage_note: >-
  What this mirror does not hold, and why.
ethos:upstream:                                # omit while upstream still serves it
  status: withdrawn                           # available|superseded|withdrawn|on-request
  checked: "2026-09-01"
  note: >-
    What happened, what was checked, and any route that remains.

# ---- provenance --------------------------------------------------------
ethos:origin: downloaded                       # default: downloaded | derived | created
ethos:derivation: >-                           # if origin: derived
  The method, parameters and inputs, in enough detail to redo it.

# ---- where the bytes are -----------------------------------------------
source_dir: /benchtop/shared_data/MyDataset   # required
ethos:remote_prefix: my-dataset                # default: the value of `name`

# ---- classification ----------------------------------------------------
ethos:access: public                           # default: public | internal | restricted
ethos:visibility: public                       # default: public | hidden
ethos:embargo:                                 # if visibility: hidden
  until: "2027-01-01"
  reason: Under peer review until publication.
  becomes: public
ethos:license_status: resolved                 # default: derived | resolved | unresolved | unknown
ethos:license_note: >-
  Internal working note on the licence. Stripped from the published catalogue.
ethos:restriction: >-                          # if access: restricted
  Why it is restricted, and how somebody entitled to it gets a copy.

# ---- inventory control -------------------------------------------------
ethos:include:                                 # repeatable
  - "rasters/**"
ethos:exclude:                                 # repeatable
  - "**/*.tmp"
ethos:shard_depth: 1
```

Real descriptors use a fraction of this. Nothing above is filler, but a mirrored
public dataset typically needs identity, `source_dir`, `licenses` and
`ethos:attribution`, and nothing from the last three groups.

Two conventions worth naming, because they recur:

- **`repeatable` means the plain YAML list**, not an extension. `sources`,
  `contributors` and `licenses` are Frictionless lists and hold as many entries
  as the truth requires — a dataset with three sources needs no special key, and
  neither does one under two licences. Where a list needs *narrowing* rather than
  extending, that is `ethos:applies_to`, described under [Licences](#licences).
- **`default:` means the build writes the value in**, not that it is merely
  assumed. An omitted `ethos:access` becomes `public` in the generated
  `datapackage.json`, so a reader never has to know the defaulting rules.

### Identity

**`name`** — *string, required.* The dataset name, as collections files
reference it. Also the default for `ethos:remote_prefix`.

**`title`** — *string.* A short human-readable title. Shown by `ethos-data list`.

**`description`** — *string.* What it is and what it is for.

**`homepage`** — *string (URL).* Frictionless: the product's landing page, where
a human goes to read about it. Not necessarily where the bytes came from — that
is `sources`.

**`id`** — *string (URI).* Frictionless: the most persistent identifier the
product actually has. A DOI when one exists; **otherwise the canonical
catalogue-record URL**.

Plenty of products have no DOI, and inventing one is worse than having none. The
rule is: name the record that identifies **the exact release whose bytes are on
disk**. Two live examples, both of which cost real time to get right:

- `corine-land-cover` holds CLC2018 raster v20 (r00). The product homepage
  advertises a DOI — but that DOI belongs to the *successor* release 2020_20u1
  (r01), which even changed the file naming convention. Putting it in `id` would
  claim the mirror is a release it is not. The r00 EEA record has no DOI, so `id`
  is that record's URL.
- `esa-cci-landcover` has no DOI at all; CEDA's own "cite this dataset as" text
  ends in the catalogue UUID URL. `id` is that URL.

When you conclude a dataset has no DOI, **write down why** in `ethos:license_note`
— including the near-miss DOI you rejected, if there was one. Otherwise the next
person re-runs the same search and reaches the opposite answer.

**`version`** — *string, quoted.* Frictionless: **the publisher's own release
designation, verbatim.** Not a SemVer you invent, and not a date — the string the
producer prints on the product, because that is what you cite, what you quote to
their helpdesk, and what tells two deliveries apart.

Record it whenever upstream has one. It is the field that makes a workflow
reproducible *in prose as well as in bytes*: the catalogue already pins content
by SHA-256 and a `collections.yaml` pins the catalogue by git tag, so a rerun is
already exact — but neither of those tells a reader of the resulting paper which
upstream release was used, and neither survives being quoted in a methods
section.

The cost of leaving it out is not hypothetical. `corine-land-cover` mirrors
CLC2018 `V2018_20`; the successor `V2020_20u1` carries **the same 2018 data**
(verified: identical class counts over all 2.99 billion cells) but encodes pixels
as the 1–44 legend index where `V2018_20` uses the 3-digit CLC code. A workflow
that says only "CLC2018" does not say which of those it read, and swapping one
for the other silently returns a wrong class for every pixel. The `version`
string is what closes that gap.

Two rules that follow from that example:

- **Quote it as the publisher writes it.** `"V2018_20"`, not `"20"` — the bare
  number does not distinguish it from `2020_20u1`.
- **A reference year is not a version.** "CLC2018" is the year the land cover was
  mapped; `V2018_20` and `V2020_20u1` are two deliveries of it. Put the reference
  year in `title`/`description` and the delivery in `version`.

`version` is promoted into `datacatalog.json`, so a consumer can see which release
they are about to fetch without pulling an inventory. It is omitted there rather
than blanked when a dataset declares none — absent means "nobody recorded it",
not "unversioned".

### Provenance: where it came from

**`sources`** — *list of `{title, path}`.* Frictionless: where it came from, or
what it was derived from. Required when `ethos:origin` is `derived`.

**`ethos:retrieved`** — *string, an ISO date, quoted.* The date **the bytes were
fetched from upstream**. Not the date the dataset was added to the catalogue, not
the date it was uploaded to the store, and *not* the files' mtime — a bulk copy
between filesystems rewrites every mtime and is not a retrieval. Where a download
log survives, the log wins over the mtime.

Use `"unknown"` when nobody can establish it, rather than guessing a plausible
date. Two GWA vintages already do; a truthful "unknown" is worth more than a
confident fiction, and it is greppable when somebody later finds the log.

The field is documentation — nothing in the code reads it. It exists so a
consumer can tell how stale a mirror is likely to be relative to a product that
has since been revised.

**`ethos:upstream`** — *mapping `{status, checked, note}`, published.* Whether the
original source still serves **this delivery**. Omit it while upstream does — its
presence is the signal.

| `status` | meaning |
|---|---|
| `available` | still served by the publisher. Rarely worth writing; omitting the block says the same |
| `superseded` | the publisher now serves only a newer release; the one we hold is gone |
| `withdrawn` | the publisher no longer serves this data in any form |
| `on-request` | not downloadable, but the publisher will supply it if asked |
| `no-upstream` | there is no original source — the data was produced here, or is a fixture |

`checked` is the date somebody actually verified this, because it decays — a
`withdrawn` from three years ago may since have been re-published, and an
`available` may not be. `note` should say what was checked and what route
remains, so the next person can tell a real dead end from a search that gave up.

This is **published, not stripped**, unlike `ethos:license_note` and
`ethos:embargo`. Two reasons. A consumer deciding whether to depend on the mirror
needs to know they cannot simply fetch the same bytes themselves. And when
upstream is gone, **this mirror is the copy of record** — losing it is not a
recoverable accident, which is a preservation fact the public catalogue should
state rather than hide.

It is not a licence field and grants nothing. That the publisher stopped
distributing something does not change the terms it was distributed under; keep
that reasoning in `licenses` and `ethos:license_note`.

```yaml
ethos:upstream:
  status: on-request
  checked: "2026-09-07"
  note: >-
    The EEA record for this delivery carries no download link, only WMS view
    services, and is marked OBSOLETE. The CLMS pre-packaged-files API offers 27
    CORINE pre-packages and all 27 are the successor release. The remaining route
    is a request to JRC-Copernicus-Land@ec.europa.eu.
```

One consequence worth planning for rather than discovering: a dataset whose
upstream is gone **can never be re-verified against the source**, because the
reference no longer exists. Its checksums still prove the bytes have not changed
*since we ingested them*; they cannot prove we ingested them correctly. Where
that matters, say in the descriptor what independent evidence exists — a
comparison against a successor release, publisher-written statistics that still
match the pixels, whatever was actually done.

**`ethos:coverage_note`** — *string, published.* What a user would otherwise assume
is here and is not. A mirror that holds one reference year of a six-year delivery,
or the map layer but not the quality flags, needs to say so — otherwise the only
way to discover the gap is to go looking for a file and conclude upstream never
made it. State the scope positively *and* name what was left out:

```yaml
ethos:coverage_note: >-
  This mirror holds the CLC2018 reference year of the version-20 100 m raster
  delivery. It does not hold the 1990, 2000, 2006 or 2012 reference years, nor
  any of the change layers the delivery also contains.
```

**`ethos:contact`** — *string, a username or team name.* The person to ask **about
this dataset**, when the answer is not in the descriptor: where it came from, why
these files and not others, whether the licence question was really settled.

It is deliberately per-dataset rather than inherited from `catalog.yaml`, because
the useful answer is usually one person — whoever ran the download — and not the
maintainer team. Fall back to the team only when no individual owns it. Like
`ethos:retrieved`, no code reads it.



**`ethos:origin`** — *string, one of `downloaded`, `derived`, `created`; default
`downloaded`.* How this dataset came to exist.

It is declared, never inferred — the same rule as `ethos:catalog_role`. "Somebody
here made this" is a claim with licensing consequences, and deducing it from the
presence of an author would make it true by accident. `downloaded` is the default
because it is both the common case and the conservative one: claiming less about
authorship than is true is safe, claiming more is not.

**`ethos:derivation`** — *string; required when `ethos:origin` is `derived`.* The
method, parameters and inputs, in enough detail to redo it.

**`contributors`** — *list of `{title, roles, organization, path, email}`.*
Frictionless. Each entry needs a `title`; the rest are optional.

```yaml
ethos:origin: derived
ethos:derivation: >-
  The GeoTIFFs are lossless gdalwarp conversions of the netCDF beside them,
  reprojected to EPSG:3035 with nearest-neighbour resampling.

contributors:
  - title: A Researcher
    roles: [author]
    organization: Forschungszentrum Jülich, ICE-2
  - title: ETHOS.RESKit maintainers
    roles: [maintainer]
```

`roles` is a **list** — Data Package v2. A v1-style scalar `roles: author` is
rejected rather than coerced: a descriptor half-following two versions of the
spec is worse than one told which it follows. Valid roles are `author`,
`contributor`, `maintainer`, `publisher`, `wrangler`.

What the build enforces:

| `ethos:origin` | Requires |
|---|---|
| `downloaded` (default) | nothing — every dataset written before this key existed still builds |
| `created` | at least one contributor with `roles: [author]` |
| `derived` | an author, **plus** `sources` (derived from what) and `ethos:derivation` (by what method) |

### Licences

**`ethos:attribution`** — *string.* The attribution statement a redistributor must
reproduce. Kept in the published catalogue, because it binds whoever takes the
data next.

**`licenses`** — *list of `{name, path, title, ethos:applies_to}`.* A Frictionless
list, so several need no extension — only checking. Each entry needs `name` (an
[Open Definition id](http://licenses.opendefinition.org/)) or `path` (a URL); a
bare `title` reads as a licence and identifies nothing.

A bespoke licence that has no Open Definition id — a national data policy, an
agency's own terms — is written with `title` and `path` and no `name`. That is
not a workaround; it is the honest encoding, and both `corine-land-cover` and
`esa-cci-landcover` use it.

```yaml
licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
  - name: CC0-1.0
    path: https://creativecommons.org/publicdomain/zero/1.0/
```

**`ethos:applies_to`** — *list of globs.* When the files are not all under the
same terms, narrow an entry:

```yaml
licenses:
  # The upstream originals we mirror.
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
    ethos:applies_to: ["originals/**"]
  # Everything else: our conversions, and the documentation.
  - name: CC0-1.0
    path: https://creativecommons.org/publicdomain/zero/1.0/
```

Patterns use the same matcher as `ethos:include` and a collection's `files:`. A
pattern matching **nothing fails the build** — silently licensing no files is how
a dataset ends up published under terms nobody applied. If every entry is
narrowed and some files are left over, the build warns: those files would be
described by no licence at all.

**`ethos:document`** — *path, relative to the dataset directory.* An archived copy
of the licence itself, stored beside `dataset.yaml` (by convention in
`licenses/`) and carried into the published catalogue verbatim.

**`ethos:document_sha256`** — *hex digest of that file.*

```yaml
licenses:
  - title: >-
      Terms and Conditions for use of Land Cover CCI datasets
    path: https://artefacts.ceda.ac.uk/licences/specific_licences/esacci_landcover_terms_and_conditions.pdf
    ethos:document: licenses/esacci_landcover_terms_and_conditions.pdf
    ethos:document_sha256: a2b89ca5649815e1a0696b3b4220351409159328e4e4dbd4116d066bec5e8377
```

**A licence that exists only as a URL is a licence that can disappear**, and this
is not a hypothetical. The `esa-cci-landcover` delivery ships a readme naming
`http://licences.ceda.ac.uk/.../esacci_landcover_terms_and_conditions.pdf` as the
governing document; that host no longer resolves at all. The terms had moved to
`artefacts.ceda.ac.uk`, but nothing in the data said so. A consumer who could not
read the terms could not honour them.

So archive the document whenever the licence is a bespoke one — an agency policy,
a publisher's own conditions, anything that is not a well-known public licence
with a stable canonical text. Keep `path` as well: the URL stays authoritative,
and the archived copy records what it said on the day it was read. The checksum
is what lets you tell later whether upstream has quietly revised it.

Two things worth knowing:

- **Some deliveries already ship their terms**, in which case they are inventoried
  as ordinary resources and need no archiving. `esa-cci-landcover`'s
  `00README_catalogue_and_licence.txt` and `landcover`'s `license/` directory both
  travel with the data. Archive the documents those *point at*, not the pointers.
- **`ethos:document` is carried into the published catalogue** — `publish` copies
  the file next to the descriptor, and fails loudly if it is missing. It is the
  one part of the public tree that is not generated text, so the renderer handles
  bytes for it.

**`ethos:license_status`** — *string, one of `resolved`, `unresolved`, `unknown`;
derived.* A present `licenses:` block implies `resolved`; otherwise the build
takes what you wrote, defaulting to `unknown`. Set it to `unresolved` when nobody
has read the upstream terms yet. Promoted into `datacatalog.json` so that warning
about licensing costs no inventory fetch.

**`ethos:license_note`** — *string.* Internal working note on the licence — what
was checked, what is still open, which document settles it. Stripped from the
published catalogue.

How it renders — see [below](#datapackagejson).

### Where the bytes are

**`source_dir`** — *string (path), required to build.* Where the files are **on
this machine**. A relative path is resolved against the dataset directory; an
absolute one is used exactly as written, symbolic links and all, so it can name
the curated namespace rather than the physical mount. Stripped from anything
published.

**`ethos:remote_prefix`** — *string; default: the value of `name`.* Folder name on
the public store. **Must not be set** for restricted data — the build rejects it,
because restricted bytes are never uploaded.

### Classification

**`ethos:access`** — *string, one of `public`, `internal`, `restricted`; default
`public`.* Who may read the bytes; picks the cache root.

**`ethos:visibility`** — *string, one of `public`, `hidden`; default `public`.*
Whether it appears in the published catalogue.

These two are independent: a dataset can be listed publicly while its bytes stay
closed, so a public user gets a useful message instead of a mystery failure; and
it can be hidden while colleagues use it daily. The one combination the build
rejects is `access: public` with `visibility: hidden` — if the bytes are
downloadable by anyone, list the dataset.

**`ethos:embargo`** — *mapping `{until, reason, becomes}`; required when
`visibility: hidden`.* `until` may be `"unspecified"`, but only with an explicit
reason. Without this block a dataset stays hidden by accident forever. Stripped
from the published catalogue: what is being withheld, and until when, is nobody
else's business.

**`ethos:restriction`** — *string; for `access: restricted`.* Why it is
restricted, and how a user entitled to the data gets it.

This is the one field here that a user actually sees. When a restricted dataset
cannot be resolved because no restricted cache is configured, the error prints
this note between the refusal and the instructions:

```
dataset 'thewindpower-turbines' is restricted and is never downloaded.
  <ethos:restriction goes here>
No restricted cache is configured on this machine.

If you have access to the licensed copy, say where it is:
    ethos-data config set-restricted-cache ...
```

So write it for the person who just hit the wall, not for the auditor: which
licence forbids the mirror, and what they should do — buy a seat, ask a named
colleague, point at an existing copy. A note that only says "restricted" tells
them nothing they did not just learn from the line above it.

### Inventory control

**`ethos:include`** — *list of globs.* Only these files are the dataset. A pattern
matching nothing **fails the build**.

**`ethos:exclude`** — *list of globs.* Applied after `include`. A pattern matching
nothing only warns.

**`ethos:shard_depth`** — *int.* Split the inventory into `manifests/<prefix>.json`
at this directory depth. Must not be negative, and must be shallow enough that
some file is actually nested that deep.

Patterns are matched against the path relative to `source_dir`, with the same
matcher as a collection's `files:`. Two conveniences: a pattern with **no
wildcard** means that path and everything under it; a **trailing slash** means the
subtree only.

See [Describe a dataset](../how-to/describe-a-dataset.md).

---

## `catalog.yaml`

One per catalogue, at its root. Hand-written; `ethos-data catalog build` merges it
with the generated dataset list into `datacatalog.json`.

```yaml
name: ETHOS.Data-Catalogue
title: ETHOS.Data Catalogue
description: >-
  What this catalogue is, who maintains it, and what it is for.

ethos:publication_url: https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files
ethos:contact: iek-3-data
ethos:catalog_role: source
```

| Key | | |
|---|---|---|
| `name`, `title`, `description` | | catalogue identity. Both catalogues share a `name` — the public one is a subset *view* of the same catalogue |
| `ethos:publication_url` | | root of the public data store. Every resource URL is `<publication_url>/<remote_prefix>/<resource path>`. Override per machine with `ethos-data config set-publication-url` |
| `ethos:contact` | | team or username |
| `ethos:catalog_role` | `source` \| `published` | always `source` in a hand-written file — `build` defaults it and **rejects** any other value. `ethos-data catalog publish` stamps `published` into the generated copy |

---

## Generated descriptors

Never hand-edit these. `ethos-data catalog build --check` fails if any is stale.

### `datacatalog.json`

The index: `catalog.yaml`'s keys plus a `datasets` array. Each entry carries
everything that can be answered **without** loading an inventory:

| Key | |
|---|---|
| `name`, `title` | identity |
| `version` | the publisher's release string, when the dataset declares one |
| `path` | `datasets/<dir>/datapackage.json`, relative to the index |
| `ethos:access`, `ethos:visibility` | classification |
| `ethos:total_bytes`, `ethos:file_count` | size, without parsing the inventory |
| `ethos:remote_prefix` | where the bytes are |
| `ethos:license_status` | promoted so that warning about licensing is free |

Those promotions are what make laziness worth having: locating a file, or
warning about a licence, would otherwise pull the whole inventory in.

### `datapackage.json`

A Data Package descriptor per dataset. Either a `resources` array, or — for a
sharded dataset — an `ethos:shards` index.

| Key | |
|---|---|
| `resources[]` | `{name, path, bytes, hash, mediatype}` per file |
| `resources[].hash` | `"sha256:…"` — the same `alg:hash` convention pooch reads, so the value passes straight through to the downloader |
| `resources[].ethos:sidecars` | companion files that must travel with this one (shapefile `.dbf`, `.shx`, …) |
| `resources[].licenses` | present only on files a narrowed licence matched — see below |
| `licenses`, `contributors`, `sources`, `ethos:origin`, `ethos:derivation` | passed through from `dataset.yaml` unchanged |
| `ethos:total_bytes`, `ethos:file_count` | totals |
| `ethos:shard_depth`, `ethos:shards` | present **instead of** `resources` when sharded |

#### How a narrowed licence renders

Frictionless lets a *resource* carry its own `licenses`, which override the
package's. So a `dataset.yaml` with one narrowed entry and one general one:

```json
{
  "licenses": [
    { "name": "CC-BY-4.0", "ethos:applies_to": ["originals/**"] },
    { "name": "CC0-1.0" }
  ],
  "resources": [
    { "path": "originals/a.nc",  "licenses": [{ "name": "CC-BY-4.0" }] },
    { "path": "converted/a.tif" }
  ]
}
```

Two things to notice.

**Every licence stays in the package-level array**, `ethos:applies_to` and all.
A reader that only looks at the package therefore sees the complete set —
conservative, and true. Dropping the narrowed ones would leave a dataset whose
licence list omits most of its licences, and would break the `license_status`
derivation, which asks only whether `licenses` is non-empty.

**The resource-level copy drops `ethos:applies_to`.** It is a build-time
instruction about which files to attach to; on the file it was attached to, it
answers a question nobody is asking.

A resource with no `licenses` key inherits the package's — which is why the
build warns when every entry is narrowed and files are left over.

### `manifests/<prefix>.json`

One shard of a sharded inventory: a `resources` array plus `ethos:shard`,
`ethos:file_count` and `ethos:total_bytes`. Files sitting at the dataset root,
above any shard directory, land in `_root`.

Shard paths in the index are relative to the **dataset** directory, not the
catalogue root.

See [The catalogue format](../explanation/catalogue-format.md).
