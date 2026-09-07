# Point the cache somewhere

Data goes to your OS's per-user cache directory unless told otherwise — the
same mechanism on Linux, macOS and Windows. Nothing needs configuring for
public data. This page is for when you want it somewhere specific.

```bash
ice2-data config show
```

prints the folder in use, **why** it was chosen, and every place that was
checked along the way. It answers most "why is my data going there?" questions
on its own, including naming the exact config file that decided it.

## Six ways, strongest first

The first one that applies wins:

| | How | Good for |
|---|---|---|
| 1 | `--root /path` on the command line, or `root=` in Python | one-off runs |
| 2 | the `ICE2_DATA_DIR` environment variable | CI, batch jobs, SLURM |
| 3 | a file called `ice2-data.yaml` in your project folder | a setting you want to see and commit |
| 4 | your personal setting | all your work, every project |
| 5 | a setting inside the conda environment | a shared install someone else manages |
| 6 | a machine-wide setting | a cluster, set by an admin |

Falling off the end gives you the per-user OS cache directory.

## Most people want option 3

An ordinary file, in the folder you work in, that you can open, read, edit and
commit. Run this from the folder you want it to appear in:

```bash
ice2-data config set-cache /data/my-analysis/ice2-data --scope project
```

```yaml title="ice2-data.yaml"
cache_dir: /data/my-analysis/ice2-data
```

It is found from anywhere *inside* the project — the same way `git` finds a
repository from a subfolder — and setting it again from a subfolder updates
that one file instead of creating a second.

!!! warning "'Project' means the whole subtree, not that one directory"
    A project config is found by walking **up** from the current directory. If
    you pin a setting in `~/work/`, it applies to every repository underneath
    it too, including ones with their own `collections.yaml`. That is usually
    what you want for `cache_dir` and almost never what you want for
    `collections` — see [below](#pinning-a-default-collections-file).

For a personal setting that follows you across projects, drop `--scope`:

```bash
ice2-data config set-cache /data/ice2-data
```

`ice2-data config unset-cache` goes back to the default.

## On a cluster

An admin sets the cache once, site-wide, and everybody else gets it with no
setup at all:

```bash
ice2-data config set-cache /projects2/shared/ice2-data --scope site
```

A batch job that needs node-local scratch can still override for one run with
`ICE2_DATA_DIR`, without touching anybody else's configuration.

If the cluster already holds copies of the datasets, an admin can also build
the cache as a directory of links to them — see
[`ice2-data catalog link-cache`](use-data-already-on-disk.md#the-maintainer-side-link-cache).
Users then point `public_cache` at that directory and nothing is ever
downloaded.

## The three roots

There are actually three cache roots, and you are expected to set at most two:

| Root | Holds | Default |
|---|---|---|
| **public cache** | public and internal data — links to data already here, plus real directories for anything downloaded | per-user OS cache directory |
| **restricted cache** | licensed data, never downloaded, never written to | **none**, deliberately |
| **staging cache** | work in progress that is not catalogued yet | **none**, opt-in |

```bash
ice2-data config set-public-cache     /path --scope site
ice2-data config set-restricted-cache /path --scope environment
ice2-data config set-staging-cache    /path            # only while developing
```

`set-cache` is an alias for `set-public-cache`, kept because it is in scripts,
job files and shell profiles from when there was only one root.

The two that have no default have none on purpose: where licensed bytes land is
a decision somebody has to make out loud, and staging is opt-in by nature. See
[Caches, classes and roots](../explanation/caches-and-access.md) for why the
configuration is two settings rather than one per dataset.

## Scopes

Every `config set-*` command takes `--scope`:

| Scope | File | Use for |
|---|---|---|
| `project` | `./ice2-data.yaml`, searched upward from the cwd | a setting you want visible and committable |
| `user` (default) | your per-user config directory | all your own work |
| `environment` | `<sys.prefix>/etc/ice2-data/config.yaml` | a conda env somebody else manages |
| `site` | the machine-wide config directory | a cluster, set by an admin |

Precedence runs in that order. `ice2-data config show` prints every file it
consults with an exists/not-present flag, so a setting that is being shadowed
is visible rather than mysterious.

## Pinning a default catalogue

A collections file pins its own catalogue (`catalog:` at the top of the YAML),
which is enough for most use. To work against a *different* one every time
without editing that file or exporting an environment variable in every shell —
developing against the internal catalogue instead of a published tag, say — set
it once:

```bash
ice2-data config set-catalog /path/to/ice2-data-catalog-internal/datacatalog.json --scope project
```

Same scopes and precedence as the cache directory. It takes a local path or an
`http(s)` URL, and is overridden by `--catalog` / `catalog=` for a single run.
`ice2-data config unset-catalog` removes it.

## Pinning a default collections file

To stop passing `-c` every time — while working inside a repository that will
never grow its own `collections.yaml`, for instance:

```bash
ice2-data config set-collections /path/to/probe-collections.yaml --scope project
```

!!! warning "This applies everywhere the project config is found"
    Not just in that one directory — the same walk-up rule as `cache_dir`. If
    you later run a bare `ice2-data list` somewhere that has its own real
    `collections.yaml` (RESKit's, say), you would still get the pinned one
    unless you pass `-c` explicitly. `ice2-data config unset-collections`
    removes it, and `config show` always says which file is in effect and why.

## Fetching from a different door

Public downloads go to whatever the catalogue declares. To fetch the same bytes
through DESY's high-throughput door instead — worth it for bulk transfers and
CI, not for interactive use:

```bash
ice2-data config set-publication-url https://hifis-storage-ht.desy.de:2880/Helmholtz/FZJ-ICE2/ice2-data-files
```

The catalogue does not change; only this machine's route to the bytes does.

## Reading the output

```title="ice2-data config show (abridged)"
the two settings that matter:

  public cache      /projects2/2026-j-belina-ResKit-Update/ice2-data-cache-new
                    from project config /projects2/2026-j-belina-ResKit-Update/ice2-data.yaml
  restricted cache  (not set -- licensed datasets will refuse to resolve)
                    ice2-data config set-restricted-cache /path --scope environment

precedence for each, first match wins:
  1. explicit --root / root=      (public cache only)
  2. $ICE2_DATA_DIR          (unset)   [public]
  3. project config           /projects2/2026-j-belina-ResKit-Update/ice2-data.yaml  [exists]
  4. user config              /home/you/.config/ice2-data/config.yaml  [not present]
  5. environment config       /home/you/miniforge3/envs/env/etc/ice2-data/config.yaml  [not present]
  6. site config              /etc/xdg/ice2-data/config.yaml  [not present]
  7. built-in default          per-user OS cache directory (public only)

public cache holds 0 link(s) and 2 real director(ies):
```

The last line is worth reading: **links** are datasets read in place from
elsewhere on the machine, **real directories** are data this cache downloaded
and owns. Which one a dataset is decides whether `fetch` writes to it — see
[Caches, classes and roots](../explanation/caches-and-access.md).

## See also

- [Configuration reference](../reference/configuration.md) — every key, every
  environment variable, every default.
- [Use data already on disk](use-data-already-on-disk.md).
