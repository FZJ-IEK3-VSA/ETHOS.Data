# Caches, classes and roots

Where a dataset's bytes come from is decided by two facts, both of which are
already recorded somewhere without anybody having to write them down.

## Three access classes

Declared per dataset in the catalogue:

| Class | Means | Comes from |
|---|---|---|
| `public` | on dCache with `o+rx` | anyone downloads it |
| `internal` | held by ICE-2, not published (yet) | VO credentials, or a local root |
| `restricted` | licensed; requires an authorised local installation | resolved in place, never downloaded |

## Three cache roots

| Root | Holds | Default |
|---|---|---|
| **public** | public and internal data — links to data already on this machine, plus real directories for anything downloaded | the per-user OS cache directory |
| **restricted** | licensed data or administrator-managed links to its installation; retrieval only reads it in place | **none** |
| **staging** | optional: work in progress that is not catalogued yet, shadowing the catalogue during development | **none** |

Two of those have no built-in default on purpose. Where licensed bytes land is
a decision somebody has to make out loud, and staging is opt-in by nature. The
public root has one that works on Linux, macOS and Windows alike, which is why
nothing has to be configured for public data.

## The rule: class picks the root, filesystem picks the mode

**Which root** a dataset comes from follows from its access class. **Whether it
is read in place** follows from whether its entry in that root is a symbolic
link:

```
/shared/ethos/public/
|-- global-wind-atlas  -> /fast/central/shared_data/Global_Wind_Atlas/GWA_4.0     (in place)
|-- corine-land-cover  -> /fast/central/shared_data/2023_gears/.../clc2018        (in place)
`-- submarine-cables/                                                             (downloaded)
```

That one rule replaces a per-dataset configuration table — and on a cache shared
by a whole institute, that matters twice over. The information is *already on
disk*, so nobody has to write it down and nothing can get out of step with
reality. And re-pointing a single link migrates every user on the machine at
once.

This is why the user-facing configuration is two settings rather than
thirty. `dataset_roots` survives as a per-dataset escape hatch for somebody
working offline from a private copy; normal users never touch it.

## Resolution order

For one dataset, first match wins:

<figure markdown="span">
  ![How one resource is resolved: configured root, staging, restricted cache, then the public cache](../assets/diagrams/resolution-order-light.svg#only-light){ .diagram }
  ![How one resource is resolved: configured root, staging, restricted cache, then the public cache](../assets/diagrams/resolution-order-dark.svg#only-dark){ .diagram }
</figure>

1. **`dataset_roots`** — the per-dataset escape hatch. It wins over everything,
   including staging, because it is the most specific thing anybody can have
   said.
2. **The staging root** — work in progress, shadowing the catalogue during
   development. Never applies to restricted data.
3. **The restricted root**, for restricted datasets: always in place, never
   downloaded, never written to.
4. **The public root**, for everything else: in place if the entry is a symbolic
   link, downloaded otherwise.

!!! warning "Gap: the lookup chain has eight places, and the cluster's shared cache is read-only"
    The target reads every file through one lookup chain of eight places:
    dataset roots, staging, bundles, the restricted cache, the shared cache, a
    link in the public cache, a copy in it, and a download
    ([decision 0012](architecture/decisions/0012-one-lookup-chain.md),
    [the lookup chain](architecture/runtime.md#the-lookup-chain)). On the
    cluster, the cache the institute shares is a read-only shared cache that
    catalogue maintainers fill; each user's public cache is personal and takes
    their downloads ([decision 0028](architecture/decisions/0028-read-only-shared-cache.md)).
    The figure and the list above show the four places the code reads.

## The rule that does not bend

Retrieval never writes restricted data into the public cache and never
downloads it. If there is nowhere to read it from, asking for it **fails with an
explanation** rather than doing something surprising.

Having no restricted cache is a legitimate, permanent state — most people, most
of the time, are not on the institute cluster and have no right to the licensed
bytes. But a workflow cannot produce its result without one of its inputs, so
there is no optional dataset: the refusal is an error. What the person who
meets it needs is what the dataset is and how to get it, so the error describes
it from its catalogue entry — title and description, homepage and sources,
licences and attribution, why it is restricted and how an entitled user obtains
a copy — and closes with the commands that register a copy once they have one.

!!! warning "Gap: unreachable datasets can still be left out"
    The current release offers `--skip-unavailable`, which leaves an
    unreachable dataset's key out of the result with a warning, and its
    error prints only the `ethos:restriction` note. See [every input is
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
| a dataset the whole machine already has | a namespace link, built by a maintainer with `ethos-data link --all` |
| one dataset whose files are already here | `ethos-data link <dataset> <directory>` |
| a private copy, or one dataset in an odd place | `ethos-data config set-root` |
| licensed data you have access to | `ethos-data config set-restricted-cache` |
| licensed data you do not have | a copy obtained under its terms, as the error describes, then `ethos-data link <dataset> <directory>` |
| data that is not catalogued yet | the [staging root](../how-to/package-maintainers/stage-development-data.md#stage-development-data) |
| a link that is about to break | `ethos-data materialize` |

## Copy ownership and frozen inventories

A link borrows a directory: moving or editing its target changes what every
reader sees. A materialized entry owns a separate copy. Materialization copies
only catalogued resources, checks their size and hash, and records the source in
`.ethos-data-materialized.json`. It is not a backup of unrelated project files.
It also does not reproduce ownership or ACLs; destination permissions determine
who can read the new copy.

The original and copy can coexist. While `source_dir` remains the build input,
a rebuild reflects changes to that original and the independent cache may then
fail verification. `materialize --force` does not overwrite a real directory;
changed data needs a deliberate version/migration decision.

If the original is retired, a verified local installation can retain its
inventory using `ethos:frozen: true` without `source_dir`. Uploaded data uses
`ethos:uploaded: true` instead. Both preserve recorded resource hashes while
allowing metadata to be regenerated. Rehashing the cache itself would erase the
independent baseline needed to detect corruption. Frozen metadata does not back
up bytes; the storage owner still needs retention and recovery arrangements.

Size checks detect some damage cheaply but miss changes of equal length. A deep
verification reads every byte and compares SHA-256. In-place reads do not
automatically perform that check. See [Check and repair](../how-to/data-users/verify-and-repair.md).

## See also

- [Link existing data into the cache](../how-to/catalogue-maintainers/link-existing-data.md) — overrides, cache links and materialized copies.
- [Work with restricted data](../how-to/data-users/set-up-your-machine.md#public-installation-users).
- [Configuration reference](../reference/configuration.md).
