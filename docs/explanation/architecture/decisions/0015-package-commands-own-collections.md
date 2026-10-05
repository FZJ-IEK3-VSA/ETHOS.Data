# 0015. Let each package's data command own its collection workflows

**Status:** implemented · **Date:** 2026-09-16

## Context

A package's collections file defines the selections its workflows need and
their test variants. That interface needs one entry point, and the catalogue
a command reads must not depend on the folder it is started in. A second,
generic route to the same collections would give users two commands for one
job and make the result depend on the working directory.

## Decision

- Each package exposes the commands that work on its collections under its
  own name, `<tool>-data`, built with `ethos_data.tool_main(collections_file, ...)`
  or `Collections.main()`. The package ships its one collections file, and no
  option substitutes another.
- The package command offers `show`, `fetch` (with `--plan` and `--paths`),
  `verify`, `staging`, `bundle` and `config`, with the global options
  `--catalog`, `--root` and `--test`.
- The standalone `ethos-data` takes no collections file. It serves catalogue
  keys (`ls`, `fetch <key>`), the settings (`config`), the cache entries
  (`link`, `unlink`, `materialize`) and catalogue maintenance (`catalog`).
- Staging uses shared roots and library code, so every package stages data
  the same way.
- Commands that other decisions add follow the same split: `propose` and
  `report` on the package command, `selftest` and `report` on `ethos-data`
  ([0017](0017-self-test-collection.md), [0025](0025-handoff-templates.md)),
  and `bundle create` and `bundle update` on the package command
  ([0020](0020-repository-bundles.md)).

## Alternatives considered

- **A generic `-c COLLECTIONS` route in `ethos-data`.** One collection
  interface would have two entry points, and the catalogue it reads would
  depend on the working directory.

## Consequences

- The package command is the package maintainer's interface to users; the
  guides call it `<your-tool>-data`.
- A script uses a package command or the Python collections API, never a
  collections file handed to `ethos-data`.
- See [Use ETHOS.Data in your package](../../../how-to/package-maintainers/use-from-a-package.md),
  [Package data commands](../../../reference/cli/package-data.md) and
  [`ethos-data`](../../../reference/cli/ethos-data.md).

## Related

- [0003. One catalogue describes the data; each package's collections file selects from it](0003-one-catalogue-many-collections.md)
- [0014. Name workflow inputs in the collection and pair test and full variants](0014-named-inputs-and-test-full-variants.md)
- [0017. Ship a self-test collection with the package](0017-self-test-collection.md)
- [0020. Keep a package's test data in a repository bundle that the catalogue publishes](0020-repository-bundles.md)
- [0025. Draft the handoffs between roles from templates](0025-handoff-templates.md)
- [3. Context and Scope](../context.md)
- [5. Building Block View](../building-blocks.md)
