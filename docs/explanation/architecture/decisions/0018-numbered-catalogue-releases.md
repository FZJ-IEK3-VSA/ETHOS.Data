# 0018. Number catalogue releases `vYYYY.MM.N` and let collections files bound them

**Status:** proposed · **Date:** 2026-10-05 · **Implemented by:** #19, #23

## Context

A package must state which catalogue releases it was tested with, while the
user still chooses which catalogue to read, the internal or the public one. A
released package must resolve the same metadata later. One release name must
cover both catalogues, and readers must be able to find the list of public
releases.

## Decision

A release is named `vYYYY.MM.N`. N counts the releases within the month from
1 and is compared as a number, so `v2026.09.10` follows `v2026.09.9`. A
collections file may bound the releases it accepts with `catalog:`:

| `catalog:` | Accepts |
|---|---|
| `{min_version: V}` | V and every later release |
| `{min_version: V, max_version: W}` | V to W, both included |
| `{exact_version: V}` | V only |
| absent | any catalogue, with or without a release |

- The release's `stamp` stage writes the name into `catalog.yaml` as
  `version`; the build checks it and writes it into the index. The same name
  tags the source catalogue and the public catalogue.
- The public index on `main` lists every public release in `ethos:releases`.
- Malformed bounds raise `CollectionError`, naming the file.
- A catalogue the settings choose (`--catalog`, a package's `catalog=`,
  `ETHOS_DATA_CATALOG`, the `catalog` setting) is refused with
  `CatalogVersionError` (exit 2), naming its release and the bounds, when it
  lies outside the bounds or records no release.
- With bounds and no catalogue configured, once a handle needs the index,
  `exact_version` reads that release's tag on GitHub, and a range reads the release list of the public
  `main` index and takes the newest admitted release, from its tag. If none is
  admitted, the error lists the releases there are. With no bounds and no
  catalogue configured, the public `main` index is read.

## Alternatives considered

- **Semantic versions.** A release changes data, not an interface, so major
  and minor numbers would promise nothing; a dated name orders the releases
  and shows their age.
- **A catalogue location per package.** It would fix the catalogue for every
  user, while the choice between the internal and the public catalogue
  belongs to the user's settings ([0010](0010-one-settings-file-per-account.md)).
- **Git commit hashes.** They are not ordered, so no range can be stated.
- **Month-only names, `vYYYY.MM`.** They allow one release a month.

## Consequences

- Packages raise `min_version` deliberately, once they are tested with the
  new release.
- The served checkout on the cluster holds the latest internal release only.
  A collections file whose bounds exclude it, with an `exact_version` of an
  older release or a `max_version` below it, is refused there, so packages
  that run on the cluster bound with `min_version` only
  ([0026](0026-internal-catalogue-on-the-cluster.md)).
- A tag URL never changes and is cached forever. A range with no catalogue
  configured reads the public `main` index, which is never cached, whenever a
  handle needs the index. A handle whose bundles hold every input reads no
  index ([0020](0020-repository-bundles.md)); otherwise offline use needs a
  configured catalogue, or an `exact_version` whose tag is already in the
  metadata cache ([0005](0005-lazy-index-descriptors-and-shards.md)).
- The self-test collection gets bounds with the first stamped public release
  ([0017](0017-self-test-collection.md)).
- See [Declare the catalogue versions](../../../how-to/package-maintainers/write-a-collections-file.md#catalog-version)
  and [Release the catalogue](../../../how-to/catalogue-maintainers/release-the-catalogue.md).

## Related

- [0010. Read settings from one file per account, once per handle](0010-one-settings-file-per-account.md)
- [0020. Keep a package's test data in a repository bundle that the catalogue publishes](0020-repository-bundles.md)
- [0021. Make a bundle version exactly what one release holds](0021-one-bundle-version-per-release.md)
- [0026. Serve the internal catalogue's latest release from one checkout on the cluster, and change it only through JuGit](0026-internal-catalogue-on-the-cluster.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [6. Runtime View](../runtime.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
