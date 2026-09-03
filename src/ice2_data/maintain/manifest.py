"""Generate Frictionless Data Package descriptors for an ICE-2 data catalogue.

Each dataset directory under ``datasets/`` holds a hand-written ``dataset.yaml``
(identity, provenance, licensing) and a generated ``datapackage.json`` (the file
inventory: paths, sizes, checksums).  Never edit ``datapackage.json`` by hand --
re-run this instead.

    ice2-catalog build                 # rebuild every dataset
    ice2-catalog build landcover       # rebuild one
    ice2-catalog build --check         # verify manifests are current

A dataset that declares ``ice2:shard_depth: N`` is written *sharded*: the
inventory is split across ``manifests/<prefix>.json``, one file per directory
prefix of N segments, and ``datapackage.json`` carries an ``ice2:shards`` index
instead of a ``resources`` array.  ``ice2_data.catalog`` then parses only the
shards a selection can match.  The grouping rule is imported from the reader
rather than reimplemented -- writer and reader must agree on it exactly.

Spec: https://datapackage.org/standard/data-package/
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import sys
from pathlib import Path

import yaml

from ..catalog import CATALOG_ROLES, ROLE_KEY, ROLE_SOURCE, ROOT_SHARD, shard_key
from . import datasets_dir

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
SHAPEFILE_SIDECAR_EXTS = [".shx", ".dbf", ".prj", ".cpg", ".qpj", ".qmd", ".sbn", ".sbx", ".xml"]

ACCESS_CLASSES = ("public", "internal", "restricted")
VISIBILITIES = ("public", "hidden")

# Where a sharded dataset keeps the split inventory, relative to its own directory.
SHARD_DIR = "manifests"

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
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_NAMES for part in path.relative_to(root).parts):
            continue
        if path.suffix in EXCLUDE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if len(relative.parts) == 1 and any(relative.match(g) for g in EXCLUDE_ROOT_GLOBS):
            continue
        yield path


def build_resource(path: Path, root: Path) -> dict:
    relative = path.relative_to(root).as_posix()
    resource = {
        "name": slugify(relative),
        "path": relative,
        "bytes": path.stat().st_size,
        "hash": f"sha256:{sha256_of(path)}",
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
            resource["ice2:sidecars"] = sidecars
    return resource


def validate_classification(name: str, meta: dict) -> tuple[str, str]:
    """Check the access/visibility pair, defaulting both to public.

    These two are independent: a dataset can be listed publicly while its bytes
    stay closed (so a public user gets a useful message instead of a mystery
    failure), and it can be hidden while colleagues use it daily (embargo).
    """
    access = meta.setdefault("ice2:access", "public")
    visibility = meta.setdefault("ice2:visibility", "public")

    if access not in ACCESS_CLASSES:
        raise SystemExit(f"{name}: ice2:access must be one of {ACCESS_CLASSES}, got {access!r}")
    if visibility not in VISIBILITIES:
        raise SystemExit(f"{name}: ice2:visibility must be one of {VISIBILITIES}, got {visibility!r}")
    if access == "public" and visibility == "hidden":
        raise SystemExit(
            f"{name}: access=public with visibility=hidden makes no sense -- "
            "if the bytes are downloadable by anyone, list the dataset."
        )
    if visibility == "hidden" and "ice2:embargo" not in meta:
        raise SystemExit(
            f"{name}: visibility=hidden needs an ice2:embargo block saying when and why "
            "it becomes public, otherwise it stays hidden by accident forever. "
            'Use `until: "unspecified"` only with an explicit reason.'
        )
    if access == "restricted" and meta.get("ice2:remote_prefix"):
        raise SystemExit(
            f"{name}: restricted data must not declare ice2:remote_prefix -- "
            "it is never uploaded. Configure dataset_roots on each machine instead."
        )
    return access, visibility


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


def render_dataset(dataset_dir: Path) -> dict[str, str]:
    """Build every generated file for one dataset.

    Returns ``{path relative to dataset_dir -> file text}``: always
    ``datapackage.json``, plus one ``manifests/<prefix>.json`` per shard when the
    dataset declares ``ice2:shard_depth``.  Rendering the whole set in memory is
    what lets ``--check`` detect a stale *shard* as readily as a stale index.
    """
    meta = yaml.safe_load((dataset_dir / "dataset.yaml").read_text())
    validate_classification(dataset_dir.name, meta)

    source_dir = Path(meta.pop("source_dir")).expanduser()  # local to the maintainer, never published
    if not source_dir.is_absolute():
        source_dir = (dataset_dir / source_dir).resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"{dataset_dir.name}: source_dir does not exist: {source_dir}")

    resources = [build_resource(p, source_dir) for p in iter_data_files(source_dir)]
    if not resources:
        raise SystemExit(f"{dataset_dir.name}: no data files found under {source_dir}")

    depth = int(meta.get("ice2:shard_depth", 0) or 0)
    if depth < 0:
        raise SystemExit(f"{dataset_dir.name}: ice2:shard_depth must not be negative")

    package = {"$schema": "https://datapackage.org/profiles/2.0/datapackage.json", **meta}
    files: dict[str, str] = {}

    if depth:
        shards = split_into_shards(resources, depth)
        if len(shards) == 1 and ROOT_SHARD in shards:
            # Every file sits at the dataset root, so sharding cannot split
            # anything -- and a lone _root shard is strictly worse than an
            # inline inventory: one extra fetch to learn what you already had.
            raise SystemExit(
                f"{dataset_dir.name}: ice2:shard_depth is {depth}, but no file is nested "
                f"{depth} director{'y' if depth == 1 else 'ies'} deep, so there is nothing "
                "to shard. Drop ice2:shard_depth, or lower it."
            )
        index = []
        for prefix, members in shards.items():
            relative = shard_path(prefix)
            files[relative] = dumps(
                {
                    "name": f"{package['name']}-{slugify(prefix)}",
                    "ice2:shard": prefix,
                    "resources": members,
                }
            )
            index.append(
                {
                    "prefix": prefix,
                    "path": relative,
                    "ice2:file_count": len(members),
                    "ice2:total_bytes": sum(r["bytes"] for r in members),
                }
            )
        package["ice2:shard_depth"] = depth
        package["ice2:shards"] = index
    else:
        # An unsharded descriptor must not advertise a depth: the reader treats
        # the presence of ice2:shards as the switch, and a stray depth alongside
        # an inline inventory is a lie waiting to be believed by the next tool.
        package.pop("ice2:shard_depth", None)
        package["resources"] = resources

    package["ice2:total_bytes"] = sum(r["bytes"] for r in resources)
    package["ice2:file_count"] = len(resources)
    files["datapackage.json"] = dumps(package)
    return files


def write_dataset(dataset_dir: Path, files: dict[str, str]) -> None:
    """Write the rendered files and remove shards that are no longer generated.

    A rebuild that drops a shard -- the tile it described was deleted upstream --
    has to delete the file too, or the index and the directory disagree and the
    stale shard is published forever.
    """
    for relative, text in files.items():
        target = dataset_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

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
        if not (dataset_dir / relative).is_file() or (dataset_dir / relative).read_text() != text
    ]
    shard_root = dataset_dir / SHARD_DIR
    if shard_root.is_dir():
        generated = {dataset_dir / relative for relative in files}
        stale += [p for p in sorted(shard_root.rglob("*")) if p.is_file() and p not in generated]
    return stale


def catalog_meta(catalog_root: Path) -> dict:
    """Read and validate catalog.yaml.

    Called before any dataset is touched. Catalogue-level mistakes are cheap to
    find and expensive to find late: checksumming a multi-terabyte dataset only
    to reject the file that names the catalogue wastes the whole run.
    """
    meta = yaml.safe_load((catalog_root / "catalog.yaml").read_text())

    # A catalogue you can run `build` in is by definition a source one: it has
    # the dataset.yaml files this reads. Default rather than demand it, so an
    # existing catalog.yaml keeps working, but reject a wrong value outright --
    # a catalogue mislabelled `published` would make every tool refuse to touch it.
    role = meta.setdefault(ROLE_KEY, ROLE_SOURCE)
    if role not in CATALOG_ROLES:
        raise SystemExit(f"catalog.yaml: {ROLE_KEY} must be one of {CATALOG_ROLES}, got {role!r}")
    if role != ROLE_SOURCE:
        raise SystemExit(
            f"catalog.yaml declares {ROLE_KEY}: {role!r}, but this is the catalogue being built "
            f"from dataset.yaml files, which makes it {ROLE_SOURCE!r}. The published copy gets "
            "its role set by `ice2-catalog publish`; do not set it by hand."
        )
    return meta


def build_catalog(catalog_root: Path, dataset_dirs: list[Path]) -> dict:
    meta = catalog_meta(catalog_root)
    datasets = []
    for dataset_dir in sorted(dataset_dirs):
        package = json.loads((dataset_dir / "datapackage.json").read_text())
        datasets.append(
            {
                "name": package["name"],
                "path": f"datasets/{dataset_dir.name}/datapackage.json",
                "title": package.get("title", ""),
                "ice2:access": package.get("ice2:access", "public"),
                "ice2:visibility": package.get("ice2:visibility", "public"),
                "ice2:total_bytes": package["ice2:total_bytes"],
                "ice2:file_count": package["ice2:file_count"],
                # Promoted out of the datapackage so that resolvers can answer
                # "where does it live?" and "is the licence settled?" from the
                # index alone. Without these, laziness buys nothing: locating a
                # file or warning about licensing would pull the whole inventory.
                "ice2:remote_prefix": package.get("ice2:remote_prefix", package["name"]),
                "ice2:license_status": (
                    "resolved" if package.get("licenses")
                    else package.get("ice2:license_status", "unknown")
                ),
            }
        )
    return {
        "$schema": "https://datapackage.org/profiles/2.0/datacatalog.json",
        **meta,
        "datasets": datasets,
    }


def run(catalog_root: Path, names: list[str], check: bool = False) -> int:
    catalog_meta(catalog_root)  # fail on a bad catalog.yaml before hashing anything
    root = datasets_dir(catalog_root)
    selected = (
        [root / name for name in names]
        if names
        else [p for p in sorted(root.iterdir()) if (p / "dataset.yaml").exists()]
    )

    stale: list[Path] = []
    for dataset_dir in selected:
        if not (dataset_dir / "dataset.yaml").exists():
            raise SystemExit(f"no dataset.yaml in {dataset_dir}")
        files = render_dataset(dataset_dir)
        package = json.loads(files["datapackage.json"])

        if check:
            stale += stale_files(dataset_dir, files)
            continue

        write_dataset(dataset_dir, files)
        size_gb = package["ice2:total_bytes"] / 1e9
        klass = f"{package['ice2:access']}/{package['ice2:visibility']}"
        shards = f"  {len(package['ice2:shards']):>4} shards" if "ice2:shards" in package else ""
        print(f"  {package['name']:<22} {package['ice2:file_count']:>5} files  "
              f"{size_gb:8.3f} GB  {klass}{shards}")

    all_dirs = [p for p in sorted(root.iterdir()) if (p / "datapackage.json").exists()]
    catalog_path = catalog_root / "datacatalog.json"
    catalog_text = dumps(build_catalog(catalog_root, all_dirs))

    if check:
        if not catalog_path.exists() or catalog_path.read_text() != catalog_text:
            stale.append(catalog_path)
        if stale:
            print("Out of date (re-run `ice2-catalog build`):", file=sys.stderr)
            for path in stale:
                print(f"  {path.relative_to(catalog_root)}", file=sys.stderr)
            return 1
        print("All manifests up to date.")
        return 0

    catalog_path.write_text(catalog_text)
    print(f"  {'datacatalog.json':<22} {len(all_dirs):>5} datasets")
    return 0
