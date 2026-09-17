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
| Report what the cache holds, not only what the plan would do | Implemented | `ethos-data link --all` reported a reclassified dataset as `skip` while its link stayed live, so the one line that mentioned licensed bytes in a shared cache read as "nothing to do" and the run still exited 0. Findings about the cache are now their own verbs and set exit 1; `--prune` removes the link. See [a namespace finding is not a skip](#a-namespace-finding-is-not-a-skip-2026-09-17). |
| Give one link command two modes rather than two commands one planner | Implemented | `ethos-data catalog link-cache` and `ethos-data link --all` drove the same planner, so they could not disagree about the namespace they built, but which of them took an explicit root, which pruned, and what either would do with a restricted dataset had no settled answer. `link --all` is now the only catalogue-wide spelling and carries `--root` and `--prune`. See [one link command, two modes](#one-link-command-with-two-modes-2026-09-17). |
| Tell the namespace planner what its root is, rather than let it infer | Implemented | Retracting a restricted link is right in this machine's public cache and destroys an authorised installation in a restricted one, and the two are the same filesystem object. The root's kind is now a required argument with no default: `--prune` retracts a restricted link only where the run can say the directory is a public cache, and `link --all` refuses the restricted cache outright. The cost is that `link --all --root DIR --prune` no longer clears such a link, and that a withdrawn licence in the restricted cache has no automated reporter. See [a namespace root says what it is](#a-namespace-root-says-what-it-is-2026-09-17). |
| Define "a directory the cache owns" by content, not by existence | Implemented | A prefix directory left empty when a family was withdrawn was reported `keep`, so a dataset the catalogue declares at that name never got an entry and the run still exited 0. Ownership is now "holds a file of its own at any depth, not counting anything under a link", and `--prune` clears an emptied prefix with `rmdir` under the verb `replace`. This is the only real directory the command removes. See [an emptied prefix is not data the cache owns](#an-emptied-prefix-is-not-data-the-cache-owns-2026-09-17). |

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
restricted cache, which is how an authorised installation is recorded. Skipping
it turned out to be only half of that -- see [a namespace finding is not a
skip](#a-namespace-finding-is-not-a-skip-2026-09-17) for what the catalogue mode
does when the cache already holds the dataset. Scripts
still on the old spelling fail loudly, with argparse's `invalid choice:
'link-cache' (choose from build, publish, upload, check-store)` and exit 2,
rather than a deprecation warning nothing would read. See
[`link`](../../reference/cli/ethos-data.md#link-dataset-directory) for the two
modes and [CLI migration](../../reference/cli/ethos-data.md#tool-command) for
the replacement spelling.

## A namespace finding is not a skip (2026-09-17)

**Status: implemented.** `ethos-data link --all` planned the namespace it wanted
and reported that plan. Anything it had decided not to do was a `skip`, and the
run exited 0 as long as every link it did plan could be made. That is a fair
description of a fresh cache and a poor one of a cache that has been rebuilt for
a year, because the interesting cases are all disagreements between the
catalogue as it is now and a cache built from the catalogue as it was.

Three of them were silent. A dataset reclassified `ethos:access: restricted`, or
whose licence was withdrawn to `ethos:license_status: unresolved`, was excluded
from the plan and reported `skip` -- while the link the same command made last
week went on serving those bytes to everybody reading the cache, under a line
that reads as though the dataset had never been there. A stale link standing
where a namespace prefix now belongs was written straight through, because
creating a parent directory succeeds on a symbolic link, so the cache's own entry
landed inside another project's tree and was counted as made. And a filesystem
that refused to create a link -- Windows without Developer Mode, the likeliest
first run there is -- ended the whole run in a traceback, with the entries after
it never attempted and no summary at all.

The decision is that the planner reports the **cache**, not only its own
intentions, and that the exit code follows one rule: 0 means every dataset the
catalogue names has an entry where its name says or was deliberately skipped, 1
means the namespace was built as far as this machine allowed and something is
left for a maintainer to fix here. The findings became verbs of their own --
`exposed` and `retract` for a reclassified dataset, `blocked` for an entry that
would land inside borrowed data, `failed` for one the filesystem refused -- so
the report says which of the four it is and the closing paragraph says what to do
about each.

Removal stayed behind `--prune`, the one flag that deletes, rather than becoming
automatic on a finding this serious. A command that removes cache entries without
being asked is a worse failure mode than a loud one that does not, and `--prune`
already carried the safety rule that makes the removal defensible: only a
symbolic link is ever unlinked, so nothing is discarded. The same rule is why a
real directory holding licensed data is still only reported -- it is the only
copy of those bytes, and deleting it on the strength of an edit to a
`dataset.yaml` is not something this command may do.

The consequence is a breaking change for scripts. A nightly `ethos-data link
--all` under `set -e` now fails on a cache that holds a reclassified dataset, a
stale prefix link, or on a machine that cannot make symbolic links, where it
previously exited 0. That is the alarm working, and the remedy is one flag:
`--prune` on the rebuild invocation removes the link instead of reporting it. See
[`link`](../../reference/cli/ethos-data.md#link-dataset-directory) for the verbs
and the exit codes, [Read the report before re-running](../../how-to/link-cluster-data.md#read-the-report)
for the operational version, and [writing below a link](../caches-and-access.md#writing-below-a-link-is-still-writing-through-it)
for why an entry under a borrowed prefix is refused rather than made.

## A namespace root says what it is (2026-09-17)

**Status: implemented.** The record above gave `--prune` the power to retract a
link for a dataset the catalogue has reclassified. That is the right move in the
cache the rule was written for — this machine's own public cache — and it was
applied to whatever directory `--root` happened to name. `--root` is how one
administrator fills several machines' caches from one checkout, which is the
migration these guides describe, so the rule was being applied to directories
this installation knows nothing about.

The two cases are the same filesystem object and opposite facts. A restricted
dataset linked in a public cache is licensed bytes served to everybody who reads
that cache. The identical link in a restricted cache is one authorised
installation, put there on purpose by `ethos-data link <dataset> <directory>` —
the thing that command exists to record. A `--prune` that cannot tell them apart
deletes the registration, reports it as a cleanup, and the person who finds out
is whoever runs the job that needed the data.

Three alternatives were weighed. **Infer it from the path**: compare the root
against the configured restricted cache inside the planner. That answers "not a
restricted cache *I* have been told about", which is a different question — a
cache belonging to another machine matches nothing here, and the answer that
comes back is the one that deletes. **Never retract a restricted link, only
report it**: rejected because reclassification is the only way licensed bytes
ever reach a public cache, and an unattended rebuild that clears it is the reason
the finding was introduced at all. **Default the answer to "public cache"**:
rejected because a default is exactly how a deletion gets justified by an
assumption nobody made out loud.

The decision is that the planner is *told* what the root is, by the caller that
has already resolved the configuration, and that the argument is required with no
default — a caller that has not decided gets a `TypeError`, not a removal. There
are three answers:

| The root is | What `link --all` does with a restricted link in it |
|---|---|
| this installation's public cache | reports `exposed`; `--prune` retracts it, as before |
| a directory this installation cannot identify | reports `exposed` and removes nothing, whatever `--prune` says; the closing paragraph gives both readings and prints the spelling to use if it is a public cache after all |
| this installation's restricted cache | refuses before reading the checkout, exit `2` |

A directory becomes "this installation's public cache" by being the configured
one, or by being named in the **top-level** `--root`, which sets the public cache
for the whole invocation. `--root` after `link` names a destination and claims
nothing about it, so it does not license a removal. An unresolved **licence** is
exempt from all of this and is retracted wherever the run happens: no namespace
anywhere is improved by holding a dataset whose terms nobody has read, so that
removal needs no knowledge of which namespace this is.

The consequences are three, and two of them are losses. `ethos-data link --all
--root DIR --prune` no longer clears a restricted exposure; the spelling that
does is `ethos-data --root DIR link --all --prune`. A script on the old spelling
keeps running and keeps exiting `1`, removing nothing restricted, until the flag
moves — loud, but it is a behaviour change. Refusing the restricted cache
outright means `link --all` never inspects it again, so an installation whose
licence is withdrawn after it was registered has no automated reporter; the mode
had no legitimate action to take there, but nothing currently replaces that
coverage. And a directory nobody can identify still has stale *names* pruned: if
it really is another machine's restricted cache holding an entry for a retired
dataset, that registration goes. It was kept because withholding it breaks the
documented cluster rebuild, and because no bytes are lost — one command puts the
registration back.

A separate contract settled in the same change: **a preview does not predict the
exit code, on purpose.** `link --all --prune --dry-run` returns `1` where the
identical run without `--dry-run` returns `0`, because a preview removed nothing
and the exposed link is still being served the moment the process exits — and the
exit code is the only part of a run an unattended rebuild reads. The asymmetry is
confined to exposures: a `link` or a `replace` that a dry run did not carry out is
work left undone rather than a standing wrong, and those do not set the code.

See [Removing an exposure depends on what the root
is](../../reference/cli/ethos-data.md#namespace-authority) for the behaviour,
[Read the report before re-running](../../how-to/link-cluster-data.md#read-the-report)
for the operational version, and [licensing](../licensing.md#a-licence-withdrawn-after-the-cache-was-built)
for why the licence case needs none of it.

## An emptied prefix is not data the cache owns (2026-09-17)

**Status: implemented.** A real directory in the cache is the only copy of those
bytes, so no command replaces one with a link. That rule was enforced by asking
whether the path exists and is a directory, which is not the same question.

`--prune` removes `<cache>/family/member` and cannot remove `<cache>/family` with
it: that is not an entry, so nothing ever plans a `prune` for it. What is left is
a husk — a namespace prefix this tool created itself, holding nothing anybody
downloaded. The day the catalogue collapses that family back into one flat
dataset, the husk stands exactly where the dataset's entry belongs, and the
existence test called it `keep`, "a real directory the cache owns", on every run
for ever: a line reading as correct, an exit code of `0`, and a declared dataset
with no entry on any rerun.

The decision is to define ownership by content rather than by existence: a
directory the cache owns is one holding a file of its own **at any depth**, not
counting anything under a symbolic link, because those bytes are borrowed. It is
the same rule the cache listing already used to tell a downloaded dataset from a
directory that merely holds other names, so both halves of the cache now agree
what the phrase means. A directory that cannot be listed counts as owned — "I
could not look" and "there is nothing here" are the same answer only to a command
that deletes on the strength of it.

A husk is therefore removable, and `--prune` removes it under a verb of its own,
`replace`, then links the dataset there. Without `--prune` it is reported
`obstructed` and nothing is written. This is the first and only real directory
this command removes, so the safety is spelled out rather than assumed: `rmdir`
only and never a recursive delete, deepest first, never through a symbolic link,
emptiness re-checked at the moment of removal, and `--prune` as the only flag that
plans it. A planner that gets it wrong costs an entry reported `failed`, because
the operating system refuses to `rmdir` a directory that is not empty. Anyone
changing one of those five is changing what this command can destroy.

See [downloads never write through a link](../caches-and-access.md#downloads-never-write-through-a-link)
for the ownership rule and [what `--prune` removes](../../reference/cli/ethos-data.md#namespace-prune)
for the verbs.
