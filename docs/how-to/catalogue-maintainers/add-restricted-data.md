# Add restricted data

Describe restricted data in the internal catalogue and register its
authorised installation in the restricted cache of its access combination.
Restricted data is licensed data, or data the institute holds without
publishing it. It is never downloaded, never uploaded and never written into
a public cache; readers use it where it lies, if the cache admits them. You
need the terms of the licence, the custodian's agreement and, on the cluster
computer, the restricted cache of the people who may read the data, for
example `/shared/ethos/restricted/<group>/`.

## 1. Describe it {#restricted-data}

Follow [Add a dataset](add-a-dataset.md#restricted-installations)
with `ethos:access: restricted` and, unless the custodian agreed to list it
publicly, `ethos:visibility: hidden` with an embargo block. Say in
`ethos:restriction` who may obtain it and how, with `homepage` and
`ethos:contact`: a user without a copy sees them in the error. Record the
terms in `licenses` or `ethos:license_note`. A restricted dataset has no
`ethos:remote_prefix` and is never marked `ethos:uploaded`. Build it.

## 2. Register the installation

```bash
ethos-data config add-restricted-cache /shared/ethos/restricted/<group>
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json \
    --root /shared/ethos/restricted/<group> \
    link gadm-3.6 /projects/licensed/gadm36_levels_shp --catalog-root <your clone>
```

Naming a restricted dataset is how one authorised installation is
registered, by somebody who knows it is authorised; `link --all` never does
this. The entry goes into a restricted cache your account lists: the one
`--root` names, or the only one listed. With several listed and no `--root`,
or none listed, `link` refuses. `--catalog-root` records the installation in
your own clone of the source catalogue.

## 3. Or move it into the restricted cache

If the terms allow a local copy, materialize into the restricted cache instead
of linking:

```bash
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json \
    --root /shared/ethos/restricted/<group> \
    materialize gadm-3.6 --from /projects/licensed/gadm36_levels_shp --dry-run
ethos-data --catalog /shared/ethos/catalogue/datacatalog.json \
    --root /shared/ethos/restricted/<group> \
    materialize gadm-3.6 --from /projects/licensed/gadm36_levels_shp --catalog-root <your clone>
```

The copy is verified against the catalogue's hashes. It inherits the group of
the cache directory; check it with `ls -ld` before announcing it.

## 4. Check

```python
import ethos_data

catalog = ethos_data.load_catalog("/shared/ethos/catalogue/datacatalog.json")
resources = catalog.resources("gadm-3.6")
findings = ethos_data.verify(catalog, resources, deep=True)
assert all(finding.ok for finding in findings)
```

Then, as a user outside the group, expect `ethos-data fetch gadm-3.6/<file>`
to be refused before anything is downloaded, with an error that names the
dataset and how to obtain it.

## 5. Release

[Release the internal catalogue](release-the-catalogue.md#internal). If the
description may appear publicly, the public catalogue lists it without
offering bytes; users outside the institute obtain their own copy under the
licence and register it as under
[Set up your machine](../data-users/set-up-your-machine.md#public-installation-users).
