# Installation

`ethos-data` is a small pure-Python package. Its only runtime dependencies are
[pooch](https://www.fatiando.org/pooch/) (hash-verified downloads), PyYAML and
[platformdirs](https://platformdirs.readthedocs.io/) (cross-platform config and
cache locations), so it installs cleanly next to whatever scientific stack you
already have. Python 3.10 or newer.

Installing it gives you one executable with a catalogue-maintenance command group:

| Command | For | Needs |
|---------|-----|-------|
| `ethos-data` | reading the catalogue: listing, planning, fetching, verifying | nothing beyond the package |
| `ethos-data catalog` | writing it: describing datasets, uploading bytes, publishing | `rclone` and `oidc-agent` on `PATH`, and only for `upload` / `check-store` |

## Install

The package is not on PyPI or conda-forge yet — install it from the repository:

```bash
pip install git+https://github.com/FZJ-IEK3-VSA/ETHOS.Data.git
```

Or, if you are declaring it as a dependency of your own package:

```toml
dependencies = [
  "ethos-data>=0.1.0",
]
```

### Optional extras

```bash
pip install "ethos-data[progress] @ git+https://github.com/FZJ-IEK3-VSA/ETHOS.Data.git"
```

Without `tqdm`, `fetch(..., progressbar=True)` still works — pooch just falls
back to silence.

## Creating an isolated environment

With conda/mamba, using the environment file in the repository:

```bash
git clone https://github.com/FZJ-IEK3-VSA/ETHOS.Data.git
cd ETHOS.Data
mamba env create -f environment.yml
mamba activate ethos_data_env
pip install -e . --no-deps
```

With `uv`:

```bash
uv venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
uv pip install -e .
```

## The maintainer tools

`ethos-data catalog upload` and `ethos-data catalog check-store` shell out to
[`rclone`](https://rclone.org/) and
[`oidc-agent`](https://indigo-dc.gitbook.io/oidc-agent/). They pull in no extra
Python dependencies, which is why there is no install extra to remember:

```bash
mamba install -c conda-forge rclone oidc-agent
```

!!! warning "On Windows: `upload` and `check-store` need WSL"

    conda-forge has no `oidc-agent` for Windows — upstream builds the CLI there
    only against the MSYS2 POSIX runtime, and recommends WSL instead — so that
    command fails on Windows and `environment.yml` does not list the package.
    Install `rclone` alone, and run those two commands from a WSL shell, where
    the Linux package works. `check-store` is a shell script and also wants a
    `bash` on `PATH`; the one Git for Windows ships will do.

Everything else in the group — `build` and `publish` — needs only the package,
and so does `ethos-data link`, which builds shared cache links from a top-level
command rather than a `catalog` subcommand: filling a cache on the machine that
already holds the data touches no remote storage, so it asks nothing of
`rclone` or `oidc-agent`.
The one-time credential setup is in
[Upload a dataset](how-to/catalogue-maintainers/upload-a-dataset.md#credentials-once-per-machine).

## Check the installation

```bash
ethos-data config show
```

This prints the cache directories in use, **why** each was chosen, and every
config file that was consulted along the way. It needs no catalogue and no
network, so it is the fastest way to confirm the install works — and the first
thing to run when data turns up somewhere unexpected.

```bash
python -c "import ethos_data; print(ethos_data.__version__)"
```

## Where data will go

Nothing more is required for public data: the cache defaults to your OS's
per-user cache directory (`~/.cache/ethos-data` on Linux). If you want it
somewhere with room — a project filesystem, a scratch volume — see
[Point the cache somewhere](how-to/data-users/set-up-your-machine.md#cache-locations).

## Development install

```bash
git clone https://github.com/FZJ-IEK3-VSA/ETHOS.Data.git
cd ETHOS.Data
pip install -e .
pytest
```

Linting uses [Ruff](https://docs.astral.sh/ruff/):

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Building this documentation

The published copy is at <https://ethos-data.readthedocs.io/>, rebuilt by
[Read the Docs](https://about.readthedocs.com/) whenever `main` changes.

The docs are [MkDocs](https://www.mkdocs.org/) with the
[Material](https://squidfunk.github.io/mkdocs-material/) theme and
[mkdocstrings](https://mkdocstrings.github.io/) for the API reference. The
toolchain is the package's `docs` extra, which is also what the hosted build
installs:

```bash
pip install -e ".[docs]"
mkdocs serve        # live preview on http://localhost:8000
mkdocs build        # static site into ./site
```

The mamba environment from `environment.yml` already carries the same tools.
`ethos-data` itself must be importable for the API reference pages to render;
the editable install above takes care of that.
