# Add restricted data

Describe a licensed dataset in the internal catalogue and register, or move,
its authorised installation in the restricted cache. Restricted data is never
downloaded, never uploaded and never written into the public cache; readers
use it where it lies, if their group may. You need the terms of the licence,
the custodian's agreement and a restricted cache root on the cluster computer.

## 1. Describe it {#restricted-data}

Follow [Add a dataset](add-a-dataset.md#restricted-installations)
with `ethos:access: restricted` and, unless the custodian agreed to list it
publicly, `ethos:visibility: hidden` with an embargo block. Record the actual
agreement in `ethos:restriction` and `licenses` or `ethos:license_note`. A
restricted dataset has no `ethos:remote_prefix` and is never marked
`ethos:uploaded`. Build it.

## 2. Register the installation

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json \
    link gadm-3.6 /projects/licensed/gadm36_levels_shp
```

Naming a restricted dataset puts its entry into the restricted cache; that is
how one authorised installation is recorded, by somebody who knows it is
authorised. `link --all` never does this.

## 3. Or move it into the restricted cache

If the terms allow a local copy, materialize into the restricted root instead
of linking:

```bash
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json \
    materialize gadm-3.6 --from /projects/licensed/gadm36_levels_shp --dry-run
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json \
    materialize gadm-3.6 --from /projects/licensed/gadm36_levels_shp
```

The copy is verified against the catalogue's hashes. Set the directory's group
to the licence group and remove read permission for everyone else before
announcing it.

## 4. Check

```python
import ethos_data

catalog = ethos_data.load_catalog("/shared/ethos/catalogue/current/datacatalog.json")
resources = catalog.resources("gadm-3.6")
findings = ethos_data.verify(catalog, resources, deep=True)
assert all(finding.ok for finding in findings)
```

Then, as a user outside the group, expect `ethos-data fetch gadm-3.6/<file>`
to fail with an explanation and no copy.

## 5. Release

[Release the internal catalogue](release-the-catalogue.md#internal). If the
description may appear publicly, the public catalogue lists it without
offering bytes; users outside the institute obtain their own copy under the
licence and register it as under
[Set up your machine](../data-users/set-up-your-machine.md#public-installation-users).
