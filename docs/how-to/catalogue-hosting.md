# Serve catalogues on the cluster and GitHub

Use a filesystem catalogue for cluster users and a versioned public catalogue
for external users. Uploaded datasets have their authoritative published bytes
on dCache; restricted datasets remain in authorised local installations.
[Register both kinds](add-internal-and-restricted-data.md) in the internal
catalogue. Git hosts store metadata; repository test fixtures are local copies
of selected published data.

The paths below are examples to replace with your cluster's actual location.

## Internal catalogue: maintain through jugit, read through the filesystem

Keep the internal catalogue's Git history on jugit and a maintainer checkout on
the cluster. Review changes, build the descriptors, and synchronize that checkout
through Git. Package contributors can submit proposals without access to the
maintainer checkout; see [Propose a dataset](propose-a-dataset.md).

Serve a complete, validated version directory separately from the working tree:

```text
/shared/ethos/catalogue/
  versions/<commit>/datacatalog.json
  versions/<commit>/datasets/...
  current -> versions/<commit>
```

Build and validate the new version before pointing `current` at it. Keep older
version directories for reproducible jobs. Avoid rebuilding the catalogue in
place while other jobs lazily read its descriptors and shards: an index from one
revision must not be paired with inventories from another.

Point a CLI invocation at the convenient alias:

```bash
ethos-data --catalog /shared/ethos/catalogue/current/datacatalog.json -c collections.yaml list
```

`collections.yaml` is the collections file your project uses or the one a
package ships.

An administrator may set a site default; an individual can set a user default:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/current/datacatalog.json
```

This setting, or `ETHOS_DATA_CATALOG`, replaces the catalogue version a
collections file pins, in the CLI and the Python API alike; see
[Add the internal data catalogue](add-internal-catalogue.md). For a published
calculation, record and use the concrete `versions/<commit>/datacatalog.json`
path rather than the moving `current` alias.

Grant readers filesystem read access to the served metadata, and reserve writes
for maintainers. Filesystem access to an internal catalogue does not grant access
to every dataset it describes. Configure data roots separately.

## Public catalogue: release metadata, retain bytes on dCache

Generate the public checkout with `ethos-data catalog publish`, review it, and
release it only after the advertised bytes have been uploaded and verified.
See [Publish the catalogue](publish-the-catalogue.md) for the generation checks.
Keep internal source paths, embargo notes, and private metadata out of the public
repository and release archive.

Pin consumers to a tag or commit in the generated public GitHub repository:

```yaml
catalog: https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/v2026.09/datacatalog.json
```

The URL is an example of the existing format; select a revision actually released
by the catalogue maintainer. The reader loads only required descriptors and
shards and caches URLs it recognises as pinned. Do not move a released tag or
replace metadata behind an existing pin.

## What GitHub Releases do and do not change

A release provides a versioned delivery point and release notes. Attaching a
catalogue archive is useful for users who want to download metadata once, extract
it, and point the existing reader at a local `datacatalog.json`. Preserve the
archive's directory structure so relative descriptor and shard references work.

Creating a release does not redirect raw GitHub URLs to release assets. The
current reader accepts JSON locations; it does not automatically download or
unpack release archives. Direct archive support would require an explicit
checksum-verified download and safe extraction implementation. Until then,
use a pinned raw URL or a locally extracted catalogue.

GitHub documents up to 1,000 assets per release, each under 2 GiB, and no limit on
total release size or bandwidth usage for release assets. This is not a promise
that raw repository requests or API calls are unlimited. See
[GitHub's release quotas](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas).

Keep ordinary repository test fixtures small: GitHub blocks regular Git files
larger than 100 MiB and recommends small repositories. Consider file history as
well as current checkout size. See
[GitHub's large-file guidance](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).
Fixture copies and catalogue snapshots reduce requests during routine testing;
dCache remains the authoritative published source.
