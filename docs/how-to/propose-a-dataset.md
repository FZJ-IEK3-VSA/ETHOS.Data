# Propose a dataset

This guide is for package maintainers who have tested new data locally and
want it included in the official catalogue. The catalogue maintainer reviews
the proposal and uploads accepted data. You do not need dCache credentials or
write access to the internal repository.

## Prepare the review material

Supply these items through the project's agreed issue, merge request, or
submission channel:

| Item | What the reviewer needs |
|---|---|
| Purpose and identity | Proposed dataset name, version, title, intended workflows, and whether it adds data or revises an existing input |
| Source metadata | A draft `dataset.yaml`, following [Describe a dataset](describe-a-dataset.md) |
| Provenance | Original source or DOI, retrieval date, authors, and any derivation script with its version and parameters |
| Redistribution and visibility | Applicable licences, attribution, access class, and any proposed embargo; identify unresolved questions |
| Inventory | Selected relative paths, sizes, SHA-256 hashes, and required sidecars; preferably a generated manifest |
| Access to the bytes | An agreed shared directory or transfer location that the reviewer can read, and how long it will remain available |
| Validation | Commands/tests used, relevant results, and the collection selection that the package will use |

An archive attached to a proposal is a transfer copy. Once accepted and
uploaded, dCache remains the authoritative store, including for test data.

If you can read the source catalogue, prepare a branch in a personal checkout
and add `datasets/<name>/dataset.yaml`. If you cannot, submit the draft metadata
and inventory separately; the reviewer can integrate and build them. Avoid
putting machine-specific paths in the consuming package's committed
collections file.

## Make the proposed bytes stable for review

Finish the local experiment in a development directory and preserve that
version for the reviewer. Changes to the files after inventory generation
invalidate its checksums. Rebuild and update the proposal if the candidate
changes.

Keep the proposed published paths distinct from paths with already published,
different bytes. A bug fix does not authorize overwriting an immutable remote
object. Explain whether the fix is only in code or also requires new data.

## Hand off publication

The catalogue maintainer follows [Accept a dataset proposal](accept-a-dataset.md):
review metadata, build and inspect the inventory, upload and verify the bytes,
then release the appropriate metadata. A successful local test or metadata
build alone does not establish that data is available to consumers.

## Adopt the accepted version

After the maintainer supplies the released catalogue version:

1. Update your package's catalogue pin and collection definitions as needed.
2. Remove the staging entry with `ethos-data staging remove <name>`; remove any
   dataset-specific local root override that was used for development.
3. Fetch and run the affected workflow against the accepted catalogue, checking
   that no staging warning remains.
4. Update any repository test-data snapshot deliberately, then run both the
   required local tests and the relevant live integration test.

See [Stage unpublished data](stage-unpublished-data.md),
[Write a collections file](write-a-collections-file.md), and
[Run package tests in CI](run-in-ci.md).
