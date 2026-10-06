# Verify provenance

Check that a downloaded dataset, catalogued or proposed, still matches what
its source publishes. This applies to datasets with `ethos:origin:
downloaded`. Created and derived datasets have no external source to compare
against; for those, the review checks the author, inputs and derivation record
instead.

Do this before adding a downloaded candidate, when a user reports a mismatch,
and periodically for datasets whose source keeps publishing new versions.

## 1. Find the source

Read the dataset's `dataset.yaml`: `sources[].path` names the origin,
`ethos:retrieved` the download date, and `description` or `version` the
release. If the source publishes checksums or a manifest, that is the
reference to compare against. If it publishes only files, you compare bytes.

## 2. Re-download into the validation folder

The cluster computer has a central validation folder for exactly this, kept
apart from the caches so that a re-download can never be mistaken for the
catalogued copy. Its location is on the ICE-2 wiki; the path below is a
placeholder.

```bash
mkdir -p /shared/ethos/validation/global-wind-atlas-v4
cd /shared/ethos/validation/global-wind-atlas-v4
curl -O https://globalwindatlas.info/.../wind_speed_cog_100m.tif
```

For a large dataset, re-download the files a workflow reads most and a random
sample of the rest, and say so in the record. Delete the re-download when the
check is done; the folder is a scratch area, not a third cache.

## 3. Compare against the catalogue's inventory

Lay the re-downloaded files out by the paths the inventory records. Then, in
your own clone of the source catalogue:

```bash
ethos-data catalog check-source global-wind-atlas-v4 /shared/ethos/validation/global-wind-atlas-v4 \
    --note "against the 2026-09 release on the provider's site"
```

It hashes every file under the folder whose path the inventory lists,
compares its size and SHA-256 with the recorded ones, names each file that
differs and each one the inventory does not list, and exits `1` if a file
differs. `--dry-run` compares without recording.

If the source publishes checksums rather than files, print the recorded
hashes and sizes instead:

```python
import ethos_data

catalog = ethos_data.load_catalog("/shared/ethos/catalogue/datacatalog.json")
for resource in catalog.dataset("global-wind-atlas-v4").resources.values():
    print(resource.hash, resource.bytes, resource.path)
```

Compare them line by line with the published checksums. Note the algorithm:
the catalogue records SHA-256; a source that publishes MD5 or SHA-1 has to be
re-downloaded for a byte comparison.

## 4. Record the outcome

`check-source` records the date, the sample compared and the result, with
the `--note`, in the dataset's `status.yaml`; `ethos-data catalog status
<dataset>` lists the dataset, and its history the checks. Write the same into
the dataset's issue. If the check was part of a proposal, it belongs in that
proposal's thread. Commit the status file on a branch and merge it by merge
request on JuGit.

## 5. If it does not match

| Finding | Meaning | Do |
| --- | --- | --- |
| The source moved on to a new version | The catalogued dataset is a snapshot of the old one. | Keep it, record the source version in `description`, and add the new version as a new dataset or under new paths. Published paths never change. |
| Our copy differs from the same source version | Our bytes are wrong or the source was corrected in place. | Treat it as a data error: [remove](withdraw-a-dataset.md) or replace under new paths, and tell the packages that use it. |
| The source is gone | The dataset can no longer be verified externally. | Record that in `description`; the catalogue's hashes become the only reference. |
