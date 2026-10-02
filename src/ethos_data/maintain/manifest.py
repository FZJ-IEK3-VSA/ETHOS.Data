"""Generate Frictionless Data Package descriptors for an ETHOS.Data catalogue.

Each dataset directory under ``datasets/`` holds a hand-written ``dataset.yaml``
(identity, provenance, licensing) and a generated ``datapackage.json`` (the file
inventory: paths, sizes, checksums).  Never edit ``datapackage.json`` by hand --
re-run this instead.

    ethos-data catalog build                 # rebuild every dataset
    ethos-data catalog build landcover       # rebuild one
    ethos-data catalog build --check         # verify manifests are current

A dataset whose ``source_dir`` holds more than the dataset -- a shared download
directory nobody is going to tidy up -- narrows the inventory with ``ethos:include``
and ``ethos:exclude``.  Both are lists of glob patterns matched against the path
relative to ``source_dir``, by the same rule a tool's ``collections.yaml`` uses,
imported from the reader so the two can never diverge.

``source_dir`` lives in the dataset's ``status.yaml`` beside it, with the
dataset's state (see :mod:`.status`), and it is not forever: once the bytes
are uploaded and verified, dCache -- not somebody's workstation or a
shared-storage mount that may get cleaned up or reorganised -- is the
authoritative copy. ``ethos-data catalog record`` freezes the dataset and
retires ``source_dir``: a rebuild then keeps the existing inventory (paths,
sizes, hashes) exactly as last recorded, re-deriving only the metadata that
never depended on the bytes -- title, licence, provenance, access. This is
also what makes a dataset build-able again after its ``source_dir`` has
genuinely disappeared. A dataset without a status file states the same in
``dataset.yaml``, as ``source_dir``, ``ethos:uploaded`` and ``ethos:frozen``,
until ``ethos-data catalog migrate`` moves them.

The build records in the status file what it changed: a draft's first build,
and an inventory that differs from the one before, which returns a dataset
whose bytes were made available to built, because what was checked is no
longer what the inventory describes. A withdrawn dataset is not built and not
in the index, and nor is a family whose members are all withdrawn.

Provenance and licensing are checked here rather than left to a reviewer's eye.
``ethos:origin`` says whether the data was downloaded, derived or created, and an
origin that claims authorship has to name an author in ``contributors``.
``licenses`` is a list because a dataset really can be under several; one entry
may narrow itself to some of the files with ``ethos:applies_to``, which is
rendered as a resource-level ``licenses`` override.

A dataset that declares ``ethos:shard_depth: N`` is written *sharded*: the
inventory is split across ``shards/<prefix>.json``, one file per directory
prefix of N segments, and ``datapackage.json`` carries an ``ethos:shards`` index
instead of a ``resources`` array.  ``ethos_data.catalogs`` then parses only the
shards a selection can match.  The grouping rule is imported from the reader
rather than reimplemented -- writer and reader must agree on it exactly.

Hashing is the expensive part -- this catalogue's source_dirs run to hundreds
of gigabytes on shared storage -- so each dataset directory keeps a
``.ice2-hash-cache.json`` alongside its datapackage.json: a private, unpublished
map of relative path to the size/mtime last seen and the digest that went with
them. A rebuild re-hashes a file only when its size or mtime has moved; the rest
is a stat call. It is not a Data Package property (a maintainer's disk paths and
timestamps mean nothing to a consumer) and it is not written at all under
``--check``, which promises to write nothing. Whatever still needs hashing is
read through a small thread pool: the cost is waiting on shared storage, not
CPU, and hashlib releases the GIL while it works a chunk, so concurrent reads
actually overlap.

Spec: https://datapackage.org/standard/data-package/
"""

from __future__ import annotations

import json
import mimetypes
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

from .. import report
from ..catalogs import ROOT_SHARD, shard_key
from ..errors import DescriptorError
from ..formats import catalogue as catalogue_format
from ..formats import dataset as dataset_format
from ..formats import keys as k
from ..formats.derived import index_row
from ..model import lifecycle
from ..model.digest import matches, of_file, recorded
from ..selection import path_matches
from . import (
    LEGACY_SHARD_DIR,
    SHARD_DIR,
    dataset_name_for,
    datasets_dir,
    is_namespace,
    iter_dataset_dirs,
    read_catalog_meta,
    read_descriptor,
    resources_of,
)
from . import status as dataset_status

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

# Per-dataset, maintainer-local, never published -- see the module docstring.
HASH_CACHE_NAME = ".ice2-hash-cache.json"

# Hashing waits on shared storage, not CPU, so this is sized for concurrent I/O
# rather than core count. High enough to hide per-file latency, low enough that
# one build does not monopolise a filesystem other people are using too.
HASH_WORKERS = 8

# Never published: VCS plumbing, editor droppings, dataset-local docs.
EXCLUDE_NAMES = {".git", ".datalad", ".gitattributes", ".gitignore", "__pycache__"}
EXCLUDE_SUFFIXES = {".pyc"}
# Matched against the path relative to the dataset root, so a data file that
# happens to be called README.md deeper in the tree is still published.
# A dataset.yaml at the top describes the data beside it -- `staging add`
# writes one -- and is never one of its files.
EXCLUDE_ROOT_GLOBS = ("README*", "LICENSE*", "CHANGELOG*", "dataset.yaml")


def load_hash_cache(dataset_dir: Path) -> dict:
    """The dataset's hash cache, or an empty one if there isn't one yet.

    Corrupt or unreadable is treated the same as absent -- worst case a stale or
    broken cache costs a full re-hash, exactly like a first build. It must never
    fail the build.
    """
    path = dataset_dir / HASH_CACHE_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_hash_cache(dataset_dir: Path, cache: dict) -> None:
    """Persist the hash cache. Best-effort: a cache write must not fail the build."""
    try:
        (dataset_dir / HASH_CACHE_NAME).write_text(
            json.dumps(cache), encoding="utf-8", newline="\n"
        )
    except OSError as error:
        report.warning(
            f"warning: could not write {HASH_CACHE_NAME} in {dataset_dir}: {error}"
        )


def resolve_hashes(
    paths: list[Path], root: Path, cache: dict
) -> dict[Path, tuple[int, str]]:
    """SHA-256 (and size) for every path, as ``{path: (size, digest)}``.

    Reuses ``cache`` when a path's size and mtime match what was last recorded
    there -- the file has not moved since it was last hashed, so re-reading it
    would only reproduce the same digest. Everything else is a genuine cache
    miss and goes through the thread pool together, since those are exactly the
    reads that are slow.

    ``cache`` is updated in place with every freshly computed digest; the caller
    decides whether that is worth writing back to disk.
    """
    relative = {path: path.relative_to(root).as_posix() for path in paths}
    stats = {path: path.stat() for path in paths}

    digests: dict[Path, str] = {}
    misses: list[Path] = []
    for path in paths:
        stat = stats[path]
        entry = cache.get(relative[path])
        if (
            entry
            and entry.get("size") == stat.st_size
            and entry.get("mtime_ns") == stat.st_mtime_ns
        ):
            digests[path] = entry["hash"]
        else:
            misses.append(path)

    if misses:
        with ThreadPoolExecutor(max_workers=min(HASH_WORKERS, len(misses))) as pool:
            for path, found in zip(misses, pool.map(of_file, misses)):
                digests[path] = found
                stat = stats[path]
                cache[relative[path]] = {
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "hash": found,
                }

    return {path: (stats[path].st_size, digests[path]) for path in paths}


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
            for path, rel in relative.items():
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
                report.warning(
                    f"note: {name}: keeping {relative[companion]} -- companion of "
                    f"{relative[path]}, which a filter would otherwise have dropped"
                )
                kept.add(companion)

    skipped = len(paths) - len(kept)
    if skipped:
        report.warning(
            f"  {name}: {len(kept)} of {len(paths)} files under {root} "
            f"selected, {skipped} filtered out"
        )
    return [path for path in paths if path in kept]


def frozen_resources(name: str, dataset_dir: Path) -> list[dict]:
    """The inventory already on disk, for a dataset that will not be re-read.

    Everything ``build_resource`` would derive from the file itself -- path,
    bytes, hash, mediatype, shapefile sidecars -- is exactly what a maintainer
    already checksummed and uploaded, so there is nothing to recompute. What is
    dropped is any per-resource ``licenses`` override from the last render:
    ``apply_resource_licenses`` is about to run again against the current
    ``dataset.yaml``, and appending onto an already-applied copy would double it
    on every subsequent freeze.
    """
    package_file = dataset_dir / "datapackage.json"
    if not package_file.is_file():
        raise DescriptorError(
            f"{name}: the inventory is declared final but there is no datapackage.json to "
            f"freeze. Build it once from its source_dir and check the result before "
            "freezing it."
        )
    resources = resources_of(
        json.loads(package_file.read_text(encoding="utf-8")), dataset_dir
    )
    return [
        {key: value for key, value in resource.items() if key != k.LICENSES}
        for resource in resources
    ]


def build_resource(path: Path, root: Path, size: int, digest: str) -> dict:
    relative = path.relative_to(root).as_posix()
    # The record ethos_data.model.resource reads back into a Resource, key for
    # key and in this order; a test holds the two together.
    resource = {
        k.NAME: slugify(relative),
        k.PATH: relative,
        k.BYTES: size,
        k.HASH: recorded(digest),
        k.MEDIATYPE: mediatype_of(path),
    }
    if path.suffix.lower() == ".shp":
        sidecars = [
            (path.with_suffix(ext)).relative_to(root).as_posix()
            for ext in SHAPEFILE_SIDECAR_EXTS
            if path.with_suffix(ext).exists()
        ]
        if sidecars:
            # Custom property -- the spec permits these, and the resolver uses it
            # to pull companion files in automatically.
            resource[k.SIDECARS] = sidecars
    return resource


def record_license_documents(
    name: str, dataset_dir: Path, licenses: list[dict]
) -> None:
    """Hash every archived licence document into its entry, or verify the hash it pins.

    The digest is taken from the file, as a resource's is: the document is a
    file the catalogue ships, and a hand-typed hash drifts the moment the text
    is replaced. Three of them had, unnoticed, until a bundle export checked.
    A digest already written in dataset.yaml is kept as a pin and verified, so
    "these are the terms somebody reviewed" can still be said where it matters;
    a mismatch stops the build rather than publishing a hash nothing matches.
    A missing document fails here, where the maintainer is, not later in publish.
    """
    for index, entry in enumerate(licenses):
        where = f"{name}: {k.LICENSES}[{index}]"
        document = entry.get(k.DOCUMENT)
        if document is None:
            continue
        # Its spelling is checked with the rest of the descriptor, before this
        # runs; what is left needs the disk.
        path = dataset_dir.joinpath(*PurePosixPath(document).parts)
        if not path.is_file():
            raise DescriptorError(
                f"{where} names {k.DOCUMENT} {document}, which is not a file at "
                f"{path}. Archive the terms there, or drop {k.DOCUMENT}."
            )
        actual = of_file(path)
        pinned = entry.get(k.DOCUMENT_SHA256)
        if pinned is not None and not matches(pinned, actual):
            raise DescriptorError(
                f"{where}: {document} hashes to {actual}, but dataset.yaml pins "
                f"{k.DOCUMENT_SHA256}: {pinned}. The archived text is not the one "
                f"that hash was recorded for. If the file is right, delete "
                f"{k.DOCUMENT_SHA256} and rebuild -- the build records the digest "
                "itself. If the hash is right, restore the file."
            )
        entry[k.DOCUMENT_SHA256] = actual


def apply_resource_licenses(
    name: str, resources: list[dict], licenses: list[dict]
) -> None:
    """Attach per-file licences, for a dataset whose files differ.

    Frictionless lets a *resource* carry its own ``licenses``, which override the
    package's -- so files under different terms are expressible without splitting
    the dataset in two. That is the point: the C3S netCDF originals and the
    GeoTIFFs we converted from them are one dataset by every other measure, and
    forcing them apart to record two licences would be the tail wagging the dog.

    Every licence stays in the package-level array as well, ``ethos:applies_to``
    and all. A reader that only looks at the package then sees the full set --
    conservative, and true -- while one that looks at a resource gets the exact
    answer. Dropping the narrowed ones from the package instead would leave a
    dataset whose licence list omits most of its licences.

    A pattern that matches nothing is an error, exactly as ``ethos:include`` is:
    silently licensing no files is how a dataset ends up published under terms
    nobody applied.
    """
    narrowed = [entry for entry in licenses if entry.get(k.APPLIES_TO)]
    if not narrowed:
        return

    for entry in narrowed:
        patterns = entry[k.APPLIES_TO]
        # The resource-level copy drops applies_to: it is a build-time
        # instruction about which files to attach to, and on the file it was
        # attached to it answers a question nobody is asking.
        published = {key: value for key, value in entry.items() if key != k.APPLIES_TO}
        matched = 0
        for resource in resources:
            if any(path_matches(resource["path"], p) for p in patterns):
                resource.setdefault(k.LICENSES, []).append(published)
                matched += 1
        if not matched:
            raise DescriptorError(
                f"{name}: {k.LICENSES} entry "
                f"{entry.get('name') or entry.get('path')!r} has {k.APPLIES_TO} "
                f"{patterns}, which matches none of the {len(resources)} files in this "
                "dataset. Fix the pattern, or drop the key so the licence covers "
                "everything."
            )

    uncovered = [r["path"] for r in resources if k.LICENSES not in r]
    if uncovered and len(narrowed) == len(licenses):
        # Every licence was narrowed, so these files inherit an empty package
        # licence -- described by nothing at all.
        shown = ", ".join(uncovered[:5])
        more = "" if len(uncovered) <= 5 else f", and {len(uncovered) - 5} more"
        report.warning(
            f"warning: {name}: every {k.LICENSES} entry is narrowed with "
            f"{k.APPLIES_TO}, so {len(uncovered)} file(s) are covered by no licence "
            f"at all: {shown}{more}. Add a licence without {k.APPLIES_TO} for the "
            "rest, or widen one of the patterns."
        )


def _checked(name: str, rule, meta: dict) -> None:
    """Run one of the format's rules, naming the dataset in its refusal."""
    try:
        rule(meta)
    except DescriptorError as error:
        raise DescriptorError(f"{name}: {error.message}") from None


def shard_path(prefix: str) -> str:
    """Where one shard's inventory lives, relative to the dataset directory."""
    return f"{SHARD_DIR}/{prefix}.json"


def split_into_shards(resources: list[dict], depth: int) -> dict[str, list[dict]]:
    """Group an inventory by shard prefix, in a stable order."""
    shards: dict[str, list[dict]] = {}
    for resource in resources:
        shards.setdefault(shard_key(resource["path"], depth), []).append(resource)
    return {prefix: shards[prefix] for prefix in sorted(shards)}


def dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_dataset(
    dataset_dir: Path,
    check: bool = False,
    *,
    name: str | None = None,
    inherited: dict | None = None,
    namespace: bool = False,
    member_totals: tuple[int, int] | None = None,
    superseded_by: list[str] | None = None,
    source: Path | None = None,
    revision: int | None = None,
) -> dict[str, str]:
    """Build every generated file for one dataset.

    Returns ``{path relative to dataset_dir -> file text}``: always
    ``datapackage.json``, plus one ``shards/<prefix>.json`` per shard when the
    dataset declares ``ethos:shard_depth``.  Rendering the whole set in memory is
    what lets ``--check`` detect a stale *shard* as readily as a stale index.

    ``check`` gates only the hash cache write at the end -- ``--check`` promises
    to write nothing, but it may still *read* an existing cache to skip hashing
    files that have not changed.

    ``name`` is the dataset's catalogue name, which for a nested dataset is its
    path below ``datasets/`` rather than its directory name. It defaults to the
    directory name, so a flat catalogue and every existing caller behave exactly
    as before.

    ``namespace`` says this directory holds other datasets rather than files of
    its own; ``member_totals`` is the ``(bytes, files)`` of everything beneath it,
    which a namespace reports in place of an inventory. ``inherited`` carries the
    few keys a member takes from the namespace above it -- see
    ``formats.dataset.INHERITED``.
    """
    name = name or dataset_dir.name
    meta = read_descriptor(dataset_dir)

    # The name is derived from where the file sits, not trusted from inside it.
    # A dataset.yaml that disagrees with its own location is a rename half-done,
    # and the failure it causes later -- a collections file resolving to nothing
    # -- is a long way from the cause.
    declared = meta.get("name")
    if declared is not None and declared != name:
        raise DescriptorError(
            f"{name}: dataset.yaml says name: {declared!r}, but the directory it is in "
            f"makes it {name!r}. The directory decides; fix the name, or move the directory."
        )
    meta["name"] = name

    if inherited:
        for key, value in inherited.items():
            meta.setdefault(key, value)

    if namespace:
        return _render_namespace(dataset_dir, name, meta, member_totals or (0, 0))

    # Where the bytes are is the status file's to say -- see the module
    # docstring -- and none of it is published.
    built_from = dataset_status.build_input(dataset_dir, meta, name)
    if built_from.status is not None:
        lifecycle.step("build", built_from.status.state, name)
    _checked(name, dataset_format.check, meta)
    if built_from.status is None:
        _checked(name, dataset_format.check_legacy_state, meta)
    for warning in dataset_format.lint(meta):
        report.warning(f"warning: {name}: {warning}")
    dataset_format.apply_defaults(meta)
    licenses = meta.get(k.LICENSES) or []
    record_license_documents(name, dataset_dir, licenses)

    for key in dataset_status.LEGACY_KEYS:
        meta.pop(key, None)
    frozen, source_dir = built_from.frozen, built_from.source_dir
    if source is not None:
        # A new revision, built from the corrected files.
        frozen, source_dir = False, source
    status = built_from.status
    if revision is None:
        revision = status.revision if status is not None else 1

    if frozen:
        resources = frozen_resources(name, dataset_dir)
    else:
        if not source_dir.is_dir():
            raise DescriptorError(f"{name}: source_dir does not exist: {source_dir}")

        found = list(iter_data_files(source_dir))
        if not found:
            raise DescriptorError(f"{name}: no data files found under {source_dir}")
        selected = select(name, source_dir, found, meta)
        if not selected:
            raise DescriptorError(
                f"{name}: {k.INCLUDE}/{k.EXCLUDE} filtered out every one of the "
                f"{len(found)} files under {source_dir}"
            )

        cache = load_hash_cache(dataset_dir)
        hashes = resolve_hashes(selected, source_dir, cache)
        if not check:
            save_hash_cache(dataset_dir, cache)
        resources = [build_resource(p, source_dir, *hashes[p]) for p in selected]
        if source is None:
            _refuse_changed_publication(name, dataset_dir, status, resources)
        _carry_revisions(resources, dataset_dir, revision)

    # After the inventory exists, because a narrowed licence has to be checked
    # against the files it claims to cover.
    apply_resource_licenses(name, resources, licenses)

    depth = int(meta.get(k.SHARD_DEPTH, 0) or 0)

    package = {
        k.SCHEMA: k.DATAPACKAGE_PROFILE,
        **meta,
    }
    files: dict[str, str] = {}

    if depth:
        shards = split_into_shards(resources, depth)
        if len(shards) == 1 and ROOT_SHARD in shards:
            # Every file sits at the dataset root, so sharding cannot split
            # anything -- and a lone _root shard is strictly worse than an
            # inline inventory: one extra fetch to learn what you already had.
            raise DescriptorError(
                f"{name}: ethos:shard_depth is {depth}, but no file is nested "
                f"{depth} director{'y' if depth == 1 else 'ies'} deep, so there is nothing "
                "to shard. Drop ethos:shard_depth, or lower it."
            )
        index = []
        for prefix, members in shards.items():
            relative = shard_path(prefix)
            files[relative] = dumps(
                {
                    "name": f"{package['name']}-{slugify(prefix)}",
                    "ethos:shard": prefix,
                    "resources": members,
                }
            )
            index.append(
                {
                    "prefix": prefix,
                    "path": relative,
                    "ethos:file_count": len(members),
                    "ethos:total_bytes": sum(r["bytes"] for r in members),
                }
            )
        package["ethos:shard_depth"] = depth
        package["ethos:shards"] = index
    else:
        # An unsharded descriptor must not advertise a depth: the reader treats
        # the presence of ethos:shards as the switch, and a stray depth alongside
        # an inline inventory is a lie waiting to be believed by the next tool.
        package.pop("ethos:shard_depth", None)
        package["resources"] = resources

    package["ethos:total_bytes"] = sum(r["bytes"] for r in resources)
    package["ethos:file_count"] = len(resources)
    if revision > 1:
        package[k.REVISION] = revision
    if superseded_by:
        package[k.SUPERSEDED_BY] = sorted(superseded_by)
    files["datapackage.json"] = dumps(package)
    return files


def _recorded(dataset_dir: Path) -> dict[str, dict]:
    """The inventory on disk, by path; empty before the first build."""
    package_file = dataset_dir / "datapackage.json"
    if not package_file.is_file():
        return {}
    package = json.loads(package_file.read_text(encoding="utf-8"))
    return {
        resource[k.PATH]: resource for resource in resources_of(package, dataset_dir)
    }


def _carry_revisions(resources: list[dict], dataset_dir: Path, revision: int) -> None:
    """Give each file the revision its bytes were published in.

    A file whose bytes the inventory on disk records keeps that record's
    revision; a file new in this revision, or with other bytes, gets
    ``revision``. Before a second revision there is nothing to carry.
    """
    if revision <= 1:
        return
    before = _recorded(dataset_dir)
    for resource in resources:
        earlier = before.get(resource[k.PATH])
        same = earlier is not None and earlier[k.HASH] == resource[k.HASH]
        kept = int(earlier.get(k.REVISION, 1)) if same else revision
        if kept > 1:
            resource[k.REVISION] = kept


def _refuse_changed_publication(
    name: str, dataset_dir: Path, status, resources: list[dict]
) -> None:
    """Refuse new bytes for a dataset whose bytes the catalogue published or owns.

    Published objects never change, so other bytes are a new revision, made on
    purpose. A dataset that is only linked changes in place with its source.
    """
    if status is None or status.state != lifecycle.AVAILABLE:
        return
    if not any(
        copy.kind in (k.COPY_UPLOADED, k.COPY_MATERIALIZED) for copy in status.copies
    ):
        return
    before = {(r[k.PATH], r[k.HASH]) for r in _recorded(dataset_dir).values()}
    if before and before != {(r[k.PATH], r[k.HASH]) for r in resources}:
        raise DescriptorError(
            f"{name}: its files are not the ones its uploaded or materialized copy "
            "holds any more, and published bytes never change. Make the change a "
            f"new revision:\n    ethos-data catalog build {name} --revision"
        )


def superseded_by_map(catalog_root: Path) -> dict[str, list[str]]:
    """Which datasets each dataset is superseded by, from every ``ethos:supersedes``.

    Raises :class:`~ethos_data.errors.DescriptorError` for a name the catalogue
    has never described: neither a dataset nor one purged.
    """
    root = datasets_dir(catalog_root)
    found: dict[str, list[str]] = {}
    for directory in iter_dataset_dirs(root):
        old = read_descriptor(directory).get(k.SUPERSEDES)
        if not old:
            continue
        name = dataset_name_for(root, directory)
        known = (root / str(old) / "dataset.yaml").is_file() or (
            root / str(old) / dataset_status.STATUS
        ).is_file()
        if not known or str(old) == name:
            raise DescriptorError(
                f"{name}: {k.SUPERSEDES} names {old!r}, which is not another dataset "
                "of this catalogue"
            )
        found.setdefault(str(old), []).append(name)
    return found


def _render_namespace(
    dataset_dir: Path, name: str, meta: dict, member_totals: tuple[int, int]
) -> dict[str, str]:
    """Render a namespace node: a dataset that names a family, not files.

    A namespace has no inventory of its own. It exists so that a set of related
    datasets has one name -- ``reskit-test-data`` for the family whose members
    are ``reskit-test-data/era5`` and the rest -- and so that the metadata they
    share is written once.

    It must not describe files. If a namespace could also carry resources then
    ``reskit-test-data`` would mean two different things depending on who asked:
    the parent's own inventory, or everything beneath it. Forbidding it is what
    keeps the name unambiguous.
    """
    _checked(name, dataset_format.check_namespace, meta)

    total_bytes, file_count = member_totals
    package = {
        k.SCHEMA: k.DATAPACKAGE_PROFILE,
        **meta,
        k.NAMESPACE: True,
        # Reported, not owned: these are the sum over the members, so that
        # a package's `show` command can report what the family costs without loading every
        # member's inventory. There is no `resources` key at all -- a namespace
        # has nothing to download, and a tool must not be able to try.
        "ethos:total_bytes": total_bytes,
        "ethos:file_count": file_count,
    }
    return {"datapackage.json": dumps(package)}


def write_dataset(dataset_dir: Path, files: dict[str, str]) -> None:
    """Write the rendered files and remove shards that are no longer generated.

    A rebuild that drops a shard -- the tile it described was deleted upstream --
    has to delete the file too, or the index and the directory disagree and the
    stale shard is published forever.

    Both arguments to ``write_text`` are load-bearing: left to its defaults it
    encodes with the *locale* codec and rewrites every "\\n" as "\\r\\n" on
    Windows. A catalogue is a git repository built and read on both platforms,
    and a descriptor whose bytes depend on who ran the build is a diff in every
    line of every file the next time somebody on the other one rebuilds it.
    """
    for relative, text in files.items():
        target = dataset_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    generated = {dataset_dir / relative for relative in files}
    for shard_root in shard_roots(dataset_dir):
        for path in sorted(shard_root.rglob("*"), reverse=True):
            if path.is_file() and path not in generated:
                path.unlink()
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        if not any(shard_root.iterdir()):
            shard_root.rmdir()


def shard_roots(dataset_dir: Path) -> list[Path]:
    """The build-owned shard directories that exist for this dataset.

    Normally ``shards/`` or nothing. A catalogue built before the rename also
    has ``manifests/``, which nothing generates any more: every file in it is
    left over, so a rebuild deletes it and ``--check`` reports it as stale.
    """
    return [
        dataset_dir / name
        for name in (SHARD_DIR, LEGACY_SHARD_DIR)
        if (dataset_dir / name).is_dir()
    ]


def stale_files(dataset_dir: Path, files: dict[str, str]) -> list[Path]:
    """Generated files that are missing, changed, or left over on disk."""
    stale = [
        dataset_dir / relative
        for relative, text in files.items()
        if not (dataset_dir / relative).is_file()
        or (dataset_dir / relative).read_text(encoding="utf-8") != text
    ]
    generated = {dataset_dir / relative for relative in files}
    for shard_root in shard_roots(dataset_dir):
        stale += [
            p
            for p in sorted(shard_root.rglob("*"))
            if p.is_file() and p not in generated
        ]
    return stale


def _inventory(dataset_dir: Path) -> set[tuple] | None:
    """The files the dataset's descriptor lists, by path, size and hash; None unbuilt."""
    package_file = dataset_dir / "datapackage.json"
    if not package_file.is_file():
        return None
    package = json.loads(package_file.read_text(encoding="utf-8"))
    return {
        (resource[k.PATH], resource[k.BYTES], resource[k.HASH])
        for resource in resources_of(package, dataset_dir)
    }


def _record_build(
    dataset_dir: Path, name: str, before: set[tuple] | None, package: dict
) -> None:
    """Record in the status file what this build changed, if anything.

    A draft's first build makes it built. A rebuild that found other files
    than the inventory before is recorded as a change, and returns a dataset
    whose bytes were made available to built. A rebuild that changed nothing,
    which is most of them, records nothing.
    """
    status = dataset_status.read(dataset_dir)
    if status is None:
        return
    size = {"files": package[k.FILE_COUNT], "bytes": package[k.TOTAL_BYTES]}
    if status.state == lifecycle.DRAFT:
        dataset_status.take(dataset_dir, status, "build", dataset=name, **size)
        return
    changed = before is not None and before != _inventory(dataset_dir)
    if not changed or status.state not in lifecycle.STEPS["change"].leads:
        return
    if status.state == lifecycle.AVAILABLE:
        report.warning(
            f"warning: {name}: its inventory changed since its bytes were made "
            "available, so it is recorded as built again; make the new bytes "
            "available before releasing it"
        )
    dataset_status.take(
        dataset_dir,
        status,
        "change",
        dataset=name,
        note="the inventory changed",
        **size,
    )


def catalog_meta(catalog_root: Path) -> dict:
    """Read and validate catalog.yaml.

    Called before any dataset is touched. Catalogue-level mistakes are cheap to
    find and expensive to find late: checksumming a multi-terabyte dataset only
    to reject the file that names the catalogue wastes the whole run.
    """
    meta = read_catalog_meta(catalog_root)

    # A catalogue you can run `build` in is by definition a source one: it has
    # the dataset.yaml files this reads. Default rather than demand it, so an
    # existing catalog.yaml keeps working, but reject a wrong value outright --
    # a catalogue mislabelled `published` would make every tool refuse to touch it.
    catalogue_format.check(meta)
    meta.setdefault(k.CATALOG_ROLE, k.ROLE_SOURCE)
    return meta


def left_out(dataset_dir: Path) -> bool:
    """Whether the build leaves this dataset out of the catalogue.

    A dataset that was withdrawn, and a family whose members, every one of
    them, were withdrawn: it would be a name pointing at nothing.
    """
    if not is_namespace(dataset_dir):
        return dataset_status.withdrawn(dataset_dir)
    members = [
        member
        for member in iter_dataset_dirs(dataset_dir)
        if member != dataset_dir and not is_namespace(member)
    ]
    return bool(members) and all(dataset_status.withdrawn(m) for m in members)


def index_text(catalog_root: Path) -> str:
    """The ``datacatalog.json`` the descriptors on disk make, without those left out."""
    root = datasets_dir(catalog_root)
    listed = [
        directory
        for directory in iter_dataset_dirs(root)
        if (directory / "datapackage.json").exists() and not left_out(directory)
    ]
    return dumps(build_catalog(catalog_root, listed))


def write_index(catalog_root: Path) -> Path:
    """Write ``datacatalog.json`` from the descriptors on disk; returns its path."""
    path = catalog_root / "datacatalog.json"
    path.write_text(index_text(catalog_root), encoding="utf-8", newline="\n")
    return path


def build_catalog(catalog_root: Path, dataset_dirs: list[Path]) -> dict:
    meta = catalog_meta(catalog_root)
    for key in catalogue_format.STRIPPED:
        meta.pop(key, None)
    datasets_root = datasets_dir(catalog_root)
    datasets = []
    for dataset_dir in sorted(dataset_dirs):
        package = json.loads(
            (dataset_dir / "datapackage.json").read_text(encoding="utf-8")
        )
        relative = dataset_dir.relative_to(datasets_root).as_posix()
        datasets.append(index_row(package, f"datasets/{relative}/datapackage.json"))
    return {
        k.SCHEMA: k.DATACATALOG_PROFILE,
        **meta,
        "datasets": datasets,
    }


def inherited_for(root: Path, dataset_dir: Path) -> dict:
    """Keys a nested dataset takes from the namespaces enclosing it.

    Outermost first, so a nearer namespace overrides a farther one, and the
    dataset's own dataset.yaml overrides both (``setdefault`` in render_dataset).
    """
    inherited: dict = {}
    current = dataset_dir.parent
    chain: list[Path] = []
    while current != root and current.is_relative_to(root):
        if (current / "dataset.yaml").is_file():
            chain.append(current)
        current = current.parent
    for parent in reversed(chain):
        meta = read_descriptor(parent)
        for key in dataset_format.INHERITED:
            if key in meta:
                inherited[key] = meta[key]
    return inherited


@report.reported
def run(catalog_root: Path, names: list[str], check: bool = False) -> int:
    catalog_meta(catalog_root)  # fail on a bad catalog.yaml before hashing anything
    root = datasets_dir(catalog_root)
    superseded = superseded_by_map(catalog_root)
    selected = [root / name for name in names] if names else iter_dataset_dirs(root)
    if names:
        # A successor built by name rebuilds the dataset it replaces too, whose
        # descriptor says who replaces it.
        for name in names:
            old = read_descriptor(root / name).get(k.SUPERSEDES)
            if old and (root / str(old) / "dataset.yaml").is_file():
                selected.append(root / str(old))
        selected = list(dict.fromkeys(selected))

    # Members before the namespaces that contain them: a namespace reports the
    # totals of everything beneath it, so it cannot be rendered until they are
    # known. Deepest first does that with no graph to walk.
    selected = sorted(selected, key=lambda p: (-len(p.relative_to(root).parts), p))

    stale: list[Path] = []
    rendered: dict[Path, dict] = {}
    rows: list[str] = []
    unmigrated: list[str] = []
    for dataset_dir in selected:
        if not (dataset_dir / "dataset.yaml").exists():
            raise DescriptorError(f"no dataset.yaml in {dataset_dir}")
        name = dataset_name_for(root, dataset_dir)
        namespace = is_namespace(dataset_dir)
        if left_out(dataset_dir):
            rows.append(f"  {name:<34} withdrawn, left out of the index")
            continue
        if not namespace and not dataset_status.path_of(dataset_dir).is_file():
            unmigrated.append(name)
        totals = None
        if namespace:
            # Sum over every member already rendered in this run, plus any whose
            # descriptor is on disk from an earlier one -- building a single
            # namespace by name must still report the family's real size.
            total_bytes = file_count = 0
            for member in iter_dataset_dirs(dataset_dir):
                if member == dataset_dir or dataset_status.withdrawn(member):
                    continue
                package = rendered.get(member)
                if package is None:
                    on_disk = member / "datapackage.json"
                    if not on_disk.is_file():
                        continue
                    package = json.loads(on_disk.read_text(encoding="utf-8"))
                if package.get(k.NAMESPACE):
                    continue
                total_bytes += package.get("ethos:total_bytes", 0)
                file_count += package.get("ethos:file_count", 0)
            totals = (total_bytes, file_count)

        files = render_dataset(
            dataset_dir,
            check=check,
            name=name,
            inherited=inherited_for(root, dataset_dir),
            namespace=namespace,
            member_totals=totals,
            superseded_by=superseded.get(name),
        )
        package = json.loads(files["datapackage.json"])
        rendered[dataset_dir] = package

        if check:
            stale += stale_files(dataset_dir, files)
            continue

        before = None if namespace else _inventory(dataset_dir)
        write_dataset(dataset_dir, files)
        if not namespace:
            _record_build(dataset_dir, name, before, package)
        size_gb = package["ethos:total_bytes"] / 1e9
        if package.get(k.NAMESPACE):
            klass = "namespace"
            shards = ""
        else:
            klass = f"{package['ethos:access']}/{package['ethos:visibility']}"
            shards = (
                f"  {len(package['ethos:shards']):>4} shards"
                if "ethos:shards" in package
                else ""
            )
        rows.append(
            f"  {package['name']:<34} {package['ethos:file_count']:>5} files  "
            f"{size_gb:8.3f} GB  {klass}{shards}"
        )

    for row in sorted(rows):
        report.info(row)
    if unmigrated:
        listed = ", ".join(unmigrated[:5])
        if len(unmigrated) > 5:
            listed += f" and {len(unmigrated) - 5} more"
        report.warning(
            f"warning: {listed} {'keeps its' if len(unmigrated) == 1 else 'keep their'} "
            f"build input in dataset.yaml, as before {dataset_status.STATUS} existed. "
            "`ethos-data catalog migrate` moves it across."
        )

    catalog_path = catalog_root / "datacatalog.json"
    catalog_text = index_text(catalog_root)

    if check:
        if (
            not catalog_path.exists()
            or catalog_path.read_text(encoding="utf-8") != catalog_text
        ):
            stale.append(catalog_path)
        if stale:
            report.warning("Out of date (re-run `ethos-data catalog build`):")
            for path in stale:
                report.warning(f"  {path.relative_to(catalog_root)}")
            return 1
        report.info("All manifests up to date.")
        return 0

    catalog_path.write_text(catalog_text, encoding="utf-8", newline="\n")
    listed = len(json.loads(catalog_text)[k.DATASETS])
    report.info(f"  {'datacatalog.json':<22} {listed:>5} datasets")
    return 0
