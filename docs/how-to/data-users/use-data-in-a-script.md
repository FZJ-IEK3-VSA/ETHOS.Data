# Use data in a script

Get the inputs a workflow needs inside a Python script or an example, fetching
them or only resolving where they are, and see beforehand how much a fetch
downloads. You need [ETHOS.Data installed](../../installation.md) and, on the
cluster computer, a [configured machine](set-up-your-machine.md).

The examples run as written on a small, real, public selection. Download
[collections.yaml](../../assets/examples/collections.yaml) and
[data_cli.py](../../assets/examples/data_cli.py) into one directory and work
there. The file defines two collections, `offshore_siting` and `placements`,
over public test fixtures of under 200 KB, and the script is the same data
command every package ships under its own name: where this page writes
`python data_cli.py`, a package's users type `<your-tool>-data`, and where it
writes `data = ethos_data.collections("collections.yaml")`, a package's users
write `from your_tool import data`. The calls are the same.

## Get a workflow's inputs by name {#by-name}

A collection names the inputs of a workflow. Ask for the collection and pass
the handles on:

```python
import ethos_data

data = ethos_data.collections("collections.yaml")
INPUTS = data.paths("offshore_siting")

PATH_WATER_DEPTH = str(INPUTS["water_depth"])
PATH_COAST_DISTANCE = str(INPUTS["coast_distance"])
```

`paths` fetches whatever the collection selects and this machine does not have
yet, checks every file against the catalogue's checksums, and returns
`{handle: absolute path}`. Data that already lies on the machine, as a bundle
in the package, a shared cache link or a restricted installation, is returned
where it is and never copied. Call it right before the workflow; no shell
command has to run first.

## Know which catalogue and caches a script uses {#settings}

A script needs no setup code. It reads the
[settings file](set-up-your-machine.md#settings-file) of the account it runs
under, whichever folder it is started from and however ETHOS.Data was
installed. The handle reads the settings once, when the script first uses
it, so every later call in the script uses the same catalogue and caches.
Print them next to your results:

```python
print(data.settings)
```

The output names the settings file, the catalogue and its version, the
public and restricted caches, and where each value came from: an argument,
an environment variable, the settings file or a built-in default. In a
package, the same object is `your_tool.data.handle().settings`.

## See what a fetch will download {#plan}

Before fetching a collection you do not know, ask for its size and for what
is missing on this machine. Neither command downloads anything:

```bash
python data_cli.py show offshore_siting          # files, total size, named paths
python data_cli.py fetch offshore_siting --plan  # already cached, in place, to download: N files, X MB
```

The plan reports, per group, the number of files and their size, and lists
the files it would download. In Python, `data.plan("offshore_siting")` returns
the same as a dictionary, with `bytes_to_download` and the `missing`
resources. The sizes come from the catalogue, which records the bytes of every
file, so the answer costs one metadata read.

## Fetch, or only resolve the paths {#fetch-or-path}

The default fetches. When the data is known to be on the machine, or the
script must not start a download, ask for the paths alone:

```python
INPUTS = data.paths("offshore_siting", fetch=False)
```

With `fetch=False` nothing is downloaded and no storage is contacted. Every
handle resolves to the path the data has on this machine. A file that is not
there raises an error that names the file, the path where it is expected, and
says that the same call with `fetch=True` downloads it to that path. A script
therefore fails at its first line rather than half-way through a calculation.

The same choice from the shell:

```bash
python data_cli.py fetch offshore_siting --paths   # fetch, then print handle<TAB>path
python data_cli.py fetch offshore_siting --plan    # what a fetch would download; downloads nothing
```

## Run on test data or the full data {#test-variant}

Collections that serve tests and examples come in two sizes with the same
handles. The full data is the default; the small variant is opt-in:

```python
inputs = data.paths("my_workflow", test=True)
```

Because both variants offer the same handles, the workflow call does not
change when `test=True` is dropped. On the command line the flag is `--test`.
The example file defines no variants.

## When a licensed input is missing {#licensed-input}

Every input a collection names is required. A collection may name a
restricted dataset that this machine has no copy of, or one you may not read.
The call then stops before anything is downloaded, with an error that
describes the dataset from its catalogue entry:

- its title, description and version;
- where it came from: its homepage and sources;
- its licences and the attribution they require;
- why it is restricted and how somebody entitled to it obtains a copy;
- whom to ask about it.

Each item appears as far as the catalogue records it; it is the same
information as [`--meta`](#metadata) prints. The error closes with the commands
that register a copy you have, which
[Set up your machine](set-up-your-machine.md#public-installation-users)
explains. A workflow cannot run without one of its inputs, so no option leaves
one out.

!!! warning "Gap: the error does not describe the dataset, and inputs can be left out"
    The error names the dataset and prints its `ethos:restriction` note
    only. `skip_unavailable=True`, `--skip-unavailable`,
    `config set-skip-unavailable true` and `ETHOS_SKIP_UNAVAILABLE` still
    drop an unreachable handle from the mapping with a warning, and the
    error suggests them. The planned change, [every input is
    required](../../explanation/architecture/decisions.md#every-input-is-required-2026-10-02),
    is to be implemented separately.

## Try catalogue data that is not in a collection yet {#by-key}

Anything the catalogue describes can be asked for by its key,
`<dataset>/<path>`, whether or not a collection selects it. That is how a
package maintainer tries a dataset before adding it to a collection, and how
a user reaches a single file. The key is resolved in the catalogue the
collections file declares:

```python
placements = data.catalog.path("reskit-test-data/placements/module_placements.csv")   # a file: fetched if missing
boundaries = data.catalog.path("reskit-test-data/boundaries", fetch=False)           # a folder: path only
```

In a package the same two calls are `data.catalog_path(KEY)`. A collection
name and a catalogue key cannot be confused: `paths()` takes a name from the
collections file, `catalog_path()` takes a key from the catalogue. A shapefile
brings its sidecars; a folder or dataset key fetches every file under it, so
list it first:

```bash
ethos-data ls                                       # every dataset, its access class and title
ethos-data ls reskit-test-data/boundaries           # the files under a key, with sizes; no download
ethos-data fetch reskit-test-data/boundaries        # fetch and print the local path
```

`ethos-data` reads the configured catalogue, or the public one; put
`--catalog LOCATION` before the subcommand to read another.

## Print the metadata of a collection or a dataset {#metadata}

To see where data comes from, under which licence, and what attribution it
requires, print the descriptors behind a collection or one dataset:

```bash
python data_cli.py show offshore_siting --meta      # every dataset the collection selects
ethos-data ls reskit-test-data/gebco --meta         # one dataset
```

Both print title, description, origin, sources, licences, attribution, access
class and contact, without fetching anything. In Python, a dataset's
descriptor is `data.catalog.dataset("reskit-test-data/gebco").descriptor`.

!!! warning "Gap: `--meta` is not implemented"
    Neither command has the flag. The descriptor is reachable in Python only.

## Check the result

Open the returned path with the reader the workflow uses. If a path is
unexpected, `print(data.settings)` or `ethos-data config show` explains which
catalogue and caches were used. If nothing can be fetched at all, run the
[self-test](set-up-your-machine.md#check-a-download) to separate the machine
from the collection. To check files on disk against the catalogue, follow
[Check and repair the cache](verify-and-repair.md). An unknown key, an
unreadable catalogue or an unavailable input exits with an error instead of a
path; [Report a problem](report-a-problem.md) says what to collect.
