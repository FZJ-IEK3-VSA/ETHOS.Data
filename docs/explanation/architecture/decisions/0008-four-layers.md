# 0008. Build the package in four layers: model, adapters, services, presentation

**Status:** implemented · **Date:** 2026-10-02 · **Implemented by:** #10, #13, #17, #20, a new PR (service groups)

## Context

Library code serves scripts, tests and the command line alike, so it may
neither print nor exit the process. Reading data must not depend on the
internals of catalogue maintenance. The command line parses and prints, and
holds no logic that a script would need. One lazy import can reverse the
direction unnoticed, so a test must check every import.

## Decision

| Layer, from the bottom | Modules | Holds |
|---|---|---|
| Model | `formats`, `model` | specifications, keys, resources, names, digests, versions, the lifecycle, the inventory reader, path matching |
| Adapters | `adapters` | the ports and their real and fake implementations ([0009](0009-ports-and-fakes-for-external-systems.md)) |
| Services: data access | `config`, `catalogs`, `selection`, `access`, `retrieval`, `verify`, `bundles`, `staging`, `linking`, `materialize`, `selftest`, `handoffs`, and the local-files service that walks and hashes data directories | settings, the catalogue reader, selection, the lookup chain, downloads, verification, bundles, staging, cache entries, the self-test, handoffs |
| Services: catalogue maintenance | `maintain` | the pipelines that build, upload, record, release and remove ([0023](0023-maintenance-pipelines.md)) |
| Presentation | `cli`, `maintain.cli`, the facade `ethos_data` | parsing, wiring, printing, exit statuses |

- A module imports only from its own layer and the layers below. `errors` and
  `report` are shared by all four and import nothing from the package.
- Catalogue maintenance may use data access. Data access never imports
  `maintain`.
- The model reads no settings, makes no network call and writes nothing. It
  reads only files it is handed, to hash them, and its own package resources,
  such as templates and schemas. The developer entry point
  `python -m ethos_data.formats` rewrites the committed schemas.
- Adapters import only the model and the shared modules. Services reach
  external systems only through ports, and default to the real adapters.
- Typed errors carry the exit status: `EthosDataError` (2) for a request that
  cannot be served, and its subclass `MaintenanceError` (1) for a maintenance
  command that refused its input. `except EthosDataError` catches every
  refusal.
- There is one reporting channel, `report.info` and `report.warning`. Inside a
  command the reporter prints `warning: …`; outside one, the default reporter
  issues Python warnings of the matching category.
- Services return results. Only the presentation prints, as
  `error: <message>`, and chooses the exit status.
- The facade `ethos_data` is the public API: the handles, the types, the
  operations, the settings-file writers, the names of the environment
  variables and every error class.
- `tests/test_layers.py` checks every import, lazy ones included, for the
  layer direction and the group rule. Its one listed exception is `selection`
  → `cli`, for `Collections.main()`, and a second test fails when that
  exception is not needed. A guard test keeps `print` in `cli.py`, `report.py`
  and `formats/__main__.py`.

## Alternatives considered

No alternative was recorded when the layers were decided. These are the
obvious ones, and why they lose:

- **A separate distribution for catalogue maintenance.** It would keep the
  maintenance code out of readers' installations, but the maintenance
  commands use the same inventory reader, lookup chain and caches as readers,
  so two packages would have to be versioned and released together. The group
  rule gives the same separation inside one package: `import ethos_data`
  loads no catalogue maintenance.
- **Layers without service groups.** Data access could then import catalogue
  maintenance, and the reader would come to depend on the writer's internals
  without a test noticing.

## Consequences

- Pipelines and lookup run in tests without the network.
- A violation fails a test that names the module and the import.
- Library users receive warnings as Python warnings, and command-line users
  as `warning:` lines.
- The command line is one module, `cli.py`, of about 2,000 lines, and
  `Collections.main()` is the one import upwards. Both are technical debt.
- See [5. Building Block View](../building-blocks.md) and
  [11. Risks and Technical Debt](../risks-and-technical-debt.md).

## Related

- [0006. Specify every file format once](0006-every-file-format-specified-once.md)
- [0007. Read every generated catalogue through one inventory reader](0007-one-inventory-reader.md)
- [0009. Reach dCache, downloads, metadata sources and git through ports with fakes](0009-ports-and-fakes-for-external-systems.md)
- [0023. Run every catalogue workflow that writes as a pipeline that plans before it acts](0023-maintenance-pipelines.md)
- [5. Building Block View](../building-blocks.md)
- [8. Crosscutting Concepts](../crosscutting-concepts.md)
