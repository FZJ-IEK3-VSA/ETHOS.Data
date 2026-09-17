# Catalogues and storage

ETHOS.Data separates descriptions from files. Setting a catalogue chooses which
datasets and versions can be resolved. Setting cache roots chooses where this
machine reads or stores their bytes. Neither setting grants access to a service
or a filesystem.

| Component | Contains | Responsible role |
|---|---|---|
| Internal source catalogue | Handwritten YAML, generated index, descriptors and inventories for all registered datasets | Catalogue maintainer |
| Generated public catalogue | Entries permitted by `ethos:visibility: public`, with private fields removed | Catalogue maintainer |
| Package collections | Named selections from a catalogue, optionally pinned to a revision | Package maintainer |
| Public cache | Downloaded files and links for public/internal inputs | User or cluster administrator |
| Restricted cache | Authorised local copies or links for restricted inputs | Dataset custodian or cluster administrator |
| dCache | Published dataset bytes at stable remote paths | Catalogue/storage maintainer |

The [public GitHub repository](https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue)
is a metadata distribution point. The private source repository and the served
internal catalogue on the cluster contain a superset of that metadata.
“Restricted catalogue” usually means this internal view; `restricted` itself
is a dataset access class, not a second file format.

A reader uses one catalogue at a time. Selecting the internal catalogue replaces
the public catalogue or a package's pin; it does not merge independent catalogues.
The administrator must therefore deploy the complete internal view, including
the public entries that packages expect.

## Access and visibility answer different questions

Visibility controls publication of the description. Access controls how bytes
are obtained. A publicly visible restricted dataset can explain how to request
a licence without offering a download. A hidden internal dataset may be usable
on the cluster before its description is released.

Filesystem permissions enforce local access. The directory called “public cache”
can contain internal entries, so its name alone is no security boundary. The
restricted root must retain the installation's permissions when files are copied.
Ordinary retrieval reads restricted data in place; explicit `link` and
`materialize` operations can create its authorised local cache entries.

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
remote deletion; old pins and existing copies still need separate consideration.

See [Caches, classes and roots](caches-and-access.md),
[The catalogue lifecycle](architecture/lifecycle.md), and
[Serve catalogues on the cluster and GitHub](../how-to/catalogue-maintainers/catalogue-hosting.md).

