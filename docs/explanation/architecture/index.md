# Architecture

`ethos-data` connects scientific packages such as ETHOS.RESKit to catalogue
metadata and the dataset files that metadata describes. This architecture guide
follows the twelve named sections of [arc42](https://arc42.org/overview/).
The surrounding site uses Diátaxis: procedures belong in how-to guides, exact
fields and signatures in Reference, and introductory explanations in
[Data concepts](../data-concepts.md).

| Section | What it explains |
|---|---|
| [1. Introduction and Goals](introduction-and-goals.md) | The needs of data users, package maintainers, and catalogue maintainers |
| [2. Architecture Constraints](constraints.md) | External conditions the design must accommodate |
| [3. Context and Scope](context.md) | The package boundary, people, and external systems |
| [4. Solution Strategy](solution-strategy.md) | How the main design choices address the goals |
| [5. Building Block View](building-blocks.md) | Package decomposition, dependencies, and interfaces |
| [6. Runtime View](runtime.md) | Requests, failures, development, and catalogue publication |
| [7. Deployment View](deployment.md) | Workstations, cluster storage, catalogue hosting, and CI |
| [8. Crosscutting Concepts](crosscutting-concepts.md) | Rules shared across components and workflows |
| [9. Architectural Decisions](decisions.md) | Significant choices and their consequences |
| [10. Quality Requirements](quality-requirements.md) | Quality tree and observable scenarios |
| [11. Risks and Technical Debt](risks-and-technical-debt.md) | Known limitations and outstanding work |
| [12. Glossary](glossary.md) | Shared vocabulary |

Data users can start with sections **3** and **6.1**. Package maintainers will
also need the local-development and testing scenarios in **6**, together with
the deployment constraints in **7**. Catalogue maintainers should read the
publication lifecycle in **6.3** and the maintainer decomposition in **5.2**.
Section **5** is also the starting point for diagnosing bugs in the package.

Views describe the current implementation unless explicitly labelled **planned**.
Hosting choices describe the intended deployment, not a claim that repositories
or releases have already been provisioned.
