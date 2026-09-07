# Use data already on disk

Some data should never be downloaded: it is already on the cluster, or it is
licensed and may not be copied, or it is catalogued but not yet uploaded. In
every case `ice2-data` can read it **where it lies** — nothing is copied, and
nothing is written into the cache.

There are two mechanisms, and picking the right one matters.

| | Mechanism | Set by | Scope |
|---|---|---|---|
| **Preferred** | a symbolic link in the public cache | a maintainer, once | everybody using that cache |
| **Escape hatch** | `config set-root <dataset> <path>` | you | your machine |

## The rule

A dataset's entry in the public cache is read **in place** when it is a
symbolic link, and is an ordinary download target when it is a real directory.
That one rule replaces a per-dataset configuration table.

```
ice2_data_cache_public/
|-- global-wind-atlas  -> /fast/central/shared_data/Global_Wind_Atlas/GWA_4.0
|-- corine-land-cover  -> /fast/central/shared_data/2023_gears/.../clc2018
`-- submarine-cables/     (a real directory, downloaded from dCache)
```

The information is already on disk, so nobody has to write it down — and
re-pointing one link migrates every user on the machine at once. Downloads
never write through a link: `fetch` refuses outright rather than putting bytes
into shared project storage the cache only borrows.

## The escape hatch: one dataset, one directory

For a private copy, or a dataset the shared cache does not carry:

```bash
ice2-data config set-root submarine-cables /benchtop/shared_data/SubmarineCables
```

Those files are then read where they lie. `--scope project` / `--scope site`
work here too, and roots from different scopes **combine** — an admin's
site-wide roots and your own do not clobber each other.

```bash
ice2-data config unset-root submarine-cables      # back to downloading
```

Confirm it took:

```bash
ice2-data config show     # lists each under "datasets read from a local root"
ice2-data plan <collection>   # should report "to download: 0 files"
```

!!! note "This is the most specific thing anybody can say"
    A configured root wins over everything — the staging root, the restricted
    cache, and the public cache alike. That is what makes it a reliable escape
    hatch, and also why it is worth `unset`-ting once the reason for it is gone.

## Data that is catalogued but not yet uploaded

Exactly the same mechanism, used as a bridge:

```bash
ice2-data config set-root landcover        /projects2/2026-j-belina-ResKit-Update/landcover
ice2-data config set-root reskit-test-data /projects2/2026-j-belina-ResKit-Update/reskit_test_data
```

Once the dataset is actually uploaded, `ice2-data config unset-root <dataset>`
switches it back to downloading. Nothing else changes — not the collections
file, not the calling code, not the checksums.

## Licensed data

Restricted datasets are a separate root, not a per-dataset root, because there
is usually more than one of them and they share a single answer:

```bash
ice2-data config set-restricted-cache /path/to/ice2_data_restricted --scope environment
```

They are *always* read in place, never downloaded, never written to. See
[Work with restricted data](restricted-data.md).

## The maintainer side: `link-cache`

Rather than have every user configure roots by hand, a maintainer builds the
whole public cache as a directory of links, from the catalogue:

```bash
ice2-data catalog link-cache --root /projects5/ice2_data_cache_public --dry-run
ice2-data catalog link-cache --root /projects5/ice2_data_cache_public
```

Every dataset whose `dataset.yaml` has a `source_dir` on this machine gets an
entry pointing at it. Nothing is copied or moved — the entries cost a few
hundred bytes in total. What they buy is a **stable name** per dataset, so when
the storage behind one is reorganised, exactly one link changes and every user
follows.

`--prune` also removes links for datasets no longer in the catalogue.

!!! warning "Real directories are never touched"
    An entry that was downloaded from dCache, or produced by `ice2-data
    materialize`, is data the cache owns. `link-cache` will not replace it with
    a link, because that would silently discard it.

This is maintainer-side on purpose: `source_dir` is a statement about one
machine and is never published, so the namespace is built once by somebody who
knows where things are, and everybody else just points `public_cache` at the
result. That is what keeps the user-facing configuration down to two settings.

## Going the other way

If you are relying on a link and the storage behind it is about to be
reorganised, deleted, or unmounted, turn it into a real copy:

```bash
ice2-data materialize global-wind-atlas --dry-run
ice2-data materialize global-wind-atlas
```

See [Check and repair the cache](verify-and-repair.md#materialize-turning-a-borrowed-dataset-into-one-you-own).

## See also

- [Caches, classes and roots](../explanation/caches-and-access.md) — the full
  resolution order, and why it is shaped this way.
- [Point the cache somewhere](configure-the-cache.md).
