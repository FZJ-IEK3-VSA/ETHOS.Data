# Add a dataset

Put a dataset into the catalogue: review its `dataset.yaml`, which a proposer
supplied or you write yourself, copy it into the catalogue, build, make the
bytes available, release. Work in your own clone of the source catalogue,
with read access to the candidate bytes, which must not change while you work.

## 1. Get the description {#write-the-description}

A [proposal](../package-maintainers/propose-a-dataset.md) brings a draft
`dataset.yaml`, beside the data or inside a bundle's `datasets/` directory. For
a dataset you add on your own decision, write it:

```yaml
name: my-dataset
title: A short human-readable title
description: What this dataset contains and which release it describes.
source_dir: /projects/shared/candidates/my-dataset
ethos:access: public
ethos:visibility: public
ethos:origin: downloaded
ethos:remote_prefix: my-dataset-v1
sources:
  - title: Original release
    path: https://example.org/dataset-release
licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
ethos:retrieved: "2026-09-01"
ethos:attribution: The attribution text the source requires.
ethos:contact: Dataset maintainer
```

`source_dir` is the directory you can read the bytes from; a relative path is
relative to the draft. It is the draft's build input: `catalog add` moves it
into the dataset's `status.yaml` ([step 3](#add-it)). For created or derived
data, add `contributors` with an `author`, and for derived data `sources` and
`ethos:derivation`. Every key is in the
[format reference](../../reference/schemas.md#datasetyaml).

### Select the files {#select-the-files}

If the source holds unrelated files, select:

```yaml
ethos:include:
  - "rasters/**"
ethos:exclude:
  - "**/*.tmp"
```

An include pattern matching nothing fails the build; an unmatched exclude only
warns. The asymmetry is deliberate: silently describing no files is how a
dataset ends up published empty. For a large inventory set
`ethos:shard_depth`, see the [sharding explanation](../../explanation/catalogue-format.md#sharding).

### Datasets that are not ready to publish {#not-ready}

```yaml
ethos:access: restricted
ethos:visibility: hidden
ethos:restriction: >-
  Not published before the accompanying paper. Every institute member may
  read it on the cluster computer.
ethos:embargo:
  until: "2027-06-30"           # or "unspecified", with a reason
  reason: Pending publication of the accompanying paper.
  becomes: public
```

Data the institute holds without publishing it is restricted data that every
member of the institute may read. When the embargo ends,
[release it as public data](release-the-catalogue.md#embargo).

### Restricted datasets {#restricted-installations}

A licensed dataset that may not be redistributed:

```yaml
ethos:access: restricted
ethos:visibility: hidden
ethos:restriction: >-
  Licensed per user. Obtain a copy from the provider under its terms, or ask
  the dataset custodian for access to the institute's copy.
ethos:embargo:
  until: "unspecified"
  reason: Metadata publication has not been approved; review with the custodian.
  becomes: restricted
```

A restricted dataset has no `ethos:remote_prefix`: its bytes are never
uploaded. With the custodian's approval it may be listed publicly without
offering bytes.

A user whose workflow needs the dataset and who has no copy gets an error
that names the dataset and prints its `ethos:restriction`, `homepage` and
`ethos:contact`, then how to register a copy. Write them for that person:
who may obtain a copy, where, and under which terms.
`ethos-data ls <name> --meta` prints the full description.

## 2. Review it

Settle every row before the file enters the catalogue:

| Question | Settled when |
| --- | --- |
| What is it, and for which workflows | Name, version, title and purpose are agreed. A revision of existing data gets new paths, never the old ones. |
| Where does it come from | `ethos:origin` is right. Downloaded data names its source and retrieval date and [matches that source](verify-provenance.md). Created or derived data names its authors, inputs and method. |
| May it be redistributed | A `licenses:` entry, or an explicit `resolved` status, based on terms somebody read. Unclear terms stay `ethos:license_status: unresolved` with the question in `ethos:license_note`, which blocks linking and upload until answered. Attribution text is recorded where the licence requires it. |
| Who may read it | `ethos:access` and `ethos:visibility` are right, a hidden dataset has an embargo block, and a restricted dataset says in `ethos:restriction` who may obtain it and how. |
| Which files | The selection covers the files the workflows need, their sidecars, and nothing unrelated. |
| Does it work | The proposer ran the affected workflow or tests against the staged or bundled candidate. |

## 3. Add it to the catalogue {#add-it}

```bash
ethos-data catalog add /projects/shared/candidates/my-dataset --dry-run
ethos-data catalog add /projects/shared/candidates/my-dataset
ethos-data catalog build my-dataset --check
git diff -- datasets/my-dataset datacatalog.json
```

`catalog add` takes the draft, its `dataset.yaml` or the directory holding
it. It checks the draft as the build would, writes `datasets/my-dataset/`
with the description and its licence documents, and builds it. `source_dir`
goes into the dataset's [`status.yaml`](../../reference/schemas.md#statusyaml)
as an absolute path. Every later step is checked against the dataset's state
and recorded there, and `ethos-data catalog status my-dataset` shows where
the dataset stands and what it needs next.

Datasets from a package's bundle come in through
`ethos-data catalog add-bundle <bundle directory> [DATASET...]`. It takes the
bundle's datasets that are ahead of the catalogue: new datasets, revisions
(only while the catalogue is still at the bundle's alignment) and changed
descriptions. It writes one directory per dataset, a family's members below
the family's own `dataset.yaml`
(`datasets/your-tool-test-data/era5/dataset.yaml`), and copies the files into
a build input the catalogue maintainers own; see
[Keep data in the repository](../package-maintainers/keep-data-in-the-repository.md#sync). The build walks `source_dir`, hashes every
selected file and writes `datapackage.json` beside the description; never
hand-edit the generated JSON. Check the generated paths, counts, sizes and
hashes against the proposal and resolve every difference before going on,
then commit the dataset's directory and `datacatalog.json` on a branch.

## 4. Make the bytes available

Which step depends on the access class:

| Access | Do |
| --- | --- |
| `public` | [Upload the dataset](upload-a-dataset.md) to dCache and verify it anonymously. On the cluster computer, [link it into the cluster's public cache](link-existing-data.md) as well if users should read it there in place. |
| `restricted` | [Register the authorised installation](add-restricted-data.md) by name in the restricted cache of its access combination. Nothing is uploaded. |

Restricted data has no copy on dCache: it is read in place, where a
restricted cache holds it. A dataset that should be downloadable is made
`public`. A dataset that is restricted until an embargo ends is registered in
the restricted cache that admits every institute member, and uploaded once it
becomes public.

## 5. Record the authoritative copy

After a successful upload and verification, freeze the dataset in your own
clone:

```bash
ethos-data catalog --catalog-root <your clone> record my-dataset
```

`record` checks the copy on dCache again, makes it the authoritative copy and
retires `source_dir`: the recorded inventory is frozen. For linked data, the
original directory stays the build input until the dataset is
[materialized](materialize-linked-data.md#retire-the-original), and the copy
is recorded then. Commit the status file on the branch and merge it by merge
request on JuGit.

## 6. Release and hand off

[Release the catalogue](release-the-catalogue.md). A dataset is available to
consumers only after this step; a successful build alone publishes nothing.

Then tell the proposer the accepted dataset name and the release that holds
it. Ask them to raise their `catalog.min_version`, remove their staging
entries, run `bundle update` so their bundle records its new alignment with
the catalogue, and run their workflow against the released catalogue. Keep the proposal, the review findings, the upload report
and the release identifiers together in the issue.
