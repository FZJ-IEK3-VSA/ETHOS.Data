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

Everything else — `build`, `publish`, `link-cache` — needs only the package.
The one-time credential setup is in
[Upload a dataset](how-to/upload-a-dataset.md#credentials-once-per-machine).

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
[Point the cache somewhere](how-to/configure-the-cache.md).

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

The docs are [MkDocs](https://www.mkdocs.org/) with the
[Material](https://squidfunk.github.io/mkdocs-material/) theme and
[mkdocstrings](https://mkdocstrings.github.io/) for the API reference:

```bash
mamba install -c conda-forge mkdocs mkdocs-material mkdocstrings mkdocstrings-python
mkdocs serve        # live preview on http://localhost:8000
mkdocs build        # static site into ./site
```

`ethos-data` itself must be importable for the API reference pages to render, so
run these from an environment where the package is installed (`pip install -e .`).
