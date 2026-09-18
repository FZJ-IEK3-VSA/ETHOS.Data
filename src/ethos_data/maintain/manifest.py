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

``source_dir`` is not forever, though: once a dataset has been uploaded (see
``ethos-data catalog upload``) and verified, dCache -- not somebody's workstation
or a shared-storage mount that may get cleaned up or reorganised -- is the
authoritative copy. Setting ``ethos:uploaded: true`` in ``dataset.yaml`` says so,
and ``source_dir`` must be removed at the same time: a rebuild then freezes the
existing inventory (paths, sizes, hashes) exactly as last recorded, re-deriving
only the metadata that never depended on the bytes -- title, licence,
provenance, access. This is also what makes a dataset build-able again after
its ``source_dir`` has genuinely disappeared.

Provenance and licensing are checked here rather than left to a reviewer's eye.
``ethos:origin`` says whether the data was downloaded, derived or created, and an
origin that claims authorship has to name an author in ``contributors``.
``licenses`` is a list because a dataset really can be under several; one entry
may narrow itself to some of the files with ``ethos:applies_to``, which is
rendered as a resource-level ``licenses`` override.

A dataset that declares ``ethos:shard_depth: N`` is written *sharded*: the
inventory is split across ``manifests/<prefix>.json``, one file per directory
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

import hashlib
import json
import mimetypes
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath, PureWindowsPath

import yaml

from ..catalogs import CATALOG_ROLES, ROLE_KEY, ROLE_SOURCE, ROOT_SHARD, shard_key
from ..selection import path_matches
from . import (
    INHERITED_KEYS,
    NAMESPACE_KEY,
    dataset_name_for,
    datasets_dir,
    is_namespace,
    iter_dataset_dirs,
    resources_of,
)

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

ACCESS_CLASSES = ("public", "internal", "restricted")
VISIBILITIES = ("public", "hidden")

#: How this dataset came to exist. Declared, never inferred -- the same reason
#: ``ethos:catalog_role`` is declared. "Somebody here made this" is a claim with
#: licensing consequences, and guessing it from the presence of an author
#: contributor would make it true by accident.
ORIGIN_KEY = "ethos:origin"
#: downloaded -- mirrored as obtained; the upstream terms are the terms.
#: derived    -- computed from other data; ours, but downstream of somebody else's.
#: created    -- produced here from scratch; ICE-2 holds the rights.
ORIGINS = ("downloaded", "derived", "created")
DEFAULT_ORIGIN = "downloaded"
#: Prose saying *how* a derived dataset was computed. Already used by
#: geothermal-resource before it was formalised here; required for `derived`,
#: because "derived from what, by what method" is the whole content of the claim.
DERIVATION_KEY = "ethos:derivation"

#: Declared, not inferred, exactly like ``ethos:origin``. Once true, dCache holds
#: the copy this manifest's hashes must match, ``source_dir`` stops being read,
#: and it must be removed outright -- a stale path nobody rebuilds from is worse
#: than no path, since nothing about the descriptor would say it stopped being
#: the truth.
UPLOADED_KEY = "ethos:uploaded"

#: The same freeze, without the claim about dCache: the inventory is final and
#: there is no local build input any more.
#:
#: Uploading is one way a dataset reaches that state and it is not the only one.
#: Restricted data is never uploaded -- the authorised installation *is* the
#: permanent copy, and this manifest's hashes are what says it is still intact --
#: so once it has been moved into the restricted cache and the original retired,
#: there is nothing left to build from and nothing that should be rebuilt. The
#: same is true of public data materialised into a cache.
#:
#: Why freeze rather than repoint ``source_dir`` at the copy: a rebuild re-reads
#: and re-hashes whatever it is pointed at. Pointed at the copy, it would record
#: that copy's current bytes as the truth -- so a corrupted copy would be written
#: into the manifest as correct, and the check that would have caught it is the
#: thing that just destroyed the evidence. Hashes taken from the original are an
#: independent witness; keeping them is the whole point.
#:
#: ``ethos:uploaded: true`` implies this. Both are maintainer bookkeeping and
#: neither is published.
FROZEN_KEY = "ethos:frozen"

CONTRIBUTORS_KEY = "contributors"
#: Data Package's suggested roles. `author` is the one that carries weight here:
#: an origin of `derived` or `created` has to name who did it.
CONTRIBUTOR_ROLES = ("author", "contributor", "maintainer", "publisher", "wrangler")
AUTHOR_ROLE = "author"

LICENSES_KEY = "licenses"
#: Optional on one entry of ``licenses``: the glob patterns that licence covers,
#: for a dataset whose files are not all under the same terms -- upstream
#: originals beside conversions we made, say. Matched by the same rule as
#: ``ethos:include`` and a collection's ``files:``.
APPLIES_TO_KEY = "ethos:applies_to"
#: Optional on one entry of ``licenses``: an archived copy of the terms, as a path
#: relative to the dataset directory. Carried verbatim into the published catalogue.
DOCUMENT_KEY = "ethos:document"
#: Derived: the build hashes the archived document and records the digest here,
#: exactly as it does for a resource. Written in dataset.yaml by hand it is a pin
#: the build verifies instead -- for terms somebody has actually reviewed.
DOCUMENT_HASH_KEY = "ethos:document_sha256"

# Where a sharded dataset keeps the split inventory, relative to its own directory.
SHARD_DIR = "manifests"

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
EXCLUDE_ROOT_GLOBS = ("README*", "LICENSE*", "CHANGELOG*")


def sha256_of(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


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
        print(
            f"warning: could not write {HASH_CACHE_NAME} in {dataset_dir}: {error}",
            file=sys.stderr,
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
            for path, digest in zip(misses, pool.map(sha256_of, misses)):
                digests[path] = digest
                stat = stats[path]
                cache[relative[path]] = {
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "hash": digest,
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
            print(
                f"warning: {path} is a symbolic link to a directory; its contents are "
                f"NOT in the manifest. Point source_dir at the real tree, or replace "
                f"the link with the files themselves.",
                file=sys.stderr,
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


INCLUDE_KEY = "ethos:include"
EXCLUDE_KEY = "ethos:exclude"


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
        raise SystemExit(f"{INCLUDE_KEY}/{EXCLUDE_KEY}: empty pattern")
    if pattern.startswith("/"):
        raise SystemExit(
            f"{INCLUDE_KEY}/{EXCLUDE_KEY}: {pattern!r} starts with '/'. Patterns are "
            "relative to source_dir; drop the leading slash."
        )
    if pattern.endswith("/"):
        return [pattern.rstrip("/") + "/**"]
    if any(character in pattern for character in "*?["):
        return [pattern]
    return [pattern, pattern + "/**"]


def _patterns(name: str, meta: dict, key: str) -> list[str] | None:
    """Read one pattern list out of dataset.yaml, or None if it is absent."""
    raw = meta.get(key)
    if raw is None:
        return None
    if isinstance(raw, str) or not isinstance(raw, list):
        raise SystemExit(
            f"{name}: {key} must be a list of patterns, got {type(raw).__name__}"
        )
    if not raw:
        raise SystemExit(
            f"{name}: {key} is an empty list, which would select nothing. "
            f"Remove the key instead -- absent means 'no filter'."
        )
    if not all(isinstance(entry, str) for entry in raw):
        raise SystemExit(f"{name}: every entry in {key} must be a string")
    return raw


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
    include = _patterns(name, meta, INCLUDE_KEY)
    exclude = _patterns(name, meta, EXCLUDE_KEY)
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
            raise SystemExit(
                f"{name}: {INCLUDE_KEY} pattern(s) match no file under {root}:\n"
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
                print(
                    f"warning: {name}: {EXCLUDE_KEY} pattern {pattern!r} matches nothing "
                    f"under {root} -- already cleaned up, or a typo?",
                    file=sys.stderr,
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
                print(
                    f"note: {name}: keeping {relative[companion]} -- companion of "
                    f"{relative[path]}, which a filter would otherwise have dropped",
                    file=sys.stderr,
                )
                kept.add(companion)

    skipped = len(paths) - len(kept)
    if skipped:
        print(
            f"  {name}: {len(kept)} of {len(paths)} files under {root} "
            f"selected, {skipped} filtered out",
            file=sys.stderr,
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
        raise SystemExit(
            f"{name}: the inventory is declared final but there is no datapackage.json to "
            f"freeze. Build once with source_dir set, check the result, and only then set "
            f"{FROZEN_KEY}: true (or {UPLOADED_KEY}: true) and remove source_dir."
        )
    resources = resources_of(
        json.loads(package_file.read_text(encoding="utf-8")), dataset_dir
    )
    return [
        {k: v for k, v in resource.items() if k != LICENSES_KEY}
        for resource in resources
    ]


def build_resource(path: Path, root: Path, size: int, digest: str) -> dict:
    relative = path.relative_to(root).as_posix()
    resource = {
        "name": slugify(relative),
        "path": relative,
        "bytes": size,
        "hash": f"sha256:{digest}",
        "mediatype": mediatype_of(path),
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
            resource["ethos:sidecars"] = sidecars
    return resource


def validate_classification(name: str, meta: dict) -> tuple[str, str]:
    """Check the access/visibility pair, defaulting both to public.

    These two are independent: a dataset can be listed publicly while its bytes
    stay closed (so a public user gets a useful message instead of a mystery
    failure), and it can be hidden while colleagues use it daily (embargo).
    """
    access = meta.setdefault("ethos:access", "public")
    visibility = meta.setdefault("ethos:visibility", "public")

    if access not in ACCESS_CLASSES:
        raise SystemExit(
            f"{name}: ethos:access must be one of {ACCESS_CLASSES}, got {access!r}"
        )
    if visibility not in VISIBILITIES:
        raise SystemExit(
            f"{name}: ethos:visibility must be one of {VISIBILITIES}, got {visibility!r}"
        )
    if access == "public" and visibility == "hidden":
        raise SystemExit(
            f"{name}: access=public with visibility=hidden makes no sense -- "
            "if the bytes are downloadable by anyone, list the dataset."
        )
    if visibility == "hidden" and "ethos:embargo" not in meta:
        raise SystemExit(
            f"{name}: visibility=hidden needs an ethos:embargo block saying when and why "
            "it becomes public, otherwise it stays hidden by accident forever. "
            'Use `until: "unspecified"` only with an explicit reason.'
        )
    if access == "restricted" and meta.get("ethos:remote_prefix"):
        raise SystemExit(
            f"{name}: restricted data must not declare ethos:remote_prefix -- "
            "it is never uploaded. Configure dataset_roots on each machine instead."
        )
    if access == "restricted" and meta.get(UPLOADED_KEY):
        # The freeze this asks for is right; the claim attached to it is not.
        # Restricted data never reaches dCache, so "dCache holds it now" would be
        # a false statement sitting in the catalogue -- and there is a key that
        # says the true half on its own.
        raise SystemExit(
            f"{name}: restricted data is never uploaded, so {UPLOADED_KEY}: true cannot "
            f"be right. If its inventory is final -- the authorised installation is the "
            f"permanent copy and there is nothing local left to build from -- say that "
            f"instead:\n    {FROZEN_KEY}: true"
        )
    return access, visibility


def validate_licenses(name: str, meta: dict) -> list[dict]:
    """Check the ``licenses`` array, and return it.

    Frictionless makes ``licenses`` a list already, so several licences need no
    extension -- only checking. A dataset really does carry more than one: a
    product whose documentation is CC-BY while the data is under bespoke terms,
    or an upstream mirror beside conversions we made and licence ourselves.

    An entry needs ``name`` (an Open Definition id) or ``path`` (a URL) to say
    anything at all; one carrying only a ``title`` reads as a licence and
    identifies nothing, which is worse than an honest
    ``ethos:license_status: unresolved``.
    """
    licenses = meta.get(LICENSES_KEY)
    if licenses is None:
        return []
    if not isinstance(licenses, list):
        raise SystemExit(
            f"{name}: {LICENSES_KEY} must be a list, even with one entry -- "
            "a dataset can be under several."
        )
    for index, entry in enumerate(licenses):
        where = f"{name}: {LICENSES_KEY}[{index}]"
        if not isinstance(entry, dict):
            raise SystemExit(f"{where} must be a mapping with 'name' and/or 'path'.")
        if not (entry.get("name") or entry.get("path")):
            raise SystemExit(
                f"{where} has neither 'name' nor 'path'. Give an Open Definition id "
                "(name: CC-BY-4.0) or a URL to the terms (path: https://...); a bare "
                "title names no licence. If the terms are not settled, drop the entry "
                "and set ethos:license_status: unresolved instead."
            )
        patterns = entry.get(APPLIES_TO_KEY)
        if patterns is None:
            continue
        if not isinstance(patterns, list) or not all(
            isinstance(p, str) and p for p in patterns
        ):
            raise SystemExit(
                f"{where}: {APPLIES_TO_KEY} must be a list of glob patterns."
            )
    return licenses


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
        where = f"{name}: {LICENSES_KEY}[{index}]"
        document = entry.get(DOCUMENT_KEY)
        if document is None:
            if DOCUMENT_HASH_KEY in entry:
                raise SystemExit(
                    f"{where} has {DOCUMENT_HASH_KEY} but no {DOCUMENT_KEY} to hash. "
                    "Archive the terms beside dataset.yaml and name the file, or drop "
                    "the hash."
                )
            continue
        relative = PurePosixPath(str(document))
        if (
            not isinstance(document, str)
            or not document
            or "\\" in document
            or relative.is_absolute()
            or PureWindowsPath(document).drive
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise SystemExit(
                f"{where}: {DOCUMENT_KEY} must be a relative path inside the dataset "
                f"directory, such as licenses/terms.txt; got {document!r}."
            )
        path = dataset_dir.joinpath(*relative.parts)
        if not path.is_file():
            raise SystemExit(
                f"{where} names {DOCUMENT_KEY} {document}, which is not a file at "
                f"{path}. Archive the terms there, or drop {DOCUMENT_KEY}."
            )
        actual = sha256_of(path)
        pinned = entry.get(DOCUMENT_HASH_KEY)
        if pinned is not None:
            if not isinstance(pinned, str):
                raise SystemExit(
                    f"{where}: {DOCUMENT_HASH_KEY} must be a hex digest in quotes; YAML "
                    f"read {pinned!r} as a number, which loses leading zeros. Quote it, "
                    f"or delete it and let the build record the digest."
                )
            declared = pinned.strip().lower().removeprefix("sha256:")
            if declared != actual:
                raise SystemExit(
                    f"{where}: {document} hashes to {actual}, but dataset.yaml pins "
                    f"{DOCUMENT_HASH_KEY}: {declared}. The archived text is not the one "
                    f"that hash was recorded for. If the file is right, delete "
                    f"{DOCUMENT_HASH_KEY} and rebuild -- the build records the digest "
                    "itself. If the hash is right, restore the file."
                )
        entry[DOCUMENT_HASH_KEY] = actual


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
    narrowed = [entry for entry in licenses if entry.get(APPLIES_TO_KEY)]
    if not narrowed:
        return

    for entry in narrowed:
        patterns = entry[APPLIES_TO_KEY]
        # The resource-level copy drops applies_to: it is a build-time
        # instruction about which files to attach to, and on the file it was
        # attached to it answers a question nobody is asking.
        published = {k: v for k, v in entry.items() if k != APPLIES_TO_KEY}
        matched = 0
        for resource in resources:
            if any(path_matches(resource["path"], p) for p in patterns):
                resource.setdefault(LICENSES_KEY, []).append(published)
                matched += 1
        if not matched:
            raise SystemExit(
                f"{name}: {LICENSES_KEY} entry "
                f"{entry.get('name') or entry.get('path')!r} has {APPLIES_TO_KEY} "
                f"{patterns}, which matches none of the {len(resources)} files in this "
                "dataset. Fix the pattern, or drop the key so the licence covers "
                "everything."
            )

    uncovered = [r["path"] for r in resources if LICENSES_KEY not in r]
    if uncovered and len(narrowed) == len(licenses):
        # Every licence was narrowed, so these files inherit an empty package
        # licence -- described by nothing at all.
        shown = ", ".join(uncovered[:5])
        more = "" if len(uncovered) <= 5 else f", and {len(uncovered) - 5} more"
        print(
            f"warning: {name}: every {LICENSES_KEY} entry is narrowed with "
            f"{APPLIES_TO_KEY}, so {len(uncovered)} file(s) are covered by no licence "
            f"at all: {shown}{more}. Add a licence without {APPLIES_TO_KEY} for the "
            "rest, or widen one of the patterns.",
            file=sys.stderr,
        )


def validate_provenance(name: str, meta: dict) -> str:
    """Check ``ethos:origin`` and ``contributors``, defaulting origin to downloaded.

    Most of this catalogue is mirrored data: somebody else made it, we hold a
    copy, and the upstream terms are the terms. Some of it is not -- the GeoTIFF
    conversions in ``landcover``, the whole of ``geothermal-resource`` -- and for
    those the licence question has a different answer, because the rights are
    ours. Nothing in a descriptor said which kind a dataset was, so it had to be
    read out of prose in ``ethos:attribution``, one dataset at a time.

    ``downloaded`` is the default because it is both the common case and the
    conservative one: claiming less about authorship than is true is safe, and
    claiming more is not.
    """
    origin = meta.setdefault(ORIGIN_KEY, DEFAULT_ORIGIN)
    if origin not in ORIGINS:
        raise SystemExit(
            f"{name}: {ORIGIN_KEY} must be one of {ORIGINS}, got {origin!r}"
        )

    contributors = meta.get(CONTRIBUTORS_KEY) or []
    if not isinstance(contributors, list):
        raise SystemExit(f"{name}: {CONTRIBUTORS_KEY} must be a list of mappings.")
    for index, person in enumerate(contributors):
        where = f"{name}: {CONTRIBUTORS_KEY}[{index}]"
        if not isinstance(person, dict):
            raise SystemExit(f"{where} must be a mapping with at least a 'title'.")
        if not person.get("title"):
            raise SystemExit(f"{where} needs a 'title' -- the person or group's name.")
        roles = person.get("roles", [])
        if isinstance(roles, str):
            # Data Package v1 spelled this `role`, singular and scalar. Reject
            # rather than coerce: a descriptor that half-follows two versions of
            # the spec is worse than one that is told which it is following.
            raise SystemExit(
                f"{where}: 'roles' is a list in Data Package v2 -- write "
                f"roles: [{roles}], not roles: {roles}."
            )
        if not isinstance(roles, list):
            raise SystemExit(f"{where}: 'roles' must be a list.")
        for role in roles:
            if role not in CONTRIBUTOR_ROLES:
                raise SystemExit(
                    f"{where}: unknown role {role!r}. Use one of {CONTRIBUTOR_ROLES}."
                )

    if origin == DEFAULT_ORIGIN:
        return origin

    authors = [p for p in contributors if AUTHOR_ROLE in (p.get("roles") or [])]
    if not authors:
        raise SystemExit(
            f"{name}: {ORIGIN_KEY} is {origin!r}, which claims this data was made here, "
            f"so it has to say by whom. Add a {CONTRIBUTORS_KEY} entry with "
            f"roles: [{AUTHOR_ROLE}]:\n"
            f"    {CONTRIBUTORS_KEY}:\n"
            f"      - title: Some Person\n"
            f"        roles: [{AUTHOR_ROLE}]\n"
            f"        organization: Forschungszentrum Julich, ICE-2"
        )

    if origin == "derived":
        if not meta.get("sources"):
            raise SystemExit(
                f"{name}: {ORIGIN_KEY}: derived needs 'sources' saying what it was "
                "derived FROM. Derived data inherits obligations from its inputs; a "
                "derivation with no named input cannot be checked against them."
            )
        if not meta.get(DERIVATION_KEY):
            raise SystemExit(
                f"{name}: {ORIGIN_KEY}: derived needs {DERIVATION_KEY} saying HOW -- the "
                "method, parameters and inputs, in enough detail that somebody could "
                "redo it. Without that, 'derived' says only that the numbers are not "
                "upstream's, which is the least useful half of the claim."
            )
    return origin


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
) -> dict[str, str]:
    """Build every generated file for one dataset.

    Returns ``{path relative to dataset_dir -> file text}``: always
    ``datapackage.json``, plus one ``manifests/<prefix>.json`` per shard when the
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
    few keys a member takes from the namespace above it -- see INHERITED_KEYS.
    """
    name = name or dataset_dir.name
    meta = yaml.safe_load((dataset_dir / "dataset.yaml").read_text(encoding="utf-8"))

    # The name is derived from where the file sits, not trusted from inside it.
    # A dataset.yaml that disagrees with its own location is a rename half-done,
    # and the failure it causes later -- a collections file resolving to nothing
    # -- is a long way from the cause.
    declared = meta.get("name")
    if declared is not None and declared != name:
        raise SystemExit(
            f"{name}: dataset.yaml says name: {declared!r}, but the directory it is in "
            f"makes it {name!r}. The directory decides; fix the name, or move the directory."
        )
    meta["name"] = name

    if inherited:
        for key, value in inherited.items():
            meta.setdefault(key, value)

    if namespace:
        return _render_namespace(dataset_dir, name, meta, member_totals or (0, 0))

    validate_classification(name, meta)
    validate_provenance(name, meta)
    licenses = validate_licenses(name, meta)
    record_license_documents(name, dataset_dir, licenses)

    # All local to the maintainer, never published -- see the module docstring.
    uploaded = bool(meta.pop(UPLOADED_KEY, False))
    # Uploading implies it; it does not imply uploading. See FROZEN_KEY.
    frozen = bool(meta.pop(FROZEN_KEY, False)) or uploaded
    raw_source_dir = meta.pop("source_dir", None)

    if frozen:
        if raw_source_dir is not None:
            reason = (
                "Once uploaded, dCache is the source of truth and source_dir is never "
                "read again -- remove it."
                if uploaded
                else "A frozen inventory is never rebuilt from local files; the copy it "
                "describes is the permanent one -- remove it."
            )
            declared = UPLOADED_KEY if uploaded else FROZEN_KEY
            raise SystemExit(
                f"{name}: declares {declared}: true and still has "
                f"source_dir: {raw_source_dir!r}. {reason}"
            )
        resources = frozen_resources(name, dataset_dir)
    else:
        if raw_source_dir is None:
            raise SystemExit(
                f"{name}: source_dir is required, unless {UPLOADED_KEY}: true says the "
                f"dataset was already uploaded, or {FROZEN_KEY}: true says its inventory "
                "is final and there is nothing local left to build from."
            )
        source_dir = Path(raw_source_dir).expanduser()
        # Only a *relative* source_dir is resolved, and only to make it absolute.
        # An absolute one is used exactly as written, symbolic links and all: when
        # it names the curated namespace (/fast/central/shared_data/...), that is
        # the path worth recording, because it is the one that stays correct when
        # the storage behind it moves. Resolving it here would silently write the
        # transient physical location into the manifest instead.
        if not source_dir.is_absolute():
            source_dir = (dataset_dir / source_dir).resolve()
        if not source_dir.is_dir():
            raise SystemExit(f"{name}: source_dir does not exist: {source_dir}")

        found = list(iter_data_files(source_dir))
        if not found:
            raise SystemExit(f"{name}: no data files found under {source_dir}")
        selected = select(name, source_dir, found, meta)
        if not selected:
            raise SystemExit(
                f"{name}: {INCLUDE_KEY}/{EXCLUDE_KEY} filtered out every one of the "
                f"{len(found)} files under {source_dir}"
            )

        cache = load_hash_cache(dataset_dir)
        hashes = resolve_hashes(selected, source_dir, cache)
        if not check:
            save_hash_cache(dataset_dir, cache)
        resources = [build_resource(p, source_dir, *hashes[p]) for p in selected]

    # After the inventory exists, because a narrowed licence has to be checked
    # against the files it claims to cover.
    apply_resource_licenses(name, resources, licenses)

    depth = int(meta.get("ethos:shard_depth", 0) or 0)
    if depth < 0:
        raise SystemExit(f"{name}: ethos:shard_depth must not be negative")

    package = {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        **meta,
    }
    files: dict[str, str] = {}

    if depth:
        shards = split_into_shards(resources, depth)
        if len(shards) == 1 and ROOT_SHARD in shards:
            # Every file sits at the dataset root, so sharding cannot split
            # anything -- and a lone _root shard is strictly worse than an
            # inline inventory: one extra fetch to learn what you already had.
            raise SystemExit(
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
    files["datapackage.json"] = dumps(package)
    return files


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
    for forbidden in (
        "source_dir",
        "ethos:uploaded",
        "ethos:shard_depth",
        INCLUDE_KEY,
        EXCLUDE_KEY,
    ):
        if forbidden in meta:
            raise SystemExit(
                f"{name}: is a namespace -- it holds other datasets -- so it cannot also "
                f"describe files of its own, and {forbidden} says it does. Move that key "
                f"into one of its members, or move the members out."
            )
    if "ethos:access" in meta:
        raise SystemExit(
            f"{name}: is a namespace and must not declare ethos:access. An access class says "
            "where bytes are read from, and a namespace has none -- its members each declare "
            "their own, which is the whole reason a family can be part public and part not."
        )
    if "licenses" in meta or meta.get("ethos:license_status"):
        raise SystemExit(
            f"{name}: is a namespace and must not carry licensing. Its members each state "
            "their own -- a licence inherited without being read is how a dataset ends up "
            "published under terms nobody applied to it."
        )

    total_bytes, file_count = member_totals
    package = {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        **meta,
        NAMESPACE_KEY: True,
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

    shard_root = dataset_dir / SHARD_DIR
    if not shard_root.is_dir():
        return
    generated = {dataset_dir / relative for relative in files}
    for path in sorted(shard_root.rglob("*"), reverse=True):
        if path.is_file() and path not in generated:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    if not any(shard_root.iterdir()):
        shard_root.rmdir()


def stale_files(dataset_dir: Path, files: dict[str, str]) -> list[Path]:
    """Generated files that are missing, changed, or left over on disk."""
    stale = [
        dataset_dir / relative
        for relative, text in files.items()
        if not (dataset_dir / relative).is_file()
        or (dataset_dir / relative).read_text(encoding="utf-8") != text
    ]
    shard_root = dataset_dir / SHARD_DIR
    if shard_root.is_dir():
        generated = {dataset_dir / relative for relative in files}
        stale += [
            p
            for p in sorted(shard_root.rglob("*"))
            if p.is_file() and p not in generated
        ]
    return stale


def catalog_meta(catalog_root: Path) -> dict:
    """Read and validate catalog.yaml.

    Called before any dataset is touched. Catalogue-level mistakes are cheap to
    find and expensive to find late: checksumming a multi-terabyte dataset only
    to reject the file that names the catalogue wastes the whole run.
    """
    meta = yaml.safe_load((catalog_root / "catalog.yaml").read_text(encoding="utf-8"))

    # A catalogue you can run `build` in is by definition a source one: it has
    # the dataset.yaml files this reads. Default rather than demand it, so an
    # existing catalog.yaml keeps working, but reject a wrong value outright --
    # a catalogue mislabelled `published` would make every tool refuse to touch it.
    role = meta.setdefault(ROLE_KEY, ROLE_SOURCE)
    if role not in CATALOG_ROLES:
        raise SystemExit(
            f"catalog.yaml: {ROLE_KEY} must be one of {CATALOG_ROLES}, got {role!r}"
        )
    if role != ROLE_SOURCE:
        raise SystemExit(
            f"catalog.yaml declares {ROLE_KEY}: {role!r}, but this is the catalogue being built "
            f"from dataset.yaml files, which makes it {ROLE_SOURCE!r}. The published copy gets "
            "its role set by `ethos-data catalog publish`; do not set it by hand."
        )
    return meta


def build_catalog(catalog_root: Path, dataset_dirs: list[Path]) -> dict:
    meta = catalog_meta(catalog_root)
    datasets_root = datasets_dir(catalog_root)
    datasets = []
    for dataset_dir in sorted(dataset_dirs):
        package = json.loads(
            (dataset_dir / "datapackage.json").read_text(encoding="utf-8")
        )
        if package.get(NAMESPACE_KEY):
            # A namespace row carries no access class, no remote prefix and no
            # licence status, because it has no bytes for any of those to be
            # about. It is in the index so that a family can be listed and
            # described by name; a resolver that meets one and tries to fetch it
            # should find nothing to fetch, not a plausible-looking default.
            datasets.append(
                {
                    "name": package["name"],
                    "path": f"datasets/{dataset_dir.relative_to(datasets_root).as_posix()}/datapackage.json",
                    "title": package.get("title", ""),
                    NAMESPACE_KEY: True,
                    "ethos:total_bytes": package["ethos:total_bytes"],
                    "ethos:file_count": package["ethos:file_count"],
                }
            )
            continue
        datasets.append(
            {
                "name": package["name"],
                "path": f"datasets/{dataset_dir.relative_to(datasets_root).as_posix()}/datapackage.json",
                "title": package.get("title", ""),
                # The publisher's own release string. Promoted for the same reason
                # as license_status: "which release of the upstream product is
                # this?" is a question a consumer asks before deciding to fetch
                # 60 GiB, and answering it should not cost an inventory read.
                # Omitted rather than blanked when a dataset does not declare one,
                # so absent means "nobody has recorded it", not "unversioned".
                **({"version": package["version"]} if package.get("version") else {}),
                "ethos:access": package.get("ethos:access", "public"),
                "ethos:visibility": package.get("ethos:visibility", "public"),
                "ethos:total_bytes": package["ethos:total_bytes"],
                "ethos:file_count": package["ethos:file_count"],
                # Promoted out of the datapackage so that resolvers can answer
                # "where does it live?" and "is the licence settled?" from the
                # index alone. Without these, laziness buys nothing: locating a
                # file or warning about licensing would pull the whole inventory.
                "ethos:remote_prefix": package.get(
                    "ethos:remote_prefix", package["name"]
                ),
                "ethos:license_status": (
                    "resolved"
                    if package.get("licenses")
                    else package.get("ethos:license_status", "unknown")
                ),
            }
        )
    return {
        "$schema": "https://datapackage.org/profiles/2.0/datacatalog.json",
        **meta,
        "datasets": datasets,
    }


def _inherited_for(root: Path, dataset_dir: Path) -> dict:
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
        meta = (
            yaml.safe_load((parent / "dataset.yaml").read_text(encoding="utf-8")) or {}
        )
        for key in INHERITED_KEYS:
            if key in meta:
                inherited[key] = meta[key]
    return inherited


def run(catalog_root: Path, names: list[str], check: bool = False) -> int:
    catalog_meta(catalog_root)  # fail on a bad catalog.yaml before hashing anything
    root = datasets_dir(catalog_root)
    selected = [root / name for name in names] if names else iter_dataset_dirs(root)

    # Members before the namespaces that contain them: a namespace reports the
    # totals of everything beneath it, so it cannot be rendered until they are
    # known. Deepest first does that with no graph to walk.
    selected = sorted(selected, key=lambda p: (-len(p.relative_to(root).parts), p))

    stale: list[Path] = []
    rendered: dict[Path, dict] = {}
    rows: list[str] = []
    for dataset_dir in selected:
        if not (dataset_dir / "dataset.yaml").exists():
            raise SystemExit(f"no dataset.yaml in {dataset_dir}")
        name = dataset_name_for(root, dataset_dir)
        namespace = is_namespace(dataset_dir)
        totals = None
        if namespace:
            # Sum over every member already rendered in this run, plus any whose
            # descriptor is on disk from an earlier one -- building a single
            # namespace by name must still report the family's real size.
            total_bytes = file_count = 0
            for member in iter_dataset_dirs(dataset_dir):
                if member == dataset_dir:
                    continue
                package = rendered.get(member)
                if package is None:
                    on_disk = member / "datapackage.json"
                    if not on_disk.is_file():
                        continue
                    package = json.loads(on_disk.read_text(encoding="utf-8"))
                if package.get(NAMESPACE_KEY):
                    continue
                total_bytes += package.get("ethos:total_bytes", 0)
                file_count += package.get("ethos:file_count", 0)
            totals = (total_bytes, file_count)

        files = render_dataset(
            dataset_dir,
            check=check,
            name=name,
            inherited=_inherited_for(root, dataset_dir),
            namespace=namespace,
            member_totals=totals,
        )
        package = json.loads(files["datapackage.json"])
        rendered[dataset_dir] = package

        if check:
            stale += stale_files(dataset_dir, files)
            continue

        write_dataset(dataset_dir, files)
        size_gb = package["ethos:total_bytes"] / 1e9
        if package.get(NAMESPACE_KEY):
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
        print(row)

    all_dirs = [p for p in iter_dataset_dirs(root) if (p / "datapackage.json").exists()]
    catalog_path = catalog_root / "datacatalog.json"
    catalog_text = dumps(build_catalog(catalog_root, all_dirs))

    if check:
        if (
            not catalog_path.exists()
            or catalog_path.read_text(encoding="utf-8") != catalog_text
        ):
            stale.append(catalog_path)
        if stale:
            print("Out of date (re-run `ethos-data catalog build`):", file=sys.stderr)
            for path in stale:
                print(f"  {path.relative_to(catalog_root)}", file=sys.stderr)
            return 1
        print("All manifests up to date.")
        return 0

    catalog_path.write_text(catalog_text, encoding="utf-8", newline="\n")
    print(f"  {'datacatalog.json':<22} {len(all_dirs):>5} datasets")
    return 0
