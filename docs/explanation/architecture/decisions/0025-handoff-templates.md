# 0025. Draft the handoffs between roles from templates

**Status:** implemented · **Date:** 2026-10-06 · **Implemented by:** #26

## Context

What one role hands another, a proposal and its answer, a problem report, the
notice of a release or a removal, must contain facts the tools already know.
Collected by hand, they arrive incomplete. Issue forms and commands must ask
for the same things, and a report must not leak tokens or personal paths.

## Decision

Each handoff has one Markdown template in
`ethos_data/formats/templates/handoffs/`, and the command that knows the facts
fills it:

| Handoff | Drafted by | Contents |
|---|---|---|
| Proposal | `<tool>-data propose DIR`, for a draft or a bundle | the draft checked as the build would check it; its inventory after `ethos:include` and `ethos:exclude`; files still writable, with the `chmod` to run; the kind (new dataset, revision or successor); the package's collections that name it; the tracker. For a bundle, the proposal covers the datasets that are ahead of the catalogue ([0021](0021-bundles-ahead-of-the-catalogue.md)), and every file must match `bundle.json`. |
| Problem report | `report`, a library function behind `ethos-data report` and `<tool>-data report` | the self-test, the settings, the collections, the plan with the state of every listed restricted cache, and a `verify` by size, with tokens, credentials in URLs, the home directory and the account name removed |
| Release notice and answers | the `notices` stage of `catalog release` | what the release added, revised, superseded and withdrew; one answer per added dataset |
| Removal notice | the `notices` stage of `catalog remove` | the reason, the last release that describes the dataset, and its successor if it has one |
| Issue templates | `catalog publish` | `propose-a-dataset` and `report-a-problem` for the public catalogue's tracker |

- Notices are printed, and written to files with `--notices DIR`.
- The tracker follows the access class: the internal tracker on JuGit for
  restricted data and for reports from a cluster installation, the public
  catalogue's tracker on GitHub otherwise. Cluster paths, restricted details
  and broken links in the cluster's public cache go to JuGit only.
- People post the drafts. ETHOS.Data writes nothing to a tracker.

## Alternatives considered

- **Free text with checklists in the guides.** The person writing would
  collect the facts by hand, and forms and guides would drift apart.

## Consequences

- Forms and commands ask for the same things, because they come from the same
  templates.
- No command writes the internal tracker's issue templates: they are
  generated from the same templates and committed once by hand.
- See [How the roles work together](../../../how-to/index.md#roles-together),
  [Propose a dataset](../../../how-to/package-maintainers/propose-a-dataset.md)
  and [Report a problem](../../../how-to/data-users/report-a-problem.md).

## Related

- [0015. Let each package's data command own its collection workflows](0015-package-commands-own-collections.md)
- [0017. Ship a self-test collection with the package](0017-self-test-collection.md)
- [0021. Let a bundle be ahead of the catalogue, and warn until it is realigned](0021-bundles-ahead-of-the-catalogue.md)
- [0023. Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [3. Context and Scope](../context.md)
- [6. Runtime View](../runtime.md)
