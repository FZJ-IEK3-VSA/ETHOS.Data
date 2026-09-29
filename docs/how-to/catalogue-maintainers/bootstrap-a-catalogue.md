# Bootstrap a catalogue

Create a source catalogue repository, its independent generated public
repository and the publication root on dCache. You need ETHOS.Data and Git;
the storage steps need [dCache access](set-up-dcache-access.md). The paths and
the catalogue name below are examples.

## 1. Create two independent repositories

```bash
mkdir source-catalogue
cd source-catalogue
git init
mkdir datasets
git init ../public-catalogue
```

Start the public repository with its own empty history. Never clone the
source repository to create it: generated public files cannot remove private
history, and every `source_dir` and embargo note would stay one `git log`
away.

Create `catalog.yaml`:

```yaml
name: my-catalogue
title: Shared inputs for our workflows
ethos:catalog_role: source
ethos:publication_url: https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ethos-data
ethos:contact: Catalogue maintenance team
```

Use your actual publication URL and contact. Build the empty index:

```bash
ethos-data catalog build
ethos-data catalog build --check
```

Expect `datacatalog.json` and a passing staleness check.

## 2. Prepare the publication root

For a new virtual organisation, probe the permissions first:

```bash
ethos-data catalog check-store FZJ-ICE2
```

The probe creates and removes temporary remote objects. Resolve reported
failures with the storage administrator.

For a root dedicated to **public data**, create it and make it world-readable
before the first upload:

```bash
rclone mkdir HIFIS:ethos-data
curl --fail-with-body -H "Authorization: Bearer $(oidc-token HIFIS)" \
  -H "Content-Type: application/json" -X POST \
  "https://hifis-storage-web.desy.de/api/v1/namespace/Helmholtz/FZJ-ICE2/ethos-data" \
  -d '{"action":"chmod","mode":493}'
curl -s -o /dev/null -w '%{http_code}\n' \
  https://hifis-storage.desy.de/Helmholtz/FZJ-ICE2/ethos-data/
```

The last request carries no credentials; expect `200`. Never make a mixed or
private root public. Keep the namespace, remote and root consistent with
`ethos:publication_url`.

## 3. Accept the first dataset

Follow [Add a dataset](add-a-dataset.md) for one small, clearly licensed
dataset. It leads through describing, uploading or linking, and recording the
authoritative copy.

## 4. Release and connect readers

Commit each repository separately. Connect the source repository to the
internal Git host and the generated repository to the public host, then
release the first internal version and the first public revision as under
[Release the catalogue](release-the-catalogue.md).

On the cluster computer, follow [Set up the shared machine](set-up-the-shared-machine.md)
so cluster users find the catalogue and the caches, and put the locations on
the ICE-2 wiki. Test a fetch and a deep verification as an ordinary user
before announcing anything.
