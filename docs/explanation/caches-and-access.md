# Caches, classes and roots

Where a dataset's bytes come from is decided by two facts, both of which are
already recorded somewhere without anybody having to write them down.

## Two access classes

Declared per dataset in the catalogue:

| Class | Means | Comes from |
|---|---|---|
| `public` | published on dCache, world-readable | the public cache: in place where its entry is a link, otherwise a copy there, downloaded if missing |
| `restricted` | not published: licensed data, and data the institute holds without publishing it | a restricted cache whose file permissions admit the reader, in place; never downloaded |

Who may obtain a restricted dataset, and how, is told by its descriptor's
`ethos:restriction`, with `homepage` and `ethos:contact`.

## Three kinds of root

| Root | Holds | Default |
|---|---|---|
| **public cache** | public data — links to data already on this machine, plus real directories for copies and downloads; one per account | the per-user OS cache directory |
| **restricted caches** | restricted data, read in place; each is a directory whose file permissions admit one access combination, the people who may read the same data; any number per account, in order | **none** |
| **staging root** | optional: work in progress that is not catalogued yet, shadowing the catalogue during development; never for restricted data | **none** |

Two of those have no built-in default on purpose. Where restricted bytes are
read is a decision somebody has to make out loud, and staging is opt-in by
nature. An account that reads public data only lists no restricted cache, on
the cluster too, and every workflow that needs no restricted data runs without
one. The public cache has a default that works on Linux, macOS and Windows
alike, which is why nothing has to be configured for public data. The roots are
separate directories: `config` refuses a root that is, contains or lies inside
another.

On the cluster, every user sets the public cache to one directory on shared
storage, as the ICE-2 wiki says: the cluster's public cache. Maintainers link
project storage into it, and any user's fetch downloads a missing public file
into it, once for everyone. The cluster's restricted caches are one directory
per group, for example `/shared/ethos/restricted/<group>/`, for every member of
the institute or for one licence group; each user lists those their groups
admit.

## The rule: class picks the root, filesystem picks the mode

**Which root** a dataset comes from follows from its access class; for
restricted data, it is the first listed restricted cache whose entry is
readable. **Whether it is read in place** follows from whether its entry in
that root is a symbolic link:

```
/shared/ethos/cache/
|-- global-wind-atlas  -> /projects/wind/GWA_4.0          (in place)
|-- corine-land-cover  -> /projects/landcover/clc2018     (in place)
`-- submarine-cables/                                     (downloaded)
```

That one rule replaces a per-dataset configuration table — and on a cache shared
by a whole institute, that matters twice over. The information is *already on
disk*, so nobody has to write it down and nothing can get out of step with
reality. And re-pointing a single link migrates every user on the machine at
once.

This is why the user-facing configuration is two settings rather than thirty,
and why there is no per-dataset root: a copy of one dataset is linked into its
cache by name with `ethos-data link`, or copied there with
`ethos-data materialize`.

## Resolution order

Every file goes through five places, in this order. The first that finds the
file decides where it is read, and a refusal ends the call before anything is
downloaded:

<figure markdown="span">
  ![Each file goes through five locators in order (staging, bundles, restricted caches, public cache, download), and the first that finds it decides where it is read: a staged entry or a listed bundle in place, restricted data in place from the first listed restricted cache with a readable entry, the public cache through a link in place or as a file of the recorded size, and otherwise a hash-checked download into the public cache, or NotFetched under `fetch=False`. A refusal ends the call before any transfer: BundleError for a bundled file that is missing or has an unrecorded change, and AccessError for restricted data without a readable entry (naming the dataset and how to obtain and register a copy) or for a missing publication URL. A file read in place must be there, so a broken link in the public cache refuses the read (AccessError) and verify reports it; plan and verify run the same chain in describe mode, where a refusal reads not available here, with its reason.](../assets/diagrams/architecture-lookup-light.svg#only-light){ .diagram }
  ![Each file goes through five locators in order (staging, bundles, restricted caches, public cache, download), and the first that finds it decides where it is read: a staged entry or a listed bundle in place, restricted data in place from the first listed restricted cache with a readable entry, the public cache through a link in place or as a file of the recorded size, and otherwise a hash-checked download into the public cache, or NotFetched under `fetch=False`. A refusal ends the call before any transfer: BundleError for a bundled file that is missing or has an unrecorded change, and AccessError for restricted data without a readable entry (naming the dataset and how to obtain and register a copy) or for a missing publication URL. A file read in place must be there, so a broken link in the public cache refuses the read (AccessError) and verify reports it; plan and verify run the same chain in describe mode, where a refusal reads not available here, with its reason.](../assets/diagrams/architecture-lookup-dark.svg#only-dark){ .diagram }
</figure>

1. **Staging**: work in progress, shadowing the catalogue during development;
   never for restricted data.
2. **Bundles**: the bundles a package lists, read in place after a size and
   SHA-256 check. A missing file, or a change `bundle update` has not
   recorded, is an error, never a reason to download.
3. **Restricted caches**, for restricted data only: the first listed cache
   with a readable entry, in place. Without one, the call is refused.
4. **The public cache**, for public data: in place where the entry is a
   symbolic link, otherwise a copy of the recorded size.
5. **A download** into the public cache, hash-checked.

[One lookup chain](architecture/decisions/0012-one-lookup-chain.md) gives what
each place considers and when it refuses.

!!! warning "Gap: no bundles in the chain"
    The code's chain is staging, the restricted caches, the public cache and
    the download. It has no bundles in the chain.

## The rule that does not bend

Retrieval never writes restricted data into the public cache and never
downloads it. If there is nowhere to read it from, asking for it **fails with an
explanation** rather than doing something surprising.

Having no restricted cache is a normal, permanent state, on the cluster too: an
account that reads public data only lists none, and every workflow that needs no
restricted data runs without one. But a workflow cannot produce its result
without one of its inputs, so there is no optional dataset: the refusal is an
error, raised before anything is downloaded. The error names the dataset, says
how to obtain it, as far as the catalogue records that, and how to register a
copy once you have one; see
[When a restricted input is missing](../how-to/data-users/use-data-in-a-script.md#licensed-input).
`--meta` prints the dataset's full description.

!!! warning "Gap: no `--meta`"
    The code has no `--meta`, and no `report`. See [every input is
    required](architecture/decisions/0013-every-input-is-required.md).

## Downloads never write through a link

`locate` already routes a symbolic-link entry to "in place", so a download
reaching one means a bug or a race — a link created between planning and
fetching. `download` checks again anyway, because the consequence would be
writing into shared project storage that the cache only borrows.

The same reasoning runs the other way in `ethos-data link`, which refuses to
replace a real directory with a link: that directory is data the cache owns, and
replacing it would silently discard it. The refusal holds in both of that
command's modes — naming one dataset fails outright, and `--all` reports such an
entry as `keep` and carries on with the rest — because the bytes at risk are the
same bytes either way.

## Where each mechanism belongs

| Situation | Use |
|---|---|
| a public dataset the whole machine already has | a namespace link, built by a maintainer with `ethos-data link --all` |
| one dataset whose files are already here, a private copy included | `ethos-data link <dataset> <directory>` |
| the same, where no symbolic link can be made | `ethos-data materialize <dataset> --from <directory>`, a verified copy |
| restricted data you may read | `ethos-data config add-restricted-cache <directory>`, for each restricted cache your groups admit |
| restricted data you do not have | a copy obtained under its terms, as the error describes, registered with `config add-restricted-cache` and `ethos-data link <dataset> <directory>` |
| data that is not catalogued yet | the [staging root](../how-to/package-maintainers/stage-development-data.md#stage-development-data) |
| a link that is about to break | `ethos-data materialize` |

## Copy ownership and frozen inventories

A link borrows a directory: moving or editing its target changes what every
reader sees. A materialized entry owns a separate copy. Materialization copies
only catalogued resources, checks their size and hash, and records the source in
`.ethos-data-materialized.json`. It is not a backup of unrelated project files.
It also does not reproduce ownership or ACLs; destination permissions determine
who can read the new copy.

The original and the copy can coexist. While the original is the dataset's
build input, a rebuild reflects changes to it, and the independent copy may
then fail verification. Nothing overwrites a real directory in a cache; changed
data becomes a [revision or a successor](architecture/decisions/0019-revisions-and-successors.md).

Once the original is retired, `catalog record` freezes the dataset: it checks a
copy file by file, makes it the authority in the dataset's status file and
retires the build input. The recorded hashes stay, so they remain the
independent baseline that detects a corrupted copy; rehashing the copy would
erase it. A frozen inventory does not back up bytes: the storage owner still
needs retention and recovery arrangements.

!!! warning "Gap: the state is kept in `dataset.yaml`"
    The code reads the build input from `source_dir` in `dataset.yaml`, marks
    a frozen or uploaded dataset with `ethos:frozen: true` or
    `ethos:uploaded: true` there, and offers `materialize --force`. See
    [dataset status files](architecture/decisions/0022-dataset-status-files.md)
    and [the clean break](architecture/decisions/0002-clean-break-during-the-beta.md).

Size checks detect some damage cheaply but miss changes of equal length. A deep
verification reads every byte and compares SHA-256. In-place reads do not
automatically perform that check. See [Check and repair](../how-to/data-users/verify-and-repair.md).

## See also

- [Link existing data into the cache](../how-to/catalogue-maintainers/link-existing-data.md) — cache links and materialized copies.
- [Work with restricted data](../how-to/data-users/set-up-your-machine.md#public-installation-users).
- [Configuration reference](../reference/configuration.md).
