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
| `test:` variant of a collection, beside its `full:` data | Examples and live-data tests that run the production code path on small inputs | Needs the catalogue and a small download; offers the same named paths as the full data, so the same code runs on both. |

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

## Test and full variants of a collection

A collection can be written twice, under `test:` and `full:`: a small live
selection that an example or a test suite runs on in seconds, and the real
inputs. Both are ordinary catalogue selections fetched through the same cache.
What they share is the set of named paths under `paths:`, and the reader checks
that when the collection is resolved — for the collection asked for and for
every collection it reaches through `extends`, so a plain `all` that extends a
lopsided pair is refused as well. That check is the interchangeability
guarantee: code written as
`ethos_data.paths("onshore_wind", package="reskit", test=True)` runs unchanged
on the full data once `test=True` is dropped, because every handle it asks for
exists in both variants. A handle present in only one of them would fail on the
machine that has the full data, long after the example passed — so the reader
refuses the collection instead.

The guarantee is about the definition, not about this machine. Whether the data
behind a handle is reachable here is the separate question `skip_unavailable`
answers: without it, unreachable data stops the fetch; with it, the handle is
left out of the mapping and named in a warning, so a workflow that treats an
input as optional has to look for its handle rather than assume it.

A test variant is not a bundle. A bundle is an offline copy of a selection,
identified by resource keys and hashes, for tests that must run without the
catalogue or dCache. A test variant is a live selection: it still needs the
catalogue and, on a fresh machine, a download — a small one — and it offers the
same handles as the full data, which a bundle does not promise. Bundle export
takes a collection's full variant. Use both where they fit: a bundle for
required offline tests, a test variant for examples and live-data tests that
exercise the production code path.

The full data is the default and `test=True` / `--test` is opt-in. A forgotten
flag then costs a large but visible download that can be interrupted. The other
default would let a real calculation run silently on fixtures and produce a
wrong result that looks right.

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

