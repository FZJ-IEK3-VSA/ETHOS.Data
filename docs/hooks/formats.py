"""Render the format reference from the specifications while the site is built.

A page asks for a generated block with a line of its own:

    <!-- ethos-data: table dataset -->           the keys of a format
    <!-- ethos-data: table package:IndexRow -->  the keys of a model of one
    <!-- ethos-data: formats -->                 every format and its schema
    <!-- ethos-data: states -->                  the states of status.yaml
    <!-- ethos-data: steps -->                   the steps between them

and the hook replaces the line with the table that
:mod:`ethos_data.formats.reference` renders. The tables therefore say what the
models and the JSON Schemas say, on every build, with nothing to regenerate
by hand. An HTML comment, so a page read on GitHub shows nothing where a
table goes rather than a stray directive.

The package is imported from ``src/`` beside this file, the source the site
documents, as mkdocstrings reads it (``paths: [src]``), not from whatever
version happens to be installed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[2] / "src"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))

from ethos_data.formats import reference

#: One generated block: ``<!-- ethos-data: <what> [<argument>] -->`` on a line of its own.
MARKER = re.compile(
    r"^<!-- ethos-data: (?P<what>[a-z-]+)(?: (?P<argument>[A-Za-z0-9_:.-]+))? -->$",
    re.MULTILINE,
)


def expand(markdown: str, where: str = "the page") -> str:
    """``markdown`` with every marker replaced by the block it names."""

    def block(match: re.Match[str]) -> str:
        try:
            return reference.render(match["what"], match["argument"]).rstrip("\n")
        except ValueError as error:
            from mkdocs.exceptions import PluginError

            raise PluginError(f"{where}: {match[0]}: {error}") from None

    return MARKER.sub(block, markdown)


def on_page_markdown(markdown, page, config, files):
    """The mkdocs hook: every page's markdown, before it is rendered."""
    return expand(markdown, page.file.src_uri)
