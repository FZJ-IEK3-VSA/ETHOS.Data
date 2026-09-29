# Set up the shared machine

Prepare the ICE-2 cluster computer so that every cluster user reads one
catalogue and one set of caches. You need a maintainer account there, a clone
of the source catalogue repository, and agreement with the dataset custodians
on who may read restricted data. The paths below are examples; the real ones
belong on the ICE-2 wiki, not in this documentation.

## 1. Lay out the directories

```text
/shared/ethos/
  catalogue/      checkout of the internal catalogue; cluster users read its datacatalog.json
  public/         public cache: links and copies of public and internal data
  restricted/     restricted cache: licensed data, one group per dataset
  validation/     re-downloads for provenance checks; maintainers only
```

| Directory | Readable by | Writable by |
| --- | --- | --- |
| `catalogue` | every cluster user | maintainers only |
| `public` | every cluster user | maintainers, plus users if downloads may land here |
| `restricted/<dataset>` | the group licensed for that dataset | maintainers |
| `validation` | maintainers | maintainers |

The caches hold datasets the institute is not permitted to pass on. Keep
them out of any directory that is synchronised elsewhere, and say so where the
paths are published. There is one catalogue on the machine, the internal one
at its latest release; no older versions are kept, and the public catalogue
is not served from the cluster computer at all once the CI publishes it (a
maintainer's checkout of it may exist as the `publish` target until then).
Staging roots are personal, set by each developer in their own
configuration, never shared.

If users may download into the shared public cache, make it group-writable
with the setgid bit so new directories inherit the group. If they may not,
users download into their own public cache and read the shared one through
per-dataset links or a second cache root of their own. Decide this before
publishing the path.

## 2. Serve the catalogue

```bash
git clone <source catalogue repository> /shared/ethos/catalogue
cd /shared/ethos/catalogue
ethos-data catalog build --check
```

Cluster users point at `/shared/ethos/catalogue/datacatalog.json`. Updating
the checkout is part of [releasing the catalogue](release-the-catalogue.md#internal);
do it only when no jobs read it, and never rebuild in place while they do.

## 3. Fill the public cache

Data that already lies on the cluster computer is linked into the public
cache rather than copied:

```bash
ethos-data link --all --catalog-root /shared/ethos/catalogue --root /shared/ethos/public --dry-run
ethos-data link --all --catalog-root /shared/ethos/catalogue --root /shared/ethos/public
```

Read the preview first. Restricted datasets and datasets with unresolved
licensing are left out on purpose. See
[Link existing data into the cache](link-existing-data.md).

## 4. Register restricted data

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json link gadm-3.6 /projects/licensed/gadm36_levels_shp
```

One dataset at a time, by name; see [Add restricted data](add-restricted-data.md).
Set the group of each entry to the licence group before announcing it.

## 5. Tell users how to configure their accounts

There is no machine-wide configuration: every user sets the three locations
for their own account. Put the commands on the ICE-2 wiki, with the real
paths:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/datacatalog.json
ethos-data config set-public-cache /shared/ethos/public
ethos-data config set-restricted-cache /shared/ethos/restricted
```

They are explained under [Set up your machine](../data-users/set-up-your-machine.md#cluster-users).

## 6. Check as an ordinary user

From a second account, or your own with the maintainer settings removed:

```bash
ethos-data config show
ethos-data ls
ethos-data fetch <small public key>
<your-tool>-data verify test_suite --deep
```

Expect the served catalogue, the shared caches, a path inside the public cache
and every file `ok`.

## 7. Record it on the ICE-2 wiki

Write down the catalogue path, the two cache roots, the validation folder,
the groups that guard restricted datasets, the source repository, and who to
contact. This documentation deliberately holds none of these.
