# 2. Architecture Constraints

These constraints come from the environment and data ownership. The selected
cache layout and metadata representation are [solution choices](solution-strategy.md).

| Constraint | Architectural consequence |
|---|---|
| Dataset redistribution terms vary | Metadata visibility and byte access need distinct rules; a catalogue entry cannot grant a licence or filesystem permission |
| Scientific packages run on workstations, institute clusters, and CI | The reader must accept filesystem paths as well as hosted metadata; callers cannot be required to deploy an `ethos-data` server |
| Dataset inventories and individual files can be large | Selection must avoid loading unrelated inventories; test repositories can include only suitably small, redistributable copies |
| dCache is authoritative for centrally published bytes, including test datasets | Local repository copies record their catalogue origin; accepting a fix and publishing revised data remain explicit maintainer actions |
| Identity, storage permissions, and availability are operated externally | Credential provisioning and service recovery cannot be guaranteed by the reader |
| Packages can pin different catalogue versions | Resource identities and retained published paths must preserve the meaning of older selections |
| Required tests should run while dCache is unavailable | Both test bytes and the metadata needed to select them must be locally available; a data cache alone is insufficient |

The intended metadata deployment is an internal catalogue on cluster storage,
synchronised through reviewed Git changes with JuGit, plus public metadata on
GitHub. Cluster users read a local generated catalogue path. Public consumers
should pin a release or revision. These are deployment decisions, documented in
[section 7](deployment.md), and do not change dCache's authority over bytes.

The current reader/writer compatibility contract is documented in
[File formats](../../reference/schemas.md). Changes must account for both local
internal metadata and the stripped public view.
