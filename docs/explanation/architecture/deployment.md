# 7. Deployment View

This chapter answers where ETHOS.Data runs and where its data lives: which
machine runs which command, what each machine holds, and what it can reach.
ETHOS.Data has no server of its own. It runs in-process on the caller's
machine, as the library, `ethos-data` or a package's `<tool>-data`, and reads
metadata and bytes from hosts that others operate.

## 7.1 Infrastructure {#infrastructure}

<figure markdown="span">
  ![Where ETHOS.Data runs and its data lives: package CI reads its bundles first; a workstation keeps a personal public cache and, optionally, restricted caches of its user's own licensed copies; on the cluster every user reads the served checkout at the latest release and shares one public cache that any user's fetch downloads into, restricted caches, one per access combination, are read in place by the users they admit, and maintainers link and copy data into both kinds of cache and record their work in their own clones, merged on JuGit. dCache, GitHub and JuGit hold the published bytes and both catalogues.](../../assets/diagrams/architecture-deployment-light.svg#only-light){ .diagram }
  ![Where ETHOS.Data runs and its data lives: package CI reads its bundles first; a workstation keeps a personal public cache and, optionally, restricted caches of its user's own licensed copies; on the cluster every user reads the served checkout at the latest release and shares one public cache that any user's fetch downloads into, restricted caches, one per access combination, are read in place by the users they admit, and maintainers link and copy data into both kinds of cache and record their work in their own clones, merged on JuGit. dCache, GitHub and JuGit hold the published bytes and both catalogues.](../../assets/diagrams/architecture-deployment-dark.svg#only-dark){ .diagram }
</figure>

| Node | Technology | What runs there | What it holds |
| --- | --- | --- | --- |
| Workstation or laptop (public installation) | Any operating system; a conda environment from conda-forge, with ETHOS.Data installed from GitHub | A consuming package with the library and its `<tool>-data` command; `ethos-data` | The account's settings file; the user's public cache and its metadata cache; optionally restricted caches with the user's own licensed copies; a personal staging root; package checkouts with collections files and bundles |
| ICE-2 cluster computer | Linux; a shared file system; home directories shared by every batch node | Users' environments and batch jobs, as on a workstation; a maintainer environment with git, rclone and oidc-agent for `ethos-data catalog`, `link` and `materialize` | The served checkout, the cluster's public cache, the restricted caches (one per access combination), the validation folder and project storage; each user's settings file and staging root; each maintainer's own clones ([7.2](#cluster)) |
| Maintainer workstation (optional) | Linux, macOS or WSL, with git, rclone and oidc-agent | `ethos-data catalog`, for review and for the commands that need no file only the cluster holds | The maintainer's own clones of the source catalogue and of the public catalogue |
| dCache at DESY (HIFIS) | An anonymous HTTPS download door, a WebDAV door and a REST frontend; a tape tier | — | The publication root, world-readable: every version of every public dataset that a release of the current major describes, and the latest public catalogue under `catalogue/` |
| Helmholtz ID (DESY Keycloak) | OIDC issuer of the bearer tokens for dCache writes and REST calls | — | — |
| GitHub | git hosting with raw file serving and issue trackers | — | The public catalogue, one tag per release, with a `main` index that lists every release; ETHOS.Data's code; package repositories |
| JuGit | GitLab | — | The source catalogue, one tag per release, with its merge requests and tracker |
| CI runners and Read the Docs | GitHub Actions; each package's own provider; Read the Docs | The test suites and the documentation build ([7.5](#ci)) | Ephemeral environments; a package's CI cache; the built site |

## 7.2 The ICE-2 cluster computer {#cluster}

The cluster computer is the only machine with the internal view; every other
machine, a cluster member's laptop included, is a public installation. Users'
environments and batch jobs read the served checkout and the caches there, and
download the public files the cluster's public cache lacks into it.
Maintainers link and copy data into the cluster's public cache and register
restricted installations in the restricted caches; each maintainer's own
clones live in their own account. The cluster administrators set the groups
and file system permissions. The paths are an example; the ICE-2 wiki holds
the real paths, groups and contacts.

| Example path | Holds | Read by | Written by |
| --- | --- | --- | --- |
| `/shared/ethos/catalogue/` | The served checkout of the internal catalogue, at its latest release | Every cluster user | `catalog update-checkout` only |
| `/shared/ethos/cache/` | The cluster's public cache, of public data only: links into project storage, copies it owns, downloads and the metadata cache | Every cluster user | Every cluster user, with the permissions the cluster administrators set (for example setgid): a fetch downloads a missing public file into it. Maintainers make the links and copies: `ethos-data link --all --root /shared/ethos/cache`, `ethos-data link NAME DIR` and `materialize` |
| `/shared/ethos/restricted/<group>/` | A restricted cache, one per access combination (every institute member, or one licence group): a setgid directory whose group every new entry inherits | The members of that group, in place | Maintainers: `ethos-data --root /shared/ethos/restricted/<group> link` or `materialize` |
| `/shared/ethos/validation/` | Re-downloads for provenance checks | Maintainers | Maintainers |
| Project storage | The data directories the caches link to, and the build inputs of datasets that are not frozen | Cluster users, through the caches' links; maintainers' commands | The projects that own them |
| A maintainer's own account | That maintainer's clone of the source catalogue, with its status files, and their clone of the public catalogue | That maintainer | The catalogue commands, and `link` and `materialize` with `--catalog-root`; the maintainer's commits, merged by merge request on JuGit |

There is no machine-wide setting. Each cluster user writes their own settings
file:

```bash
ethos-data config set-catalog /shared/ethos/catalogue/datacatalog.json
ethos-data config set-public-cache /shared/ethos/cache
ethos-data config add-restricted-cache /shared/ethos/restricted/<group>   # once per group, if any
```

`add-restricted-cache` is run once for each restricted cache the user's
groups admit, and for no other; a user of public data only adds none. Nothing
else needs setting.

Public data is read from the cluster's public cache: in place where its entry
is a link, otherwise from the copy there. A public file it lacks is downloaded
into it, once for everyone. Restricted data is read in place from the first
listed restricted cache whose entry the user may read.

There is no shared working checkout. A maintainer records work (an upload, a
link, a copy, a freeze, a provenance check) in the status files of their own
clone, reviews the diff, commits on a branch and merges by merge request on
JuGit; no command commits or pushes a record. A release runs in a clone of the
merged state, and `catalog release --push` pushes its commit and tag to JuGit
and the public catalogue and its tag to GitHub; it is the one direct push to
the release branch on JuGit. Maintainers fill and prune the cluster's public
cache with `link --all` only from a clone at the merged state of the served
release.

The served checkout changes only through `catalog update-checkout`, which runs
on the cluster computer because a runner elsewhere cannot reach the checkout.
It fast-forwards the checkout in place to the newest release tag, so it runs
while no jobs read it, and checks the result with `build --check`, which writes
nothing. Because the checkout holds the latest release only, a collections file
whose bounds exclude that release is refused there with `CatalogVersionError`;
packages that run on the cluster bound their releases with `min_version` only.
These choices are recorded in
[0026](decisions/0026-internal-catalogue-on-the-cluster.md) and
[0028](decisions/0028-one-public-cache-on-the-cluster.md).

## 7.3 Where each command runs {#commands}

| Command | Runs on | Needs |
| --- | --- | --- |
| `config …`, `staging …` | Any machine | No network and no catalogue |
| `ls`, `fetch`, `verify`, `selftest`, `report`; `<tool>-data show`, `fetch`, `verify`, `report` | A workstation, the cluster computer, a package's CI | The catalogue, over HTTPS or from the served checkout; the download door for missing public files |
| `bundle …` | A package checkout; `bundle export` on any machine | `update` records changes offline; with the package's catalogue readable, it records each dataset's alignment, and `verify` compares with the catalogue. `export` reads through the package's handle: its bundles, then the caches and the download door |
| `propose DIR` | Where the candidate bytes are readable | Optionally the catalogue, to tell a new dataset from a revision |
| `link`, `unlink`, `materialize` into a personal public cache, or into a restricted cache of the user's own licensed copies | Any machine | — |
| `ethos-data [--root <cache>] link`, `unlink` or `materialize` into the cluster's public cache or one of its restricted caches; `ethos-data link --all --root <the cluster's public cache>` | The cluster computer, in a maintainer's environment | `--catalog-root` names the maintainer's own clone, never the served checkout |
| `catalog add`, `build`, `status --check`, `record`, `check-source`, `remove` | The cluster computer, in the maintainer's own clone | The build inputs (`source_dir`) and recorded copies of the datasets it handles; for `check-source`, the validation folder |
| `catalog status`, `publish [--check]` | Wherever the maintainer's clones are | — |
| `catalog upload` | The cluster computer, or a maintainer workstation that can read every build input it uploads | rclone, oidc-agent, the WebDAV door and the REST frontend |
| `catalog remove --purge` | The cluster computer, in the maintainer's own clone, once a major release is recorded after the removal: its `cache` stage deletes the recorded entries in the cluster's public cache and the restricted caches | The same as `upload`, for its `store` stage; write access to every cache that holds a recorded entry, which `check` confirms before any deletion |
| `catalog release` | The maintainer's own clone at the merged state of JuGit, beside their clone of the public catalogue; on the cluster computer while any build input is readable only there | `build --check` reads the build input of every dataset that is not frozen; `--push` reaches JuGit and GitHub; `--upload` reaches dCache |
| `catalog update-checkout` | The cluster computer, in the served checkout | A git fetch from JuGit; no local changes |
| `catalog migrate`, the one-time converter of [0002](decisions/0002-clean-break-during-the-beta.md) | The cluster computer, once, in a maintainer's own clone | A merge request afterwards |
| `catalog check-store` | Any machine with bash, curl, python3 and oidc-agent | No catalogue |

## 7.4 Reachability and placement {#reachability}

1. Restricted data is read in place, from a restricted cache whose file
   permissions admit the reader. It is never downloaded or uploaded, never
   written into a public cache, never shadowed by staging and never put into
   a bundle; restricted data the institute holds has no copy off the cluster.
   Without a readable entry, a request is refused before anything is
   downloaded, naming the dataset and how to obtain and register a copy. An
   account that lists no restricted cache, on the cluster too, runs every
   workflow that needs no restricted data
   ([0011](decisions/0011-access-class-picks-the-root.md),
   [0013](decisions/0013-every-input-is-required.md)).
2. A local copy is made usable as a cache entry, with
   `ethos-data link NAME DIR` or `materialize`: in the public cache for public
   data, in a restricted cache for restricted data. There is no per-dataset
   root. On Windows without the right to create symbolic links, `link`
   refuses and offers `ethos-data materialize NAME --from DIR`, a verified
   copy.
3. Every cluster user may write the cluster's public cache; the cluster
   administrators set its permissions, and maintainers make its links. Four
   rules keep the sharing safe without a lock
   ([0028](decisions/0028-one-public-cache-on-the-cluster.md)).
4. A broken link in the cluster's public cache refuses every user's read of
   that dataset until a maintainer repairs it; `verify` reports the link, and
   the problem report goes to the internal tracker.
5. A release's `check` stage runs `build --check`, which reads the build input
   of every dataset that is not frozen. While any dataset is only linked, the
   release therefore runs on the cluster computer. Freezing a dataset with
   `catalog record` removes the tie. `catalog add-bundle` copies a bundle's
   files into a build input the catalogue maintainers own, so no release reads
   a package checkout.
6. dCache serves anonymous reads only under a world-readable folder; upload
   sets 0755 through the REST frontend unless `--no-chmod` is given. Writes go
   through the WebDAV door with a bearer token, which the REST frontend needs
   too, for permissions and locality. A file on tape (`NEARLINE`) can make the
   first read slow. A mixed or private root is never made public.
7. The OIDC login needs a browser once per profile. On the cluster computer
   or another remote machine, the redirect port (`http://localhost:8080`) is
   forwarded to the machine with the browser.
8. A metadata URL that names no moving ref, such as a release tag, is kept in
   the metadata cache forever; `main` is read again every time. With no
   catalogue configured, a collections file whose bounds are a range (a
   prefix `exact_version` included) therefore reads the public `main` index
   whenever a handle reads the index, which needs the network and meets
   GitHub's request limits. A handle whose bundles hold every input reads no
   index.
9. Restricted caches hold data the institute may not pass on, so they stay
   out of synchronised directories. A public cache holds public data only.
10. The test suite never leaves the machine: it reaches loopback only,
    refuses to run rclone or `oidc-token`, and reads none of the developer's
    settings.

## 7.5 Continuous integration {#ci}

| Runner | Runs | Reaches |
| --- | --- | --- |
| ETHOS.Data, GitHub Actions on a self-hosted runner | On every push and on manual dispatch: a conda environment from `environment.yml`, `pip install -e . --no-deps`, and the test suite. Read the Docs builds the documentation with `mkdocs build --strict`, pull request previews included. | conda-forge and GitHub; the tests reach loopback only |
| A package's CI, on the package's own runner | A required job with the network blocked, whose inputs and their metadata come from the package's bundles. A live job: `ethos-data selftest`, then `<tool>-data fetch --plan`, `fetch` and `verify --deep`, with the public cache in the CI cache (`ETHOS_DATA_DIR`) and optionally a settings file of its own (`ETHOS_DATA_CONFIG`). A bundle ahead of the catalogue only warns. | The public catalogue and the download door. Restricted data needs a runner on the cluster computer whose settings list the restricted caches it needs; its public cache is the cluster's or its own. |
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
