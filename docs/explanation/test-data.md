# Test data, development inputs, and reproducibility

A test needs a known input and a clear reason to fail. Choosing where its data
lives determines whether a failing test points to code, data changes, or a remote
service. One package can use several approaches.

| Input | Suitable for | Tradeoff |
|---|---|---|
| Tiny synthetic fixture created in a test or committed directly | Parser edge cases and self-contained unit tests | The package owns its meaning and updates; no catalogue is required. |
| Verified repository bundle of catalogued data | Regression tests that must run without network access | Larger checkout; the bundle must be refreshed deliberately. |
| Pinned catalogue plus download cache | Large fixtures and tests of live data access | A fresh runner needs metadata and data access; retained caches reduce transfers. |
| Staged development dataset | New inputs or inventory changes before catalogue acceptance | Mutable, warned about, and not evidence of an official version. |

A test that generates three numbers need not propose them to the institute's
catalogue. Catalogue a fixture when its identity, provenance, reuse, or connection
to a real published input matters. Bundles currently accept public data only;
licensed fixtures belong in authorised local installations and restricted CI.

## Downloading is conditional

Normal fetching reuses the shared cache. It does not download every file on
every test run. A fresh CI worker or an evicted cache does need a transfer, and
loading remote metadata can still require a network request. An offline bundle
carries its metadata and bytes together, so its reads need neither the live
catalogue nor dCache.

For catalogued public fixtures, the published store remains authoritative. A
repository bundle is a selected snapshot, identified by resource keys and original
hashes. A file in a Git checkout is not automatically that published version.

## Changed bytes and new test cases are different operations

`allow_modified=True` permits intentional edits to an **existing** bundled
resource and emits a warning. It retains the original hashes and does not allow
missing resources. Strict verification continues to report the difference.
Adding a file beside a bundle does not add it to the recorded collection.

A new test using existing inputs needs only code. A new synthetic corner case
can stay in the package. A new catalogued input needs a dataset proposal and an
updated collection; staging lets a developer test it before acceptance.

Once changed data is accepted, update the catalogue pin, collection, bundle
metadata, and bytes together. Return to strict checking. Never fix a mismatch
by editing the generated hash to agree with an unexplained change.

## A metadata pin is only part of reproducibility

An exact catalogue revision fixes the inventory. Its data paths must still
provide the same bytes. Changing only `ethos:remote_prefix` leaves the local
cache key `<dataset>/<resource path>` unchanged, so two revisions with changed
bytes would compete for that entry. Use a new dataset identifier or versioned
resource paths as well as new remote paths when versions must coexist.

Record the package revision, catalogue revision, collections, and any local
overrides used by an experiment. A configured catalogue override replaces a
package's pin; a staged dataset or per-dataset root can select local bytes.
A successful in-place fetch establishes availability, while `verify --deep`
checks those bytes against the recorded inventory.

See [Update test data](../how-to/update-test-data.md),
[Run package tests in CI](../how-to/run-in-ci.md), and
[Licensing and immutability](licensing.md).

