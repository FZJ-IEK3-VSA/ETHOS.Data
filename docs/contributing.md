# Contributing

`ethos-data` lives at
[iek-3/shared-code/ethos-data](https://jugit.fz-juelich.de/iek-3/shared-code/ethos-data)
on jugit. Issues, merge requests and questions are all welcome.

## What lives where

Three repositories are involved, and knowing which one a change belongs in
saves most of the confusion:

| Repository | Holds | Change it when |
|---|---|---|
| **ethos-data** (this one) | the code: the reader (`ethos_data`) and the writer (`ethos_data.maintain`) | the *format* or the *tooling* changes |
| **ethos-data-catalog-internal** | metadata only: `catalog.yaml`, `datasets/*/dataset.yaml`, generated manifests | a *dataset* is added, described, embargoed or withdrawn |
| **ethos-data-catalog** | the generated public subset | never by hand — it is overwritten by `ethos-data catalog publish` |

A tool that *consumes* data (RESKit, say) changes none of these: it only edits
its own `collections.yaml`. See
[Use it from your own package](tutorials/use-from-a-library.md).

Both halves of the format — the code that writes descriptors and the code that
reads them — deliberately live in this one distribution. A format whose writer
and reader sit in different repositories drifts silently: the reader grows a
feature, the writer never emits it, and nothing fails loudly enough for anyone
to notice.

## Development setup

```bash
git clone https://jugit.fz-juelich.de/iek-3/shared-code/ethos-data.git
cd ethos-data
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

**Restricted data is never written into a shared cache and never silently
downloaded.** If it cannot be reached, asking for it fails with an explanation.
See [Caches, classes and roots](explanation/caches-and-access.md).

## Changing the catalogue format

`ethos:` keys are the format's extension points, and both halves have to move
together:

1. Emit it in `ethos_data/maintain/manifest.py`.
2. Read it in `ethos_data/catalog.py`.
3. Decide whether `ethos_data/maintain/publish.py` should **strip** it from the
   public catalogue (`source_dir`, `ethos:embargo` and `ethos:license_note` are
   stripped; a leak of any of them is the failure that matters).
4. Document it in [File formats](reference/schemas.md).

Manifests are generated, never hand-edited. `ethos-data catalog build --check` fails
if any is stale, which is what CI should run.

## Documentation

These pages are MkDocs + Material; see
[Building this documentation](installation.md#building-this-documentation).
The structure follows [Diátaxis](https://diataxis.fr/), so a new page has a
section by construction:

- a **tutorial** teaches by doing, start to finish, and assumes nothing;
- a **how-to** gets one task done for somebody who already knows what they want;
- an **explanation** justifies a design decision;
- **reference** describes what exists, exhaustively and without narrative.

If a page would fit two of those, it is two pages.

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

The ETHOS logo family uses the shared layout in `docs/branding/logo.tex`,
package symbols in `docs/branding/icons.tex`, and names in
`docs/branding/packages.json`. The typeface is Weissenhof Grotesk from the local
`docs/font/` directory. Rebuild ETHOS.DATA with `python docs/branding/render.py`,
or all eight package designs with `python docs/branding/render.py --all --preview`.
The preview option uses `rsvg-convert` for review sheets and PNG favicons.

Tooling, proportions and asset usage are described in `docs/branding/README.md`.
Commit the outlined SVGs in `docs/assets/branding/`; documentation builds use
these files directly. Local fonts and design references are excluded from the
generated site.

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
`environment.yml` as a dev dependency, and the docs CI job installs neither.
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
