# `ice2-data catalog`

The maintainer counterpart to [`ice2-data`](ice2-data.md). Everything here
**writes** — to a catalogue checkout, or to the storage behind it — which is why
it is a separate command rather than more subcommands on the consumer tool. The
two have different audiences, and nothing a data *user* runs should be one typo
away from republishing a catalogue.

```
ice2-data catalog [--catalog-root DIR] <command> ...
```

The catalogue to act on is found by searching **upward** from the current
directory for `catalog.yaml`, so these commands work from anywhere inside a
checkout. `--catalog-root` overrides that.

A catalogue is identified by its hand-written `catalog.yaml`. The generated
`datacatalog.json` is *not* a marker — a published catalogue has one too, and
must never be mistaken for a source one. Running these inside a published
catalogue gets an explicit refusal naming the source catalogue to use instead.

## `build [datasets...]`

Regenerate `datapackage.json` (and `manifests/*.json` for a sharded dataset)
from each `dataset.yaml`, plus the catalogue-wide `datacatalog.json`.

```bash
ice2-data catalog build my-dataset      # one
ice2-data catalog build                 # all
ice2-data catalog build --check         # CI: fail if any manifest is out of date
```

Walks `source_dir`, computes a SHA-256 per file, applies
`ice2:include`/`ice2:exclude`, pulls in shapefile companions, and excludes VCS
plumbing, `__pycache__` and root `README*`/`LICENSE*`/`CHANGELOG*`.

An `ice2:include` pattern matching nothing **fails**; an `ice2:exclude` pattern
matching nothing only warns. See
[Describe a dataset](../../how-to/describe-a-dataset.md#the-asymmetry-is-deliberate).

| Flag | |
|---|---|
| `--check` | report staleness and exit non-zero; write nothing |

## `publish <target>`

Generate the public catalogue from this source one, into a checkout of the
public repository.

```bash
ice2-data catalog publish ../ice2-data-catalog
ice2-data catalog publish ../ice2-data-catalog --check
```

Emits `datacatalog.json`, each public `datasets/<name>/datapackage.json` with
`source_dir`, `ice2:embargo` and `ice2:license_note` stripped, and the README
table — for every dataset marked `ice2:visibility: public`. Anything it no
longer generates is deleted from the target.

!!! danger "It wipes everything in its target except `.git`"
    Point it only at the public repository. See
    [Publish the catalogue](../../how-to/publish-the-catalogue.md).

| Flag | |
|---|---|
| `--check` | fail if the target is out of date; write nothing |

## `upload <dataset>`

Put a dataset's bytes on dCache, then verify them anonymously. Needs `rclone`
and `oidc-agent` on `PATH`.

```bash
ice2-data catalog upload my-dataset --dry-run
ice2-data catalog upload my-dataset
ice2-data catalog upload my-dataset --verify-only
```

| Flag | Default | |
|---|---|---|
| `--dry-run` | | show what rclone would transfer |
| `--verify-only` | | skip the upload, just check readability |
| `--allow-internal` | | required for an `internal` dataset |
| `--no-chmod` | | do not set `0755` on the dataset prefix |
| `--transfers N` | `8` | parallel transfers |
| `--remote NAME` | `HIFIS` | rclone remote name |
| `--oidc-profile NAME` | `HIFIS` | oidc-agent profile |
| `--vo-path PATH` | `Helmholtz/FZJ-ICE2` | namespace path of the VO |
| `--root NAME` | last segment of `catalog.yaml`'s `ice2:publication_url` | publication root under the VO |

Refuses `restricted` datasets outright, warns on unresolved licensing, and
passes `rclone --immutable` so a published path can never be overwritten. After
transferring it HEADs every file in the manifest with **no credentials** and
reports anything unreadable or the wrong size, plus the storage locality
(`ONLINE` / `ONLINE_AND_NEARLINE` / `NEARLINE`).

Full runbook: [Upload a dataset](../../how-to/upload-a-dataset.md).

## `link-cache --root <directory>`

Build the public cache as a directory of symbolic links to data already on this
machine, one entry per dataset with a `source_dir`.

```bash
ice2-data catalog link-cache --root /projects5/ice2_data_cache_public --dry-run
ice2-data catalog link-cache --root /projects5/ice2_data_cache_public --prune
```

| Flag | |
|---|---|
| `--root DIR` | **required** — the public cache directory to build |
| `--dry-run` | show what would change, write nothing |
| `--prune` | also remove links for datasets no longer in the catalogue |

Nothing is copied or moved. **Real directories are never touched** — an entry
downloaded from dCache or produced by `ice2-data materialize` is data the cache
owns, and replacing it with a link would discard it.

See [Use data already on disk](../../how-to/use-data-already-on-disk.md#the-maintainer-side-link-cache).

## `check-store [vo]`

Probe what this account can do on dCache InfiniteSpace. Default VO:
`FZJ-ICE2`.

```bash
ice2-data catalog check-store FZJ-ICE2
```

Non-destructive: it uses a throwaway subdirectory and cleans up after itself. It
reports whether you can chmod at all (self-managed vs. root-owned "Simple"
model — the latter needs a HIFIS ticket) and whether permissions inherit to new
files.

It is a shell script by necessity: it reproduces exactly what a maintainer would
type against `curl` and `rclone`, so the commands it prints on failure are the
ones it actually ran. This is the one subcommand that does not need a catalogue
checkout.

## See also

- [Describe a dataset](../../how-to/describe-a-dataset.md)
- [Publish the catalogue](../../how-to/publish-the-catalogue.md)
- [Bootstrap a new catalogue](../../how-to/bootstrap-a-catalogue.md)
- [API: maintainer tooling](../api/maintain.md)
