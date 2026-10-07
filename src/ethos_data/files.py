"""The files of a data directory, as the catalogue records them.

Walks a dataset's directory, applies its ``ethos:include`` and
``ethos:exclude``, keeps shapefile companions together, and makes the record
each file gets. Data access and catalogue maintenance both use it: the build
inventories a ``source_dir`` with it, and a link or a bundle checks a
directory against the same rules, so no service needs the maintenance group
to read a directory.
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from . import report
from .errors import DescriptorError
from .formats import keys as k
from .model.digest import recorded
from .model.patterns import path_matches
from .model.resource import Resource, to_record

__all__ = [
    "EXTRA_MEDIATYPES",
    "SHAPEFILE_SIDECAR_EXTS",
    "build_resource",
    "expand_pattern",
    "iter_data_files",
    "mediatype_of",
    "select",
    "slugify",
]

# Scientific formats that ``mimetypes`` does not know about.
EXTRA_MEDIATYPES = {
    ".nc": "application/x-netcdf",
    ".nc4": "application/x-netcdf",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".shp": "application/octet-stream",
    ".shx": "application/octet-stream",
    ".dbf": "application/octet-stream",
    ".prj": "text/plain",
    ".qpj": "text/plain",
    ".cpg": "text/plain",
    ".qmd": "application/xml",
}

# An ESRI shapefile is several files that are useless apart.  Selecting the .shp
# must drag the rest along, or GDAL fails at read time with a confusing error.
SHAPEFILE_SIDECAR_EXTS = [
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".qpj",
    ".qmd",
    ".sbn",
    ".sbx",
    ".xml",
]

# Never published: VCS plumbing, editor droppings, dataset-local docs.
EXCLUDE_NAMES = {".git", ".datalad", ".gitattributes", ".gitignore", "__pycache__"}
EXCLUDE_SUFFIXES = {".pyc"}
# Matched against the path relative to the dataset root, so a data file that
# happens to be called README.md deeper in the tree is published.
# A dataset.yaml at the top describes the data beside it -- `staging add`
# writes one -- and is never one of its files.
EXCLUDE_ROOT_GLOBS = ("README*", "LICENSE*", "CHANGELOG*", "dataset.yaml")


def slugify(relative_path: str) -> str:
    """Turn a relative path into a Data Package resource name.

    The spec requires lowercase alphanumerics plus ``.``, ``-`` and ``_``, and
    the name must stay stable across rebuilds -- it is half of the logical
    identity that lets two tools recognise the same file.
    """
    slug = relative_path.replace("/", "-").lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", slug)
    return re.sub(r"-{2,}", "-", slug).strip("-")


def mediatype_of(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in EXTRA_MEDIATYPES:
        return EXTRA_MEDIATYPES[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def iter_data_files(root: Path):
    """Every publishable file under ``root``, relative paths in sorted order.

    ``rglob`` descends when ``root`` itself is a symbolic link -- which is what
    lets a source_dir point into the curated namespace -- but it does **not**
    descend into symbolic links found *inside* the tree. Such a directory would
    therefore be silently absent from the manifest, so it is reported rather
    than skipped in silence.
    """
    for path in sorted(root.rglob("*")):
        if path.is_symlink() and path.is_dir():
            report.warning(
                f"warning: {path} is a symbolic link to a directory; its contents are "
                f"NOT in the manifest. Point source_dir at the real tree, or replace "
                f"the link with the files themselves."
            )
            continue
        if not path.is_file():
            continue
        if any(part in EXCLUDE_NAMES for part in path.relative_to(root).parts):
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if len(relative.parts) == 1 and any(
            relative.match(g) for g in EXCLUDE_ROOT_GLOBS
        ):
            continue
        yield path


def expand_pattern(pattern: str) -> list[str]:
    """The glob patterns one ``ethos:include`` / ``ethos:exclude`` entry stands for.

    Wildcard patterns are used as written, with the reader's rule: ``*`` inside
    one path segment, ``**`` across any number of them.

    A pattern with no wildcard is a literal path, and naming a folder is the
    obvious way to say "this folder" -- so it stands for the path itself *and*
    everything under it.  ``"test"`` therefore excludes the directory's whole
    contents, not just a file that happens to be called ``test``.  Purely
    syntactic: it does not look at the disk, so the descriptor means the same
    thing on a machine where that directory has already been cleaned up.

    A trailing slash asks for the subtree only, for the rare case where a file
    and a directory share a name.
    """
    pattern = pattern.strip()
    if not pattern:
        raise DescriptorError(f"{k.INCLUDE}/{k.EXCLUDE}: empty pattern")
    if pattern.startswith("/"):
        raise DescriptorError(
            f"{k.INCLUDE}/{k.EXCLUDE}: {pattern!r} starts with '/'. Patterns are "
            "relative to source_dir; drop the leading slash."
        )
    if pattern.endswith("/"):
        return [pattern.rstrip("/") + "/**"]
    if any(character in pattern for character in "*?["):
        return [pattern]
    return [pattern, pattern + "/**"]


def select(name: str, root: Path, paths: list[Path], meta: dict) -> list[Path]:
    """Narrow an inventory to what ``ethos:include`` / ``ethos:exclude`` ask for.

    Exists because ``source_dir`` is frequently somebody else's download
    directory -- a shared tree holding the dataset *and* the zip it was
    extracted from, a wget log, a colleague's test clip -- that we have neither
    the write access nor the standing to tidy up.  Without this the only way to
    publish five rasters out of eighteen files was to move the other thirteen.

    Two guard rails, because a silently smaller manifest is the failure mode
    that matters here:

    * an ``ethos:include`` pattern that matches nothing is an error, named.  A
      typo, or a file renamed upstream, must not quietly shrink the dataset.
    * an ``ethos:exclude`` pattern that matches nothing is only a warning -- the
      stray it named may simply have been cleaned up since, and failing the
      build for a cleanup that actually happened would be perverse.

    Shapefile companions are added back after filtering, mirroring what the
    reader does when a collection selects a ``.shp``: a ``.shp`` without its
    ``.dbf`` and ``.shx`` is unreadable, and an include list is exactly where
    somebody would forget them.
    """
    # Their shape is checked with the rest of the descriptor, before this runs.
    include = meta.get(k.INCLUDE)
    exclude = meta.get(k.EXCLUDE)
    if include is None and exclude is None:
        return paths

    relative = {path: path.relative_to(root).as_posix() for path in paths}

    def matched_by(patterns: list[str]) -> dict[str, set[str]]:
        """Which source patterns each path matched, keyed by the pattern as written."""
        hits: dict[str, set[str]] = {pattern: set() for pattern in patterns}
        for pattern in patterns:
            globs = expand_pattern(pattern)
            for rel in relative.values():
                if any(path_matches(rel, glob) for glob in globs):
                    hits[pattern].add(rel)
        return hits

    kept = set(paths)

    if include is not None:
        hits = matched_by(include)
        empty = [pattern for pattern, found in hits.items() if not found]
        if empty:
            raise DescriptorError(
                f"{name}: {k.INCLUDE} pattern(s) match no file under {root}:\n"
                + "".join(f"    {pattern}\n" for pattern in empty)
                + "Fix the pattern, or drop it if the file is gone. An include list that\n"
                "silently matches nothing would publish a smaller dataset than intended."
            )
        wanted = set().union(*hits.values())
        kept = {path for path in paths if relative[path] in wanted}

    if exclude is not None:
        hits = matched_by(exclude)
        for pattern, found in hits.items():
            if not found:
                report.warning(
                    f"warning: {name}: {k.EXCLUDE} pattern {pattern!r} matches nothing "
                    f"under {root} -- already cleaned up, or a typo?"
                )
        unwanted = set().union(*hits.values()) if hits else set()
        kept = {path for path in kept if relative[path] not in unwanted}

    # Drag shapefile companions back in, the same way the reader does.
    for path in list(kept):
        if path.suffix.lower() != ".shp":
            continue
        for extension in SHAPEFILE_SIDECAR_EXTS:
            companion = path.with_suffix(extension)
            if companion in relative and companion not in kept:
                report.info(
                    f"note: {name}: keeping {relative[companion]} -- companion of "
                    f"{relative[path]}, which a filter would otherwise have dropped"
                )
                kept.add(companion)

    skipped = len(paths) - len(kept)
    if skipped:
        report.info(
            f"  {name}: {len(kept)} of {len(paths)} files under {root} "
            f"selected, {skipped} filtered out"
        )
    return [path for path in paths if path in kept]


def build_resource(path: Path, root: Path, size: int, digest: str) -> dict:
    """The record of one file under ``root``, written as every record is written.

    A shapefile names the companions found beside it, so a reader never takes
    the ``.shp`` without them.
    """
    relative = path.relative_to(root).as_posix()
    sidecars: tuple[str, ...] = ()
    if path.suffix.lower() == ".shp":
        sidecars = tuple(
            path.with_suffix(ext).relative_to(root).as_posix()
            for ext in SHAPEFILE_SIDECAR_EXTS
            if path.with_suffix(ext).exists()
        )
    return to_record(
        Resource(
            # A record does not name its dataset; the descriptor holding it does.
            dataset="",
            name=slugify(relative),
            path=relative,
            bytes=size,
            hash=recorded(digest),
            mediatype=mediatype_of(path),
            sidecars=sidecars,
        )
    )
