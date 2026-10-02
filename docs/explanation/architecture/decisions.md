# 9. Architectural Decisions

These are retrospective summaries of decisions expressed in the current code
and explanations. They do not assign historical decision dates or claim that
unrecorded alternatives were formally evaluated. Each linked explanation remains
the canonical account of the reasoning.

| Decision | Status | Reason and consequence |
|---|---|---|
| Separate catalogue inventories from tool-owned collections | Implemented | Avoids repeated inventories drifting between tools; consumers must request catalogue-defined resources. See [Why one catalogue](../deduplication.md). |
| Derive cache paths from resource identity | Implemented | Enables tools to reuse the same local files; identity and layout become compatibility contracts. See [deduplication](../deduplication.md). |
| Ship descriptor writer and reader together | Implemented | Allows format changes to be reviewed together; maintainer tooling shares the distribution. See [catalogue format](../catalogue-format.md). |
| Load descriptors and shards lazily | Implemented | Limits metadata work to what a request needs; descriptor and shard availability can fail later than initial index loading. See [catalogue format](../catalogue-format.md). |
| Treat restricted files as in-place data | Implemented | Ordinary retrieval uses authorised local storage without downloads; users need an accessible local copy. See [access policy](../caches-and-access.md). |
| Validate selected datasets before subset transfers | Implemented | Detects preflight errors before earlier transfers start; does not provide rollback for later failures. See [catalogue lifecycle](runtime.md#63-catalogue-lifecycle). |
| Keep uploaded bytes immutable and publication separate | Implemented | Preserves the meaning of existing paths; maintainers coordinate readiness and catalogue releases. See [licensing and immutability](../licensing.md). |
| Freeze an inventory rather than rebuild it from the copy it describes | Implemented | `ethos:frozen` states that a dataset has no local build input left, so recorded hashes stay an independent witness to the permanent copy; rebuilding from that copy would record its current bytes as correct. `ethos:uploaded` becomes the dCache-specific case of the same thing and is rejected for restricted data. See [file formats](../../reference/schemas.md#where-the-bytes-are). |
| Refuse to link or upload datasets with unresolved licensing | Implemented | Distribution waits for a licence answer while development does not: staging stays open, and reading data already present still only warns. See [licensing and immutability](../licensing.md). |
| Name workflow inputs in the collection and pair test and full selections | Implemented | A collection's `paths:` maps handles to catalogue keys, so a workflow's caller asks for `era5` or `gwa_100m` and never learns a resource key; the handles are a compatibility contract between the package maintainer and the workflow. A `test:` and a `full:` variant must offer the same handles, checked when the collection is resolved, so code that ran on fixtures runs unchanged on the real inputs. Full is the default: a forgotten flag costs a visible download, not a silently wrong result. See [test data](../test-data.md#test-and-full-variants-of-a-collection). |
| Give one link command two modes rather than two commands one planner | Implemented | `ethos-data catalog link-cache` and `ethos-data link --all` drove the same planner, so they could not disagree about the namespace they built, but which of them took an explicit root, which pruned, and what either would do with a restricted dataset had no settled answer. `link --all` is now the only catalogue-wide spelling and carries `--root` and `--prune`. See [one link command, two modes](#one-link-command-with-two-modes-2026-09-17). |
| Read settings from one file per account | Implemented | A script finds its catalogue and caches the same way whichever folder it starts in and however ETHOS.Data was installed. The project, environment and machine-wide files and `--scope` go; `ETHOS_DATA_CONFIG` names a replacement file for CI and jobs. See [one settings file per account](#one-settings-file-per-account-2026-10-02). |
| Treat every input as required, and describe a missing licensed dataset | Implemented | A workflow cannot run without one of its inputs, so `skip_unavailable` goes. The error for a licensed dataset this machine cannot read prints its description, provenance and licence and how to obtain a copy. See [every input is required](#every-input-is-required-2026-10-02). |
| Ship a small public collections file for a self-test | Implemented | `ethos-data selftest` and `ethos_data.EXAMPLE_COLLECTIONS` check settings, catalogue, store and cache with a download of under 200 KB, without any package's collections. See [a self-test collection ships with the package](#a-self-test-collection-ships-with-the-package-2026-10-02). |
| Specify every file format once | Proposed | One pydantic model per file drives validation, typed access, JSON Schemas, templates, the publish strip list, the index row and the reference tables, so a key and its default are written down once. See [every file format is specified once](#every-file-format-is-specified-once-2026-10-02). |
| Record each dataset's state in a status file | Implemented | `datasets/<name>/status.yaml` holds the state, the build input and a history, and the commands check every transition. `source_dir`, `ethos:uploaded` and `ethos:frozen` leave `dataset.yaml`. See [datasets record their state](#datasets-record-their-state-in-a-status-file-2026-10-02). |
| Find files through one lookup chain | Proposed | Root override, staging, bundles, restricted cache, public cache and download are one locator each, and each answers found, pass or refuse. See [one lookup chain](#one-lookup-chain-decides-where-a-file-is-read-2026-10-02). |
| Run catalogue maintenance as pipelines | Implemented, except notices | Accepting, releasing and removing a dataset become commands whose stages plan before they act and record what they did; dCache, downloads, metadata and git sit behind ports. See [catalogue maintenance runs as pipelines](#catalogue-maintenance-runs-as-pipelines-2026-10-02). |
| Version data as revisions or successors | Proposed | A byte-level change becomes a revision of the same dataset under the same keys; a changed layout becomes a successor dataset. Published objects, rather than paths, never change. See [revisions and successors](#revisions-and-successors-2026-10-02). |
| Give the handoffs between roles templates | Proposed | Proposals, answers, problem reports and notices are filled in by `propose`, `report`, `catalog release` and `catalog remove` from templates beside the formats. See [handoffs have templates](#handoffs-between-roles-have-templates-2026-10-02). |
| Separate the model, the services, the adapters and the presentation | Proposed | Library code raises typed errors and reports progress through a reporter; only the command line prints and chooses exit codes. See [four layers](#four-layers-2026-10-02). |

For a new decision that changes an architectural contract, add a dated record
with context, considered alternatives, decision, consequences, and status. Link
it here and update the affected explanation in the same change. Mark proposals
as proposed until implemented; retain superseded records when their history
helps explain compatibility constraints.

## Documentation, test data, and hosting decisions

| Decision | Status | Consequences |
|---|---|---|
| Retain Diátaxis and use exact arc42 sections under Architecture | Adopted documentation structure | Data concepts remains a sibling guide; lifecycle belongs to Runtime View; shared details are linked rather than copied |
| Keep dCache authoritative for centrally published test data | Required design constraint | Repository fixtures retain catalogue identities and hashes; revised published bytes still use new paths |
| Permit explicit temporary divergence in repository test copies | Implemented through repository bundles | Supports bug reproduction without publishing first; ordinary cache integrity and explicit verification keep their existing meaning |
| Serve the internal catalogue from a cluster filesystem path and synchronise through JuGit | Intended deployment | Readers need no Git hosting access; maintainers must review, build, validate, and activate complete metadata snapshots |
| Host public catalogue metadata on GitHub with deliberate versioned releases | Intended deployment | Consumers pin metadata; metadata distribution remains distinct from dataset storage and needs a release process |

The hosting directions do not assert that repositories or releases are already
deployed. Update statuses when implementation and validation establish
the documented behaviour.

## Package wrappers own collection workflows (2026-09-16)

**Status: implemented.** Package collections define workflow selections and
test variants; discovering a separate collections file in the standalone CLI
duplicated that interface and made catalogue choice depend on the working directory.

The standalone CLI now handles direct keys, configuration, shared cache
administration and catalogue maintenance. Consuming packages expose collection,
bundle and staging commands through the common `tool_main` builder. Staging
continues to use shared roots and library logic.

Keeping the generic `-c` route would preserve old scripts but also retain two
collection entry points. The chosen split removes that route and requires
scripts to use a package wrapper or the explicit Python collections API.
See [CLI migration](../../reference/cli/ethos-data.md#tool-command) for replacements.

## One link command with two modes (2026-09-17)

**Status: implemented.** `ethos-data catalog link-cache` and `ethos-data link
--all` were two entrances to one planner. They could not disagree about the
result -- `link --all` already delegated to `namespace.run`, so both built the
same namespace from the same checkout -- but they disagreed about how they were
driven: only `link-cache` accepted an explicit `--root` and could `--prune`,
while `link --all` always built the cache this machine is configured to read and
pruned nothing. Which spelling a script should call, which one removed anything,
and whether a restricted dataset could reach the public cache through either of
them were recurring questions with no good answer, and the shared planner that
settled the last of them was invisible from the command surface that made people
ask.

`catalog link-cache` is removed outright, with no alias and no deprecation shim.
`--all` selects catalogue mode on `link`, and `--root` and `--prune` move onto
`link` with it. `unlink` stays its own verb rather than folding in as `link
--remove`, because removal answers to a different safety rule: `link --force`
exists to repoint an entry that is already a link, whereas `unlink` refuses a
real directory and offers nothing to overrule that refusal. A flag on the
command that creates entries is the wrong home for the rule that protects the
cache's own copies.

Keeping `link-cache` as a hidden deprecated alias, or keeping it visible and
labelled deprecated, were both rejected. A hidden alias keeps the second
entrance working for everyone who already types it while telling nobody it is
going, and a visible deprecated one keeps the two-entrance question alive in the
help output that was supposed to settle it. Making the mode implicit -- a bare
`ethos-data link` meaning the whole catalogue -- was rejected because the
catalogue-wide run is the one that writes many entries at once, and a forgotten
dataset name should not be the invocation that rebuilds a shared cache; a bare
`ethos-data link` instead prints the usage for both modes and exits 2.

A flag belonging to the other mode is now refused rather than quietly ignored:
`--all` with a dataset name, `--all --force`, and `--root` or `--prune` with a
named dataset each exit 2 with an explanation of which mode the offending
argument belongs to. `--dry-run` is the documented exception, stated as such in
the command's own help -- it is accepted with a named dataset and has no effect
there, because a single link applies immediately. The restricted-dataset
asymmetry became a documented property of one command's two modes instead of an
unexplained difference between two commands: catalogue mode does not link a
restricted dataset, because a cache several people read must never hold licensed
bytes nobody reviewed, while naming that dataset deliberately links it into the
restricted cache, which is how an authorised installation is recorded. Scripts
still on the old spelling fail loudly, with argparse's `invalid choice:
'link-cache' (choose from build, publish, upload, check-store)` and exit 2,
rather than a deprecation warning nothing would read. See
[`link`](../../reference/cli/ethos-data.md#link-dataset-directory) for the two
modes and [CLI migration](../../reference/cli/ethos-data.md#tool-command) for
the replacement spelling.

## One settings file per account (2026-10-02)

**Status: implemented.** The settings stay in `ethos_data.config`, which
packages patch in their tests; `Settings` and `read_settings` are the snapshot.

A script such as a package example finds its catalogue and caches through the
settings, so the settings must resolve the same way however the script is
started. The current release reads four files, first match wins: an
`ethos-data.yaml` found by searching upward from the working directory, a file
in the user's account, `<sys.prefix>/etc/ethos-data/config.yaml`, and a
machine-wide file. Three of them depend on something other than the person and
the machine:

- The project file depends on the working directory. The same example,
  started from its own folder, from the repository root by an editor, or from
  a notebook server elsewhere, can read different files. A handle also fixes
  its catalogue when it is built but resolves the caches on every call, so a
  script that changes directory can end up with new caches and the old
  catalogue.
- The environment file depends on the interpreter. In a conda or virtual
  environment it is that environment. After a pip install outside any
  environment it is the system Python's prefix, which is not writable or is
  shared by everything on the machine. With pipx or `uv tool`, `ethos-data`
  runs in an environment of its own, so a setting written there is invisible
  to the scripts.
- The machine-wide file contradicts the cluster deployment, in which every
  user configures their own account.

On Windows the file in the account is
`%LOCALAPPDATA%\ethos-data\ethos-data\config.yaml`, because platformdirs
repeats the application name as the author, which makes it hard to find.

**Decision.** Settings say where data lies for one person on one machine.
Which data a workflow needs, and which catalogue versions it accepts, stays in
the package's collections file. Each setting is resolved from the first of:

1. an explicit argument: `root=` / `--root`, `catalog=` / `--catalog`;
2. an environment variable: `ETHOS_DATA_DIR`, `ETHOS_RESTRICTED_DIR`,
   `ETHOS_STAGING_DIR`, `ETHOS_DATA_CATALOG`, `ETHOS_PUBLICATION_URL`;
3. the settings file: the file `ETHOS_DATA_CONFIG` names, else the file in
   the account;
4. the built-in default: the per-user cache directory for the public cache;
   for the catalogue, the collections file's pin, then the public catalogue.

The file in the account is `~/.config/ethos-data/config.yaml` on Linux
(`$XDG_CONFIG_HOME` respected), `%LOCALAPPDATA%\ethos-data\config.yaml` on
Windows and `~/Library/Application Support/ethos-data/config.yaml` on macOS,
from platformdirs with `appauthor=False`. The default public cache on Windows
moves the same way, to `%LOCALAPPDATA%\ethos-data\Cache`. On Linux neither
path changes.

`ETHOS_DATA_CONFIG` replaces the file in the account rather than merging with
it, so a CI job or a test run is isolated from the account it runs under. The
named file must exist; only `config set-*` creates it, and every other command
stops and names the missing file. The `config` setters and unsetters write to
the settings file in effect and lose `--scope`.

A handle reads every setting once, when it is first used, into one snapshot
with the source of each value, and uses that snapshot for every later call.
Collections and catalogue handles expose it as `settings`. Printing it gives
the settings file, the catalogue location and version, the three caches and
where each came from, so a script can record its inputs next to its results.

**Alternatives considered.** Keeping the four files and fixing the lookup,
by searching for the project file from the running script's folder and
refusing the environment file outside a conda or virtual environment, would
keep a file a team can commit. But a committed file carries one machine's
paths and fails on every other machine, the catalogue version is already
pinned in the collections file, and four places to look remains the source of
confusion. Keeping an environment file beside the account file was rejected
because with pipx, `uv tool` or several environments the command that writes
a setting and the script that reads it run in different interpreters;
`conda env config vars set ETHOS_DATA_CONFIG=...` gives a per-environment
file without ETHOS.Data having to tell environments apart. Merging
`ETHOS_DATA_CONFIG` over the account file was rejected because a test run or
a CI job would then inherit whatever the account has set.

**Consequences.**

- Settings no longer depend on the working directory or the interpreter. The
  same script reads the same settings from an editor, a terminal, a notebook
  or a batch job, and a setting written by any package's data command
  applies to all of them.
- An existing `ethos-data.yaml`, environment file or machine-wide file is
  ignored; `config show` names each one it finds as ignored. The old Windows
  settings file and cache directory are read for one release, with a note
  that names the new location.
- The lesson generator writes its `ethos-data.yaml` for the project scope, and
  [Find data through an internal catalogue](../../tutorials/restricted-access.md)
  uses `--scope project`. Both lessons switch to a lesson file named in
  `ETHOS_DATA_CONFIG`, so they never touch the reader's own settings.
- The configuration reference, the CLI reference and the glossary are
  rewritten with the implementation.

## A self-test collection ships with the package (2026-10-02)

**Status: implemented.** The file is `src/ethos_data/examples/collections.yaml`;
a test keeps the documentation's copy identical to it.

Whether a machine can obtain data at all, with the catalogue readable, the
store reachable and the cache writable, could so far only be checked with a
package's own collections, which may be large, restricted or not installed.

**Decision.** ETHOS.Data ships a small collections file of its own, the
documentation's example file (`docs/assets/examples/collections.yaml`), moved
into the package and exposed as `ethos_data.EXAMPLE_COLLECTIONS`. It selects
public test data of under 200 KB that both the public and the internal
catalogue describe, and pins the public catalogue like any package's file.

`ethos-data selftest` builds a handle on that file and reports three steps:
the settings snapshot, with unreachable caches marked; the catalogue location
and version; and, for every file of every collection in the file, whether it
was downloaded into the public cache, already present or read in place, each
checked against the catalogue's checksums. It ends with `selftest passed` and
exit status `0`, or names the failed step and exits with `1`. It honours the
global `--catalog` and `--root`, so an empty `--root` forces a real download
where the files are already cached or linked.

**Consequences.** The documentation's examples and the self-test share one
file, so a change to it changes both; the copy under `docs/assets/examples/`
is generated from the shipped file or checked against it by a test. The file
must keep naming published public data. A catalogue release that drops it
makes the self-test fail.

## Every input is required (2026-10-02)

**Status: implemented.** The description is
`ethos_data.formats.derived.reader_description`; `--meta` will print the same.

A collection names the inputs of a workflow, and a licensed dataset among them
cannot be downloaded. The current release offers a way past that:
`skip_unavailable=True`, `--skip-unavailable`, the `skip_unavailable` setting
or `ETHOS_SKIP_UNAVAILABLE` leave an unreachable dataset out of the result,
drop its `paths` handle with a warning and record it in `NamedPaths.omitted`.
The error that is raised otherwise names the dataset, prints its
`ethos:restriction` note and suggests skipping.

No workflow treats an input as optional. A dropped handle surfaces as a
`KeyError` deep inside the calculation, or forces every package to branch on
every input, and a skip set once for a machine changes what every workflow on
it computes. What the person who meets the refusal needs is to know what the
dataset is and how to get a copy.

**Decision.** Every input a collection names is required. `skip_unavailable`
is removed from the API (`fetch`, `paths`, `locate`, `download`), the package
data commands (`--skip-unavailable`), the settings (`skip_unavailable`,
`config set-skip-unavailable` and `unset-skip-unavailable`,
`ETHOS_SKIP_UNAVAILABLE`), and with it `NamedPaths.omitted`.

Wherever a restricted dataset cannot be read on this machine, because no
restricted cache is configured, the cache has no entry for it, or the reader
lacks permission, the call raises `AccessError` before anything is downloaded.
The message is built from the dataset's descriptor, each item as far as it is
recorded: `title`, `description` and `version`; `homepage` and `sources`;
`licenses` and `ethos:attribution`; `ethos:restriction`; `ethos:upstream`
status and note; and `ethos:contact`. It closes with the commands that
register a copy: `config set-restricted-cache` and
`link <dataset> <directory>`. `fetch --plan` and `show` only describe, so
they keep listing such data as not available here instead of failing.

**Alternatives considered.** Keeping the skip as an explicit opt-in per call
was rejected: the call then returns a mapping whose keys depend on the
machine, and every caller has to check for each handle, which none does. A
per-input `optional:` flag in the collections file was rejected for the same
reason, and because no workflow has an input it can do without.

**Consequences.**

- Packages that pass the parameter through drop it; RESKit's `reskit.data`
  `fetch` and `paths` do.
- The descriptor fields above become user-facing text, so catalogue
  maintainers write `ethos:restriction`, `homepage` and `sources` for the
  person without a copy.
- A `skip_unavailable` key left in a settings file is ignored, and
  `config show` says so. The lesson generator stops writing it, and
  [Find data through an internal catalogue](../../tutorials/restricted-access.md)
  stops mentioning `ETHOS_SKIP_UNAVAILABLE`.
- The configuration, package-command, API and file-format references, the
  resolution-order diagram and the runtime, crosscutting and context sections
  of this architecture are rewritten with the implementation.

## Every file format is specified once (2026-10-02)

**Status: proposed.** Implemented by the refactoring pull requests; each one
updates the guides it changes.

The formats are described in [File formats](../../reference/schemas.md) as
prose and implemented as dictionary code that repeats every key and its
default. The `public` default for access and visibility is written as a
literal in fifteen places, `dataset.yaml` is read in five places that treat an
empty file differently, and the index row is built twice with different keys:
the published row has no visibility, remote prefix, licence status, version or
`ethos:namespace`, so a published family reads as an ordinary dataset. Nothing
validates a draft `dataset.yaml` before a maintainer builds it, and nothing
helps its author write it.

**Decision.** `ethos_data.formats` holds one specification per standardized
file, written as a pydantic model: `dataset.yaml`, `datapackage.json` and its
shards, the `datacatalog.json` index and its rows, `catalog.yaml`,
`collections.yaml`, `bundle.json`, the settings file, the staging registry,
the dataset status file, the materialization record and the handoff texts.
Each field declares its type, its default and when it is required, and four
properties:

| Property | Means |
|---|---|
| `published` | kept by `publish`; a field without it is stripped from the published catalogue |
| `promoted` | copied into the index row, so reading it needs no descriptor |
| `user_facing` | printed by `--meta` and by the error for a licensed dataset this machine cannot read |
| `inherited` | taken from the enclosing family's `dataset.yaml` when the member does not set it |

From that one declaration come the validation, which reports every problem at
once with its place in the file; typed access in the code; the JSON Schemas
shipped with the package, which give editors completion through a
`# yaml-language-server: $schema=` line; the strip list `publish` applies and
its leak check derives; the index row that `build` and `publish` share; the
error text; and the reference tables in File formats.

The files people write have templates beside their specifications, in
`ethos_data/formats/templates/`: `dataset.yaml` for downloaded, derived,
created and restricted data and a minimal one for staging, `catalog.yaml`,
`collections.yaml`, the settings file and the handoffs. Every command that
creates such a file starts from its template, every template is validated by
a test, and the documentation includes the templates instead of copying them.

Known keys are validated. The rules the build already enforces stay errors,
with their messages. What the specifications add, a value of the wrong type or
outside a closed vocabulary, is reported as a warning at first, so a catalogue
that built before builds after; a later release can make the warnings errors.
Unknown keys pass through as they do today, and the build lists an unknown
`ethos:` key as a warning, since it is usually a typo. Keys the catalogue used
before the reference named them, such as `ethos:provenance` and
`ethos:tiling`, become part of the format. Generated files stay byte-identical:
the specifications fix the order of keys, and the tests round-trip every
generated fixture.

**Alternatives considered.** Dataclasses with a validator of our own would
avoid the dependency but add some 400 lines to maintain and give poorer
messages. JSON Schema files with the `jsonschema` library would keep the
specification as data, but the rules that cross fields, such as derived data
needing sources and a derivation, read badly in it, and the code would still
need typed access.

**Consequences.**

- `pydantic>=2` becomes a dependency, in `pyproject.toml`, `environment.yml`
  and the conda-forge recipe. The formats are imported when a file is read,
  so `--help` stays fast.
- File formats is partly generated from the specifications.

## Datasets record their state in a status file (2026-10-02)

**Status: implemented.** Every command that takes a step records it, and
`catalog release` adds a release step to every dataset that changed.

A dataset's progress through the catalogue is implicit in its
`dataset.yaml`: whether `source_dir` is there, and `ethos:uploaded` and
`ethos:frozen`. Nothing records that an upload was verified, when the
provenance was last checked, or which release first held the dataset, and no
command checks that a step is allowed: access can change after an upload, and
`ethos:uploaded: true` is a hand edit nothing verifies.

**Decision.** Every dataset in a source catalogue has a
`datasets/<name>/status.yaml`, written by the `catalog` commands and never
published. It holds the dataset's state and revision, its build input
(`source_dir`) while it has one, where its authoritative copy is once it is
frozen, and an append-only history: what was done, by whom and when, with the
upload report, the release and the result of a provenance check.

| State | Means | Reached by |
|---|---|---|
| `draft` | described, not built | `catalog add` |
| `built` | inventory built from `source_dir`; a rebuild keeps the state | `catalog build` |
| `available` | bytes reachable for the access class: uploaded and verified, linked, or registered | `catalog upload`, `ethos-data link`, `ethos-data materialize` |
| `frozen` | inventory final, no build input left, authoritative copy recorded | `catalog record` |
| `withdrawn` | out of the catalogue; bytes not yet deleted | `catalog remove` |
| `purged` | bytes deleted after the release that dropped the dataset; the directory goes | `catalog remove --purge` |

The commands check each transition against the state: licensing must be
settled before an upload or a link, restricted data is never uploaded, a
dataset is frozen only with a verified copy, and bytes are purged only when
the latest release no longer lists the dataset. A frozen dataset rebuilds its
metadata only; changed bytes start a new [revision](#revisions-and-successors-2026-10-02).
Releases are a second dimension: the history names the release that holds
each change, so `catalog status` can show what is not released yet.

`dataset.yaml` describes the dataset and nothing else: `source_dir`,
`ethos:uploaded` and `ethos:frozen` move into the status file. `catalog
migrate` writes the status files of an existing catalogue from those keys and
removes them from `dataset.yaml`; until then the build still reads them, with
a warning. `catalog status` lists every dataset with its state and next step,
and `catalog status --check` compares the record with the evidence: an
inventory that is current, a cache entry that exists, objects that dCache
serves.

**Alternatives considered.** Deriving the state from today's keys needs no new
file but leaves no place for a history. A state key inside `dataset.yaml`
would have the tools rewrite a hand-written file and lose its comments.

**Consequences.** The guides change where they say to set
`ethos:uploaded: true` and remove `source_dir`: that is `catalog record` now.
A proposal's draft may still name `source_dir`; `catalog add` moves it into
the status file.

## One lookup chain decides where a file is read (2026-10-02)

**Status: implemented, except the bundle locator,** which arrives with
repository-first bundles. The chain is `ethos_data.access.chain_for`, the
catalogue resolver `Settings.choose_catalog`.

Where a file is read is decided by one long function, and package bundles are
not part of it: a package that ships its test data has to implement
bundle-first reads, a download switch and a catalogue override of its own,
and RESKit does. Settings are read again on every call, and the catalogue is
chosen by three separate implementations.

**Decision.** Lookup is a chain of locators, each of which looks in one place:

1. a dataset-root override in the settings, read in place;
2. the personal staging root, never for restricted data, read in place
   without checksums and with a warning;
3. the package's bundles, read in place and hash-checked once per process,
   unless `download=True` or `ETHOS_DATA_DOWNLOAD=1` skips them;
4. the restricted cache, for restricted data only;
5. a link in the public cache, read in place;
6. a copy already in the public cache;
7. a download from the publication root, for public data only.

Each locator answers *found*, *pass* or *refuse*. A refusal ends the chain,
which is what keeps a restricted file without an installation, or a bundled
file that is missing or altered, from ever falling through to a download. The
chain is built once per handle from the settings snapshot and touches only
the file system. `plan`, `paths`, `fetch`, `verify` and `show` use the same
chain, and `config show` prints it. Whether a file that would have to be
downloaded is downloaded is the caller's choice: `fetch=False` raises instead,
naming the path the file belongs at. The settings and the catalogue are
resolved by the same pattern, an explicit argument, the environment, the
settings file and a default in that order, which replaces the three
implementations.

The overrides come first because they are explicit statements of one person;
bundles come before the caches because the repository is the source of truth
for its test data; restricted data refuses before the public cache is
consulted.

**Consequences.** `bundles=`, the download switch and `fetch=False` become
options of the chain rather than package code.

## Catalogue maintenance runs as pipelines (2026-10-02)

**Status: implemented, except notices.** Accepting, freezing, releasing,
removing and purging, and checking provenance run as pipelines through ports
with fakes, and the store's settings come from `catalog.yaml`. The notices a
release and a removal send come with the handoff templates. A release is a
command a maintainer runs; which CI runs it on a tag is still open.

Adding, releasing and removing a dataset are sequences of commands and hand
edits in the guides, and their order is the maintainer's to remember: bytes
are deleted only after the release that drops their metadata, and a release
waits for verified uploads. Library functions print, exit the process and
take parsed command-line arguments, so they can be neither composed nor
tested without the command line.

**Decision.** Each maintainer workflow is a pipeline of stages. A stage
declares the states it applies to, plans its actions without side effects,
which is its dry run, carries them out through ports, verifies the result and
records the transition in the status file. A pipeline plans the whole batch
before its first side effect, as `upload` already does, and can resume from
the status files.

| Workflow | Command | Stages |
|---|---|---|
| Accept | `catalog add SOURCE` | intake from a draft or a bundle, validate, place, build |
| Make the bytes available | `catalog upload`; `ethos-data link` and `materialize` with `--catalog-root` | transfer or link, verify, record |
| Freeze | `catalog record NAME` | check the copy, move the build input out, keep the inventory |
| Release | `catalog release VERSION` | build check, publish check with the leak check, version stamp, commit and tag, public catalogue, copy to dCache, notices |
| Remove | `catalog remove NAME`, then `--purge` | metadata out, release, cache entries, bytes |
| Check provenance | `catalog check-source NAME DIR` | hash a re-download, compare, record |

External systems are ports with one adapter each and a fake for the tests:
the dCache store (rclone, its REST interface and anonymous HTTP), the
downloader, the metadata source (file or HTTP, with the metadata cache as a
decorator) and git. The store's remote, path and REST endpoint come from
`catalog.yaml`, with today's values as defaults, instead of from the code.

**Consequences.** Removal and release stop being manual. The checkout on the
cluster computer is updated there by `catalog update-checkout`, because a CI
runner elsewhere cannot reach it.

## Revisions and successors (2026-10-02)

**Status: proposed.** Implemented by the refactoring pull requests.

Published paths never change, so changed bytes need new paths, which somebody
has to choose by hand; [Keep data in the repository](../../how-to/package-maintainers/keep-data-in-the-repository.md#sync)
leaves open how two versions of a bundle share a cache. Some datasets change
at the byte level and keep their layout; others gain folders, move files and
replace most of them, so that an automatic version would share little with
the one before.

**Decision.** There are two kinds of new version.

| | Revision | Successor |
|---|---|---|
| For | the same layout, files changed at the byte level, perhaps a few added | a changed layout: folders added, files moved, mostly new files |
| Made by | editing the files in place in a bundle, or pointing the build at the corrected source; `bundle update` or `catalog build --revision` numbers it | a new dataset under a name its author chooses, with `ethos:supersedes: <old name>` in its description |
| Keys | unchanged; a catalogue release names one revision of each dataset | new; named handles keep the workflow code unchanged |
| Older version | readable through older releases | stays as its own dataset and is shown as superseded |

`bundle update` reports the files that changed, appeared, disappeared or
moved, and suggests a successor when files disappear, because a key that
disappears breaks every collection that names it. The person decides.

A revision is part of where the bytes are stored: published objects never
change. Each resource records its object path on dCache, by default
`<remote_prefix>/<path>`; a revision from the second on publishes its changed
and new files under `<remote_prefix>@<revision>/` and keeps the objects of
unchanged files. In a cache, the first revision keeps the entry `<dataset>/`
and a later one gets `<dataset>@<revision>/`, whose unchanged files are linked
or copied from the previous entry where it exists. `ethos:revision` is
assigned by the tools; `version` stays the publisher's own release string.
Revisions need bytes the catalogue controls, uploaded or materialized; a
dataset that is only linked changes in place with its source.

**Consequences.** The guides that say changed bytes need new paths change. A
revision needs no change to any collections file; a successor needs new keys
under the same handles.

## Handoffs between roles have templates (2026-10-02)

**Status: proposed.** Implemented by the refactoring pull requests.

What one role hands another, the blue arrows in the
[use-case figure](../../how-to/index.md#roles-together), is free text today: a
proposal, the answer to it, a problem report, the notice of a release or a
removal. The guides list what each must contain, and the person writing it
has to collect those facts by hand.

**Decision.** Each handoff has a template among the formats, and commands fill
it from what the tools already know:

- `<your-tool>-data propose DIR` checks a draft `dataset.yaml`, or a bundle,
  against its specification, inventories the bytes, warns when they are still
  writable, and prints the text of the proposal with the items
  [Propose a dataset](../../how-to/package-maintainers/propose-a-dataset.md#4-submit)
  asks for;
- `ethos-data report` runs the self-test, the settings and the plan and prints
  the [report](../../how-to/data-users/report-a-problem.md#report-a-problem),
  with tokens and personal paths removed;
- `catalog release` drafts the release notice and the answer to every
  proposal the release accepted, and `catalog remove` drafts the removal
  notice.

The same templates serve as issue templates in the catalogue repositories.

## Four layers (2026-10-02)

**Status: implemented.** Typed errors, the reporter and the adapters are in:
library code neither prints nor exits, and dCache, downloads and git sit
behind ports with fakes. The command line is still one module, now of parsing,
wiring and printing only.

The reader imports the writer, library code prints and exits the process,
and the command line is one module of 1,700 lines that also holds logic.

**Decision.** The package has four layers, and each imports only from the
ones below it:

| Layer | Modules | Holds |
|---|---|---|
| Model | `formats`, `model` | specifications, keys, resources, descriptors, versions, the state machine; no input or output |
| Services | `settings`, `access`, `retrieval`, `bundles`, `staging`, `cache`, `maintain` | lookup, fetching, verification, the pipelines; external systems only through ports |
| Adapters | `adapters` | dCache, downloads, metadata sources, git, each with a fake |
| Presentation | `cli`, the package facade | parsing, wiring, printing, exit codes |

Library code raises the typed errors of `ethos_data.errors`, whose existing
names stay, and reports progress through a reporter; only the command line
prints and decides an exit code. The public API, `collections`, `catalog`,
`tool_main`, `load_bundle`, `verify` and the handles, keeps its names.
