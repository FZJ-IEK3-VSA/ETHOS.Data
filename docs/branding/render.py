#!/usr/bin/env python3
"""Render the ETHOS logo family with Tectonic and the local FZJ typeface.

    python docs/branding/render.py --preview       # ETHOS.DATA
    python docs/branding/render.py --all --preview # whole family

Only outlined SVGs and rendered PNGs are exported. Local fonts and reference
manuals are not build or runtime dependencies of the documentation site.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "assets" / "branding"
DEFAULT_FONTS = HERE.parent / "font/weissenhof-grotesk/weissenhof-grotesk/OTF"
FONT_STYLES = ("Regular", "Bold", "Italic", "BoldItalic")
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def need(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise SystemExit(f"{name} is required; see docs/branding/README.md")
    return found


def write_svg(root: ET.Element, path: Path) -> None:
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    print(path.relative_to(HERE.parents[1]), flush=True)


def render(package: dict, fonts: Path, dark: bool = False, icon: bool = False) -> Path:
    suffix = "icon" if icon else f"logo-{'dark' if dark else 'light'}"
    name = f"{package['slug']}-{suffix}"
    with tempfile.TemporaryDirectory(prefix="ethos-logo-") as directory:
        temporary = Path(directory)
        for style in FONT_STYLES:
            filename = f"WeissenhofGrotesk-{style}.otf"
            (temporary / filename).symlink_to(fonts / filename)
        (temporary / "icons.tex").symlink_to(HERE / "icons.tex")
        (temporary / "layout.tex").symlink_to(HERE / "logo.tex")
        source = temporary / "logo.tex"
        source.write_text(
            "\\documentclass[border=0pt]{standalone}\n"
            f"\\def\\ethosdark{{{int(dark)}}}\n"
            f"\\def\\ethossymbolonly{{{int(icon)}}}\n"
            f"\\def\\ethosname{{{package['wordmark']}}}\n"
            f"\\def\\ethosicon{{{package['icon']}}}\n"
            "\\input{layout.tex}\n"
        )
        result = subprocess.run(
            [need("tectonic"), "-X", "compile", "--outdir", str(temporary), str(source)],
            cwd=temporary, capture_output=True, text=True,
        )
        if result.returncode:
            raise SystemExit(f"{name}: {result.stderr}")
        if not icon:
            font_info = subprocess.check_output(
                [need("pdffonts"), str(temporary / "logo.pdf")], text=True,
            )
            if "WeissenhofGrotesk-Bold" not in font_info:
                raise SystemExit(f"{name}: expected Weissenhof Grotesk Bold, got:\n{font_info}")
        rendered = temporary / "logo.svg"
        subprocess.run([need("pdftocairo"), "-svg", str(temporary / "logo.pdf"),
                        str(rendered)], check=True)
        root = ET.parse(rendered).getroot()
        root.set("role", "img")
        root.set("aria-labelledby", f"{name}-title {name}-description")
        title = ET.Element(f"{{{SVG}}}title", id=f"{name}-title")
        title.text = package["wordmark"]
        description = ET.Element(f"{{{SVG}}}desc", id=f"{name}-description")
        description.text = f"{package['symbol']}. {package['purpose']}."
        root.insert(0, title)
        root.insert(1, description)
        destination = OUT / f"{name}.svg"
        write_svg(root, destination)
        return destination


def embedded(asset: Path, prefix: str, x: float, y: float, scale: float) -> ET.Element:
    """Place outlined artwork at a shared scale without colliding glyph ids."""
    logo = deepcopy(ET.parse(asset).getroot())
    ids = {element.attrib["id"]: f"{prefix}-{element.attrib['id']}"
           for element in logo.iter() if "id" in element.attrib}
    for element in logo.iter():
        for key, value in list(element.attrib.items()):
            if key == "id":
                element.set(key, ids[value])
            elif key == "aria-labelledby":
                element.set(key, " ".join(ids.get(part, part) for part in value.split()))
            elif value.startswith("#") and value[1:] in ids:
                element.set(key, "#" + ids[value[1:]])
            elif "url(#" in value:
                for original, renamed in ids.items():
                    value = value.replace(f"url(#{original})", f"url(#{renamed})")
                element.set(key, value)
    _, _, width, height = map(float, logo.attrib["viewBox"].split())
    logo.attrib.update(x=str(x), y=str(y), width=str(width * scale), height=str(height * scale))
    return logo


def canvas(width: int, height: int, label: str) -> ET.Element:
    return ET.Element(f"{{{SVG}}}svg", {
        "width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}",
        "role": "img", "aria-label": label,
    })


def background(root: ET.Element, width: int, height: int, colour: str, y: int = 0) -> None:
    ET.SubElement(root, f"{{{SVG}}}rect", {
        "x": "0", "y": str(y), "width": str(width), "height": str(height), "fill": colour,
    })


def png(source: Path, destination: Path, size: int | None = None) -> None:
    command = [need("rsvg-convert"), str(source), "-o", str(destination)]
    if size is not None:
        command.extend(["--width", str(size), "--height", str(size)])
    subprocess.run(command, check=True)


def preview_pair(package: dict) -> None:
    root = canvas(1200, 520, f"{package['wordmark']} on light and dark backgrounds")
    for index, (theme, colour) in enumerate((("light", "#FFFFFF"), ("dark", "#1E2129"))):
        background(root, 1200, 260, colour, y=index * 260)
        asset = OUT / f"{package['slug']}-logo-{theme}.svg"
        _, _, width, height = map(float, ET.parse(asset).getroot().attrib["viewBox"].split())
        scale = min(1080 / width, 180 / height)
        root.append(embedded(asset, theme, 60, index * 260 + 40, scale))
    destination = OUT / f"{package['slug']}-logo-preview.svg"
    write_svg(root, destination)
    png(destination, destination.with_suffix(".png"))


def family_preview(packages: list[dict], dark: bool) -> None:
    theme = "dark" if dark else "light"
    assets = [OUT / f"{package['slug']}-logo-{theme}.svg" for package in packages]
    widths = [float(ET.parse(asset).getroot().attrib["viewBox"].split()[2]) for asset in assets]
    # Keep the icon and font sizes identical across names of different lengths.
    scale = min(640 / max(widths), 1.05)
    height = ((len(packages) + 1) // 2) * 156 + 48
    root = canvas(1440, height, f"Proposed ETHOS logo family, {theme} background")
    background(root, 1440, height, "#1E2129" if dark else "#FFFFFF")
    for index, asset in enumerate(assets):
        root.append(embedded(asset, f"package-{index}", 40 + (index % 2) * 720,
                             32 + (index // 2) * 156, scale))
    destination = OUT / f"ethos-family-{theme}-preview.svg"
    write_svg(root, destination)
    png(destination, destination.with_suffix(".png"))


def favicon_preview(packages: list[dict]) -> None:
    root = canvas(760, 64 + len(packages) * 104, "ETHOS favicons at 16, 32, 48 and 64 pixels")
    background(root, 760, 64 + len(packages) * 104, "#FFFFFF")
    for row, package in enumerate(packages):
        asset = OUT / f"{package['slug']}-icon.svg"
        height = float(ET.parse(asset).getroot().attrib["viewBox"].split()[3])
        for column, size in enumerate((16, 32, 48, 64)):
            root.append(embedded(asset, f"icon-{row}-{size}", 48 + column * 100,
                                 48 + row * 104 + (64 - size) / 2, size / height))
        wordmark = OUT / f"{package['slug']}-logo-light.svg"
        root.append(embedded(wordmark, f"name-{row}", 464, 67 + row * 104, 0.35))
    destination = OUT / "ethos-family-favicons-preview.svg"
    write_svg(root, destination)
    png(destination, destination.with_suffix(".png"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="render all entries in packages.json")
    parser.add_argument("--preview", action="store_true", help="also export PNG favicons and review sheets")
    parser.add_argument("--font-dir", type=Path, default=DEFAULT_FONTS, help="local Weissenhof Grotesk OTF directory")
    args = parser.parse_args()
    fonts = args.font_dir.expanduser().resolve()
    for style in FONT_STYLES:
        if not (fonts / f"WeissenhofGrotesk-{style}.otf").is_file():
            raise SystemExit(f"Missing Weissenhof Grotesk {style} in {fonts}; pass --font-dir.")
    packages = json.loads((HERE / "packages.json").read_text())
    if not args.all:
        packages = [package for package in packages if package["slug"] == "ethos-data"]
    for package in packages:
        for key, pattern in (("slug", r"ethos-[a-z0-9-]+"), ("wordmark", r"ETHOS\.[A-Za-z0-9]+"),
                             ("icon", r"[a-z]+")):
            if not re.fullmatch(pattern, package[key]):
                raise SystemExit(f"Invalid {key}: {package[key]!r}")
    OUT.mkdir(parents=True, exist_ok=True)
    for package in packages:
        render(package, fonts)
        render(package, fonts, dark=True)
        icon = render(package, fonts, icon=True)
        if args.preview:
            for size in (16, 32, 48):
                png(icon, OUT / f"{package['slug']}-favicon-{size}.png", size=size)
            if package["slug"] == "ethos-data":
                preview_pair(package)
    if args.preview and args.all:
        family_preview(packages, dark=False)
        family_preview(packages, dark=True)
        favicon_preview(packages)


if __name__ == "__main__":
    main()
