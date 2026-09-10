# Keep test data in a repository

Use a **test-data bundle** when small catalogued datasets should travel with a
package checkout so tests do not depend on dCache availability. dCache remains
the authoritative published source. The bundle contains copies of selected files
and a generated snapshot of their catalogue metadata.

Bundle reads compare local files with the recorded hashes. They do not query
live dCache or fetch a newer catalogue; the snapshot identifies the published
version against which the copy is checked. An explicit development override lets
you test changed local bytes before proposing an update to the authoritative data.

## Create a verified copy

Choose a collection containing the test inputs, pin its catalogue, and export it:

```bash
ethos-data -c reskit/data/collections.yaml bundle export tests/data-bundle test_suite \
  --source-revision v2026.09
```

Use your actual catalogue revision. `--source-revision` records provenance; it
does not select that revision. The collection's `catalog:` URL or `--catalog`
must already point to the desired version.

To use files already present in the repository as the source, avoid downloading:

```bash
ethos-data -c reskit/data/collections.yaml bundle export tests/data-bundle test_suite \
  --source-root reskit-test-data=reskit/data/test_cache/data --source-revision v2026.09
```

This succeeds only if the local source has the catalogue's relative layout and
matches its hashes. The RESKit path is an example of an existing fixture tree;
verify its mapping before migration. Export creates a new bundle and never
replaces the source tree. Keep the existing `TEST_DATA` interface until its
callers have been migrated deliberately.

Export accepts public datasets suitable for portable copies. Restricted and
internal datasets are refused by this first implementation. Review the retained
licence/provenance metadata before committing fixtures to a public repository.
Do not commit credentials or internal catalogue working files with them.

The result has this layout:

```text
tests/data-bundle/
  bundle.json                 # generated metadata and exact collection membership
  data/<dataset>/<path>       # selected bytes, including declared sidecars
```

`bundle.json` retains original hashes and source information. Do not edit it to
make a modified file appear verified. Files not selected by a bundled collection
do not become test inputs merely because they are present in the directory.

## Read it from tests

Resolve the bundle relative to the test module, not the working directory:

```python
from pathlib import Path
from ethos_data import load_bundle

BUNDLE = Path(__file__).resolve().parent / "data-bundle"

def test_my_workflow():
    files = load_bundle(BUNDLE).fetch("test_suite")
    # Pass files or files.one("known-input.nc") to the workflow under test.
    assert files
```

For a pytest fixture shared between tests, load the bundle once and call
`fetch` when the test needs checked paths. Bundle reads are independent of user
cache settings, staging overlays, and `--skip-unavailable`. They never download,
repair, or write into the repository. Missing files fail, including missing
sidecars. Hash mismatches fail by default.

Use the CLI for a pre-test check:

```bash
ethos-data bundle verify tests/data-bundle test_suite
```

Commit both metadata and the selected files so a fresh checkout contains all
required inputs. A restored CI cache is optional; it is not required for this
workflow. Bundle reads work with an empty external cache and blocked network.
Package installation and checkout themselves may still require network access.

## Temporarily use changed data while fixing a bug

Modify the local copy, then opt into divergence explicitly in a development test:

```python
files = load_bundle(BUNDLE).fetch("test_suite", allow_modified=True)
```

Or inspect the same selection through the CLI:

```bash
ethos-data bundle fetch tests/data-bundle test_suite --allow-modified
```

Changed files produce a warning naming their resource keys. Their original
hashes remain in the snapshot. The override permits changed existing files; it
does not permit missing files, incomplete metadata, or escaping paths. No changes
are sent to dCache.

Keep the override local to the test or development branch that needs it. A
regression test can temporarily run against modified bytes while a separate
strict verification check continues to report the divergence. Do not add a
project-wide switch that makes every test silently accept arbitrary changes.
For entirely new resources or changing inventories, use
[staging](stage-unpublished-data.md) and the dataset-proposal workflow.

## Promote an accepted fix

1. Verify the bug fix and the modified test inputs locally.
2. [Propose the revised data](propose-a-dataset.md), identifying changed files and
   their derivation. Published paths remain immutable: changed bytes need new paths.
3. The catalogue maintainer builds, uploads, verifies, and releases the revision.
4. Update the package's catalogue pin and collection selection.
5. Export the new bundle to a fresh directory, review its differences, and replace
   the old tracked bundle as an ordinary repository change.
6. Remove the development override and require strict verification again.

Export refuses an existing target to protect local changes. Refreshing fixtures
is a maintainer action; ordinary test execution never refreshes them automatically.

## Scope and hosting

The first workflow targets source checkouts and CI. If fixtures should also ship
inside a wheel, configure package-data inclusion and test the installed layout;
placing them under `tests/` alone does not include them in a wheel.

For public metadata hosting and GitHub file-size constraints, see
[Serve catalogues on the cluster and GitHub](catalogue-hosting.md).
See [Bundle CLI reference](../reference/cli/ethos-data.md#bundle) for exact options
and [Integrity API](../reference/api/integrity.md#repository-test-data-bundles)
for the Python interface.
