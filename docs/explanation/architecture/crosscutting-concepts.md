# 8. Crosscutting Concepts

These rules apply across the building blocks. The linked Data concepts pages
are the canonical detailed explanations, avoiding a second account of the same
behaviour inside Architecture.

| Concept | Shared rule | Canonical explanation or reference |
|---|---|---|
| Identity and paths | `<dataset>/<resource path>` connects selection, cache reuse, verification, and upload; a revision keeps the keys and changes only where the bytes are, `<remote_prefix>@<revision>/` on the store and `<dataset>@<revision>/` in a cache | [Why one catalogue](../deduplication.md); [Publish a new version](../../how-to/catalogue-maintainers/publish-a-new-version.md) |
| Configuration and location | One lookup chain decides where a file is read: explicit and configured roots, staging, bundles, the access class and filesystem state, each a locator that finds, passes or refuses | [Caches, classes and roots](../caches-and-access.md); [where a file is read](../../reference/configuration.md#lookup-order) |
| Metadata representation | Every file format is specified once, as a model in `ethos_data.formats`; validation, the JSON Schemas, the templates, the publish strip list and the reference tables come from it. Internal inventories and the public view share a reader contract; descriptors and shards are lazy | [Catalogue format](../catalogue-format.md); [File formats](../../reference/schemas.md) |
| Integrity | Download-managed and bundled files are hash-checked; ordinary in-place access checks existence; explicit verification serves a separate purpose | [Runtime View](runtime.md#61-data-request); [verify and repair](../../how-to/data-users/verify-and-repair.md) |
| Access and publication | Visibility determines metadata publication; access determines how bytes may be used; a key the specifications mark as never published is stripped, and the leak check looks for it | [Licensing and immutability](../licensing.md) |
| Reproducibility | A package names the catalogue releases it works with; published objects never change; development overrides and changed local test copies are declared | [Licensing and immutability](../licensing.md); [quality scenarios](quality-requirements.md) |
| Errors and required data | Every input is required. Library code raises the typed errors of `ethos_data.errors` and reports progress through a reporter; only the command line prints and chooses the exit status each error has | [Errors](../../reference/api/errors.md); [Runtime View](runtime.md#62-access-failures-and-development-data) |
| Dataset state | A dataset's `status.yaml` says where it stands; every command checks its step against the state and records it | [File formats](../../reference/schemas.md#statusyaml); [catalogue lifecycle](runtime.md#63-catalogue-lifecycle) |
| Plan before acting | Maintainer commands are pipelines: every stage plans, reading but never writing, before any acts; `--dry-run` is the plan; a rerun does only what is left | [Building blocks](building-blocks.md#522-catalogue-maintenance) |
| Ports and fakes | dCache, downloads and git are reached through ports with real adapters and fakes, so the pipelines run in tests without the network | [Adapters](../../reference/api/adapters.md) |
| Layers | A module imports only from its own layer and the ones below: model, adapters, services, presentation | [Building blocks](building-blocks.md#51-level-1-overall-package); [decision](decisions.md#four-layers-2026-10-02) |
| Handoffs | What one role hands another, a proposal, a problem report, an answer or a notice, is drafted from a template by the command that knows the facts | [decision](decisions.md#handoffs-between-roles-have-templates-2026-10-02) |
| Publication readiness | Build, upload, verification, and release are separate stages with an explicit review boundary; a release refuses a public dataset without a verified upload | [Catalogue lifecycle](runtime.md#63-catalogue-lifecycle) |

## Local test divergence

A repository test copy can serve two purposes: repeatable tests without remote
traffic, and a temporary changed input used to verify a bug fix. A repository
bundle is the source of truth for its files, so a change is recorded with
`bundle update` and published as the bundle's next version; until then a
changed file is refused rather than replaced. For an exported bundle,
`Bundle.fetch()` distinguishes those states, retains the authoritative
resource key and expected checksum, and warns when `allow_modified=True`
accepts changed bytes. Neither updates the official manifest to disguise the
difference. Catalogue maintainers still review and publish accepted changes.
See the [runtime scenario](runtime.md#64-repository-test-data).
