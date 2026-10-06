# Set up the shared machine

Prepare the ICE-2 cluster computer so that every cluster user reads one
catalogue and one public cache, and the restricted caches their groups admit.
You need a maintainer account there, a clone of the source catalogue
repository, and agreement with the dataset custodians on who may read
restricted data. The paths below are examples; the real ones belong on the
ICE-2 wiki, not in this documentation.

## 1. Lay out the directories

```text
/shared/ethos/
  catalogue/            checkout of the internal catalogue; cluster users read its datacatalog.json
  cache/                the cluster's public cache: links, copies and downloads of public data
  restricted/<group>/   one restricted cache per access combination: every institute member, or one licence group
  validation/           re-downloads for provenance checks; maintainers only
```

| Directory | Readable by | Writable by |
| --- | --- | --- |
| `catalogue` | every cluster user | maintainers only |
| `cache` | every cluster user | every cluster user, through the institute group |
| `restricted/<group>` | the members of the group | the maintainers in the group |
| `validation` | maintainers | maintainers |

The cluster administrators set the permissions of `cache`, for example with
the setgid bit, so that everything in it belongs to the institute group. Each
restricted cache is a setgid directory of one group, and every new entry
inherits that group. Maintainers link project storage into `cache` and
materialize copies there; a fetch by any cluster user downloads a missing
public file into it, once for everyone. Sharing it is safe: a download is
hash-checked before it appears, nothing writes through a link, and
`verify --repair` never removes or replaces one
([decision 0028](../../explanation/architecture/decisions/0028-one-public-cache-on-the-cluster.md)).

The restricted caches hold data the institute may not pass on. Keep them out
of any directory that is synchronised elsewhere, and say so where the paths
are published. There is one catalogue on the machine, the internal one at its
latest release; no older versions are kept, and the public catalogue is not
served from the cluster computer at all once the CI publishes it (a
maintainer's checkout of it may exist as the `publish` target until then).
Staging roots are personal, set by each developer in their own
configuration, never shared.

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

Data that already lies on the cluster computer is linked into the cluster's
public cache rather than copied. Run this from your own clone of the source
catalogue, at the merged state of the release the cluster serves, so that the
links match what users read:

```bash
ethos-data link --all --root /shared/ethos/cache --catalog-root <your clone> --dry-run
ethos-data link --all --root /shared/ethos/cache --catalog-root <your clone>
```

Read the preview first. It links public data only: restricted datasets are
registered by name in step 4, and datasets with unresolved licensing are left
out. See [Link existing data into the cache](link-existing-data.md).

## 4. Register restricted data

```bash
ethos-data config add-restricted-cache /shared/ethos/restricted/<group>
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json \
    --root /shared/ethos/restricted/<group> \
    link gadm-3.6 /projects/licensed/gadm36_levels_shp --catalog-root <your clone>
```

One dataset at a time, by name, into the restricted cache of its access
combination; see [Add restricted data](add-restricted-data.md).

## 5. Tell users how to configure their accounts

There is no machine-wide configuration. Every user sets the catalogue and the
cluster's public cache for their own account, and adds the restricted cache
of each group they belong to; a user of public data only adds none. Put the
commands on the ICE-2 wiki, with the real paths:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/datacatalog.json
ethos-data config set-public-cache /shared/ethos/cache
ethos-data config add-restricted-cache /shared/ethos/restricted/<group>   # once per group
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

Expect `config show` to name the served catalogue, the cluster's public cache
and the restricted caches you added; `fetch` to print a path inside the
cluster's public cache; and every file `ok`.

## 7. Record it on the ICE-2 wiki

Write down the catalogue path, the cluster's public cache, every restricted
cache with the group it admits, the validation folder, the source repository,
and who to contact. This documentation deliberately holds none of these.
