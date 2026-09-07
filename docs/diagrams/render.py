#!/usr/bin/env python3
"""Render every docs/diagrams/*.tex to a light/dark pair of SVGs.

    python docs/diagrams/render.py            # all, if the source is newer
    python docs/diagrams/render.py caches     # just caches.tex
    python docs/diagrams/render.py --force    # ignore timestamps

Output lands in docs/assets/diagrams/<name>-light.svg and -dark.svg, and both
are COMMITTED. An ordinary `mkdocs build` therefore needs no LaTeX at all; this
script runs only when a diagram's source changes. That is the same arrangement
ETHOS.TSAM uses for its d2 architecture diagrams, and it keeps the docs CI job
to a pip install.

Why two files instead of one plus CSS: pdftocairo converts text to vector paths,
so there is no text left in the SVG to recolour, and a single render is
unreadable in one of the two themes. The pages select with Material's
"#only-light" / "#only-dark" convention.

Toolchain (conda env, see environment.yml):
    tectonic   TikZ -> PDF. Fetches LaTeX packages on demand, which matters:
               a system TeX Live install often lacks standalone, preview and
               arrows.meta, all of which these diagrams use.
    pdftocairo PDF -> SVG (poppler).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets" / "diagrams"
STYLE = HERE / "ice2style.tex"

PREAMBLE = r"""\documentclass[border=4pt]{standalone}
\def\icetwodark{%d}
\input{%s}
\begin{document}
%s
\end{document}
"""


def need(tool: str) -> str:
    found = shutil.which(tool)
    if not found:
        sys.exit(
            f"{tool} not found on PATH.\n"
            "The diagram toolchain is a dev dependency, not a docs-build one:\n"
            "    mamba env update -f environment.yml\n"
            "    mamba activate ice2_data_env\n"
            "Committed SVGs mean `mkdocs build` never needs it."
        )
    return found


def render(source: Path, dark: bool, force: bool) -> bool:
    suffix = "dark" if dark else "light"
    target = OUT / f"{source.stem}-{suffix}.svg"
    if not force and target.is_file():
        newest = max(source.stat().st_mtime, STYLE.stat().st_mtime)
        if target.stat().st_mtime >= newest:
            return False

    body = source.read_text()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tex = tmp / "d.tex"
        tex.write_text(PREAMBLE % (1 if dark else 0, STYLE.as_posix(), body))

        result = subprocess.run(
            [need("tectonic"), "-X", "compile", "--outdir", str(tmp),
             "--keep-logs", "--print", str(tex)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            # Tectonic puts the useful lines on stderr; show them rather than a
            # traceback about a missing PDF three frames later.
            sys.exit(f"\n{source.name} ({suffix}) failed to compile:\n{result.stderr}")

        OUT.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [need("pdftocairo"), "-svg", str(tmp / "d.pdf"), str(target)],
            check=True,
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="diagram stems (default: all)")
    parser.add_argument("--force", action="store_true", help="re-render even if up to date")
    args = parser.parse_args()

    sources = sorted(HERE.glob("*.tex"))
    sources = [s for s in sources if s != STYLE]
    if args.names:
        wanted = set(args.names)
        sources = [s for s in sources if s.stem in wanted]
        missing = wanted - {s.stem for s in sources}
        if missing:
            sys.exit(f"no such diagram: {', '.join(sorted(missing))}")
    if not sources:
        sys.exit("no diagram sources found")

    written = 0
    for source in sources:
        for dark in (False, True):
            if render(source, dark, args.force):
                print(f"  {source.stem}-{'dark' if dark else 'light'}.svg")
                written += 1
    print(f"{written} file(s) written" if written else "everything up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
