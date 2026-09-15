# Describe a dataset

Create source metadata and a generated inventory for a proposed dataset. Work
in a source-catalogue checkout with read access to stable candidate files.

## 1. Write the source description

Create `datasets/my-dataset/dataset.yaml`:

```yaml
name: my-dataset
title: A short human-readable title
description: What this dataset contains and which release it describes.
source_dir: /path/to/candidate
ethos:access: public
ethos:visibility: public
ethos:remote_prefix: my-dataset-v1
sources:
  - title: Original release
    path: https://example.org/dataset-release
licenses:
  - name: CC-BY-4.0
    path: https://creativecommons.org/licenses/by/4.0/
ethos:retrieved: "2026-09-01"
ethos:contact: Dataset maintainer
```

Replace the examples with the actual source, release, licence, and contact.
A relative `source_dir` is relative to this dataset directory. For created or
derived data, record `ethos:origin`, authors, and derivation details using the
[format reference](../reference/schemas.md#datasetyaml).

If terms are unresolved, set `ethos:license_status: unresolved` and document
the question in `ethos:license_note`; do not invent an open licence. Review must
finish before linking or uploading.

## 2. Select the files

If the source contains unrelated files, add selection rules:

```yaml
ethos:include:
  - "rasters/**"
ethos:exclude:
  - "**/*.tmp"
```

Check all required sidecars are included. For a large inventory, set
`ethos:shard_depth` as described in the
[sharding explanation](../explanation/catalogue-format.md#sharding).

### The asymmetry is deliberate

An include pattern matching nothing fails the build; an unmatched exclude warns.
Correct spelling and input paths when selection differs from the proposal.

## 3. Build and review

```bash
ethos-data catalog build my-dataset
ethos-data catalog build my-dataset --check
git diff -- datasets/my-dataset datacatalog.json
```

Confirm names, selected paths, counts, sizes, SHA-256 hashes, provenance, and
access/visibility. Do not hand-edit generated JSON or shards.

## Datasets that are not ready to publish

For an internal candidate, use:

```yaml
ethos:access: internal
ethos:visibility: hidden
ethos:embargo:
  until: "unspecified"
  reason: Review before public release.
  becomes: public
```

Use a dated review when possible. For restricted data, use
[Add internal and restricted datasets](add-internal-and-restricted-data.md);
do not declare a remote prefix.

Continue with [Accept a dataset proposal](accept-a-dataset.md).
See [File formats](../reference/schemas.md) for the full metadata reference and
[Licensing and immutability](../explanation/licensing.md) for the rationale.
