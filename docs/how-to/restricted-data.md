# Work with restricted data

Some catalogued datasets require licensed access. Ordinary `ethos-data` retrieval
reads an authorised local installation in place, or fails with an explanation
when it cannot reach one. It never downloads these files into the public cache.
Maintainers register them through [Add internal and restricted datasets](add-internal-and-restricted-data.md);
any local storage relocation must respect the terms for that installation.

## If you have access

Say where the licensed copy is, once:

```bash
ethos-data config set-restricted-cache /path/to/ice2_data_restricted --scope environment
```

Every restricted dataset is then read from `<restricted cache>/<dataset>/…`,
in place. Nothing is copied and nothing is written; the directory can be
read-only, and should be.

For a single dataset in a non-standard location, the per-dataset escape hatch
works too and wins over the restricted cache:

```bash
ethos-data config set-root licensed-example /path/to/licensed-example --scope environment
```

## If you do not

Most people, most of the time, are not on the institute cluster and have no
right to the licensed bytes. That is a legitimate, permanent state, not a
misconfiguration — so it is offered as a choice:

```bash
ethos-data ... --skip-unavailable                  # for one run
ethos-data config set-skip-unavailable true        # once, for this machine
```

Datasets you cannot reach are then **left out of the result and listed**,
rather than silently missing. In Python, the unreachable files simply have no
key in the returned mapping, and a `UserWarning` names them:

```python
files = fetch("onshore_wind", collections="collections.yaml")
if "licensed-example/layer.tif" not in files:
    ...     # a missing key is something you can notice
```

That is why the entry is absent rather than mapped to a path: a `Path` to a
file that is not there is not something a caller can check.

```bash
ethos-data config unset-skip-unavailable           # back to stopping
```

## What the refusal looks like

Without a restricted cache and without `--skip-unavailable`, asking for one
stops the command and tells you both ways forward:

```title="Output"
dataset 'licensed-example' is restricted and is never downloaded.
  Licensed from <vendor> under contract <ref>. Redistribution prohibited.
No restricted cache is configured on this machine.

If you have access to the licensed copy, say where it is:
    ethos-data config set-restricted-cache /path/to/ice2_data_restricted --scope environment
    ethos-data config set-root licensed-example /path/to/licensed-example --scope environment    # just this one

If you do not -- working away from the institute cluster, say -- then carry on without it:
    ethos-data ... --skip-unavailable
    ethos-data config set-skip-unavailable true    # once, for this machine
Datasets you cannot reach are then left out of the result and listed, rather than silently missing.
```

The failure is deliberate and it is up front: a clear message before anything
runs, rather than a workflow dying deep inside on a missing file.

## Supported operations for restricted data

| | |
|---|---|
| downloaded | never, under any configuration |
| copied into the public cache | never |
| shadowed by the [staging root](stage-unpublished-data.md) | never — licence terms are not a development concern |
| uploaded by `ethos-data catalog upload` | refused outright |
| materialized from a namespace link | explicit local copy in the restricted root, where permitted; see [restricted migration](migrate-cluster-data.md#restricted-data) |

## Verifying it

`ethos-data verify` covers restricted data like anything else, and reports what
it could not reach as `unavailable here` rather than as a failure:

```bash
ethos-data verify --all
```

Because restricted data is read in place from storage the cache does not own,
`--deep` is more worth running on it than on downloaded data, which was
hash-checked when it arrived.

## See also

- [Caches, classes and roots](../explanation/caches-and-access.md) — the three
  access classes and the full resolution order.
- [Licensing and immutability](../explanation/licensing.md) — how a dataset
  comes to be marked restricted in the first place.

- [Add internal and restricted datasets](add-internal-and-restricted-data.md) — maintainer registration, inventory updates, and metadata release.
- [Migrate cluster data](migrate-cluster-data.md#restricted-data) — authorised local installation links and later relocation.
