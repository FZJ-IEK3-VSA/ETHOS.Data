# 4. Solution Strategy

| Goal | Chosen approach | Consequence and detailed explanation |
|---|---|---|
| Reuse data across packages | One catalogue inventory; package-owned collections select resources | Shared keys derive shared cache paths. [Why one catalogue](../deduplication.md) |
| Preserve understandable ownership | Separate metadata from authoritative dataset storage | Catalogues can be mirrored and versioned without duplicating large data archives. [Context](context.md) |
| Support large inventories | Load descriptors and inventory shards on demand | Later selection may encounter metadata failures even after an index has loaded. [Catalogue format](../catalogue-format.md) |
| Respect data access conditions | One lookup chain resolves explicit roots, staging, bundles and access classes before any download | Existing restricted copies are used in place; missing required files fail with locations and the dataset's description. [Caches and access](../caches-and-access.md) |
| Keep reader and writer compatible | Specify every file format once, as a model both sides read, and ship them in one distribution | Validation, the JSON Schemas, the templates and the reference tables come from the same declaration; maintainer dependencies are imported at their command boundary. [Building blocks](building-blocks.md) |
| Preserve published input identities | Published objects never change; packages name the catalogue releases they accept | Changed bytes become a revision beside the old ones, or a successor dataset; pins also depend on retention. [Licensing and immutability](../licensing.md) |
| Catch avoidable transfer failures early | Validate a selected upload batch before transferring its first dataset | Later network failures still require recovery; there is no batch rollback. [Runtime](runtime.md#63-catalogue-lifecycle) |
| Make maintenance safe to interrupt and to review | Maintainer commands are pipelines that plan every stage before any acts; each dataset's state is a state machine recorded in its status file | `--dry-run` is the plan, a rerun does only what is left, and a step the state does not allow is refused. [Runtime](runtime.md#63-catalogue-lifecycle) |
| Reduce repeated CI downloads while allowing bug investigation | A package keeps its test data in its repository as a repository bundle, read first | The repository is the source of truth for its test data and the catalogue publishes its versions; a change is recorded explicitly. [Testing scenario](runtime.md#64-repository-test-data) |
| Keep the code changeable | Four layers; dCache, downloads and git behind ports with fakes | The pipelines run in tests without the network; a test holds the layer rule. [Building blocks](building-blocks.md#51-level-1-overall-package) |

Exported bundles remain for copies of canonical catalogue data, through a
self-contained local manifest and explicit `allow_modified` reads. Ordinary
public cache downloads continue to enforce their checksum checks. Hosting
choices and versioned catalogue releases are described in
[Deployment View](deployment.md).
