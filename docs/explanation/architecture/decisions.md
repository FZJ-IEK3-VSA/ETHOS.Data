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
