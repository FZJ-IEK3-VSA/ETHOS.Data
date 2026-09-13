"""Catalogue-verified fixture copies for offline package tests.

dCache remains the published authority. A bundle records selected catalogue
metadata and copies its files under data/<dataset>/<path>. Reads consult only
these files, independently of configuration, staging, CWD, and the network.
An explicit allow_modified development override never changes original hashes.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Mapping, Sequence

import pooch
import yaml

from .catalog import Catalog, Resource
from .retrieval import DataFiles
from .selection import load_collections

__all__ = [
    "Bundle", "BundleError", "BundleFinding", "ModifiedBundleWarning",
    "export_bundle", "load_bundle",
]

MANIFEST = "bundle.json"
FORMAT = "ethos-data-bundle-v1"
_SHA256 = re.compile(r"sha256:[0-9a-fA-F]{64}\Z")


class BundleError(ValueError):
    """The bundle is incomplete, invalid, or differs from its catalogue."""


class ModifiedBundleWarning(UserWarning):
    """An explicit development read used changed fixture bytes."""


@dataclass(frozen=True)
class BundleFinding:
    """Integrity of one fixture: ok, modified, or missing."""

    key: str
    path: Path
    status: str
    expected_hash: str
    actual_hash: str | None
    expected_bytes: int
    actual_bytes: int | None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _relative(value: str, label: str = "path") -> PurePosixPath:
    # Check spelling before PurePath normalizes away '.' and empty components.
    if (
        not isinstance(value, str) or not value or "\\" in value or "\x00" in value
        or PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise BundleError(f"unsafe {label}: {value!r}; expected a relative path")
    return PurePosixPath(value)


def _inside(root: Path, relative: str) -> Path:
    path = root.joinpath(*_relative(relative).parts)
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, RuntimeError):
        raise BundleError(f"path escapes its bundle/source directory: {path}") from None
    return path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _resource(record: dict, dataset: str) -> Resource:
    try:
        name, path, size, digest = record["name"], record["path"], record["bytes"], record["hash"]
    except (KeyError, TypeError):
        raise BundleError(f"incomplete resource metadata for {dataset!r}") from None
    _relative(path, "resource path")
    if not isinstance(name, str) or not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise BundleError(f"invalid resource metadata for {dataset}/{path}")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise BundleError(f"{dataset}/{path} needs its catalogue sha256 hash")
    sidecars = record.get("ethos:sidecars", [])
    if not isinstance(sidecars, list):
        raise BundleError(f"invalid sidecars for {dataset}/{path}")
    for sidecar in sidecars:
        _relative(sidecar, "sidecar path")
    return Resource(dataset, name, path, size, digest, record.get("mediatype", "application/octet-stream"), tuple(sidecars))


def _record(resource: Resource) -> dict:
    record = {
        "name": resource.name, "path": resource.path, "bytes": resource.bytes,
        "hash": resource.hash, "mediatype": resource.mediatype,
    }
    if resource.sidecars:
        record["ethos:sidecars"] = list(resource.sidecars)
    return record


@dataclass
class Bundle:
    """A local snapshot; reads never download, repair, or change the snapshot.

    Construct with load_bundle/export_bundle. Source records the catalogue
    location and supplied revision, if known. Dataset metadata retains licences
    and provenance. Collections contain their exact expanded resource keys.
    """

    path: Path
    source: dict
    datasets: dict
    collections: dict[str, list[str]]
    resources: dict[str, Resource]

    def names(self) -> list[str]:
        return sorted(self.collections)

    def verify(self, collection: str) -> list[BundleFinding]:
        """Hash selected files, reporting missing and changed fixtures.

        Invalid paths, escaping symlinks, and unreadable files are always errors.
        No files change and ambient configuration is never consulted.
        """
        if collection not in self.collections:
            raise BundleError(f"collection {collection!r} is not bundled; available: {', '.join(self.names())}")
        findings = []
        for key in self.collections[collection]:
            resource = self.resources[key]
            path = _inside(self.path, "data/" + key)
            try:
                if not path.is_file():
                    findings.append(BundleFinding(key, path, "missing", resource.hash, None, resource.bytes, None))
                    continue
                size, digest = path.stat().st_size, _digest(path)
            except OSError as error:
                raise BundleError(f"cannot read fixture {key}: {error}") from error
            status = "ok" if size == resource.bytes and digest.lower() == resource.hash.lower() else "modified"
            findings.append(BundleFinding(key, path, status, resource.hash, digest, resource.bytes, size))
        return findings

    def fetch(self, collection: str, *, allow_modified: bool = False) -> DataFiles:
        """Return checked local paths; opt in explicitly for development edits.

        The override permits existing changed files only. It never suppresses
        missing files, adds resources, downloads replacements, or updates hashes.
        """
        findings = self.verify(collection)
        missing = [finding.key for finding in findings if finding.status == "missing"]
        if missing:
            raise BundleError("missing bundled files: " + ", ".join(missing))
        changed = [finding.key for finding in findings if finding.status == "modified"]
        if changed:
            message = "bundled files differ from the catalogue: " + ", ".join(changed)
            if not allow_modified:
                raise BundleError(message + "; allow_modified=True is available for temporary development edits")
            warnings.warn(message + ". Development override active; original hashes are retained.",
                          ModifiedBundleWarning, stacklevel=2)
        return DataFiles((finding.key, finding.path) for finding in findings)


def load_bundle(path: str | Path) -> Bundle:
    """Load local metadata without reading remote locations.

    Accept a directory or its bundle.json. Integrity is checked by fetch/verify;
    metadata and collection/sidecar completeness are checked here.
    """
    path = Path(path).expanduser().absolute()
    root = path.parent if path.name == MANIFEST else path
    manifest = _inside(root, MANIFEST)
    try:
        document = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BundleError(f"cannot read bundle metadata {manifest}: {error}") from error
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise BundleError(f"unsupported or missing bundle format in {manifest}")
    source, datasets, collections = document.get("source"), document.get("datasets"), document.get("collections")
    if not isinstance(source, dict) or not isinstance(source.get("catalog"), str) or not source["catalog"]:
        raise BundleError("bundle metadata needs its source catalogue location")
    if not isinstance(datasets, dict) or not datasets or not isinstance(collections, dict) or not collections:
        raise BundleError("bundle metadata needs datasets and collections")
    resources = {}
    for name, package in datasets.items():
        if len(_relative(name, "dataset name").parts) != 1:
            raise BundleError(f"dataset name must be one path component: {name!r}")
        if not isinstance(package, dict) or not isinstance(package.get("resources"), list):
            raise BundleError(f"missing resource metadata for {name!r}")
        if (package.get("ethos:access", "public") != "public"
                or package.get("ethos:visibility", "public") != "public"
                or package.get("ethos:staged")):
            raise BundleError(f"{name!r} is not a public catalogue snapshot")
        for record in package["resources"]:
            resource = _resource(record, name)
            if resource.key in resources:
                raise BundleError(f"duplicate resource metadata: {resource.key}")
            resources[resource.key] = resource
    for name, keys in collections.items():
        if not isinstance(name, str) or not name or not isinstance(keys, list) or not keys:
            raise BundleError(f"invalid or empty bundled collection: {name!r}")
        if any(not isinstance(key, str) or key not in resources for key in keys):
            raise BundleError(f"collection {name!r} refers to missing resource metadata")
        if len(keys) != len(set(keys)):
            raise BundleError(f"collection {name!r} has duplicate resource keys")
        for key in keys:
            for sidecar in resources[key].sidecars:
                if f"{resources[key].dataset}/{sidecar}" not in keys:
                    raise BundleError(f"collection {name!r} lacks sidecar metadata for {key}: {sidecar}")
    return Bundle(root.resolve(), source, datasets, collections, resources)


def export_bundle(
    collections: str | Path,
    names: str | Sequence[str],
    target: str | Path,
    *,
    catalog: str | Catalog | None = None,
    dataset_roots: Mapping[str, str | Path] | None = None,
    source_revision: str | None = None,
    progressbar: bool = False,
) -> Bundle:
    """Copy selected canonical resources and metadata into a new bundle.

    dataset_roots maps dataset names to existing input fixture directories;
    every byte must match the catalogue. Other files are obtained from the
    catalogue publication URL. Staging and configured roots are ignored.
    The target must not exist; export never replaces an existing bundle.

    source_revision records the caller's pinned catalogue commit or release.
    The exporter does not infer immutability or verify Git references.
    """
    from .maintain.publish import STRIP_FROM_PACKAGE

    target = Path(target).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise BundleError(f"bundle target already exists: {target}; export to a new directory")
    try:
        loaded = load_collections(collections, catalog=catalog, include_staging=False)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise BundleError(f"cannot load collections for bundle export: {error}") from error
    requested = [names] if isinstance(names, str) else list(names)
    if not requested or any(not isinstance(name, str) or not name for name in requested):
        raise BundleError("select at least one named collection")
    unknown = sorted(set(requested) - set(loaded.names()))
    if unknown:
        raise BundleError(f"unknown collections: {', '.join(unknown)}; available: {', '.join(loaded.names())}")
    selected: dict[str, Resource] = {}
    members = {}
    for name in dict.fromkeys(requested):
        try:
            resources = {resource.key: resource for resource in loaded.resolve(name)}
        except (KeyError, OSError, ValueError) as error:
            raise BundleError(f"cannot resolve collection {name!r}: {error}") from error
        pending = list(resources.values())
        while pending:
            resource = pending.pop()
            for sidecar in resource.sidecars:
                companion = loaded.catalog.dataset(resource.dataset).resource_at(sidecar)
                if companion is None:
                    raise BundleError(f"missing catalogue sidecar metadata: {resource.dataset}/{sidecar}")
                if companion.key not in resources:
                    resources[companion.key] = companion
                    pending.append(companion)
        if not resources:
            raise BundleError(f"collection {name!r} selects no resources")
        selected.update(resources)
        members[name] = sorted(resources)

    packages = {}
    for resource in selected.values():
        dataset = loaded.catalog.dataset(resource.dataset)
        if len(_relative(dataset.name, "dataset name").parts) != 1:
            raise BundleError(f"dataset name must be one path component: {dataset.name!r}")
        _resource(_record(resource), dataset.name)
        if dataset.descriptor.get("ethos:staged") or dataset.access == "staging":
            raise BundleError(f"cannot export staged dataset {dataset.name!r}")
        if dataset.access != "public" or dataset.visibility != "public":
            raise BundleError(f"{dataset.name!r} is {dataset.access}/{dataset.visibility}; portable fixture bundles require public data")
        if (dataset.descriptor.get("ethos:access", "public") != "public"
                or dataset.descriptor.get("ethos:visibility", "public") != "public"):
            raise BundleError(f"{dataset.name!r} descriptor is not public")
        if resource.dataset not in packages:
            package = dict(dataset.descriptor)
            for field in ("resources", "ethos:shards", "ethos:shard_depth", *STRIP_FROM_PACKAGE):
                package.pop(field, None)
            package["resources"] = []
            packages[resource.dataset] = package
        record = dataset.resource_descriptor(resource.path) or _record(resource)
        for field in STRIP_FROM_PACKAGE:
            record.pop(field, None)
        packages[resource.dataset]["resources"].append(record)
    for package in packages.values():
        package["resources"].sort(key=lambda record: record["path"])
        package["ethos:file_count"] = len(package["resources"])
        package["ethos:total_bytes"] = sum(record["bytes"] for record in package["resources"])

    source = {
        "catalog": loaded.catalog.location,
        "revision": source_revision,
        "catalog_version": loaded.catalog.descriptor.get("version"),
        "catalog_descriptor_sha256": "sha256:" + hashlib.sha256(
            json.dumps(loaded.catalog.descriptor, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }
    document = {"format": FORMAT, "source": source, "datasets": packages, "collections": members}
    roots = {name: Path(root).expanduser().resolve() for name, root in (dataset_roots or {}).items()}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".ethos-bundle-", dir=target.parent))
    try:
        for key, resource in sorted(selected.items()):
            destination = _inside(temporary, "data/" + key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if resource.dataset in roots:
                origin = _inside(roots[resource.dataset], resource.path)
                if not origin.is_file():
                    raise BundleError(f"missing input fixture {key}: {origin}")
                if origin.stat().st_size != resource.bytes or _digest(origin).lower() != resource.hash.lower():
                    raise BundleError(f"input fixture differs from the catalogue: {key}")
                shutil.copyfile(origin, destination)
            else:
                publication = loaded.catalog.descriptor.get("ethos:publication_url", "").rstrip("/")
                if not publication.startswith(("https://", "http://")):
                    raise BundleError(f"no HTTP(S) publication URL for {key}; supply dataset_roots")
                prefix = loaded.catalog.dataset(resource.dataset).remote_prefix
                _relative(prefix, "remote prefix")
                pooch.retrieve(
                    url=f"{publication}/{prefix}/{resource.path}", known_hash=resource.hash,
                    fname=destination.name, path=destination.parent, progressbar=progressbar,
                )
        # newline as well as encoding: a bundle is committed to the package that
        # ships it, so a manifest written on Windows must not differ from the
        # same manifest written on Linux in every line.
        (temporary / MANIFEST).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
        bundle = load_bundle(temporary)
        for name in members:
            bundle.fetch(name)
        # Exclusive mkdir refuses even an empty existing target directory.
        target.mkdir(exist_ok=False)
        try:
            for child in temporary.iterdir():
                child.rename(target / child.name)
        except BaseException:
            shutil.rmtree(target)
            raise
    except FileExistsError as error:
        raise BundleError(f"bundle target already exists: {target}") from error
    finally:
        shutil.rmtree(temporary)
    return load_bundle(target)
