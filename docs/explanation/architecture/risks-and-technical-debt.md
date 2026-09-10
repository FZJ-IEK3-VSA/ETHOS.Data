# 11. Risks and Technical Debt

These are known boundaries and open design questions. Resolving one requires
updating its related [quality scenario](quality-requirements.md) and runtime
explanation as well as code and validation.


- **Reproducibility depends on retention.** Catalogue pins do not prevent remote
  deletion or mutation by a hosting operator. Local roots and staging can also
  contain bytes different from a manifest; ordinary in-place fetch checks existence.
- **A batch upload is not atomic.** Transfer or verification failures can leave
  completed uploads behind. Public catalogue generation has no shared transaction
  with those transfers. Maintainers must review readiness before release.
- **Internal verification needs a distinct success criterion.** The current
  uploader checks anonymous readability even for allowed internal uploads. The
  operational consequence is a failed verification result for deliberately private
  bytes. An authenticated verification mode is an open design question, not an
  implemented capability.
- **Reader authentication is separate from upload authentication.** Retrieval
  uses Pooch without configuring the uploader's oidc-agent flow. Local roots are
  needed where the ordinary download interface cannot access internal files.
- **Remote size checks are not content audits.** Anonymous HEAD verification
  does not establish that remote bytes match the manifest hash. Download verification
  and explicit local verification address different stages of integrity.
- **Shared storage remains an external dependency.** Permissions, broken links,
  concurrent writers, and remote availability require operational care. This guide
  does not promise lock-based coordination or a measured concurrency guarantee.
- **Performance targets are not yet quantified here.** Lazy loading is a mechanism;
  a latency or memory target needs an agreed workload and measurement environment.
- **Repository bundle scope is deliberately limited.** Export currently accepts
  public, non-staged catalogue resources. Fixture updates use a new directory for
  review; no background synchronisation repairs or republishes developer edits.
  Large data and live service behaviour belong in separate integration tests.
  Installed-package fixture distribution needs explicit package-data inclusion.
- **A mutable cluster checkout can expose mixed metadata revisions.** Serving a
  versioned generated snapshot and switching the published path after validation
  avoids readers observing files partway through an update. Synchronisation with
  JuGit and activation of a cluster snapshot remain operational steps.
- **Catalogue hosting does not remove all request limits.** Pinned metadata and
  local snapshots reduce repeated requests. Release generation, retention,
  distribution, and any client refresh behaviour still need an explicit process.

When resolving a limit, update its scenario and explanation together. A proposed
improvement becomes a guarantee only when implementation and validation support it.
