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

## The rule that does not bend

Retrieval never writes restricted data into the public cache and never
downloads it. If there is nowhere to read it from, asking for it **fails with an
explanation** rather than doing something surprising.

Having no restricted cache is a legitimate, permanent state — most people, most
of the time, are not on the institute cluster and have no right to the licensed
bytes. That is not a misconfiguration to be corrected, so the refusal offers a
choice rather than reporting an error only: configure the cache, or set
`--skip-unavailable` and have unreachable datasets left out of the result and
listed.

The listing matters. When a dataset is skipped, its key is simply **absent**
from the returned mapping — because a missing key is something a caller can
notice, whereas a `Path` to a file that is not there is not.

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

"Data the cache owns" is a question with an answer on disk, and it is the same
answer in both halves of the cache: **does this directory hold a file of its
own, at any depth?** Nothing under a symbolic link counts, because those bytes
are borrowed. A directory that holds no file is not a downloaded dataset and
never was; it is a namespace prefix this tool made itself, the shape left behind
when the family under a name is withdrawn. Calling that `keep` was the mistake
worth naming: the run reported "a real directory the cache owns", exited `0`, and
the dataset the catalogue declares at that name had no entry on any rerun.
`link --all` now reports it `obstructed`, and `--prune` clears it with `rmdir`
and links the dataset there under the verb `replace`. A directory that cannot be
listed counts as owned, because "I could not look" and "there is nothing here"
are the same answer only to a command that deletes on the strength of it.

## Writing *below* a link is still writing through it

There is a third way through a link, and it is the one that does not look like
writing at all: creating an entry underneath one. If `<cache>/family` is a link
and the catalogue describes `family/member`, then making the entry's parent
directory succeeds — the "already exists" error is swallowed and the check that
it is a directory follows the link — so `<cache>/family/member` is created
*inside* the borrowed tree and reported as made. That is the one thing a borrowed
entry promises cannot happen. It is also fragile in a way nothing reports: the
entry disappears the day its owner removes that one link, having been printed as
linked and counted in a summary.

The shape is not exotic. It is the reorganisation the namespace planner exists
for: a dataset that was flat becomes a family, `family` stops being an entry and
becomes a prefix, and the machine still holds yesterday's
`<cache>/family -> /project/storage/family`. Both link modes refuse it — naming
the dataset fails, `--all` reports the entry as `blocked` and carries on — and
`--prune` will not remove `<cache>/family` either, because the catalogue does
still describe something under that name.

The refusal names the *link*, not the entry, because removing the link is the
move that is certainly the cache's to make: nothing under it belongs to the
cache, so removing it discards nothing. Deleting whatever sits at
`<cache>/family/member` might instead delete the other project's own entry. Only
a symbolic link is found this way; a junction is reported as an ordinary
directory here exactly as it is everywhere else, so the guarantee is "no symbolic
link above the entry", not "no borrowed tree at all".

## Where each mechanism belongs

| Situation | Use |
|---|---|
| a dataset the whole machine already has | a namespace link, built by a maintainer with `ethos-data link --all` |
| one dataset whose files are already here | `ethos-data link <dataset> <directory>` |
| a private copy, or one dataset in an odd place | `ethos-data config set-root` |
| licensed data you have access to | `ethos-data config set-restricted-cache` |
| licensed data you do not have | `--skip-unavailable` |
| data that is not catalogued yet | the [staging root](../how-to/propose-a-dataset.md#stage-development-data) |
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
automatically perform that check. See [Check and repair](../how-to/verify-and-repair.md).

## See also

- [Manage local dataset copies](../how-to/link-cluster-data.md) — overrides, cache links and materialized copies.
- [Work with restricted data](../how-to/set-up-your-machine.md#restricted-data).
- [Configuration reference](../reference/configuration.md).
