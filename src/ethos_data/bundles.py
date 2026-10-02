"""Test data a package keeps in its repository: bundles.

A bundle holds a family of datasets' files under ``data/<dataset>/<path>``,
their inventory in ``bundle.json`` and their descriptions under
``datasets/<dataset>/``. Two kinds:

* A **repository bundle** is the source of truth for its family. ``bundle
  create`` inventories files a package maintainer put there, ``bundle update``
  records each change, and its version counts the changes the catalogue has
  to publish; ``catalog add-bundle`` takes a version into the catalogue.
* An **exported bundle** is a copy of what the catalogue publishes, with the
  collections it was exported for.

A package lists its bundles in its handle (``bundles=``), and reads then go
to them first: their files are hash-checked once per process, a missing or
altered one is an error and never a reason to download, and a version no
catalogue release holds yet is read with a warning. Reads consult only the
files, independently of configuration, staging, CWD, and the network. An
explicit allow_modified development override never changes original hashes.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

import yaml

from . import report
from .catalogs import Catalog
from .errors import BundleError, CatalogUnavailable, IncompleteCatalog
from .formats import keys as k
from .formats.derived import license_status_of, remote_prefix_of, resource_url
from .model import digest, names
from .model.inventory import Inventory
from .model.resource import Resource, checked, to_record
from .retrieval import DataFiles
from .selection import load_collections

__all__ = [
    "Bundle",
    "BundleFinding",
    "BundleUpdate",
    "ModifiedBundleWarning",
    "UnpublishedBundleWarning",
    "create_bundle",
    "export_bundle",
    "load_bundle",
    "update_bundle",
    "with_bundles",
]

MANIFEST = "bundle.json"
FORMAT = "ethos-data-bundle-v1"
#: A repository bundle's manifest.
REPOSITORY_FORMAT = "ethos-data-bundle-v2"
#: Where a bundle keeps its files: ``data/<dataset>/<path>``.
DATA_DIR = "data"
#: Where archived licence documents sit, mirroring the published catalogue's
#: own ``datasets/<name>/<document>`` layout so the two are read the same way.
METADATA_DIR = "datasets"


class ModifiedBundleWarning(UserWarning):
    """An explicit development read used changed fixture bytes."""


class UnpublishedBundleWarning(UserWarning):
    """A bundle version is read that no catalogue release holds yet."""


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
    expected = {
        entry[k.DOCUMENT]: entry.get(k.DOCUMENT_SHA256)
        for entry in package.get(k.LICENSES, [])
        if entry.get(k.DOCUMENT)
    }
    collected = {}
    for document in wanted:
        try:
            raw = dataset.inventory.read_part(document)
        except (IncompleteCatalog, CatalogUnavailable) as error:
            raise BundleError(
                f"cannot read the licence document {document!r} of "
                f"{dataset.name!r} (catalogue {catalog_location}): {error.message}"
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
    #: Each bundled dataset's inventory, read by the one inventory reader.
    inventories: dict[str, Inventory]

    def names(self) -> list[str]:
        return sorted(self.collections)

    def file(self, key: str) -> Path:
        """Where the bundle keeps the file ``key``."""
        return _inside(self.path, f"{DATA_DIR}/{key}")

    def dataset(self, name: str) -> Dataset:
        """One of the bundle's datasets as a catalogue entry: what a read sees first."""
        package = self.datasets[name]
        records = package[k.RESOURCES]
        meta = {key: value for key, value in package.items() if key != k.RESOURCES}
        entry = {
            k.NAME: name,
            k.TITLE: meta.get(k.TITLE) or name,
            k.ACCESS: meta.get(k.ACCESS, k.PUBLIC),
            k.VISIBILITY: meta.get(k.VISIBILITY, k.PUBLIC),
            k.TOTAL_BYTES: sum(record[k.BYTES] for record in records),
            k.FILE_COUNT: len(records),
            k.REMOTE_PREFIX: remote_prefix_of({**meta, k.NAME: name}),
            k.LICENSE_STATUS: license_status_of(meta),
        }
        return Dataset(
            name,
            entry[k.TITLE],
            entry=entry,
            _descriptor={**meta, k.NAME: name, k.RESOURCES: records},
            _resources={
                resource.path: resource
                for resource in self.resources.values()
                if resource.dataset == name
            },
        )

    def verify(self, collection: str | None = None) -> list[BundleFinding]:
        """Hash the files, reporting missing and changed fixtures.

        ``collection`` narrows an exported bundle to one of its collections;
        without it every file is hashed. Invalid paths, escaping symlinks, and
        unreadable files are always errors. No files change and ambient
        configuration is never consulted.
        """
        if collection is None:
            selected = sorted(self.resources)
        elif collection not in self.collections:
            raise BundleError(
                f"collection {collection!r} is not bundled; available: "
                f"{', '.join(self.names()) or 'none, read every file without one'}"
            )
        else:
            selected = self.collections[collection]
        findings = []
        for key in selected:
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

    def fetch(
        self, collection: str | None = None, *, allow_modified: bool = False
    ) -> DataFiles:
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
            report.warning(
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
    if isinstance(document, dict) and document.get("format") == REPOSITORY_FORMAT:
        return _load_repository(root, document)
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
    inventories = {}
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
            # Committed to a repository, so checked before it is trusted.
            resource = _resource(record, name)
            if resource.key in resources:
                raise BundleError(f"duplicate resource metadata: {resource.key}")
            resources[resource.key] = resource
        inventories[name] = Inventory.from_records(name, package)
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
    return Bundle(root.resolve(), source, datasets, collections, resources, inventories)


def _description(root: Path, name: str) -> dict:
    """A repository bundle member's ``dataset.yaml``, without its ``source_dir``."""
    path = _inside(root, f"{METADATA_DIR}/{name}/dataset.yaml")
    if not path.is_file():
        raise BundleError(
            f"the bundle at {root} has no description of {name!r}; write "
            f"{METADATA_DIR}/{name}/dataset.yaml, or run `bundle update` to draft one"
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise BundleError(f"{path} is not valid YAML: {error}") from None
    if not isinstance(document, dict):
        raise BundleError(f"{path} must hold keys and their values")
    document.pop(k.SOURCE_DIR, None)
    return document


def _load_repository(root: Path, document: dict) -> Bundle:
    """A repository bundle, its descriptions read and its inventory checked."""
    family, version, release = (
        document.get("family"),
        document.get("version", 1),
        document.get("release"),
    )
    if not isinstance(family, str) or not family or "/" in family:
        raise BundleError("a repository bundle names its family, one path segment")
    _relative(family, "family name")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise BundleError(f"a bundle version is a whole number from 1, got {version!r}")
    if release is not None and not isinstance(release, str):
        raise BundleError(
            f"a bundle release names a catalogue release, got {release!r}"
        )
    datasets = document.get("datasets")
    if not isinstance(datasets, dict) or not datasets:
        raise BundleError("bundle metadata needs its datasets")
    packages, resources = {}, {}
    for name, entry in datasets.items():
        _relative(name, "dataset name")
        if name == family or not names.within(name, family):
            raise BundleError(f"{name!r} is not a member of the family {family!r}")
        records = entry.get(k.RESOURCES) if isinstance(entry, dict) else None
        if not isinstance(records, list):
            raise BundleError(f"missing resource metadata for {name!r}")
        for record in records:
            resource = _resource(record, name)
            if resource.key in resources:
                raise BundleError(f"duplicate resource metadata: {resource.key}")
            resources[resource.key] = resource
        description = _description(root, name)
        for document_path in _license_documents(description):
            if not _inside(root, f"{METADATA_DIR}/{name}/{document_path}").is_file():
                raise BundleError(
                    f"bundle lacks the licence document {document_path!r} for {name!r}"
                )
        packages[name] = {**description, k.RESOURCES: records}
    _distinct_datasets(packages)
    return Bundle(root.resolve(), {}, packages, {}, resources, family, version, release)


def _inventory(root: Path, family: str) -> dict[str, list[dict]]:
    """Every member's files under ``data/<family>/<member>/``, as inventory records."""
    from .maintain.manifest import build_resource, iter_data_files

    base = root / DATA_DIR / family
    if not base.is_dir():
        raise BundleError(
            f"no {DATA_DIR}/{family}/ in {root}: put each member's files in "
            f"{DATA_DIR}/{family}/<member>/"
        )
    loose = sorted(p.name for p in base.iterdir() if p.is_file())
    if loose:
        raise BundleError(
            f"{', '.join(loose)} lie directly in {DATA_DIR}/{family}/, in no member; "
            f"move them into {DATA_DIR}/{family}/<member>/"
        )
    found = {}
    for member in sorted(p for p in base.iterdir() if p.is_dir()):
        files = list(iter_data_files(member))
        if files:
            found[f"{family}/{member.name}"] = [
                build_resource(path, member, path.stat().st_size, digest.of_file(path))
                for path in files
            ]
    return found


def _draft(root: Path, name: str, template: str, **values: str) -> bool:
    """Write a description draft for ``name`` unless one is there; whether one was written."""
    from .formats import registry

    target = _inside(root, f"{METADATA_DIR}/{name}/dataset.yaml")
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(registry.template(template, name=name, **values).encode("utf-8"))
    return True


def _draft_member(root: Path, name: str) -> bool:
    depth = "/".join([".."] * (len(PurePosixPath(name).parts) + 1))
    return _draft(
        root,
        name,
        "dataset-bundled",
        source_dir=f"{depth}/{DATA_DIR}/{name}",
        description="What these files are, and what they are for.",
    )


def _write_manifest(
    root: Path, family: str, version: int, release: str | None, datasets: dict
) -> None:
    document = {
        "format": REPOSITORY_FORMAT,
        "family": family,
        "version": version,
        "release": release,
        "datasets": {
            name: {k.RESOURCES: records} for name, records in sorted(datasets.items())
        },
    }
    (root / MANIFEST).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def create_bundle(directory: str | Path, family: str) -> Bundle:
    """Start a repository bundle from the files under ``directory/data/<family>/``.

    Every directory below ``data/<family>/`` is a member dataset, named
    ``<family>/<member>``. Hashes every file, writes ``bundle.json`` as version
    1, not yet published, and drafts a ``dataset.yaml`` for the family and for
    each member that has none yet. Refuses a directory that is a bundle already.
    """
    root = Path(directory).expanduser().absolute()
    if (root / MANIFEST).exists():
        raise BundleError(
            f"{root} is a bundle already; record changes with `bundle update`"
        )
    if not isinstance(family, str) or not family or "/" in family:
        raise BundleError(
            "a family name is one path segment, such as my-tool-test-data"
        )
    _relative(family, "family name")
    datasets = _inventory(root, family)
    if not datasets:
        raise BundleError(
            f"no files under {root / DATA_DIR / family}: put each member's files "
            f"in {DATA_DIR}/{family}/<member>/"
        )
    _draft(root, family, "family", title=f"Test data of {family}")
    for name in datasets:
        _draft_member(root, name)
    _write_manifest(root, family, 1, None, datasets)
    return load_bundle(root)


@dataclass(frozen=True)
class BundleUpdate:
    """What ``bundle update`` found and did."""

    bundle: Bundle
    previous_version: int
    changed: dict[str, list[str]] = field(default_factory=dict)
    added: dict[str, list[str]] = field(default_factory=dict)
    removed: dict[str, list[str]] = field(default_factory=dict)
    moved: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    new_members: list[str] = field(default_factory=list)
    gone_members: list[str] = field(default_factory=list)
    #: The release this update recorded, when it found one.
    released: str | None = None

    @property
    def changes(self) -> bool:
        return bool(
            self.changed or self.added or self.removed or self.moved
            or self.new_members or self.gone_members
        )  # fmt: skip


def _published_in(catalog: Catalog, inventory: dict[str, list[dict]]) -> bool:
    """Whether ``catalog`` holds every member with the same files, byte for byte."""
    for name, records in inventory.items():
        dataset = catalog.datasets.get(name)
        if dataset is None:
            return False
        held = {r.path: digest.expected(r.hash) for r in dataset.resources.values()}
        if held != {r[k.PATH]: digest.expected(r[k.HASH]) for r in records}:
            return False
    return True


def update_bundle(
    directory: str | Path, catalog: Catalog | None = None
) -> BundleUpdate:
    """Record the changes to a repository bundle's files; its next version if published.

    Files added, changed, moved or removed, and members new or gone, are
    recorded. A version a release already holds is never changed: the first
    change after it starts the next version, which waits for its own release.
    ``catalog``, the catalogue the package reads, is asked when nothing changed
    whether a release holds the current version, which is then recorded.
    """
    bundle = load_bundle(directory)
    if not bundle.repository:
        raise BundleError(
            f"{bundle.path} is a copy exported from the catalogue; export it again "
            "rather than update it"
        )
    now = _inventory(bundle.path, bundle.family)
    before = {
        name: {record[k.PATH]: record for record in package[k.RESOURCES]}
        for name, package in bundle.datasets.items()
    }
    changed, added, removed, moved = {}, {}, {}, {}
    for name in sorted(set(now) & set(before)):
        after = {record[k.PATH]: record for record in now[name]}
        old = before[name]
        gone = sorted(set(old) - set(after))
        new = sorted(set(after) - set(old))
        pairs = []
        for path in list(gone):
            match = next(
                (n for n in new if after[n][k.HASH] == old[path][k.HASH]), None
            )
            if match is not None:
                pairs.append((path, match))
                gone.remove(path)
                new.remove(match)
        differ = sorted(
            path
            for path in set(after) & set(old)
            if after[path][k.HASH] != old[path][k.HASH]
        )
        for found, value in (
            (changed, differ),
            (added, new),
            (removed, gone),
            (moved, pairs),
        ):
            if value:
                found[name] = value
    new_members = sorted(set(now) - set(before))
    gone_members = sorted(set(before) - set(now))
    result = BundleUpdate(
        bundle,
        bundle.version,
        changed,
        added,
        removed,
        moved,
        new_members,
        gone_members,
    )
    if result.changes:
        version = bundle.version + 1 if bundle.published else bundle.version
        for name in new_members:
            _draft_member(bundle.path, name)
        _write_manifest(bundle.path, bundle.family, version, None, now)
        return dataclasses.replace(result, bundle=load_bundle(bundle.path))
    if not bundle.published and catalog is not None and _published_in(catalog, now):
        release = catalog.version or "published"
        _write_manifest(bundle.path, bundle.family, bundle.version, release, now)
        return dataclasses.replace(
            result, bundle=load_bundle(bundle.path), released=release
        )
    return result


def with_bundles(catalog: Catalog, bundles: Sequence[Bundle]) -> Catalog:
    """``catalog`` with the bundles' datasets in place of its own: read first.

    The repository is the source of truth for what a bundle holds, so a
    bundled dataset replaces the catalogue's entry of the same name, and a
    member no release holds yet is added. The view remembers the bundles,
    which the lookup chain reads the files from.
    """
    if not bundles:
        return catalog
    datasets = dict(catalog.datasets)
    for bundle in bundles:
        for name in bundle.datasets:
            datasets[name] = bundle.dataset(name)
        if bundle.repository and bundle.family not in datasets:
            members = [bundle.dataset(name) for name in bundle.datasets]
            datasets[bundle.family] = Dataset(
                bundle.family,
                bundle.family,
                entry={
                    k.NAME: bundle.family,
                    k.TITLE: bundle.family,
                    k.NAMESPACE: True,
                    k.TOTAL_BYTES: sum(m.total_bytes for m in members),
                    k.FILE_COUNT: sum(m.file_count for m in members),
                },
                _descriptor={k.NAME: bundle.family, k.NAMESPACE: True},
            )
    return dataclasses.replace(
        catalog, datasets=datasets, bundles=(*catalog.bundles, *bundles)
    )


#: (path, size, mtime) of every bundled file already hashed in this process.
_CHECKED: dict[tuple[str, int, int], bool] = {}
#: Bundles this process has warned about as not in the catalogue yet.
_WARNED: set[str] = set()


def checked_file(bundle: Bundle, resource: Resource) -> str:
    """Why the bundle's copy of ``resource`` cannot be read; "" when it can.

    Hashed once per process: a test suite that reads the same fixture in a
    hundred tests pays for it once, and a file edited meanwhile is hashed again.
    """
    path = bundle.file(resource.key)
    try:
        stat = path.stat()
    except OSError:
        return "the file is missing"
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    ok = _CHECKED.get(key)
    if ok is None:
        ok = stat.st_size == resource.bytes and digest.matches(
            resource.hash, digest.of_file(path)
        )
        _CHECKED[key] = ok
    return "" if ok else "it differs from the size or hash the bundle records"


def warn_if_unpublished(bundle: Bundle) -> None:
    """Warn, once per process, that a bundle version is not in the catalogue yet."""
    if bundle.published or str(bundle.path) in _WARNED:
        return
    _WARNED.add(str(bundle.path))
    warnings.warn(
        f"{bundle.path} version {bundle.version} is not in the catalogue yet; "
        "propose it so it can be published.",
        UnpublishedBundleWarning,
        stacklevel=6,
    )


def export_bundle(
    collections: str | Path,
    names: str | Sequence[str],
    target: str | Path,
    *,
    catalog: str | Catalog | None = None,
    dataset_roots: Mapping[str, str | Path] | None = None,
    source_revision: str | None = None,
    progressbar: bool = False,
    downloader: Downloader | None = None,
) -> Bundle:
    """Copy selected canonical resources and metadata into a new bundle.

    dataset_roots maps dataset names to existing input fixture directories;
    every byte must match the catalogue. Other files are obtained from the
    catalogue publication URL. Staging and configured roots are ignored.
    The target must not exist; export never replaces an existing bundle.

    source_revision records the catalogue release or commit the caller read.
    The exporter does not infer immutability or verify Git references.
    ``downloader`` fetches the files from the publication URL, hash-checked;
    pooch by default.
    """
    from .adapters.downloads import PoochDownloader
    from .formats.dataset import STRIPPED as STRIP_FROM_PACKAGE

    downloader = downloader if downloader is not None else PoochDownloader()

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
        record = dataset.inventory.record(resource.path) or to_record(resource)
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
                dataset = loaded.catalog.dataset(resource.dataset)
                _relative(dataset.remote_prefix, "remote prefix")
                from .formats.derived import object_folder

                downloader.fetch(
                    resource_url(
                        publication,
                        object_folder(dataset.remote_prefix, resource.revision),
                    ),
                    _inside(temporary, f"{DATA_DIR}/{resource.dataset}"),
                    {resource.path: resource.hash},
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
