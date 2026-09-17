# Manage local dataset copies

Read existing catalogued data in place, add a shared cache link, or create an
independent verified copy. You need a readable catalogue inventory and source
files with the catalogue's relative layout. Paths below are examples.

## Choose how to use the existing data

| Need | Method |
| --- | --- |
| Use one dataset from another directory for your account/project | A dataset-root setting. |
| Share an existing directory through the cache | A symbolic cache link. |
| Make the cache own an independent copy | Materialize the dataset. |

New datasets first need [source metadata](describe-a-dataset.md) and licensing
review. For unpublished experiments, use [staging](propose-a-dataset.md#stage-development-data).

## Dataset-root overrides {#dataset-root-overrides}

```bash
ethos-data config set-root global-wind-atlas-v4 /data/GWA_4.0
ethos-data config show
```

The directory points directly at the dataset's files. Append `--scope project`
for one project. Files are read in place. Stop using the override with:

```bash
ethos-data config unset-root global-wind-atlas-v4
```

This removes configuration, not files. Future retrieval uses the applicable
cache. It does not make a restricted dataset downloadable.

## Create or remove cache links {#cache-links}

```bash
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public link climate-inputs /legacy/climate-inputs
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public unlink climate-inputs
```

A link is visible to everyone sharing that cache. `unlink` removes only symbolic
links and leaves their sources intact; it refuses real directories. It looks in
the root for the dataset's current access class, so it cannot remove a
public-cache entry for a dataset the catalogue now calls restricted — see the
report table below. `--force` on a named dataset deliberately repoints an
existing link. `link` refuses an entry whose path runs through a symbolic link,
with or without `--force`, because that directory is borrowed rather than owned
by the cache; `unlink` deliberately does not, so an entry written inside one
before that check existed can still be taken away.

If the directory is omitted, `link` reads `source_dir` from the source checkout
selected with `--catalog-root`. Keep that value pointing at the original.
To populate a cache from every eligible source descriptor at once, pass `--all`
in place of a dataset name:

```bash
ethos-data --root /shared/ethos/public link --all --catalog-root /path/to/source-catalogue --dry-run
ethos-data --root /shared/ethos/public link --all --catalog-root /path/to/source-catalogue
```

Review the preview. Restricted and unresolved-licence datasets are left out of
the namespace, and real directories are never replaced with a link.

Put `--root` **before** `link`, as above, whenever the directory really is a
public cache. There are two spellings and they do not mean the same thing:

| Spelling | Meaning |
| --- | --- |
| `ethos-data --root DIR link --all` | `DIR` is this invocation's public cache. Building it and cleaning it are both permitted. |
| `ethos-data link --all --root DIR` | build a namespace in `DIR`. Nothing is claimed about what `DIR` is. |

Both build the same namespace. Only the first lets `--prune` retract a link for a
dataset the catalogue now calls restricted, because in an unidentified directory
that same link may be another machine's authorised installation — see
[Read the report](#read-the-report). Either way the destination is named in the
run's first two lines; read it there before it writes.

`link --all` refuses outright, with exit `2` and without reading the checkout, if
the directory it is pointed at is this machine's **restricted cache** — or if the
public and restricted caches are configured to the same directory. That cache is
not built from a catalogue; see [Restricted data](#restricted-data).

### Read the report before re-running {#read-the-report}

The run exits `1` when it could not finish the namespace, and names each cause on
its own line. Act on the line rather than repeating the command:

| Line | What it means | What to do |
| --- | --- | --- |
| `missing` | the dataset's `source_dir` is not on this machine | fix `source_dir` or the storage |
| `exposed` | the cache still links a dataset that has since become restricted, or whose licence was withdrawn | re-run with `--prune`, on a root named as a public cache |
| `blocked` | a link in the cache stands where a namespace prefix now belongs, so the entry under it was not written | remove that link, then re-run |
| `conflict` | the checkout gives one name files of its own and datasets below it, so neither can have an entry | fix the checkout as the line says; the datasets below were still linked |
| `obstructed` | a file, or a directory left over from a withdrawn family, stands where the entry belongs | move the file yourself; `--prune` clears an emptied family directory |
| `collides` | the cache spells an entry differently from the catalogue name | rename it as the line says — until then no `prune` runs at all |
| `failed` | one entry could not be written or removed; the rest were still built | fix the cause the message names |

`exposed` is the one to act on the same day: the link is still serving those
bytes to everyone who reads that cache. `ethos-data unlink <dataset>` does not
clear it — after a reclassification to `restricted` that command looks in the
restricted cache and reports no entry, while the public link stays. Use:

```bash
ethos-data --root /shared/ethos/public link --all --catalog-root /path/to/source-catalogue --prune
```

The same entry is then reported as `retract`, the link is removed, and the data
behind it is untouched.

The `--root` goes before `link` here and that is not a style preference. For a
**restricted** dataset the retraction only happens when the run can say the
directory is a public cache; `link --all --root DIR --prune` claims nothing about
`DIR`, so the entry stays `exposed` and the run still exits `1`. The closing
paragraph says as much and prints the identifying spelling to use instead. A
withdrawn **licence** is retracted either way — no namespace may hold a dataset
whose terms nobody has read.

Two cases are never retracted at all. A reclassified dataset the cache holds
as a **real directory** is reported `skip`: that is the cache's own copy of those
bytes, possibly the only one, so deal with it deliberately. An entry reached
through a **borrowed link** is reported `exposed` with the borrowed link named —
remove that link, which discards nothing, rather than the entry inside it.

Avoid `--prune` during migration otherwise: it also removes links for datasets
the catalogue no longer lists, and mid-migration the catalogue is deliberately
behind the filesystem. It never removes a real directory that holds files, and
never removes a name that is a namespace prefix of a dataset the catalogue still
describes. The one directory it does remove is an empty one standing where an
entry belongs — the husk left when a family is collapsed back into a flat
dataset. That is reported `replace`, uses `rmdir` only, and without `--prune`
shows up as `obstructed` instead.

Preview with `--dry-run` before any `--prune` run. It writes nothing, and it
prints the same plan — but not the same exit code: a preview that plans a
`retract` still returns `1`, because it removed nothing and the link is live when
the process exits. A `--prune --dry-run` returning `1` followed by the real run
returning `0` is the expected sequence, not a disagreement.

Create and inspect links on the hosting machine. Windows symbolic links require
Developer Mode or elevation; otherwise use a dataset-root setting. Without them
the affected entries are reported `failed` and the run continues. Directory
junctions are unsuitable because the cache can treat them as owned directories,
and because the `blocked` check only sees symbolic links.

## Materialize copies {#materialize-copies}

Set intended destination permissions/default ACLs first; copying does not preserve
source ownership or ACLs. Keep source files unchanged while copying.

```bash
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public materialize climate-inputs --dry-run
ethos-data --catalog /path/to/datacatalog.json --root /shared/ethos/public materialize climate-inputs
```

The complete inventory is copied and checked before replacing the link. Leave
checksum verification enabled. Pause readers for the final switch, when the link
is briefly absent. Existing real directories are skipped even with `--force`.

To seed an absent entry or copy from another source, append
`--from /legacy/climate-inputs` to the same preview and copy commands. This form
requires one dataset. Without a link or `--from`, a source descriptor's
`source_dir` can supply the source.

Expect a real directory, `materialized` in the report, and
`.ethos-data-materialized.json` recording provenance. The original is preserved.

## Verify the complete dataset {#verify-complete-dataset}

Remove staging and per-dataset overrides that would redirect the check to the
original. A package's `verify` checks only its selected files. To check an entire
dataset independently, use the integrity API:

```python
import ethos_data

catalog = ethos_data.load_catalog("/path/to/datacatalog.json")
roots = ethos_data.resolve_roots("/shared/ethos/public")
resources = list(catalog.dataset("climate-inputs").resources.values())
findings = ethos_data.verify(catalog, resources, roots, deep=True)
for finding in findings:
    print(finding.status, finding.resource.key)
assert all(finding.status == "ok" for finding in findings)
```

Confirm the intended paths and permissions, then run a representative workflow.
For a materialized dataset, also confirm that the cache entry is a real directory.

## Restricted data {#restricted-data}

`materialize --all` discovers public-cache entries only, and `link --all` refuses
the restricted cache outright: pointed at it, the command exits `2` without
reading the checkout or planning anything. That cache is not built from a
catalogue. Every entry in it is one authorised installation, registered by name
by somebody entitled to hold the bytes — `source_dir` describes the maintainer's
own machine and says nothing about who may have a copy.

Configure a protected restricted root, then explicitly name a licensed dataset:

```bash
ethos-data config set-restricted-cache /shared/ethos/restricted
ethos-data --catalog /path/to/internal/datacatalog.json link licensed-example /legacy/licensed-example
```

If its terms permit a local copy, use `materialize licensed-example --from
/legacy/licensed-example` with the same catalogue, previewing with `--dry-run`.
Verify the complete dataset and permissions as above, substituting its name.
No restricted bytes are downloaded or uploaded, and a link grants no access.

## Retire an original installation {#retire-the-original}

Keep `source_dir` while the original remains the build input. Already uploaded
datasets retain `ethos:uploaded: true` and no `source_dir`.

Before retiring an original whose verified copy becomes the permanent local
installation, remove `source_dir`, set `ethos:frozen: true`, and rebuild.
Do not rehash the copy to establish a new baseline. See
[Copy ownership and frozen inventories](../explanation/caches-and-access.md#copy-ownership-and-frozen-inventories).

Have the owner check legacy scripts, other links, root overrides, files outside
the inventory, and versions needed by older pins. Retirement is a separate
operation. Public copies can later be [uploaded](upload-a-dataset.md);
restricted copies remain local.
