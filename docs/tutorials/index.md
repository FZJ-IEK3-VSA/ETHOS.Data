# Tutorials

Each tutorial is a lesson: follow it from start to finish, on practice data
where possible, and you end with something that works. The lessons are grouped
by role; one person may take all of them. To get a specific job done on real
data, use the [how-to guides](../how-to/index.md) instead.

## Data users

You use ETHOS.RESKit or another package and need its input data.

- [Your first fetch](first-fetch.md) — fetch a tiny CSV by catalogue key from a local practice
  server, reuse it in Python, then detect and repair a changed cache copy.
  No public catalogue release or cluster account is needed.
- [Find data through an internal catalogue](restricted-access.md) — distinguish
  hidden metadata from an unavailable installation and use a restricted root
  with synthetic practice data.

## Package maintainers

You integrate data into a package, its examples, workflows, or tests.

- [Develop and propose a dataset](develop-and-propose-data.md) — read a new,
  uncatalogued input through the ordinary API, then prepare what a catalogue
  maintainer needs to accept it. Needs no catalogue account or upload
  credentials.
- [Run a test with repository data](bundled-tests.md) — export a verified copy
  of catalogued test data into a repository, test offline, and see how a
  deliberate local edit is reported.

## Catalogue maintainers

You review proposals, maintain the catalogue, and look after its storage.

- [Add a dataset to the catalogue](add-a-dataset.md) — on a practice catalogue
  on your own machine: describe a dataset, build its inventory, publish the
  public view, link the data into a shared cache, and turn that link into a
  copy. Nothing is uploaded or published anywhere.

For the design behind these steps, see [Explanation](../explanation/index.md).
