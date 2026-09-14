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
