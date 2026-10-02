# 12. Glossary

The [shared glossary](../../reference/glossary.md) is the canonical definition of
catalogue terminology for Architecture, tutorials, how-to guides, and Reference.

In this architecture, **data user**, **package maintainer**, and **catalogue
maintainer** refer to the responsibilities in [section 1](introduction-and-goals.md#12-stakeholders).
A **building block** is a named part of the package with a responsibility and
interface; its internals are shown when needed in [section 5](building-blocks.md).
A **layer** is one of the four the building blocks fall into — model,
adapters, services, presentation — each importing only from the ones below it.
A **port** is the interface through which a service reaches an external
system, dCache, the network or git; an **adapter** implements it, and a
**fake** implements it for tests. A **pipeline** is a maintainer command made
of **stages**, each of which plans what it would do before any of them acts.
A **specification** is the model in `ethos_data.formats` that defines one
file format.

A **repository bundle** is test data a package keeps in its repository and is
the source of truth for; the catalogue publishes its versions. An **exported
bundle** is a local copy of catalogue-listed data whose authoritative
published bytes remain on dCache. A temporary modification to either is a
development state, not a new published dataset version, until it is recorded
and released.
