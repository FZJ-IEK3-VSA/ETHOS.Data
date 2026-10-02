"""Catalogue-verified fixture copies for offline package tests.

dCache remains the published authority. A bundle records selected catalogue
metadata and copies its files under data/<dataset>/<path>. Reads consult only
these files, independently of configuration, staging, CWD, and the network.
An explicit allow_modified development override never changes original hashes.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

import pooch
import yaml

from .catalogs import Catalog, Resource, _join, _read_binary
from .errors import BundleError
from .formats import keys as k
from .formats.derived import resource_url
from .model import digest, names
from .model.resource import checked, to_record
from .retrieval import DataFiles
from .selection import load_collections

__all__ = [
    "Bundle",
    "BundleFinding",
    "ModifiedBundleWarning",
    "export_bundle",
    "load_bundle",
]

MANIFEST = "bundle.json"
FORMAT = "ethos-data-bundle-v1"
#: Where archived licence documents sit, mirroring the published catalogue's
#: own ``datasets/<name>/<document>`` layout so the two are read the same way.
METADATA_DIR = "datasets"


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
    """:func:`ethos_data.model.names.relative`, refusing as a bundle refuses."""
    try:
        return names.relative(value, label)
    except ValueError as error:
        raise BundleError(str(error)) from None


def _inside(root: Path, relative: str) -> Path:
    path = root.joinpath(*_relative(relative).parts)
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, RuntimeError):
        raise BundleError(f"path escapes its bundle/source directory: {path}") from None
    return path


def _distinct_datasets(datasets: Iterable[str]) -> None:
    """Refuse a dataset that lives underneath another dataset.

    A name may contain "/" -- a family member is spelled
    ``reskit-test-data/era5`` -- so ``data/<dataset>/<path>`` locates a file
    unambiguously only while no name is a prefix of another. Were both ``a``
    and ``a/b`` bundled, ``data/a/b/x.tif`` would be the place for two
    different resources, and whichever was copied second would win.

    This is the invariant the old "one path component" rule was really
    protecting. Traversal and spelling are not its business: ``_relative``
    rejects absolute, empty, ``.``, ``..`` and backslash components, and
    ``_inside`` confirms containment afterwards.
    """
    found = names.nested(datasets)
    if found is not None:
        name, ancestor = found
        raise BundleError(
            f"dataset {name!r} lives under dataset {ancestor!r}; "
            "their bundled files would share a path"
        )


def _license_documents(package: Mapping) -> list[str]:
    """The archived licence files a dataset descriptor points at.

    Relative to the descriptor's own directory, which is how
    ``ethos-data catalog publish`` writes them and how it expects to read
    them back.
    """
    documents = []
    for entry in package.get(k.LICENSES, []):
        if not isinstance(entry, Mapping):
            raise BundleError("invalid licences entry")
        document = entry.get(k.DOCUMENT)
        if not document:
            continue
        if not isinstance(document, str):
            raise BundleError(f"invalid {k.DOCUMENT}: {document!r}")
        _relative(document, "licence document")
        documents.append(document)
    return documents


def _collect_documents(dataset, package: Mapping, catalog_location: str) -> dict:
    """Read a dataset's archived licences, checking each against its hash.

    Keyed by the path the bundle stores them at. The descriptor records a
    ``ethos:document_sha256`` for exactly this: a licence fetched over the
    network is only the licence if it still hashes to what the catalogue
    signed off, and a bundle is where that check has to happen, because
    afterwards nobody is online to repeat it.
    """
    wanted = _license_documents(package)
    if not wanted:
        return {}
    try:
        descriptor_location = _join(dataset.base, dataset.entry[k.PATH])
    except (KeyError, TypeError) as error:
        raise BundleError(
            f"cannot locate the descriptor of {dataset.name!r} to read its licences"
        ) from error
    base = descriptor_location.rsplit("/", 1)[0] + "/"
    expected = {
        entry[k.DOCUMENT]: entry.get(k.DOCUMENT_SHA256)
        for entry in package.get(k.LICENSES, [])
        if entry.get(k.DOCUMENT)
    }
    collected = {}
    for document in wanted:
        location = _join(base, document)
        try:
            raw = _read_binary(location)
        except OSError as error:
            raise BundleError(
                f"cannot read the licence document {document!r} of "
                f"{dataset.name!r} at {location} (catalogue {catalog_location}): {error}"
            ) from error
        declared = expected.get(document)
        if declared is not None:
            if not isinstance(declared, str):
                raise BundleError(
                    f"invalid {k.DOCUMENT_SHA256} for {dataset.name!r}: {declared!r}"
                )
            if not digest.matches(declared, digest.of_bytes(raw)):
                raise BundleError(
                    f"licence document {document!r} of {dataset.name!r} does not "
                    f"match its catalogued hash"
                )
        collected[f"{METADATA_DIR}/{dataset.name}/{document}"] = raw
    return collected


def _resource(record: dict, dataset: str) -> Resource:
    """:func:`ethos_data.model.resource.checked`, refusing as a bundle refuses."""
    try:
        return checked(dataset, record)
    except ValueError as error:
        raise BundleError(str(error)) from None


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
            raise BundleError(
                f"collection {collection!r} is not bundled; available: {', '.join(self.names())}"
            )
        findings = []
        for key in self.collections[collection]:
            resource = self.resources[key]
            path = _inside(self.path, "data/" + key)
            try:
                if not path.is_file():
                    findings.append(
                        BundleFinding(
                            key,
                            path,
                            "missing",
                            resource.hash,
                            None,
                            resource.bytes,
                            None,
                        )
                    )
                    continue
                size, actual = path.stat().st_size, digest.of_file(path)
            except OSError as error:
                raise BundleError(f"cannot read fixture {key}: {error}") from error
            status = (
                "ok"
                if size == resource.bytes and digest.matches(resource.hash, actual)
                else "modified"
            )
            findings.append(
                BundleFinding(
                    key,
                    path,
                    status,
                    resource.hash,
                    digest.recorded(actual),
                    resource.bytes,
                    size,
                )
            )
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
                raise BundleError(
                    message
                    + "; allow_modified=True is available for temporary development edits"
                )
            warnings.warn(
                message
                + ". Development override active; original hashes are retained.",
                ModifiedBundleWarning,
                stacklevel=2,
            )
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
    source, datasets, collections = (
        document.get("source"),
        document.get("datasets"),
        document.get("collections"),
    )
    if (
        not isinstance(source, dict)
        or not isinstance(source.get("catalog"), str)
        or not source["catalog"]
    ):
        raise BundleError("bundle metadata needs its source catalogue location")
    if (
        not isinstance(datasets, dict)
        or not datasets
        or not isinstance(collections, dict)
        or not collections
    ):
        raise BundleError("bundle metadata needs datasets and collections")
    resources = {}
    for name, package in datasets.items():
        _relative(name, "dataset name")
        if not isinstance(package, dict) or not isinstance(
            package.get(k.RESOURCES), list
        ):
            raise BundleError(f"missing resource metadata for {name!r}")
        if (
            package.get(k.ACCESS, k.PUBLIC) != k.PUBLIC
            or package.get(k.VISIBILITY, k.PUBLIC) != k.PUBLIC
            or package.get(k.STAGED)
        ):
            raise BundleError(f"{name!r} is not a public catalogue snapshot")
        for record in package[k.RESOURCES]:
            resource = _resource(record, name)
            if resource.key in resources:
                raise BundleError(f"duplicate resource metadata: {resource.key}")
            resources[resource.key] = resource
    _distinct_datasets(datasets)
    # An archived licence that did not travel is a licence the reader cannot
    # honour, so a bundle missing one is incomplete rather than merely thinner.
    for name, package in datasets.items():
        for document in _license_documents(package):
            if not _inside(root, f"{METADATA_DIR}/{name}/{document}").is_file():
                raise BundleError(
                    f"bundle lacks the licence document {document!r} for {name!r}"
                )
    for name, keys in collections.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(keys, list)
            or not keys
        ):
            raise BundleError(f"invalid or empty bundled collection: {name!r}")
        if any(not isinstance(key, str) or key not in resources for key in keys):
            raise BundleError(
                f"collection {name!r} refers to missing resource metadata"
            )
        if len(keys) != len(set(keys)):
            raise BundleError(f"collection {name!r} has duplicate resource keys")
        for key in keys:
            for sidecar in resources[key].sidecars:
                if f"{resources[key].dataset}/{sidecar}" not in keys:
                    raise BundleError(
                        f"collection {name!r} lacks sidecar metadata for {key}: {sidecar}"
                    )
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
    from .formats.dataset import STRIPPED as STRIP_FROM_PACKAGE

    target = Path(target).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise BundleError(
            f"bundle target already exists: {target}; export to a new directory"
        )
    try:
        loaded = load_collections(collections, catalog=catalog, include_staging=False)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise BundleError(
            f"cannot load collections for bundle export: {error}"
        ) from error
    requested = [names] if isinstance(names, str) else list(names)
    if not requested or any(
        not isinstance(name, str) or not name for name in requested
    ):
        raise BundleError("select at least one named collection")
    unknown = sorted(set(requested) - set(loaded.names()))
    if unknown:
        raise BundleError(
            f"unknown collections: {', '.join(unknown)}; available: {', '.join(loaded.names())}"
        )
    selected: dict[str, Resource] = {}
    members = {}
    for name in dict.fromkeys(requested):
        try:
            resources = {resource.key: resource for resource in loaded.resolve(name)}
        except (KeyError, OSError, ValueError) as error:
            raise BundleError(f"cannot resolve collection {name!r}: {error}") from error
        # Every sidecar, and theirs: a bundle is read offline, so a companion
        # left behind here cannot be fetched later.
        resources, missing = loaded.catalog.with_sidecars(list(resources.values()))
        if missing:
            raise BundleError(f"missing catalogue sidecar metadata: {missing[0]}")
        if not resources:
            raise BundleError(f"collection {name!r} selects no resources")
        selected.update(resources)
        members[name] = sorted(resources)

    packages = {}
    documents: dict[str, bytes] = {}
    for resource in selected.values():
        dataset = loaded.catalog.dataset(resource.dataset)
        _relative(dataset.name, "dataset name")
        _resource(to_record(resource), dataset.name)
        if dataset.descriptor.get(k.STAGED) or dataset.access == k.STAGING:
            raise BundleError(f"cannot export staged dataset {dataset.name!r}")
        if dataset.access != k.PUBLIC or dataset.visibility != k.PUBLIC:
            raise BundleError(
                f"{dataset.name!r} is {dataset.access}/{dataset.visibility}; portable fixture bundles require public data"
            )
        if (
            dataset.descriptor.get(k.ACCESS, k.PUBLIC) != k.PUBLIC
            or dataset.descriptor.get(k.VISIBILITY, k.PUBLIC) != k.PUBLIC
        ):
            raise BundleError(f"{dataset.name!r} descriptor is not public")
        if resource.dataset not in packages:
            package = dict(dataset.descriptor)
            for field in (k.RESOURCES, k.SHARDS, k.SHARD_DEPTH, *STRIP_FROM_PACKAGE):
                package.pop(field, None)
            package[k.RESOURCES] = []
            packages[resource.dataset] = package
            documents.update(
                _collect_documents(dataset, package, loaded.catalog.location)
            )
        record = dataset.resource_descriptor(resource.path) or to_record(resource)
        for field in STRIP_FROM_PACKAGE:
            record.pop(field, None)
        packages[resource.dataset][k.RESOURCES].append(record)
    _distinct_datasets(packages)
    for package in packages.values():
        package[k.RESOURCES].sort(key=lambda record: record[k.PATH])
        package[k.FILE_COUNT] = len(package[k.RESOURCES])
        package[k.TOTAL_BYTES] = sum(record[k.BYTES] for record in package[k.RESOURCES])

    source = {
        "catalog": loaded.catalog.location,
        "revision": source_revision,
        "catalog_version": loaded.catalog.descriptor.get("version"),
        "catalog_descriptor_sha256": digest.recorded(
            digest.of_bytes(
                json.dumps(loaded.catalog.descriptor, sort_keys=True).encode("utf-8")
            )
        ),
    }
    document = {
        "format": FORMAT,
        "source": source,
        "datasets": packages,
        "collections": members,
    }
    roots = {
        name: Path(root).expanduser().resolve()
        for name, root in (dataset_roots or {}).items()
    }
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
                if origin.stat().st_size != resource.bytes or not digest.matches(
                    resource.hash, digest.of_file(origin)
                ):
                    raise BundleError(
                        f"input fixture differs from the catalogue: {key}"
                    )
                shutil.copyfile(origin, destination)
            else:
                # From the URL the catalogue itself declares, never this
                # machine's override: a bundle is a copy of the authoritative
                # publication, whoever exports it.
                publication = loaded.catalog.descriptor.get(k.PUBLICATION_URL, "")
                if not publication.startswith(("https://", "http://")):
                    raise BundleError(
                        f"no HTTP(S) publication URL for {key}; supply dataset_roots"
                    )
                prefix = loaded.catalog.dataset(resource.dataset).remote_prefix
                _relative(prefix, "remote prefix")
                pooch.retrieve(
                    url=resource_url(publication, prefix, resource.path),
                    known_hash=resource.hash,
                    fname=destination.name,
                    path=destination.parent,
                    progressbar=progressbar,
                )
        for relative, raw in sorted(documents.items()):
            destination = _inside(temporary, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        # newline as well as encoding: a bundle is committed to the package that
        # ships it, so a manifest written on Windows must not differ from the
        # same manifest written on Linux in every line.
        (temporary / MANIFEST).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
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
