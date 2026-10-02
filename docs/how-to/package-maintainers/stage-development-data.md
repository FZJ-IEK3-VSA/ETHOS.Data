# Stage development data

Use data that is not in the catalogue yet through the ordinary `paths()` and
`fetch()` calls, so a workflow can be developed against it before it is
proposed. Staged data is read where it lies: nothing is fetched, copied or
checksummed, and the calls simply return its paths. Staging needs no
catalogue write access and no credentials.

To try a dataset that *is* in the catalogue but not yet in your collections,
staging is not needed: ask for it by key with `data.catalog_path(KEY)`, see
[Use data in a script](../data-users/use-data-in-a-script.md#by-key). Test
data that should end up in the catalogue is better created as a
[bundle](keep-data-in-the-repository.md) in the repository, which carries its
description with it. A bundle holds public data with settled licensing only;
data whose licensing is unsettled is developed here, in staging.

A staged dataset is a directory registered under a name. While it is
registered, that name resolves to the directory instead of to the catalogue,
for every ETHOS tool you run with this configuration.

## 1. Choose a staging root

```bash
<your-tool>-data config set-staging-cache /scratch/me/ethos-staging
```

The root has no default and is yours: it is set in your own configuration,
never shared with other users. Keep it apart from the public and restricted
caches.

## 2. Register the directory {#stage-development-data}

```bash
<your-tool>-data staging add my-new-dataset /scratch/me/candidate --note "candidate for review"
<your-tool>-data staging list
```

Registration links to the directory by default, so later edits there are
seen at once. `--copy` copies it instead, which turns the entry into a
snapshot. Restricted datasets are never shadowed: who may read them is not a
development concern.

`staging add` also writes a minimal `dataset.yaml` into the directory, unless
one is there already:

```yaml
name: my-new-dataset
source_dir: .
description: candidate for review
```

That file is the start of the later [proposal](propose-a-dataset.md); fill in
the source, licence and origin as you learn them. Staging itself does not
read it.

## 3. Use it

Add the dataset to a collection in your package's file as under
[Write a collections file](write-a-collections-file.md), then call the
ordinary API:

```bash
<your-tool>-data show my_workflow
<your-tool>-data fetch my_workflow --paths
```

Collection resolution still needs a readable catalogue index, even for a
dataset that exists only in staging. Every read of staged data warns, and
`verify` reports staged files as `unverifiable`, so an official run cannot use
them unnoticed.

## 4. Remove it

```bash
<your-tool>-data staging remove my-new-dataset
```

Removing a linked entry leaves the source directory alone. A copied entry
needs `--force` and is deleted. Once a dataset has been accepted into the
catalogue, remove its staging entry so the accepted version is what your
package reads.

See the [staging command reference](../../reference/cli/package-data.md#staging)
for every flag.
