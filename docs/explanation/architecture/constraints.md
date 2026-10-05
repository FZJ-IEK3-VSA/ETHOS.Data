# 2. Architecture Constraints

This chapter answers which conditions, set outside the project, the design
has to accept. The approaches chosen within them are in
[section 4](solution-strategy.md).

| # | Constraint | Consequence |
|---|---|---|
| 1 | Redistribution terms vary per dataset | Visibility (is the metadata published?) and access (how may the bytes be used?) are separate rules. A catalogue entry grants no licence or permission. |
| 2 | Packages run on workstations, on the ICE-2 cluster computer and in CI | The library reads metadata from file system paths and over HTTPS. There is no server to deploy. |
| 3 | Inventories and files are large: ERA5 alone has about 170,000 resources | The index is read first and inventories on demand, in shards. Repositories hold only small, redistributable copies, with files under 100 MiB. |
| 4 | dCache at DESY (HIFIS, VO `Helmholtz/FZJ-ICE2`) stores the published bytes | Readers download anonymously over HTTPS, which works only under world-readable folders, so an upload sets 0755. Maintainers write through the WebDAV door with rclone and use the REST frontend for permissions and locality, both with a bearer token from Helmholtz ID through oidc-agent. |
| 5 | Identity, storage permissions and availability are operated by others: the storage operators at DESY and the ICE-2 cluster administrators | Credential provisioning, file system groups and service recovery are outside the package. |
| 6 | Packages accept different catalogue releases | Resource identities and published objects never change their meaning. |
| 7 | Required package tests must run without dCache | Repository bundles carry both the bytes and the metadata of their members. |
| 8 | Python 3.10 or later; dependencies from conda-forge: PyYAML, platformdirs, pooch and `pydantic>=2`, with tqdm optional, and rclone and oidc-agent for maintainers | A dependency is acceptable only if conda-forge has it. ETHOS.Data itself has no release on a package index, so packages install it from GitHub. |
| 9 | conda-forge has no oidc-agent for Windows | `catalog upload`, `catalog release --upload`, `catalog remove --purge` and `catalog check-store` run on Linux, macOS or WSL. Symbolic links on Windows need Developer Mode. |
| 10 | A runner outside the cluster cannot reach the cluster computer's file system, and cluster users have no access to Git hosting | Cluster users read the internal catalogue from a checkout on that file system. `catalog update-checkout` runs there, and so does every command that reads a build input only the cluster holds. |
| 11 | Public metadata is served by `raw.githubusercontent.com`, with request limits | A tag URL never changes, so it is cached forever. `main` moves, so it is never cached. |
| 12 | The docs build has no LaTeX | TikZ sources are rendered locally into committed light and dark SVGs. |
| 13 | Internal locations, groups and contacts must not appear in public pages | The ICE-2 wiki holds them; the docs use placeholders. |
| 14 | On the cluster, much of the data already sits on shared storage, in project directories | Cluster users read it in place, through a shared cache that maintainers fill, instead of each downloading a copy. |

[Section 7](deployment.md) shows where these constraints place each command.
