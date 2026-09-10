<p class="landing-logos">
  <span class="hero-product-logo">
    <img src="assets/branding/ethos-data-logo-light.svg#only-light" alt="ETHOS.DATA" class="hero-logo hero-logo--ethos-data">
    <img src="assets/branding/ethos-data-logo-dark.svg#only-dark" alt="ETHOS.DATA" class="hero-logo hero-logo--ethos-data">
  </span>
  <a href="https://www.fz-juelich.de/en/ice/ice-2" class="hero-logo-link">
    <img src="https://raw.githubusercontent.com/FZJ-IEK3-VSA/README_assets/v.1.0.0/ICE2_Logos/JSA-Header.svg#only-light" alt="Jülich Systems Analysis" class="hero-logo hero-logo--jsa">
    <img src="https://raw.githubusercontent.com/FZJ-IEK3-VSA/README_assets/v.1.0.0/ICE2_Logos/JSA-Header-dark.svg#only-dark" alt="Jülich Systems Analysis" class="hero-logo hero-logo--jsa">
  </a>
</p>

# ETHOS.DATA {#ethos-data}

**One shared, hash-verified data cache for every ICE-2 tool on a machine.**

ETHOS.DATA is the new project name. For now, installation uses `ethos-data`,
Python imports use `ethos_data`, and the command is `ethos-data`.

One institute-wide catalogue describes the input datasets — file paths, sizes,
SHA-256 checksums, original sources and licences, as
[Frictionless Data Packages](https://datapackage.org/). Each software project
declares only which *slices* of those datasets it needs, in its own
`collections.yaml`. Because every tool resolves the same catalogue into the
same cache layout, a dataset used by five tools is downloaded **once**.

```python
from ethos_data import fetch

paths = fetch("onshore_wind", collections="collections.yaml")
```

```bash
ethos-data list                  # what collections exist
ethos-data info onshore_wind     # which files are in one
ethos-data plan onshore_wind     # what a fetch would download, without downloading
ethos-data fetch onshore_wind    # do it
```

## How this documentation is organized

It follows the [Diátaxis framework](https://diataxis.fr/), which splits
documentation by what you came for:

| Section | Use it to |
|---------|-----------|
| **[Tutorials](tutorials/index.md)** | Learn ethos-data by working through a complete example. |
| **[How-to guides](how-to/index.md)** | Get one specific task done. |
| **[Explanation](explanation/index.md)** | Understand the cache layout, the access classes, and the decisions behind them. |
| **[Reference](reference/cli/ethos-data.md)** | Look up a command, a config key, a file format, or a function. |

There are two audiences, and every section is split the same way: people who
**use** data, and people who **maintain the catalogue** it comes from. The
`ethos-data` command is the reading half; `ethos-data catalog`, installed alongside
it, is the writing half.

## Main features

- **Deduplication that needs no synchronisation.** Every tool derives the same
  path, `<cache>/<dataset>/<resource path>`, from the same catalogue — so the
  second tool to ask for a file simply finds it already there. No symlink farm,
  no per-tool copy, nothing to keep in step. See
  [Why one catalogue](explanation/deduplication.md).
- **Nothing to configure for public data.** The cache defaults to your OS's
  per-user cache directory on Linux, macOS and Windows alike;
  [six layers of configuration](how-to/configure-the-cache.md) exist for when
  you want it somewhere specific, and `ethos-data config show` always says which
  one won and why.
- **Data already on the machine is read where it lies.** A cluster share, a
  licensed dataset that may never be copied, or a dataset not yet uploaded, all
  resolve [in place](how-to/use-data-already-on-disk.md) — nothing is
  duplicated into a shared cache.
- **Integrity is checked, not assumed.** Downloads are verified against the
  manifest by [pooch](https://www.fatiando.org/pooch/); data read in place can
  be audited and re-fetched with
  [`ethos-data verify --repair`](how-to/verify-and-repair.md).
- **Large datasets stay cheap to query.** A catalogue is loaded lazily and a
  big inventory is [sharded](explanation/catalogue-format.md#sharding), so
  selecting one ERA5 tile parses that tile's 664 resources rather than all
  170,000.
- **Licensing is a question, not a default.** A dataset whose redistribution
  terms nobody has confirmed carries `ethos:license_status: unresolved`, and
  every download of it warns until somebody answers. See
  [Licensing and immutability](explanation/licensing.md).

## Where to start

| If you want to… | Go to |
|------------------|-------|
| Install the package | [Installation](installation.md) |
| Download your first collection | [Your first fetch](tutorials/first-fetch.md) |
| Put the cache somewhere specific | [Point the cache somewhere](how-to/configure-the-cache.md) |
| Wire your own Python package up to the catalogue | [Use it from your own package](tutorials/use-from-a-library.md) |
| Add a dataset to the catalogue | [Add a dataset](tutorials/add-a-dataset.md) |
| Upload a dataset's bytes to dCache | [Upload a dataset](how-to/upload-a-dataset.md) |
| Understand why the cache is shaped this way | [Why one catalogue](explanation/deduplication.md) |
| Look up a command or a flag | [`ethos-data`](reference/cli/ethos-data.md) · [`ethos-data catalog`](reference/cli/catalog.md) |
| Look up a function or a class | [API Reference](reference/api/index.md) |

## About

ethos-data is developed at
[ICE-2, Forschungszentrum Jülich](https://www.fz-juelich.de/en/ice/ice-2), and
is part of the input-data layer shared by the
[Energy Transformation PatHway Optimization Suite (ETHOS)](https://www.fz-juelich.de/de/ice/ice-2/leistungen/model-services)
tools — [RESKit](https://github.com/FZJ-IEK3-VSA/RESKit) is the worked example
throughout these pages. Contributions, questions and issues are welcome on
[jugit](https://jugit.fz-juelich.de/iek-3/shared-code/ethos-data); see
[Contributing](contributing.md).

See [Architecture — how data access and catalogue maintenance fit together](explanation/architecture/index.md) for the system-level explanation.
