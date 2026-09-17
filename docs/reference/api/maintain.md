# Maintainer tooling

`ethos_data.maintain` is the writing half of the format: the code that produces
the descriptors `ethos_data.catalogs` reads. Consumers usually need no maintainer
imports; ordinary APIs also manage downloads, caches, and local development data.

Both halves ship in one distribution on purpose. The `ethos:` extensions are a
format, and a format whose writer and reader live in separate repositories
drifts silently.

Two commands lead here. [`ethos-data catalog`](../cli/catalog.md) drives the
manifest builder, the publisher and the uploader below — the work that writes
and ships metadata about the data. The cache namespace builder is the exception:
it is reached from
[`ethos-data link --all`](../cli/ethos-data.md#link-dataset-directory), because
building a namespace is site administration on the machine that holds the data
rather than catalogue maintenance. It writes symbolic links into one machine's
cache and never a descriptor, and filling a whole cache from a checkout is the
same job as pointing one dataset at a directory, only at a larger scale. That is
exactly why its command sits with the user-facing `link` rather than under
`catalog`.

The catalogue-locating helpers below serve both entry points: `link --all` reads
`source_dir` from the hand-written `dataset.yaml` of a source checkout, and it
finds that checkout the same way the maintainer commands find theirs.

## Locating a catalogue

::: ethos_data.maintain
    options:
      members:
        - find_catalog_root
        - resolve_catalog_root
        - catalogue_role
        - datasets_dir
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Building manifests

::: ethos_data.maintain.manifest
    options:
      members:
        - run
        - render_dataset
        - write_dataset
        - stale_files
        - build_catalog
        - catalog_meta
        - select
        - expand_pattern
        - iter_data_files
        - build_resource
        - split_into_shards
        - shard_path
        - validate_classification
        - validate_provenance
        - validate_licenses
        - apply_resource_licenses
        - slugify
        - mediatype_of
        - sha256_of
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Publishing

::: ethos_data.maintain.publish
    options:
      members:
        - run
        - render
        - public_datasets
        - strip
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## The cache namespace

Built by [`ethos-data link --all`](../cli/ethos-data.md#link-dataset-directory).
`run` takes the catalogue checkout and the namespace root as plain arguments,
neither of them optional, because the command decides which cache it means once
and hands the answer down: a planner that looked the cache up for itself could
answer differently from the caller that had already looked, and the result would
be a whole link tree built somewhere nobody named.

`authority` arrives the same way and is keyword-only with **no default**. It says
what the root is — `PUBLIC_CACHE`, `RESTRICTED_CACHE` or `UNIDENTIFIED` — and one
decision turns on it and no other: whether a link for a *restricted* dataset may
be removed. A default would be a deletion justified by an assumption nobody made
out loud, so there is none, and a caller that has not thought about it gets a
`TypeError` rather than a removal. `authority_for(roots, root)` computes it from
roots the caller has already resolved, over
[`which_cache`][ethos_data.access.which_cache]; `restricted_root_message` is the
text a caller prints when the answer is `RESTRICTED_CACHE`, where the run is
refused rather than planned.

Every line the command prints is one `Action`, and its verb is the planner's
whole vocabulary — written down once on `Action` below. Six of those verbs are
findings rather than work — they are the `FINDINGS` tuple — and `plan` produces
them by *reading* the cache rather than discovering them while writing it, which
is why `--dry-run` reports the same plan a real run reports. `apply` adds the
seventh, `failed`, for an entry that could not be written or removed; it edits the
action in place, so `run` reads each outcome out of the same list it passed in and
counts what actually happened rather than what was planned. `run` returns `1`
while any of the seven is outstanding. `FINDINGS` is one tuple used both to build
the report's buckets and to compute the exit code, so a finding cannot be added to
the vocabulary and left out of the code a rebuild script reads.

`plan` writes nothing, and no state the *cache* is in makes it raise — a dangling
link, an entry removed underneath it, a directory it cannot list. That is what
makes `--dry-run` safe to point at a cache in any condition and what keeps the
exit-code contract: a caller gets a code, never a stack trace where the summary
should be. A malformed *checkout* still stops the run, because that is a fault in
what is being read from rather than in what is being described.

Where an entry may be written is one rule shared with `ethos-data link
<dataset>`, and it lives with the code that decides what a cache entry *is*:
[`borrowed_parent`][ethos_data.access.borrowed_parent], beside `entry_for`, which
defines an entry as `<root>/<name>` and nothing else.

::: ethos_data.maintain.namespace
    options:
      members:
        - run
        - plan
        - apply
        - authority_for
        - restricted_root_message
        - Action
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3

## Uploading

::: ethos_data.maintain.upload
    options:
      members:
        - run
        - preflight
        - resources_of
        - remote_manifest_check
        - locality
        - chmod
        - token
        - load
      show_root_heading: false
      show_root_toc_entry: false
      heading_level: 3
