# Bootstrap a new catalogue

Create a source metadata repository and an independent generated public
repository. You need ETHOS.Data and Git; storage setup also needs
[dCache access](set-up-dcache-access.md). The paths and catalogue name below
are examples.

## 1. Create independent repositories

```bash
mkdir source-catalogue
cd source-catalogue
git init
mkdir datasets
git init ../public-catalogue
```

Start the public repository with its own empty history. Never clone the internal
repository to create it: generated public files cannot remove private history.

Create `catalog.yaml`:

```yaml
name: my-catalogue
title: Shared inputs for our workflows
ethos:catalog_role: source
ethos:publication_url: https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files
ethos:contact: Catalogue maintenance team
```

Use your actual publication URL and contact. Build the empty index:

```bash
ethos-data catalog build
ethos-data catalog build --check
```

Expect `datacatalog.json` and a successful staleness check.

## 2. Prepare the publication root

For a new VO, probe permissions first:

```bash
ethos-data catalog check-store FZJ-ICE2
```

The probe creates and removes temporary remote objects. Resolve reported access
failures with the storage administrator.

For a root dedicated to **public data**, create it and establish public
permissions before any upload:

```bash
rclone mkdir HIFIS:ice2-data-files
curl --fail-with-body -H "Authorization: Bearer $(oidc-token HIFIS)" \
  -H "Content-Type: application/json" -X POST \
  "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/ice2-data-files" \
  -d '{"action":"chmod","mode":493}'
curl -s -o /dev/null -w '%{http_code}\n' \
  https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ice2-data-files/
```

The last request has no credentials; expect `200`. Do not make a mixed/private
storage root public. Use the namespace, remote, and root approved for the new
catalogue, and keep them consistent with `ethos:publication_url`.

## 3. Accept the first dataset

Follow the [acceptance checklist](accept-a-dataset.md) for a small approved
dataset. It links to the canonical describe, upload/verification, and
public-generation procedures. For a local restricted/internal catalogue,
establish and verify the authorised installation instead of uploading.

## 4. Release metadata and configure readers

Review and commit each repository separately. Connect the source repository to
the private Git host and the generated repository to the public host. Deploy a
complete versioned internal tree and release the public revision using
[Catalogue hosting](catalogue-hosting.md).

Give users the actual internal `datacatalog.json`, public/restricted cache roots,
and support contact through the internal onboarding channel. Configure defaults
with [Set up your machine](../data-users/set-up-your-machine.md). Test a representative fetch
and deep verification as an ordinary reader.

Add [catalogue CI checks](catalogue-ci.md), document release ownership, and retain
versions needed by pinned workflows. Local data can be made available through
[cache links](link-cluster-data.md) without another transfer.
