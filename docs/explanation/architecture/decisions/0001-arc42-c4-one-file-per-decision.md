# 0001. Describe the target architecture in arc42, with C4 views and one file per decision

**Status:** implemented · **Date:** 2026-10-05 · **Implemented by:** #36

## Context

Readers need procedures, field references, introductions and the
architecture, without two accounts of the same thing. The architecture must be
reviewable before it is implemented, so that a problem in the design is found
before the code that would carry it. Each decision needs a status of its own,
which the pull request that implements it changes. Diagrams must live in
version control and render in the light and the dark theme.

## Decision

- The documentation is organised by Diátaxis: tutorials, how-to guides,
  explanation and reference. arc42's twelve sections sit under Explanation →
  Architecture. Data concepts is a sibling guide, and the architecture links
  to it instead of repeating it.
- The architecture describes the target only, in the present tense. Two places
  say where the code differs from it: the status line of a decision file, and
  the boxes marked **Gap** in the how-to guides, which describe the target too.
- The views follow the C4 model:

| View | C4 level | arc42 section |
|---|---|---|
| System context | 1 | 3. Context and Scope |
| Containers and data stores | 2 | 5. Building Block View, 5.1 |
| Components | 3 | 5. Building Block View, 5.2 and 5.3 |
| Dynamic views, and the dataset lifecycle as a state machine | dynamic | 6. Runtime View |
| Nodes and where each command runs | deployment | 7. Deployment View |

- Each decision is one file in `decisions/`, named `NNNN-slug.md`, with one
  template: a title stated as the decision; a status line with the status, the
  date and the pull requests that implement it; then Context, Decision,
  Alternatives considered, Consequences and Related. The
  [index](index.md) lists every decision with its status.
- A decision is `proposed` until the code on develop does what its Decision
  section says. The last pull request in its "Implemented by" list sets it to
  `implemented`. A decision that also needs an event outside the code, such as
  a first release, names that event in its status line.
- A superseded decision is folded into the decision that takes its place.
  There is no history section, and no record is kept for its history.
- Diagrams are TikZ sources in `docs/diagrams/*.tex`, sharing the C4 styles of
  `ethosstyle.tex`. `docs/diagrams/render.py` renders each one into a light and
  a dark SVG, and the SVGs are committed. Every C4 view draws its own key, and
  every figure has alt text that carries its content.

## Alternatives considered

- **One page of decisions with dated sections.** Every pull request edits the
  same page to change one status, and other pages link to long anchors inside
  it.
- **Keeping superseded records for their history.** A reader has to work out
  which record still holds. With a clean break
  ([0002](0002-clean-break-during-the-beta.md)) there is no compatibility
  constraint for the history to explain.
- **Another diagram language.** A second notation splits the styles and the
  keys. The TikZ styles already render both themes, and committed SVGs keep
  the docs build free of LaTeX and of diagram renderers.

## Consequences

- The decisions index is the page of section 9, at
  `explanation/architecture/decisions/`. Other pages link to a decision file,
  never to an anchor in a list of decisions, and there are no redirect pages.
- A pull request that implements a decision changes that decision's status
  line. The chapters cite no pull request.
- A design problem can be raised against the target before any code changes.
- Editing `ethosstyle.tex` makes every rendered SVG stale, so every diagram is
  rendered again with it.
- See [Architecture documentation](../../../contributing.md#architecture-documentation)
  and [Diagrams](../../../contributing.md#diagrams) in the contributing guide.

## Related

- [0002. Make a clean break during the beta; `catalog migrate` converts the internal catalogue once](0002-clean-break-during-the-beta.md)
- [9. Architectural Decisions](index.md)
- [Architecture overview](../index.md)
