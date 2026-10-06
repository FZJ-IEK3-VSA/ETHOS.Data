# Catalogues and storage

ETHOS.Data separates descriptions from files. Setting a catalogue chooses which
datasets and versions can be resolved. Setting cache roots chooses where this
machine reads or stores their bytes. Neither setting grants access to a service
or a filesystem.

| Component | Contains | Responsible role |
|---|---|---|
| Internal source catalogue | Handwritten YAML, generated index, descriptors and inventories for all registered datasets | Catalogue maintainer |
| Generated public catalogue | Entries permitted by `ethos:visibility: public`, with private fields removed | Catalogue maintainer |
| Package collections | Named selections from a catalogue, optionally with release bounds | Package maintainer |
| Public cache | Downloaded files, links and copies of public data; on the cluster, one directory every user shares | User or cluster administrator |
| Restricted caches | Authorised local copies or links for restricted data, each cache for one access combination; only where someone sets them up | Dataset custodian or cluster administrator |
| dCache | Published dataset bytes at stable remote paths | Catalogue/storage maintainer |

The [public GitHub repository](https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue)
is a metadata distribution point. The private source repository and the served
internal catalogue on the cluster contain a superset of that metadata.
“Restricted catalogue” usually means this internal view; `restricted` itself
is a dataset access class, not a second file format.

A reader uses one catalogue at a time. Selecting the internal catalogue replaces
the public catalogue, within a package's release bounds; it does not merge
independent catalogues. The administrator must therefore deploy the complete
internal view, including the public entries that packages expect.

## Access and visibility answer different questions

Visibility controls publication of the description. Access controls how bytes
are obtained. A publicly visible restricted dataset can explain how to request
a licence without offering a download. A hidden restricted dataset that the
institute holds without publishing it may be usable on the cluster before its
description is released.

Filesystem permissions enforce local access. The public cache holds public data
only, and on the cluster every user may write it. Each restricted cache admits
one access combination, such as every member of the institute or one licence
group, and must retain the installation's permissions when files are copied.
Ordinary retrieval reads restricted data in place; explicit `link` and
`materialize` operations can create its authorised entries in a restricted
cache.

## Availability has several independent checks

A successful metadata build proves that descriptors match the build inputs.
It does not upload bytes. Generating the public view does not push Git commits
or deploy a cluster release.

An upload checks anonymous HTTP readability and reported sizes; it is not a
remote SHA-256 audit. A consumer's `verify --deep` compares actual local bytes.
A correct checksum establishes identity with the catalogue, not scientific
validity. The acceptance review and package tests address that separate question.

The normal release order is review, build, transfer and check bytes, then release
metadata. Restricted inputs use verified local storage instead of a transfer.
The inverse withdrawal order removes current metadata before any deliberate
remote deletion, and that deletion waits for a major release, so releases of
the current major keep resolving the dataset. Copies in caches on other
machines still need separate consideration.

See [Caches, classes and roots](caches-and-access.md),
[The catalogue lifecycle](architecture/runtime.md#dataset-lifecycle), and
[Release the catalogue](../how-to/catalogue-maintainers/release-the-catalogue.md).

