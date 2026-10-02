# 11. Risks and Technical Debt

These are known boundaries and open design questions. Resolving one requires
updating its related [quality scenario](quality-requirements.md) and runtime
explanation as well as code and validation.

## Risks

- **Reproducibility depends on retention.** Catalogue pins do not prevent remote
  deletion or mutation by a hosting operator. Local roots and staging can also
  contain bytes different from a manifest; ordinary in-place fetch checks existence.
- **A batch upload is not atomic.** Transfer or verification failures can leave
  completed uploads behind. A release refuses a public dataset without a
  verified upload, but upload and release share no transaction.
- **Internal verification needs a distinct success criterion.** The current
  uploader checks anonymous readability even for allowed internal uploads. The
  operational consequence is a failed verification result for deliberately private
  bytes. An authenticated verification mode is an open design question, not an
  implemented capability.
- **Reader authentication is separate from upload authentication.** Retrieval
  downloads through the `Downloader` port, Pooch by default, without the
  uploader's oidc-agent flow. Local roots are needed where the ordinary
  download interface cannot access internal files.
- **Remote size checks are not content audits.** Anonymous HEAD verification
  does not establish that remote bytes match the manifest hash. Download verification
  and explicit local verification address different stages of integrity.
- **Shared storage remains an external dependency.** Permissions, broken links,
  concurrent writers, and remote availability require operational care. This guide
  does not promise lock-based coordination or a measured concurrency guarantee.
- **Performance targets are not yet quantified here.** Lazy loading is a mechanism;
  a latency or memory target needs an agreed workload and measurement environment.
- **Repository bundle scope is deliberately limited.** A repository bundle holds
  one family of test data; export accepts public, non-staged catalogue
  resources. No background synchronisation repairs or republishes developer
  edits. Large data and live service behaviour belong in separate integration
  tests. Installed-package fixture distribution needs explicit package-data
  inclusion.
- **An updating cluster checkout can expose mixed metadata revisions.**
  `catalog update-checkout` fast-forwards the served checkout in place, so a
  reader listing the index during the update can find inventories of the other
  release. Run it when no jobs read the checkout; serving each release from its
  own directory behind a switched link would remove the risk, and is not
  automated.
- **Catalogue hosting does not remove all request limits.** Pinned metadata and
  local snapshots reduce repeated requests. Retention, distribution, and any
  client refresh behaviour still need an explicit process.

## Technical debt

- **The command line is one large module.** `cli.py` holds parsing, wiring and
  printing only, but about 2,000 lines of it for `ethos-data` and the package
  commands together. Splitting it per command group is open.
- **One import goes up a layer.** `Collections.main()`, the package command a
  handle can run, imports the command line when called. `tests/test_layers.py`
  lists it as the rule's only exception.
- **Readers of older files stay for one release.** The build still reads
  `source_dir`, `ethos:uploaded` and `ethos:frozen` in a `dataset.yaml` without
  a status file, with a warning, until `catalog migrate` moves them; the
  settings file and cache at the old Windows location are read while the new
  one does not exist; exported bundles keep the first bundle format. Each
  reader goes in a later release.
- **What the specifications add is a warning, not yet an error.** A value of
  the wrong type or outside a closed vocabulary, such as an `ethos:upstream`
  status the format does not know, is reported by the build and does not stop
  it, so a catalogue that built before still builds. A later release can make
  these errors.
- **A release is a command a maintainer runs.** Which CI runs
  `catalog release` on a tag is still open.
- **The internal tracker's issue templates are not written by a command.**
  `publish` writes the public catalogue's from the handoff templates;
  `handoffs.issue_template` produces the same for the internal repository,
  which nothing writes there yet.

When resolving a limit, update its scenario and explanation together. A proposed
improvement becomes a guarantee only when implementation and validation support it.
