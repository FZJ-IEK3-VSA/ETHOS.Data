# 0006. Specify every file format once

**Status:** proposed · **Date:** 2026-10-02 · **Implemented by:** #11, #12, #13, #27

## Context

Every key and its default must be written down once. The reader and the
writer must agree, and a published index row must say what the source row
says. A draft `dataset.yaml` must be checked before it is built, and its
author helped with completion and templates. The reference must not drift
from the code.

## Decision

`ethos_data.formats` holds one pydantic model per standardised file, thirteen
in all: `dataset.yaml` and a family's `dataset.yaml`, `catalog.yaml`,
`status.yaml`, `collections.yaml`, the settings file, `datapackage.json`,
`shards/<prefix>.json`, `datacatalog.json`, both kinds of `bundle.json`, the
staging registry and the materialization record. Each field declares a type,
a default, whether it is required, a description and four properties, which
the JSON Schema carries as `x-ethos`:

| Property | Means |
|---|---|
| `published` | kept by `publish`; a field without it is stripped from the public catalogue, and the leak check looks for it |
| `promoted` | copied into the index row, so reading it needs no descriptor |
| `user_facing` | printed by `--meta` and by the refusal of a restricted dataset this machine cannot read ([0013](0013-every-input-is-required.md)) |
| `inherited` | taken from the family's `dataset.yaml` when a member does not set it; only keys that cannot weaken a claim are inherited |

Derived from the models:

- validation that reports every problem at once, with its place; a file people
  write is validated when it is read;
- typed access in the code;
- the committed JSON Schemas, rewritten by `python -m ethos_data.formats` and
  checked by a staleness test;
- the strip list and the leak check;
- one index row, shared by the build and `publish`;
- the error texts;
- the reference tables, rendered at site build by an mkdocs hook.

Further rules:

- The files people write have templates, each with a `yaml-language-server`
  schema line. A command that creates such a file starts from its template,
  and the docs include the templates.
- The settings file has no template, because `config set-*` writes it.
  Handoff texts are templates ([0025](0025-handoff-templates.md)), not formats.
- The build's rules are errors. What the specifications add, a wrong type or a
  value outside a closed vocabulary, is a lint warning. Unknown keys pass; an
  unknown `ethos:` key warns, because it is usually a typo.
- Generated files are deterministic, in a fixed key order.
- The model holds the rules all formats share: SHA-256 digests, safe names and
  family membership, and one reader and writer of resource records with their
  sidecars.
- A top-level `dataset.yaml` is never a resource.
- `import ethos_data` loads no pydantic; the models load on first use.

## Alternatives considered

- **Dataclasses with a validator of our own.** About 400 more lines to
  maintain, and poorer messages.
- **JSON Schema files, checked with `jsonschema`.** Rules that cross fields,
  such as derived data needing sources and a derivation, read badly, and the
  code still needs typed access.
- **Committed Markdown copies of the reference, with a staleness test.** A
  second copy to keep current.

## Consequences

- `pydantic>=2` is a dependency, in `pyproject.toml`, `environment.yml` and
  the conda-forge recipe.
- A format change is one reviewable commit: validation, the schema, the
  template checks and the reference change with the model.
- A value that only the specifications reject passes the build, with a
  warning.
- See [File formats](../../../reference/schemas.md), which is partly generated
  from the models.

## Related

- [0005. Read the index first and inventories on demand](0005-lazy-index-descriptors-and-shards.md)
- [0007. Read every generated catalogue through one inventory reader](0007-one-inventory-reader.md)
- [0013. Treat every input as required, and describe what is missing](0013-every-input-is-required.md)
- [0025. Draft the handoffs between roles from templates](0025-handoff-templates.md)
- [0027. Release the public catalogue as a generated view, tagged on GitHub](0027-public-catalogue-releases-on-github.md)
- [5. Building Block View](../building-blocks.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
