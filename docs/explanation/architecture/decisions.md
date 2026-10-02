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
| Read settings from one file per account | Proposed | A script finds its catalogue and caches the same way whichever folder it starts in and however ETHOS.Data was installed. The project, environment and machine-wide files and `--scope` go; `ETHOS_DATA_CONFIG` names a replacement file for CI and jobs. See [one settings file per account](#one-settings-file-per-account-2026-10-02). |
| Treat every input as required, and describe a missing licensed dataset | Proposed | A workflow cannot run without one of its inputs, so `skip_unavailable` goes. The error for a licensed dataset this machine cannot read prints its description, provenance and licence and how to obtain a copy. See [every input is required](#every-input-is-required-2026-10-02). |
| Ship a small public collections file for a self-test | Proposed | `ethos-data selftest` and `ethos_data.EXAMPLE_COLLECTIONS` check settings, catalogue, store and cache with a download of under 200 KB, without any package's collections. See [a self-test collection ships with the package](#a-self-test-collection-ships-with-the-package-2026-10-02). |

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

**Status: proposed.** To be implemented separately; the how-to guides already
describe the result, with Gap boxes where the code differs.

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

**Status: proposed.** To be implemented separately; the how-to guides already
describe the result, with Gap boxes where the code differs.

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

**Status: proposed.** To be implemented separately; the how-to guides already
describe the result, with Gap boxes where the code differs.

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
