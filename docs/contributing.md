# Contributing

`ethos-data` lives at
[FZJ-IEK3-VSA/ETHOS.Data](https://github.com/FZJ-IEK3-VSA/ETHOS.Data)
on GitHub. Issues, pull requests and questions are all welcome.

## What lives where

Three repositories are involved, and knowing which one a change belongs in
saves most of the confusion:

| Repository | Holds | Change it when |
|---|---|---|
| **ethos-data** (this one) | the code: the reader (`ethos_data`) and the writer (`ethos_data.maintain`) | the *format* or the *tooling* changes |
| **ethos-data-catalog-internal** | metadata only: `catalog.yaml`, `datasets/*/dataset.yaml`, generated manifests | a *dataset* is added, described, embargoed or withdrawn |
| **ETHOS.Data-Catalogue** | the generated public subset | never by hand — it is overwritten by `ethos-data catalog publish` |

A tool that *consumes* data (RESKit, say) changes none of these: it only edits
its own `collections.yaml`. See
[Use ETHOS.Data in your package](how-to/use-from-a-package.md).

Both halves of the format — the code that writes descriptors and the code that
reads them — deliberately live in this one distribution. A format whose writer
and reader sit in different repositories drifts silently: the reader grows a
feature, the writer never emits it, and nothing fails loudly enough for anyone
to notice.

## Development setup

```bash
git clone https://github.com/FZJ-IEK3-VSA/ETHOS.Data.git
cd ETHOS.Data
mamba env create -f environment.yml
mamba activate ethos_data_env
pip install -e . --no-deps
pytest
```

## Style and checks

```bash
ruff check src/ tests/         # lint
ruff format src/ tests/        # format
pytest                         # tests
```

The comment style in this codebase is unusual on purpose: comments explain
**why** a rule exists and what breaks without it, not what the line does. A
patch that changes a rule should change the comment that justifies it in the
same commit — the reasoning is the part that is expensive to recover.

## Two invariants that a patch must not break

**Deduplication depends on path agreement.** Every tool must derive the same
cache path from the same catalogue entry, or the sharing stops silently and
nobody finds out for months. Anything touching `local_path`, `Resource.key`, or
the cache layout is a compatibility change, not a refactor.

**Retrieval never writes restricted data into the public cache or downloads
it.** If it cannot be reached, asking for it fails with an explanation.
See [Caches, classes and roots](explanation/caches-and-access.md).

## Changing the catalogue format

`ethos:` keys are the format's extension points, and both halves have to move
together:

1. Emit it in `ethos_data/maintain/manifest.py`.
2. Read it in `ethos_data/catalogs.py`.
3. Decide whether `ethos_data/maintain/publish.py` should **strip** it from the
   public catalogue (`source_dir`, `ethos:embargo` and `ethos:license_note` are
   stripped; a leak of any of them is the failure that matters).
4. Document it in [File formats](reference/schemas.md).

Manifests are generated, never hand-edited. `ethos-data catalog build --check` fails
if any is stale, which is what CI should run.

## Documentation

These pages are MkDocs + Material; see
[Building this documentation](installation.md#building-this-documentation).
The published site is built by [Read the Docs](https://about.readthedocs.com/)
from `.readthedocs.yaml` whenever `main` changes. That build runs
`mkdocs build --strict`, so a warning that a plain local build only prints
fails the hosted one. The tools it installs are the `docs` extra in
`pyproject.toml`; `environment.yml` lists the same tools for developers, and
the two lists are kept in step by hand.

The structure follows [Diátaxis](https://diataxis.fr/), so a new page has a
section by construction:

- a **tutorial** teaches by doing, start to finish, with stated prerequisites,
  practice inputs, and observable results;
- a **how-to** gets one task done for somebody who already knows what they want;
- an **explanation** justifies a design decision;
- **reference** describes what exists, exhaustively and without narrative.

If a page would fit two of those, it is two pages.

Keep how-to guides focused on prerequisites, necessary actions, and a success
check. Tutorials give learners a reliable exercise with expected results and
brief cues about what to notice. Put extended rationale and comparisons in
Explanation and option inventories in Reference. This follows the
[Diátaxis tutorial guidance](https://diataxis.fr/tutorials/), including its
recommendation to keep explanation brief during an exercise.

Public documentation uses clearly labelled example cluster paths. Obtain actual
deployment locations and internal support contacts through the internal onboarding
channel; do not copy them into these pages.

Tutorials and how-to guides are the pair that blur most easily. A page that
gets one real task done is a how-to guide, even when it is written for
newcomers. A tutorial never sends the reader into a how-to guide halfway
through the lesson, and a how-to guide does not stop to teach; each links to
the other only as a next step.

### Architecture documentation

The [architecture guide](explanation/architecture/index.md) follows the twelve named arc42 sections
within Diátaxis Explanation, alongside the Data concepts pages. Write first for data users and catalogue
maintainers; keep module details in the implementation view, command procedures
in how-to guides, and exhaustive fields and options in reference.

When changing access rules, resource identity, metadata formats, publication
ordering, or external interfaces, update the relevant architecture explanation
and quality scenario in the same change. Reuse existing explanations rather than
copying them into an arc42 chapter. Record significant new decisions with context,
alternatives, consequences, and status; distinguish proposals from implemented
behaviour. Verify guarantees against code and tests, including failure paths.

Validate documentation with `mkdocs build --strict`. When a diagram changes,
render and inspect both themes before committing the source and generated SVGs.

### Logo

These pages show no ETHOS.Data product logo yet: the ETHOS logo family is a
design proposal that has not been adopted. Its sources stay in `docs/branding/`
— the shared layout in `logo.tex`, package symbols in `icons.tex`, and names in
`packages.json`. Tooling, proportions and asset usage are described in
`docs/branding/README.md`. The typeface is Weissenhof Grotesk, read from a local
`docs/font/` directory that is not part of the repository.

Once the logo is adopted, render it with `python docs/branding/render.py` (or
all eight package designs with `python docs/branding/render.py --all --preview`,
which uses `rsvg-convert` for review sheets and PNG favicons), commit the
outlined SVGs in `docs/assets/branding/`, and only then reference them — from
`theme.logo` and `theme.favicon` in `mkdocs.yml` and from the logo row on the
landing page. A reference to an asset that does not exist does not fail
`mkdocs build --strict`; it shows a broken image on every page.

### Diagrams

Diagrams are TikZ. Sources live in `docs/diagrams/*.tex`, sharing the palette
and node vocabulary in `ethosstyle.tex`; the rendered SVGs live in
`docs/assets/diagrams/` and **are committed**.

```bash
python docs/diagrams/render.py                # re-render what changed
python docs/diagrams/render.py usecases-overview --force
```

That means an ordinary `mkdocs build` needs no LaTeX — only editing a diagram
does. The toolchain (`tectonic` for TikZ → PDF, `poppler` for PDF → SVG) is in
`environment.yml` as a dev dependency, and the Read the Docs build installs
neither.
Tectonic rather than a system TeX Live because it fetches LaTeX packages on
demand: these diagrams use `standalone` and `arrows.meta`, which a distro TeX
install frequently lacks.

Every diagram is rendered **twice**, light and dark, and the pages select
between them with Material's `#only-light` / `#only-dark` convention:

```markdown
<figure markdown="span">
  ![alt](../assets/diagrams/name-light.svg#only-light){ .diagram }
  ![alt](../assets/diagrams/name-dark.svg#only-dark){ .diagram }
</figure>
```

The pair is necessary, not belt-and-braces: `pdftocairo` converts text to vector
paths, so there is no text left in the SVG for CSS to recolour, and one render
would be unreadable in one of the two themes.
