# 1. Introduction and Goals

This chapter answers what ETHOS.Data is for, whom it serves, and which
qualities decide between designs.

## 1.1 Requirements overview

ETHOS.Data is one Python distribution, `ethos_data`, with the console script
`ethos-data`. It connects scientific packages such as ETHOS.RESKit to
catalogue metadata and dataset files.

For data users and their packages:

- A package names the slices of data its workflows need in one collections
  file.
- ETHOS.Data selects the matching catalogue resources and decides, for every
  file, where it is read on this machine.
- It downloads and verifies what is missing and returns local paths.

For catalogue maintainers, the same distribution:

- describes datasets and builds their inventories;
- makes the bytes available, by access class;
- records each dataset's state;
- releases the internal and the public catalogue;
- publishes new versions of datasets, and withdraws and purges them.

Metadata and bytes are kept apart. The metadata is the catalogues: the source
catalogue on JuGit, a served checkout of its latest release on the ICE-2
cluster computer, and the public catalogue on GitHub. The bytes live on
dCache, in caches and in bundles. Every user has a public cache for public
data. On the cluster it is one directory that every cluster user shares, so
each public file is linked or downloaded there once. Restricted data, licensed
or held by the institute without publishing it, is read in place from
restricted caches. These exist only where someone sets them up: on the
cluster, one for each group of people who may read the same data; on a
workstation, a directory with the user's own licensed copies. An account that
reads public data only needs none.

What ETHOS.Data leaves to other systems and people is listed under
[3.3 Scope](context.md#33-scope).

## 1.2 Stakeholders

| Role | Needs |
|---|---|
| Data user, on a public installation or as a cluster user | Obtain every input a package's collection names; know the origin, size, access conditions and reuse of each; work offline once the data is cached; check and repair a cache; report a problem with the facts attached |
| Package maintainer | Wire one collections file, one handle and a `<tool>-data` command into a package; keep attributed data in bundles and run the required tests and examples from them, offline and in CI, without dCache; realign a bundle with the catalogue, and export one to another repository; develop with staged data before proposing it; propose datasets; raise the release bounds deliberately |
| Catalogue maintainer | Review proposals and accept datasets; build inventories; make the bytes available: upload public data, and link or materialize data into the cluster's public cache and its restricted caches; record where each dataset stands and freeze it, in their own clone of the source catalogue, merged by merge request; release both catalogues; publish revisions and successors; withdraw and purge; check provenance; diagnose reports |

One person can hold several roles. Three supporting roles stay outside the
package:

| Supporting role | Responsibility |
|---|---|
| Storage operator (DESY, HIFIS) | The VO (virtual organisation) on dCache, its permissions, the OIDC client and availability |
| Cluster administrator (ICE-2) | File system groups and permissions on the cluster computer |
| Dataset custodian | Owns a licence group and grants access to the institute's copy of a restricted dataset |

## 1.3 Quality goals

These priorities decide between designs. [Section 10](quality-requirements.md)
gives the scenarios that check them.

| Priority | Goal | Why it matters |
|---|---|---|
| 1 | Traceable, repeatable inputs | A workflow must identify its catalogue release and its dataset resources. Local experiments must stay distinguishable from published data. |
| 2 | Controlled access and publication | Licence, visibility and file system restrictions must survive catalogue generation and retrieval. |
| 3 | Reuse and availability | Shared paths avoid duplicate downloads: on the cluster, one copy of each public file serves every user. Bundles keep the required tests independent of dCache. |
| 4 | Safe maintenance and diagnosis | Invalid selections fail before the first transfer. A step a dataset's state does not allow is refused. A dry run is the plan. An interrupted command, run again, does only what is left. Failures name the dataset, the resource and the location. |
| 5 | Scalable metadata access | A request does not load inventories it does not need. |
| 6 | Changeable code | A key, its default and its checks are written once. Each file format has one reader. A module depends only on its own layer and the layers below. |

Within a major release, dCache keeps every version it published, and a
published version never changes. A package's bundle is authoritative for that
package: the package reads what its bundle holds, even where the bundle is
ahead of the catalogue, and its maintainer is warned to realign the bundle
with the catalogue soon. A bundled file changed by hand is refused until
`bundle update` records it.
