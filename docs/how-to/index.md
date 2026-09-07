# How-to guides

Task-focused recipes. They assume you already know what `ice2-data` does and
which knob you want to turn — if you are still finding your feet,
[Your first fetch](../tutorials/first-fetch.md) walks the whole thing end to
end. For *why* a rule exists, see [Explanation](../explanation/index.md).

## Who does what

<figure markdown="span">
  ![Use cases by actor: data user, library author, catalogue maintainer](../assets/diagrams/usecases-overview-light.svg#only-light){ .diagram }
  ![Use cases by actor: data user, library author, catalogue maintainer](../assets/diagrams/usecases-overview-dark.svg#only-dark){ .diagram }
  <figcaption>Three actors, and the guides below grouped by which one you are.
  Dashed use cases write; everything else only reads.</figcaption>
</figure>

The one crossing relation is worth noticing: a library can only name a dataset
the catalogue already describes, so
[Write a collections file](write-a-collections-file.md) depends on somebody
having done [Describe a dataset](describe-a-dataset.md) first. If that somebody
is also you, the [round-trip tutorial](../tutorials/add-a-dataset.md) walks both
halves in order.

## Find your task

| I want to… | Page |
|---|---|
| put the cache somewhere other than `~/.cache` | [Point the cache somewhere](configure-the-cache.md) |
| set it once for a whole cluster | [Point the cache somewhere](configure-the-cache.md#on-a-cluster) |
| use a dataset that is already on this machine | [Use data already on disk](use-data-already-on-disk.md) |
| work with licensed data, or work *without* it | [Work with restricted data](restricted-data.md) |
| find out whether my data is still intact | [Check and repair the cache](verify-and-repair.md) |
| stop depending on a symlink into somebody's project folder | [Check and repair](verify-and-repair.md#materialize-turning-a-borrowed-dataset-into-one-you-own) |
| cache downloaded data between CI runs | [Run it in CI](run-in-ci.md) |
| declare which files my package needs | [Write a collections file](write-a-collections-file.md) |
| use data that is not in the catalogue yet | [Stage uncatalogued data](stage-unpublished-data.md) |
| add a dataset to the catalogue | [Describe a dataset](describe-a-dataset.md) |
| put a dataset's bytes on dCache | [Upload a dataset](upload-a-dataset.md) |
| regenerate the public catalogue | [Publish the catalogue](publish-the-catalogue.md) |
| take a dataset out of publication, or delete it | [Withdraw a dataset](withdraw-a-dataset.md) |
| start a catalogue from nothing | [Bootstrap a new catalogue](bootstrap-a-catalogue.md) |

## Getting data

<figure markdown="span">
  ![Consumer use cases and the command for each](../assets/diagrams/usecases-getting-data-light.svg#only-light){ .diagram }
  ![Consumer use cases and the command for each](../assets/diagrams/usecases-getting-data-dark.svg#only-dark){ .diagram }
  <figcaption>What a data user does, and the command that does it.</figcaption>
</figure>

**[Point the cache somewhere](configure-the-cache.md)** — the six ways to set
the cache directory, which one to pick, and how to set it once for a whole
machine or a whole cluster.

**[Use data already on disk](use-data-already-on-disk.md)** — read a dataset
where it lies instead of downloading it: a cluster share, a private copy, or
data that is catalogued but not yet uploaded.

**[Work with restricted data](restricted-data.md)** — licensed datasets that
may never be copied into a shared cache, and how to carry on without them when
you are not on the institute cluster.

**[Check and repair the cache](verify-and-repair.md)** — `verify` for sizes and
checksums, `--repair` to re-fetch what drifted, and `materialize` to turn a
borrowed dataset into one the cache owns.

**[Run it in CI](run-in-ci.md)** — cache the downloaded data between runs, and
pin the catalogue so a green build stays green.

## Building on it

**[Write a collections file](write-a-collections-file.md)** — the pattern
grammar, `extends`, sidecars, and pinning a catalogue version.

**[Stage uncatalogued data](stage-unpublished-data.md)** — develop against data
that is still changing shape, using the ordinary API from day one, with no
hard-coded paths to unpick later.

## Maintaining a catalogue

These use `ice2-data catalog`, the writing half of the package. Start with the
[round-trip tutorial](../tutorials/add-a-dataset.md) if you have not done this
before.

<figure markdown="span">
  ![The catalogue lifecycle: describe, build, upload, publish; and withdrawal in reverse](../assets/diagrams/usecases-maintainer-light.svg#only-light){ .diagram }
  ![The catalogue lifecycle: describe, build, upload, publish; and withdrawal in reverse](../assets/diagrams/usecases-maintainer-dark.svg#only-dark){ .diagram }
  <figcaption>The maintainer guides in the order the runbooks walk them. These
  steps are ordered, and withdrawal deliberately runs them in reverse.</figcaption>
</figure>

**[Describe a dataset](describe-a-dataset.md)** — every `dataset.yaml` key,
narrowing an inventory with `ice2:include`/`ice2:exclude`, and sharding a large
one.

**[Upload a dataset](upload-a-dataset.md)** — the one-time credential setup and
the runbook for putting bytes on dCache, including what to do when it fails.

**[Publish the catalogue](publish-the-catalogue.md)** — generate the public
subset, and check that nothing internal leaked into it.

**[Withdraw a dataset](withdraw-a-dataset.md)** — unpublish, then delete. The
order is the opposite of publishing, and it matters.

**[Bootstrap a new catalogue](bootstrap-a-catalogue.md)** — day zero: before
`catalog.yaml` exists, before the dCache folder exists.

---

For the commands and flags themselves, see
[`ice2-data`](../reference/cli/ice2-data.md) and
[`ice2-data catalog`](../reference/cli/catalog.md); for the config keys,
[Configuration](../reference/configuration.md).
