# Architecture

This guide answers how ETHOS.Data is built and why. ETHOS.Data, the Python
package `ethos_data`, connects scientific packages such as ETHOS.RESKit to
catalogue metadata and dataset files, and gives catalogue maintainers the
tools to keep both. The guide describes the target architecture, in the
present tense. Each decision file carries its implementation status.

## How the guide is organised

The guide follows the twelve sections of [arc42](https://arc42.org/overview/),
and its views follow the levels of the [C4 model](https://c4model.com/). It
belongs to the Explanation part of the site: procedures are in the
[how-to guides](../../how-to/index.md), exact fields and signatures in
Reference, and the concepts for users in [Data concepts](../data-concepts.md).
[Decision 0001](decisions/0001-arc42-c4-one-file-per-decision.md) records this
structure.

| Section | Question it answers | C4 views |
|---|---|---|
| [1. Introduction and Goals](introduction-and-goals.md) | What must ETHOS.Data do, for whom, and which qualities come first? | — |
| [2. Architecture Constraints](constraints.md) | Which conditions set by others must the design accept? | — |
| [3. Context and Scope](context.md) | Whom does ETHOS.Data exchange information with, and where does its responsibility end? | Level 1: system context |
| [4. Solution Strategy](solution-strategy.md) | Which approaches meet the goals? | — |
| [5. Building Block View](building-blocks.md) | Which parts make up ETHOS.Data, and how do they depend on each other? | Level 2: containers and data stores (5.1); level 3: components (5.2, 5.3) |
| [6. Runtime View](runtime.md) | How do the parts work together, and which states does a dataset pass through? | Dynamic views; the state machine of a dataset |
| [7. Deployment View](deployment.md) | Where does each part run, and where does its data live? | Deployment |
| [8. Crosscutting Concepts](crosscutting-concepts.md) | Which rules hold across all parts? | — |
| [9. Architectural Decisions](decisions/index.md) | Which decisions shape the design, and why? One file per decision. | — |
| [10. Quality Requirements](quality-requirements.md) | How is each quality goal checked? | — |
| [11. Risks and Technical Debt](risks-and-technical-debt.md) | Which risks and debts does the design accept? | — |
| [12. Glossary](glossary.md) | What do the terms mean? | — |

## Reading the diagrams

Each diagram carries a key that names the kinds of element and arrow it uses;
the pages add no legend. In the C4 views, blue marks ETHOS.Data, its
containers and its data stores, teal its components, and grey the systems and
stores outside it. An element gives its kind and technology in brackets, and
an arrow gives what it carries and, in brackets, the technology. A solid arrow
is a request or a dependency. A dashed arrow is a handoff that a person makes,
such as a proposal or a notice. An arrow to dCache is teal: solid for an
anonymous download, dashed for authenticated maintenance. The dynamic views
number their steps, and they and the state machine explain their notation
inside the picture. Each diagram has a light and a dark version, and its alt
text carries its content.

## Where to start

| You are | Start with | Then read |
|---|---|---|
| Data user | [3. Context and Scope](context.md) | [6](runtime.md): how a handle finds every file or refuses it; [7](deployment.md): workstations and the cluster computer |
| Package maintainer | [3. Context and Scope](context.md) | [6](runtime.md): handles, repository bundles, staging and package CI; [8](crosscutting-concepts.md): release bounds and changed test data; decisions [0018](decisions/0018-numbered-catalogue-releases.md) and [0020](decisions/0020-repository-bundles.md) |
| Catalogue maintainer | The [dataset lifecycle](runtime.md#dataset-lifecycle) | [5](building-blocks.md): the maintenance pipelines; [7](deployment.md): the cluster layout; decisions [0022](decisions/0022-dataset-status-files.md), [0023](decisions/0023-maintenance-pipelines.md), [0026](decisions/0026-internal-catalogue-on-the-cluster.md) and [0028](decisions/0028-read-only-shared-cache.md) |
| Reviewer or contributor | [4. Solution Strategy](solution-strategy.md) and [9. Architectural Decisions](decisions/index.md) | [5](building-blocks.md): the layers, where a bug hunt also starts; [10](quality-requirements.md) and [11](risks-and-technical-debt.md): the quality scenarios and the risks |

The tasks of each role are in the [how-to guides](../../how-to/index.md), and
the [use-case figure](../../how-to/index.md#roles-together) shows what the
roles hand each other.
