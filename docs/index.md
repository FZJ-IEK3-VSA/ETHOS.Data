<p class="landing-logos">
  <a href="https://www.fz-juelich.de/en/ice/ice-2" class="hero-logo-link">
    <img src="https://raw.githubusercontent.com/FZJ-IEK3-VSA/README_assets/v.1.0.0/ICE2_Logos/JSA-Header.svg#only-light" alt="Jülich Systems Analysis" class="hero-logo hero-logo--jsa">
    <img src="https://raw.githubusercontent.com/FZJ-IEK3-VSA/README_assets/v.1.0.0/ICE2_Logos/JSA-Header-dark.svg#only-dark" alt="Jülich Systems Analysis" class="hero-logo hero-logo--jsa">
  </a>
</p>

# ETHOS.Data {#ethos-data}

**One shared, hash-verified data cache for every ETHOS tool and workflow on a machine.**

One institute-wide catalogue describes the input datasets — file paths, sizes,
SHA-256 checksums, original sources and licences, as
[Frictionless Data Packages](https://datapackage.org/). Each software package
declares which *slices* of those datasets it needs, in a `collections.yaml` it
ships with itself. Because every tool resolves the same catalogue into the same
cache layout, a dataset used by five tools is downloaded **once**.

```python
import ethos_data

data = ethos_data.collections("collections.yaml")
inputs = data.paths("onshore_wind", test=True)     # {"era5": Path, "gwa_100m": Path, ...}
files = data.fetch("onshore_wind")                 # {"<dataset>/<file>": Path}
placements = ethos_data.catalog().path("reskit-test-data/placements/turbine_placements.csv")
```

The direct CLI takes catalogue keys:

```bash
ethos-data ls
ethos-data fetch reskit-test-data/era5
ethos-data config show
```

Package workflows use their own API and command. With RESKit installed:

```bash
reskit-data show
reskit-data fetch onshore_wind --test --paths
reskit-data staging list
```

A package's wrapper binds collections, bundles and staging to its shipped file.
Shared configuration, direct retrieval, cache administration and catalogue
maintenance stay with `ethos-data`. See the
[command reference](reference/cli/ethos-data.md) and
[package-command reference](reference/cli/package-data.md).

## How this documentation is organized

It follows the [Diátaxis framework](https://diataxis.fr/), which splits
documentation by what you came for:

| Section | Use it to |
|---------|-----------|
| **[Tutorials](tutorials/index.md)** | Learn ETHOS.Data by working through a complete example. |
| **[How-to guides](how-to/index.md)** | Get one specific task done. |
| **[Explanation](explanation/index.md)** | Understand the cache layout, the access classes, and the decisions behind them. |
| **[Reference](reference/cli/ethos-data.md)** | Look up a command, a config key, a file format, or a function. |

Tutorials and how-to guides are grouped by three roles, and one person can hold
several of them. **Data users** fetch the inputs their ETHOS tools and workflows
need. **Package maintainers** wire data into a package and propose new
datasets. **Catalogue maintainers** accept those proposals and publish the
catalogue. Packages provide the collection workflow. The `ethos-data` CLI provides
direct access and shared administration; its `catalog` group maintains metadata
and publication.

## Who does what

<figure markdown="span">
  ![Three columns. Data user: set up the machine with a public and a restricted cache, fetch data, check data integrity. Package maintainer: ship collections and a data command, stage data through the package command, propose a dataset, keep catalogued test data in the repository, use data in CI from dCache, from the repository copy, or both. Catalogue maintainer: accept a dataset proposal as public or restricted data, upload public data, add restricted data, publish the catalogue internally and publicly, link data already on disk into the cache, copy data that was linked. The package maintainer's collections and wrapper go to the data user and their proposal goes to the catalogue maintainer. Every role reads from or writes to the shared catalogue and storage.](assets/diagrams/usecases-overview-light.svg#only-light){ .diagram }
  ![Three columns. Data user: set up the machine with a public and a restricted cache, fetch data, check data integrity. Package maintainer: ship collections and a data command, stage data through the package command, propose a dataset, keep catalogued test data in the repository, use data in CI from dCache, from the repository copy, or both. Catalogue maintainer: accept a dataset proposal as public or restricted data, upload public data, add restricted data, publish the catalogue internally and publicly, link data already on disk into the cache, copy data that was linked. The package maintainer's collections and wrapper go to the data user and their proposal goes to the catalogue maintainer. Every role reads from or writes to the shared catalogue and storage.](assets/diagrams/usecases-overview-dark.svg#only-dark){ .diagram }
  <figcaption>How ETHOS.Data is used and extended. Package maintainers extend
  it by proposing datasets; catalogue maintainers accept and publish them;
  data users receive them through the collections their package ships.</figcaption>
</figure>

Start with [machine setup](how-to/data-users/set-up-your-machine.md), or follow the
[first-fetch lesson](tutorials/first-fetch.md) with local practice data.
The [how-to overview](how-to/index.md) lists tasks by role, including
[reporting problems](how-to/data-users/troubleshoot-catalogue.md#report-a-problem),
[updating test fixtures](how-to/package-maintainers/keep-test-data-in-a-repository.md#promote-an-accepted-fix), and
[managing dCache folders](how-to/catalogue-maintainers/manage-dcache-folders.md).

## Main features

- **Deduplication that needs no synchronisation.** Every tool derives the same
  path, `<cache>/<dataset>/<resource path>`, from the same catalogue — so the
  second tool to ask for a file simply finds it already there. No symlink farm,
  no per-tool copy, nothing to keep in step. See
  [Why one catalogue](explanation/deduplication.md).
- **Almost no configuration.** The public catalogue is built in and each
  package ships its own collections. Set the cache location once, or keep the
  standard per-user cache directory — there are
  [configuration scopes](how-to/data-users/set-up-your-machine.md#cache-locations). Every dataset
  keeps the same position relative to the cache on every machine, so nothing
  else has to be configured to use the data.
- **Inputs by name, on test data or the real thing.** A package names the
  inputs its workflows take in its collections file, so
  `ethos_data.collections("collections.yaml").paths("onshore_wind", test=True)`
  hands a workflow `{name: path}` for a small test selection, and the same
  call without `test=True` the full data — the two are guaranteed to offer
  the same names. See [Get data for a task](how-to/data-users/get-data-for-a-task.md).
- **A path, not a download routine.** `ethos_data.catalog().path("<dataset>/<file>")`
  returns the absolute path of a file or folder in the cache and downloads it
  the first time — so an example script or notebook needs one line per input.
  See [Get data for a task](how-to/data-users/get-data-for-a-task.md).
- **One copy per machine, however many projects and people use it.** If you
  work on several ETHOS projects on one machine, or share a workstation or
  compute server with colleagues who also use ETHOS tools and workflows, each
  dataset needs to be there only once. Data that is already on the machine is
  read [where it lies](how-to/catalogue-maintainers/link-cluster-data.md#dataset-root-overrides), and every project
  and every user reads that same copy — nothing is downloaded again or
  duplicated into a second cache.
- **Non-redistributable data is declared, not shipped.** Proprietary or
  licensed datasets that may not be passed on are still described in the
  catalogue, with their source, their licence and a note on how to obtain
  access. A workflow therefore states exactly which of them it needs.
  Retrieval never downloads or copies such data: it reads your authorised copy
  in place, or stops and says what is missing and how to get it. See
  [Work with restricted data](how-to/data-users/set-up-your-machine.md#restricted-data).
- **Integrity is checked, not assumed.** Downloads are verified against the
  manifest by [pooch](https://www.fatiando.org/pooch/); data read in place can
  be audited and re-fetched with
  [`reskit-data verify --repair`](how-to/data-users/verify-and-repair.md).
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
| Download your first file | [Your first fetch](tutorials/first-fetch.md) |
| Get the path of an input file in a script | [Get data for a task](how-to/data-users/get-data-for-a-task.md) |
| Put the cache somewhere specific | [Configure the cache](how-to/data-users/set-up-your-machine.md#cache-locations) |
| Ship your package's data needs with the package | [Use ETHOS.Data in your package](how-to/package-maintainers/use-from-a-package.md) |
| Learn how a dataset enters the catalogue | [Add a dataset to the catalogue](tutorials/add-a-dataset.md) |
| Upload a dataset's bytes to dCache | [Upload a dataset](how-to/catalogue-maintainers/upload-a-dataset.md) |
| Understand why the cache is shaped this way | [Why one catalogue](explanation/deduplication.md) |
| Look up a command or a flag | [`ethos-data`](reference/cli/ethos-data.md) · [`ethos-data catalog`](reference/cli/catalog.md) |
| Look up a function or a class | [API Reference](reference/api/index.md) |

## About

ETHOS.Data is developed at
[ICE-2, Forschungszentrum Jülich](https://www.fz-juelich.de/en/ice/ice-2), and
is part of the input-data layer shared by the
[Energy Transformation PatHway Optimization Suite (ETHOS)](https://www.fz-juelich.de/de/ice/ice-2/leistungen/model-services)
tools — [RESKit](https://github.com/FZJ-IEK3-VSA/RESKit) is the worked example
throughout these pages. Contributions, questions and issues are welcome on
[GitHub](https://github.com/FZJ-IEK3-VSA/ETHOS.Data); see
[Contributing](contributing.md).

See [Architecture — how data access and catalogue maintenance fit together](explanation/architecture/index.md) for the system-level explanation.
