# Test data, development inputs, and reproducibility

A test needs a known input and a clear reason to fail. Choosing where its data
lives determines whether a failing test points to code, data changes, or a remote
service. One package can use several approaches.

| Input | Suitable for | Tradeoff |
|---|---|---|
| Tiny synthetic fixture created in a test or committed directly | Parser edge cases and self-contained unit tests | The package owns its meaning and updates; no catalogue is required. |
| Verified bundle of attributed public data | Required tests and examples that must run without network access | Larger checkout; a bundle ahead of the catalogue warns until it is realigned. |
| Catalogue release within the release bounds, plus download cache | Large fixtures and tests of live data access | A fresh runner needs metadata and data access; retained caches reduce transfers. |
| Staged development dataset | New inputs or inventory changes before catalogue acceptance | Mutable, warned about, and not evidence of an official version. |
| `test:` variant of a collection, beside its `full:` data | Examples and live-data tests that run the production code path on small inputs | Needs the catalogue and a small download; offers the same named paths as the full data, so the same code runs on both. |

A test that generates three numbers need not propose them to the institute's
catalogue. Catalogue a fixture when its identity, provenance, reuse, or connection
to a real published input matters. A bundle holds public data with settled
licensing only, because the repository distributes it; licensed fixtures belong
in restricted CI.

## Downloading is conditional

Normal fetching reuses the public cache; on the cluster, that is one directory
every user shares. It does not download every file on every test run. A fresh
CI worker or an evicted cache does need a transfer, and loading remote metadata
can still require a network request. A bundle carries its descriptions and
bytes together, so reading it needs neither the catalogue nor dCache.

Within a major release, dCache keeps every version it published, and a
published version never changes. A package's bundle is authoritative for that
package: the package reads what its bundle holds, even where the bundle is
ahead of the catalogue, and its maintainer is warned to realign the bundle with
the catalogue soon. `bundle.json` records which catalogue revision each dataset
was last aligned with, and what changed since.

## Test and full variants of a collection

A collection can be written twice, under `test:` and `full:`: a small live
selection that an example or a test suite runs on in seconds, and the real
inputs. Both are ordinary catalogue selections fetched through the same cache.
What they share is the set of named paths under `paths:`, and the reader checks
that when the collection is resolved — for the collection asked for and for
every collection it reaches through `extends`, so a plain `all` that extends a
lopsided pair is refused as well. That check is the interchangeability
guarantee: code written as
`data.paths("onshore_wind", test=True)`, where
`data = ethos_data.collections("collections.yaml")`, runs unchanged
on the full data once `test=True` is dropped, because every named path it asks
for exists in both variants. A named path present in only one of them would fail
on the machine that has the full data, long after the example passed — so the
reader refuses the collection instead.

Every named path is required, and no option leaves one out: a call returns
all of them, or stops before anything is downloaded and says what is missing.

- **A variant is missing.** The error names the collection and the variant,
  or the named path that only one of its variants offers.
- **The data is restricted.** The error names the dataset, says that it is
  restricted and how or where to obtain it, as far as the catalogue records
  that, and how to register a copy once you have one. `--meta` prints the
  dataset's full description.
- **The name is not found.** A mistyped name and a dataset the catalogue does
  not publish get the same answer: the dataset cannot be found.

Test and full variants are not bundles. Both are selections from the
catalogue, fetched through the caches; a bundle is data a package keeps in
its own repository.

The full data is the default and `test=True` / `--test` is opt-in. A forgotten
flag then costs a large but visible download that can be interrupted. The other
default would let a real calculation run silently on fixtures and produce a
wrong result that looks right.

## Changed bytes and new test cases are different operations

`allow_modified=True` permits intentional edits to an **existing** bundled
resource and emits a warning. It retains the original hashes and does not allow
missing resources. Strict verification continues to report the difference.
Adding a file beside a bundle does not record it. To keep a change, an added
file included, record it with `bundle update` and return to strict checking;
the dataset is then ahead of the catalogue.

A new test using existing inputs needs only code. A new synthetic corner case
can stay in the package. A new catalogued input needs a dataset proposal and an
updated collection; staging, or the package's bundle, lets a developer use it
before acceptance.

Propose what a bundle holds ahead of the catalogue. Once the catalogue has
accepted it in a release, raise `min_version` to that release and run
`bundle update` with the catalogue readable: it records the new alignment, and
the warning stops. Never fix a mismatch by editing the recorded hash to agree
with an unexplained change.

!!! warning "Gap: a bundle cannot be ahead of the catalogue"
    The code's bundles are copies exported from the catalogue, which stays
    authoritative for them. There is no `bundle update`, nothing records a
    change or warns about one, and a changed file is read only with
    `allow_modified=True`.

## Release bounds are only part of reproducibility

An exact catalogue release, such as `exact_version: v1.2.0`, fixes the
inventory. A patch release changes metadata only, so `exact_version: v1.3`
keeps the same bytes and takes corrected metadata. The bytes must still be
there. Within a major release, dCache keeps every version it published, and a
published object never changes: a revision puts its changed files under new
remote paths and an entry of its own, `<dataset>@<r>`, so two revisions never
compete for one cache entry. Withdrawn data may be purged only after a major
release. Data that is only linked, and restricted installations, change with
their source.

!!! warning "Gap: no revisions"
    The code has no revisions. Changing only `ethos:remote_prefix` leaves the
    cache path `<dataset>/<resource path>` unchanged, so two versions with
    changed bytes need a new dataset name or new resource paths.

Record the package revision, catalogue release, collections, and any local
overrides used by an experiment. A configured catalogue is read instead of the
public release the bounds select, and its release must lie within them; a
staged dataset, or a bundle ahead of the catalogue, selects local bytes. A
successful in-place fetch establishes availability, while `verify --deep`
checks those bytes against the recorded inventory.

See [Keep data in the repository](../how-to/package-maintainers/keep-data-in-the-repository.md#update-data),
[Run package tests in CI](../how-to/package-maintainers/run-in-ci.md), and
[Licensing and immutability](licensing.md).
