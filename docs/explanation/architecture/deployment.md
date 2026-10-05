# 7. Deployment View

This chapter answers where ETHOS.Data runs and where its data lives: which
machine runs which command, what each machine holds, and what it can reach.
ETHOS.Data has no server of its own. It runs in-process on the caller's
machine, as the library, `ethos-data` or a package's `<tool>-data`, and reads
metadata and bytes from hosts that others operate.

## 7.1 Infrastructure {#infrastructure}

<figure markdown="span">
  ![Where ETHOS.Data runs and its data lives: workstations and CI read public metadata and data; the cluster serves the internal catalogue at its latest release and a read-only shared cache that maintainers fill, and each user keeps a personal public cache; maintainers work in their own clones and merge on JuGit; dCache, GitHub and JuGit hold the published bytes and both catalogues.](../../assets/diagrams/architecture-deployment-light.svg#only-light){ .diagram }
  ![Where ETHOS.Data runs and its data lives: workstations and CI read public metadata and data; the cluster serves the internal catalogue at its latest release and a read-only shared cache that maintainers fill, and each user keeps a personal public cache; maintainers work in their own clones and merge on JuGit; dCache, GitHub and JuGit hold the published bytes and both catalogues.](../../assets/diagrams/architecture-deployment-dark.svg#only-dark){ .diagram }
</figure>

| Node | Technology | What runs there | What it holds |
| --- | --- | --- | --- |
| Workstation or laptop (public installation) | Any operating system; a conda environment from conda-forge, with ETHOS.Data installed from GitHub | A consuming package with the library and its `<tool>-data` command; `ethos-data` | The account's settings file; the user's public cache and its metadata cache; optionally a restricted cache with the user's own licensed copies; a personal staging root; package checkouts with collections files and bundles |
| ICE-2 cluster computer | Linux; a shared file system; home directories shared by every batch node | Users' environments and batch jobs, as on a workstation; a maintainer environment with git, rclone and oidc-agent for `ethos-data catalog`, `link` and `materialize` | The served checkout, the shared cache, the cluster's restricted cache, the validation folder and project storage; each user's settings file, public cache and staging root; each maintainer's own clones ([7.2](#cluster)) |
| Maintainer workstation (optional) | Linux, macOS or WSL, with git, rclone and oidc-agent | `ethos-data catalog`, for review and for the commands that need no file only the cluster holds | The maintainer's own clones of the source catalogue and of the public catalogue |
| dCache at DESY (HIFIS) | An anonymous HTTPS download door, a WebDAV door and a REST frontend; a tape tier | — | The publication root, world-readable: every published version of every public dataset, and the latest public catalogue under `catalogue/` |
| Helmholtz ID (DESY Keycloak) | OIDC issuer of the bearer tokens for dCache writes and REST calls | — | — |
| GitHub | git hosting with raw file serving and issue trackers | — | The public catalogue, one tag per release, with a `main` index that lists every release; ETHOS.Data's code; package repositories |
| JuGit | GitLab | — | The source catalogue, one tag per release, with its merge requests and tracker |
| CI runners and Read the Docs | GitHub Actions; each package's own provider; Read the Docs | The test suites and the documentation build ([7.5](#ci)) | Ephemeral environments; a package's CI cache; the built site |

## 7.2 The ICE-2 cluster computer {#cluster}

The cluster computer is the only machine with the internal view; every other
machine, a cluster member's laptop included, is a public installation. Users'
environments and batch jobs read the served checkout and the caches there. A
maintainer environment fills the shared cache and the restricted cache, and
each maintainer's own clones live in their own account. The cluster
administrators set the groups and file system permissions. The paths are an
example; the ICE-2 wiki holds the real paths, groups and contacts.

| Example path | Holds | Read by | Written by |
| --- | --- | --- | --- |
| `/shared/ethos/catalogue/` | The served checkout of the internal catalogue, at its latest release | Every cluster user | `catalog update-checkout` only |
| `/shared/ethos/cache/` | The shared cache: links into project storage and copies it owns, of public and internal data, never restricted data. No downloads and no metadata cache. | Every cluster user, in place | Maintainers only: `ethos-data link --all --root /shared/ethos/cache`, and `ethos-data --root /shared/ethos/cache link` or `materialize` |
| `/shared/ethos/restricted/` | The cluster's restricted cache: one entry per licensed dataset, each with its own group | That dataset's licence group | Maintainers (`link`, `materialize`) |
| `/shared/ethos/validation/` | Re-downloads for provenance checks | Maintainers | Maintainers |
| Project storage | The data directories the shared cache links to, and the build inputs of datasets that are not frozen | Cluster users, through the shared cache's links; maintainers' commands | The projects that own them |
| A maintainer's own account | That maintainer's clone of the source catalogue, with its status files, and their clone of the public catalogue | That maintainer | The catalogue commands, and `link` and `materialize` with `--catalog-root`; the maintainer's commits, merged by merge request on JuGit |
| A user's per-user cache directory, or the path the ICE-2 wiki recommends (for example on scratch storage) | That user's public cache, with their metadata cache | That user | That user's downloads, links and copies |

There is no machine-wide setting. Each cluster user names the three shared
locations in their own settings file:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/datacatalog.json
ethos-data config set-shared-cache /shared/ethos/cache
ethos-data config set-restricted-cache /shared/ethos/restricted
```

A file the shared cache holds is read there, in place. A public file it lacks
is read from, or downloaded into, the user's own public cache, which
`config set-public-cache DIR` may move to the path the wiki recommends.
Internal data is read only from the shared cache.

There is no shared working checkout. A maintainer records work (an upload, a
link, a copy, a freeze, a provenance check) in the status files of their own
clone, reviews the diff, commits on a branch and merges by merge request on
JuGit; no command commits or pushes a record. A release runs in a clone of the
merged state, and `catalog release --push` pushes its commit and tag to JuGit
and the public catalogue and its tag to GitHub; it is the one direct push to
the release branch on JuGit. Maintainers fill and prune the shared cache with
`link --all` only from a clone at the merged state of the served release.

The served checkout changes only through `catalog update-checkout`, which runs
on the cluster computer because a runner elsewhere cannot reach the checkout.
It fast-forwards the checkout in place to the newest release tag, so it runs
while no jobs read it, and checks the result with `build --check`, which writes
nothing. Because the checkout holds the latest release only, a collections file
whose bounds exclude that release is refused there with `CatalogVersionError`;
packages that run on the cluster bound their releases with `min_version`.
These choices are recorded in
[0026](decisions/0026-internal-catalogue-on-the-cluster.md) and
[0028](decisions/0028-read-only-shared-cache.md).

## 7.3 Where each command runs {#commands}

| Command | Runs on | Needs |
| --- | --- | --- |
| `config …`, `staging …` | Any machine | No network and no catalogue |
| `ls`, `fetch`, `verify`, `selftest`, `report`; `<tool>-data show`, `fetch`, `verify`, `report` | A workstation, the cluster computer, a package's CI | The catalogue, over HTTPS or from the served checkout; the download door for missing public files |
| `bundle …` | A package checkout; `bundle export` on any machine | `update` asks the package's catalogue which release holds the version; `export` reads the catalogue and the download door, or `--source-root` copies |
| `propose DIR` | Where the candidate bytes are readable | Optionally the catalogue, to tell a new dataset from a revision |
| `link`, `unlink`, `materialize` into the user's own public cache or restricted cache | Any machine | — |
| `ethos-data --root <shared cache> link`, `unlink` or `materialize`; `ethos-data link --all --root <shared cache>`; `link` or `materialize` into the cluster's restricted cache | The cluster computer, in a maintainer's environment | `--catalog-root` names the maintainer's own clone, never the served checkout |
| `catalog add`, `build`, `status --check`, `record`, `check-source`, `remove` | The cluster computer, in the maintainer's own clone | The build inputs (`source_dir`) and recorded copies of the datasets it handles; for `check-source`, the validation folder |
| `catalog status`, `publish [--check]` | Wherever the maintainer's clones are | — |
| `catalog upload` | The cluster computer, or a maintainer workstation that can read every build input it uploads | rclone, oidc-agent, the WebDAV door and the REST frontend |
| `catalog remove --purge` | The cluster computer, in the maintainer's own clone: its `cache` stage deletes the recorded entries in the shared cache and the restricted cache | The same as `upload`, for its `store` stage |
| `catalog release` | The maintainer's own clone at the merged state of JuGit, beside their clone of the public catalogue; on the cluster computer while any build input is readable only there | `build --check` reads the build input of every dataset that is not frozen; `--push` reaches JuGit and GitHub; `--upload` reaches dCache |
| `catalog update-checkout` | The cluster computer, in the served checkout | A git fetch from JuGit; no local changes |
| `catalog migrate`, the one-time converter of [0002](decisions/0002-clean-break-during-the-beta.md) | The cluster computer, once, in a maintainer's own clone | A merge request afterwards |
| `catalog check-store` | Any machine with bash, curl, python3 and oidc-agent | No catalogue |

## 7.4 Reachability and placement {#reachability}

1. Internal data is never downloaded and never uploaded. On the cluster
   computer it is read from the shared cache, where maintainers link or copy
   it. A personal public cache never holds it, so elsewhere it is readable
   only through an explicit override: a per-dataset root or a staging entry
   ([0011](decisions/0011-access-class-picks-the-root.md)).
2. Restricted data is read in place, from a restricted cache the account may
   read. It is never downloaded, uploaded, or written into a public cache or
   the shared cache. Without a readable installation, a request is refused
   with the dataset's description.
3. Cluster users never write the shared cache. Its permissions let only
   maintainers write it, and no user command writes it: downloads and repairs
   go into the user's own public cache, which needs room for the public files
   the shared cache lacks. While a shared entry is broken, its public files
   are downloaded into each user's own cache and its internal files are
   refused; `verify` reports the entry, and a maintainer fixes it.
4. A release's `check` stage runs `build --check`, which reads the build input
   of every dataset that is not frozen. While any dataset is only linked, the
   release therefore runs on the cluster computer; while a bundle member is
   not frozen, it needs the package checkout that holds the member. Freezing a
   dataset with `catalog record` removes the tie.
5. dCache serves anonymous reads only under a world-readable folder; upload
   sets 0755 through the REST frontend unless `--no-chmod` is given. Writes go
   through the WebDAV door with a bearer token, which the REST frontend needs
   too, for permissions and locality. A file on tape (`NEARLINE`) can make the
   first read slow. A mixed or private root is never made public.
6. The OIDC login needs a browser once per profile. On the cluster computer
   or another remote machine, the redirect port (`http://localhost:8080`) is
   forwarded to the machine with the browser.
7. A metadata URL that names no moving ref, such as a release tag, is kept in
   the user's metadata cache forever; `main` is read again every time. A
   collections file with a range of bounds and no configured catalogue
   therefore reads the public `main` index whenever a handle reads the index,
   which needs the network and meets GitHub's request limits. A handle whose
   bundles hold every input reads no index.
8. The shared cache and the restricted cache hold data the institute may not
   pass on, so they stay out of synchronised directories. A personal public
   cache holds public data only.
9. The test suite never leaves the machine: it reaches loopback only, refuses
   to run rclone or `oidc-token`, and reads none of the developer's settings.

## 7.5 Continuous integration {#ci}

| Runner | Runs | Reaches |
| --- | --- | --- |
| ETHOS.Data, GitHub Actions on a self-hosted runner | On every push and on manual dispatch: a conda environment from `environment.yml`, `pip install -e . --no-deps`, and the test suite. Read the Docs builds the documentation with `mkdocs build --strict`, pull request previews included. | conda-forge and GitHub; the tests reach loopback only |
| A package's CI, on the package's own runner | A required job with the network blocked, whose inputs and their metadata come from the repository bundles. A live job: `ethos-data selftest`, then `<tool>-data fetch --plan`, `fetch` and `verify --deep`, with the public cache in the CI cache (`ETHOS_DATA_DIR`) and optionally a settings file of its own (`ETHOS_DATA_CONFIG`). | The public catalogue and the download door. Internal and restricted data need a runner on the cluster computer with the shared cache and the restricted cache configured; its public cache is the runner account's own. |
| The catalogue release | No runner. The release runs where a maintainer runs it: in their own clone, placed as in [7.3](#commands). | — |

A release runner is proposed in a
[feature request](https://github.com/FZJ-IEK3-VSA/ETHOS.Data/issues/34). It
has to reach JuGit, GitHub and dCache with a token that does not depend on a
person's oidc-agent session, and read every build input that is not frozen,
so it runs on the cluster computer. `catalog release` refuses a tag it did not
make unless the tagged commit is already stamped, so such a runner either runs
the whole release from a manual trigger, or finishes, on the tag, a release
that a maintainer started and pushed. The checks `catalog build --check` and
`catalog publish DIR --check` compare and write nothing, so they suit every
merge request of the source catalogue.

The procedures are in [Set up the shared machine](../../how-to/catalogue-maintainers/set-up-the-shared-machine.md),
[Set up your machine](../../how-to/data-users/set-up-your-machine.md#cluster-users),
[Release the catalogue](../../how-to/catalogue-maintainers/release-the-catalogue.md),
[Set up dCache access](../../how-to/catalogue-maintainers/set-up-dcache-access.md)
and [Run tests and examples in CI](../../how-to/package-maintainers/run-in-ci.md).
