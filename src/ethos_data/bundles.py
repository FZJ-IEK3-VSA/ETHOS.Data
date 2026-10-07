"""Data a package keeps in its repository: bundles.

    BUNDLES = (Path(__file__).with_name("test_data"),)
    data = ethos_data.collections(COLLECTIONS, tool="mytool", bundles=BUNDLES)

A bundle is a directory in a repository. It holds the files of a selection of
catalogue datasets under ``data/<dataset>/<path>``, each dataset's
description and licence documents under ``datasets/<dataset>/``, and
``bundle.json``: for each dataset its alignment with the catalogue, whether
it holds every file or a selection, the changes recorded since the
alignment, and every file's size and SHA-256 (see
:mod:`ethos_data.formats.bundle`). It holds public, visible data with settled
licensing only, because a repository distributes it.

A package's handle reads what its bundles hold first, hash-checked once per
process: a missing file, or a change ``bundle update`` has not recorded, is an
error and never a reason to download. A bundle is authoritative for its
package, so it is read even when it is ahead of the catalogue: when it holds
recorded changes, or a dataset the catalogue does not describe. Every
process that reads one of its datasets is warned once per bundle, with
:class:`BundleAlignmentWarning`, until the bundle is realigned: towards the
catalogue by a proposal and ``catalog add-bundle``, or from it by ``bundle
update --from-catalog``. Where the handle reads the catalogue index anyway,
a bundle behind the catalogue, or holding a dataset it withdrew, warns the
same way.

``bundle create`` starts a bundle from data directories, ``bundle update``
records its changes and its alignment, and ``bundle export`` writes a new
bundle of what a package reads, for another repository.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import yaml

from . import report
from .catalogs import Catalog, Dataset
from .errors import (
    BundleError,
    CatalogUnavailable,
    EthosDataError,
    IncompleteCatalog,
)
from .formats import keys as k
from .formats.derived import license_settled, license_status_of, remote_prefix_of
from .model import digest, names
from .model.inventory import Inventory
from .model.resource import Resource, checked, to_record
from .retrieval import DataFiles

if TYPE_CHECKING:
    from .formats.bundle import BundledDataset, BundleManifest
    from .selection import Collections

__all__ = [
    "Bundle",
    "BundleAlignmentWarning",
    "BundleCreated",
    "BundleFinding",
    "BundleUpdate",
    "ModifiedBundleWarning",
    "create_bundle",
    "export_bundle",
    "load_bundle",
    "update_bundle",
    "with_bundles",
]

MANIFEST = k.BUNDLE_FILE
DATA_DIR = k.BUNDLE_DATA_DIR
DESCRIPTIONS_DIR = k.BUNDLE_DESCRIPTIONS_DIR

#: The keys of a published descriptor that the build generates, and a bundled
#: description therefore does not state.
_GENERATED = (
    k.SCHEMA,
    k.RESOURCES,
    k.SHARDS,
    k.SHARD_DEPTH,
    k.TOTAL_BYTES,
    k.FILE_COUNT,
    k.NAMESPACE,
    k.REVISION,
    k.SUPERSEDED_BY,
)


class ModifiedBundleWarning(UserWarning):
    """A test read bundled files changed without ``bundle update`` recording it."""


class BundleAlignmentWarning(UserWarning):
    """A bundle is ahead of the catalogue, or behind it: realign it soon.

    Its own category, so a package can filter it, and keep it a warning in a
    test run that turns warnings into errors.
    """


@dataclass(frozen=True)
class BundleFinding:
    """One bundled file, checked: ``ok``, ``modified``, ``missing`` or ``unrecorded``."""

    key: str
    path: Path
    status: str
    expected_hash: str | None
    actual_hash: str | None
    expected_bytes: int | None
    actual_bytes: int | None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# -- paths ------------------------------------------------------------------------


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
        raise BundleError(f"path escapes its bundle directory: {path}") from None
    return path


def _distinct_datasets(datasets: Iterable[str]) -> None:
    """Refuse a dataset that lives underneath another dataset.

    A name may contain "/" -- a family member is spelled ``family/member`` --
    so ``data/<dataset>/<path>`` locates a file unambiguously only while no
    name is a prefix of another.
    """
    found = names.nested(datasets)
    if found is not None:
        name, ancestor = found
        raise BundleError(
            f"dataset {name!r} lives under dataset {ancestor!r}; "
            "their bundled files would share a path"
        )


def _record(path: Path, relative: str) -> dict:
    """A document's record: its path, size and SHA-256."""
    return {
        k.PATH: relative,
        k.BYTES: path.stat().st_size,
        k.HASH: digest.recorded(digest.of_file(path)),
    }


def _write_json(path: Path, document: Mapping) -> None:
    # newline as well as encoding: a bundle is committed, so a manifest written
    # on Windows must not differ in every line from the same one on Linux.
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _checked_manifest(document: object, where: Path) -> BundleManifest:
    """``bundle.json`` read through its model, or BundleError naming every problem."""
    from pydantic import ValidationError

    from .formats.bundle import BundleManifest
    from .formats.fields import describe

    try:
        return BundleManifest.model_validate(document)
    except ValidationError as error:
        problems = "".join(f"\n  {line}" for line in describe(error))
        raise BundleError(
            f"{where} is not a valid bundle manifest:{problems}"
        ) from None


def _manifest_document(manifest: BundleManifest) -> dict:
    return manifest.model_dump(mode="json", by_alias=True, exclude_defaults=False)


# -- descriptions -----------------------------------------------------------------


def _read_description(root: Path, name: str) -> dict:
    """The ``dataset.yaml`` a bundle keeps for ``name``, as written."""
    path = _inside(root, f"{DESCRIPTIONS_DIR}/{name}/{k.DESCRIPTION_FILE}")
    if not path.is_file():
        raise BundleError(
            f"{root} has no description of {name!r}: write "
            f"{DESCRIPTIONS_DIR}/{name}/{k.DESCRIPTION_FILE}"
        )
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise BundleError(f"{path} is not valid YAML: {error}") from None
    if not isinstance(document, dict):
        raise BundleError(f"{path} must hold keys and their values")
    return document


def _license_documents(meta: Mapping) -> list[str]:
    """The licence documents a description names, relative to its directory."""
    documents = []
    for entry in meta.get(k.LICENSES) or []:
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


def _refusal(name: str, meta: Mapping) -> str:
    """What keeps ``name`` out of a bundle: data that is not public, or unsettled terms."""
    access = meta.get(k.ACCESS, k.PUBLIC)
    visibility = meta.get(k.VISIBILITY, k.PUBLIC)
    if access != k.PUBLIC:
        return (
            f"{name} is {access}: a bundle holds public data only, because a "
            "repository passes its files on to everyone who clones it"
        )
    if visibility != k.PUBLIC:
        return (
            f"{name} is {visibility}: a bundle holds data the public catalogue "
            "lists only, because a repository passes it on"
        )
    if not license_settled(dict(meta)):
        return (
            f"{name}: its licensing is not settled, and a repository passes its "
            "files on. Record its terms in its dataset.yaml, a `licenses:` entry "
            "or `ethos:license_status: resolved`; develop it in staging meanwhile"
        )
    return ""


def description_of(descriptor: Mapping) -> dict:
    """The description a bundle keeps for a catalogue dataset: its descriptor's own keys."""
    from .formats.dataset import STRIPPED

    return {
        key: value
        for key, value in descriptor.items()
        if key not in _GENERATED and key not in STRIPPED
    }


def _comparable(meta: Mapping) -> dict:
    """The keys of a description two copies of one dataset must agree on.

    Every key the description publishes, contributors and provenance as much
    as the title, the defaults filled in, so a description that leaves out
    ``ethos:access: public`` agrees with one that states it.
    """
    from .formats.dataset import apply_defaults

    return apply_defaults(description_of(meta))


def _inheriting(root: Path, name: str, families: Iterable[str]) -> dict:
    """The description a bundle keeps for ``name``, its families' inherited keys applied."""
    from .formats.dataset import INHERITED

    meta = {}
    for family in names.ancestors(name):
        if family in families:
            meta.update(
                {
                    key: value
                    for key, value in _read_description(root, family).items()
                    if key in INHERITED
                }
            )
    meta.update(_read_description(root, name))
    meta[k.NAME] = name
    return meta


# -- a bundle ---------------------------------------------------------------------


@dataclass
class Bundle:
    """A bundle as :func:`load_bundle` read it; reads never download or change it."""

    path: Path
    manifest: BundleManifest
    #: Each dataset's description, its family's inherited keys applied.
    descriptions: dict[str, dict]
    #: Every bundled file, by key: ``<dataset>/<path>``.
    resources: dict[str, Resource]
    inventories: dict[str, Inventory]
    #: The data command that realigns it, for the warning.
    prog: str = "<tool>-data"

    @property
    def datasets(self) -> dict[str, BundledDataset]:
        return self.manifest.datasets

    def names(self) -> list[str]:
        return sorted(self.manifest.datasets)

    def file(self, key: str) -> Path:
        """Where the bundle keeps the file ``key``."""
        return _inside(self.path, f"{DATA_DIR}/{key}")

    def dataset(self, name: str) -> Dataset:
        """One of the bundle's datasets as a catalogue entry: what a read sees first."""
        meta = self.descriptions[name]
        entry = self.datasets[name]
        records = [
            record.model_dump(by_alias=True, exclude_none=True)
            for record in entry.resources
        ]
        row = {
            k.NAME: name,
            k.TITLE: meta.get(k.TITLE) or name,
            k.ACCESS: meta.get(k.ACCESS, k.PUBLIC),
            k.VISIBILITY: meta.get(k.VISIBILITY, k.PUBLIC),
            k.TOTAL_BYTES: sum(record[k.BYTES] for record in records),
            k.FILE_COUNT: len(records),
            k.REMOTE_PREFIX: remote_prefix_of({**meta, k.NAME: name}),
            k.LICENSE_STATUS: license_status_of(dict(meta)),
        }
        if entry.alignment is not None and entry.alignment.revision > 1:
            row[k.REVISION] = entry.alignment.revision
        return Dataset(name, row[k.TITLE], row, self.inventories[name])

    def ahead(self) -> dict[str, str]:
        """The datasets ahead of the catalogue, and why, from ``bundle.json`` alone."""
        found = {}
        for name, entry in sorted(self.datasets.items()):
            if entry.alignment is None:
                found[name] = "not in the catalogue"
            elif entry.changes:
                files = [change for change in entry.changes if not change.document]
                documents = [change for change in entry.changes if change.document]
                parts = []
                if files:
                    parts.append(
                        f"{len(files)} file{'s' if len(files) > 1 else ''} changed"
                    )
                if documents:
                    parts.append("its description changed")
                found[name] = ", ".join(parts)
        return found

    def behind(self, catalog: Catalog) -> dict[str, str]:
        """The datasets behind ``catalog``, or withdrawn from it, read from its index rows.

        Asks only rows the index holds: no descriptor and no shard is read.
        """
        found = {}
        for name, entry in sorted(self.datasets.items()):
            if entry.alignment is None:
                continue
            row = catalog.datasets.get(name)
            if row is None:
                found[name] = (
                    "withdrawn from the catalogue: drop it from the bundle, or "
                    "switch to its successor"
                )
                continue
            revision = int(row.entry.get(k.REVISION, 1))
            if revision > entry.alignment.revision:
                found[name] = (
                    f"revision {revision} in the catalogue, {entry.alignment.revision} "
                    "here"
                )
        return found

    def _selected(self, selection: Sequence[str]) -> list[str]:
        """The keys a selection of datasets or keys names; every key without one."""
        if not selection:
            return sorted(self.resources)
        keys: list[str] = []
        for item in selection:
            if item in self.datasets:
                keys += sorted(
                    key for key, resource in self.resources.items()
                    if resource.dataset == item
                )  # fmt: skip
            elif item in self.resources:
                keys.append(item)
            else:
                raise BundleError(
                    f"{item!r} is neither a dataset nor a file of the bundle at "
                    f"{self.path}; it holds {', '.join(self.names())}"
                )
        return list(dict.fromkeys(keys))

    def verify(self, *selection: str) -> list[BundleFinding]:
        """Hash the files, the descriptions and the licence documents.

        Reports each file as ``ok``, ``modified`` or ``missing``, and a file
        under ``data/`` or ``datasets/`` that ``bundle.json`` does not record as
        ``unrecorded``. ``selection`` narrows it to datasets or keys. Nothing is
        changed, and no setting is read.
        """
        findings = [self._check(key) for key in self._selected(selection)]
        wanted = (
            {self.resources[f.key].dataset for f in findings}
            if selection
            else set(self.datasets)
        )
        for name in sorted(wanted):
            for record in self.datasets[name].documents:
                findings.append(
                    self._check_document(name, record.path, record.bytes, record.hash)
                )
            findings += self._unrecorded(name)
        return findings

    def _check(self, key: str) -> BundleFinding:
        resource = self.resources[key]
        path = self.file(key)
        try:
            if not path.is_file():
                return BundleFinding(
                    key, path, "missing", resource.hash, None, resource.bytes, None
                )
            size, actual = path.stat().st_size, digest.of_file(path)
        except OSError as error:
            raise BundleError(f"cannot read the bundled file {key}: {error}") from None
        same = size == resource.bytes and digest.matches(resource.hash, actual)
        return BundleFinding(
            key,
            path,
            "ok" if same else "modified",
            resource.hash,
            digest.recorded(actual),
            resource.bytes,
            size,
        )

    def _check_document(
        self, name: str, relative: str, size: int, recorded: str
    ) -> BundleFinding:
        key = f"{DESCRIPTIONS_DIR}/{name}/{relative}"
        path = _inside(self.path, key)
        if not path.is_file():
            return BundleFinding(key, path, "missing", recorded, None, size, None)
        actual = digest.of_file(path)
        same = path.stat().st_size == size and digest.matches(recorded, actual)
        return BundleFinding(
            key,
            path,
            "ok" if same else "modified",
            recorded,
            digest.recorded(actual),
            size,
            path.stat().st_size,
        )

    def _unrecorded(self, name: str) -> list[BundleFinding]:
        recorded = {
            resource.path
            for resource in self.resources.values()
            if resource.dataset == name
        }
        documents = {record.path for record in self.datasets[name].documents}
        found = []
        for base, known, prefix in (
            (_inside(self.path, f"{DATA_DIR}/{name}"), recorded, f"{name}/"),
            (
                _inside(self.path, f"{DESCRIPTIONS_DIR}/{name}"),
                documents,
                f"{DESCRIPTIONS_DIR}/{name}/",
            ),
        ):
            for path in _files_under(
                base, nested=set(self.datasets) - {name}, name=name
            ):
                relative = path.relative_to(base).as_posix()
                if relative not in known:
                    found.append(
                        BundleFinding(
                            prefix + relative, path, "unrecorded", None,
                            None, None, path.stat().st_size,
                        )
                    )  # fmt: skip
        return found

    def fetch(self, *selection: str, allow_modified: bool = False) -> DataFiles:
        """The bundled files, by key, checked against ``bundle.json``.

        ``selection`` names datasets or keys; without it, every file.
        ``allow_modified=True`` lets one test read files changed without
        ``bundle update`` recording it, with a warning naming them: the
        recorded hashes stay, and nothing is repaired, republished or updated.
        It never lets a missing file pass.
        """
        findings = [self._check(key) for key in self._selected(selection)]
        missing = [finding.key for finding in findings if finding.status == "missing"]
        if missing:
            raise BundleError(
                f"the bundle at {self.path} lacks {', '.join(missing)}: restore "
                "them from the repository"
            )
        changed = [finding.key for finding in findings if finding.status == "modified"]
        if changed:
            message = (
                f"bundled files differ from what {MANIFEST} records: "
                + ", ".join(changed)
            )
            if not allow_modified:
                raise BundleError(
                    f"{message}. Record the change with `bundle update`, or read it "
                    "in one test with allow_modified=True"
                )
            report.warning(
                f"{message}; read as changed, the recorded hashes are kept.",
                ModifiedBundleWarning,
                stacklevel=2,
            )
        warn_once(self)
        return DataFiles((finding.key, finding.path) for finding in findings)


def _files_under(base: Path, *, nested: set[str], name: str) -> list[Path]:
    """The files under one dataset's directory, without those of datasets nested in it."""
    if not base.is_dir():
        return []
    inner = {
        other[len(name) + 1 :]
        for other in nested
        if names.within(other, name) and other != name
    }
    found = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(base).as_posix()
        if any(names.within(relative, prefix) for prefix in inner):
            continue
        found.append(path)
    return found


def load_bundle(path: str | Path, *, prog: str | None = None) -> Bundle:
    """Read a bundle: ``bundle.json``, through its model, and every description.

    Accepts the directory or its ``bundle.json``. Refuses, with
    :class:`~ethos_data.errors.BundleError` naming the dataset and what is
    missing, a dataset that is not public in access and visibility, whose
    licensing is not settled, or whose description or licence document is not
    there. The files are checked when they are read. ``prog`` is the data
    command that realigns it, for the warning.
    """
    path = Path(path).expanduser().absolute()
    root = path.parent if path.name == MANIFEST else path
    manifest_path = _inside(root, MANIFEST)
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BundleError(
            f"cannot read the bundle manifest {manifest_path}: {error}"
        ) from None
    manifest = _checked_manifest(document, manifest_path)
    if not manifest.datasets:
        raise BundleError(f"{manifest_path} holds no dataset")
    for name in manifest.datasets:
        _relative(name, "dataset name")
    for family in manifest.families:
        _relative(family, "family name")
    _distinct_datasets(manifest.datasets)

    families = {name: _read_description(root, name) for name in manifest.families}
    descriptions: dict[str, dict] = {}
    resources: dict[str, Resource] = {}
    inventories: dict[str, Inventory] = {}
    from .formats.dataset import INHERITED

    for name, entry in manifest.datasets.items():
        own = _read_description(root, name)
        meta = {}
        for family in names.ancestors(name):
            meta.update(
                {
                    key: value
                    for key, value in families.get(family, {}).items()
                    if key in INHERITED
                }
            )
        meta.update(own)
        meta[k.NAME] = name
        refusal = _refusal(name, meta)
        if refusal:
            raise BundleError(f"the bundle at {root} cannot hold it: {refusal}")
        recorded = {record.path for record in entry.documents}
        for document in [k.DESCRIPTION_FILE, *_license_documents(meta)]:
            if document not in recorded:
                raise BundleError(
                    f"{name}: {DESCRIPTIONS_DIR}/{name}/{document} is not recorded in "
                    f"{MANIFEST}; record it with `bundle update`"
                )
            if not _inside(root, f"{DESCRIPTIONS_DIR}/{name}/{document}").is_file():
                raise BundleError(
                    f"the bundle at {root} lacks {DESCRIPTIONS_DIR}/{name}/{document}"
                )
        records = []
        for record in entry.resources:
            raw = record.model_dump(by_alias=True, exclude_none=True)
            try:
                resource = checked(name, raw)
            except ValueError as error:
                raise BundleError(str(error)) from None
            if resource.key in resources:
                raise BundleError(f"{MANIFEST} records {resource.key} twice")
            resources[resource.key] = resource
            records.append(raw)
        descriptions[name] = meta
        inventories[name] = Inventory.from_records(name, {**meta, k.RESOURCES: records})
    return Bundle(
        root.resolve(),
        manifest,
        descriptions,
        resources,
        inventories,
        prog or "<tool>-data",
    )


def refuse_what_the_catalogue_withholds(bundle: Bundle, catalog: Catalog) -> None:
    """Refuse a bundled dataset the catalogue's index lists as restricted or hidden.

    A bundle is authoritative for bytes and descriptions, not for access or
    visibility. Read from the index rows alone.
    """
    for name in sorted(bundle.datasets):
        row = catalog.datasets.get(name)
        if row is None:
            continue
        for value, key in ((row.access, k.ACCESS), (row.visibility, k.VISIBILITY)):
            if value != k.PUBLIC:
                raise BundleError(
                    f"the bundle at {bundle.path} holds {name}, which the catalogue "
                    f"lists as {value} ({key}). A bundle holds public data only: "
                    "drop the dataset from the bundle."
                )


# -- the warning ------------------------------------------------------------------

#: Bundles this process warned about, by path and kind.
_WARNED: set[tuple[str, str]] = set()
#: (path, size, mtime) of every bundled file hashed in this process.
_CHECKED: dict[tuple[str, int, int], bool] = {}


def _relative_to_cwd(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return str(path)


def warn_once(bundle: Bundle) -> None:
    """Warn, once per process, that ``bundle`` is ahead of the catalogue."""
    ahead = bundle.ahead()
    marker = (str(bundle.path), "ahead")
    if not ahead or marker in _WARNED:
        return
    _WARNED.add(marker)
    where = _relative_to_cwd(bundle.path)
    listed = ", ".join(f"{name} ({why})" for name, why in ahead.items())
    known = [name for name, why in ahead.items() if why != "not in the catalogue"]
    take = (
        f", or take the catalogue's version: {bundle.prog} bundle update {where} "
        f"--from-catalog {' '.join(known)}"
        if known
        else ""
    )
    report.warning(
        f"bundle {where} is ahead of the catalogue: {listed}. Realign it soon: "
        f"{bundle.prog} propose {where}{take}",
        BundleAlignmentWarning,
    )


def warn_behind(bundle: Bundle, catalog: Catalog) -> None:
    """Warn, once per process, that ``bundle`` is behind ``catalog``, or holds what it withdrew."""
    behind = bundle.behind(catalog)
    marker = (str(bundle.path), "behind")
    if not behind or marker in _WARNED:
        return
    _WARNED.add(marker)
    where = _relative_to_cwd(bundle.path)
    listed = ", ".join(f"{name} ({why})" for name, why in behind.items())
    later = [name for name, why in behind.items() if why.startswith("revision")]
    take = (
        f" Take the catalogue's version: {bundle.prog} bundle update {where} "
        f"--from-catalog {' '.join(later)}"
        if later
        else ""
    )
    report.warning(
        f"bundle {where} is behind the catalogue: {listed}.{take}",
        BundleAlignmentWarning,
    )


def checked_file(bundle: Bundle, resource: Resource) -> str:
    """Why the bundle's copy of ``resource`` cannot be read; "" when it can.

    Hashed once per process: a test suite that reads the same file in a
    hundred tests pays for it once, and a file edited meanwhile is hashed again.
    """
    path = bundle.file(resource.key)
    try:
        stat = path.stat()
    except OSError:
        return "the file is missing"
    marker = (str(path), stat.st_size, stat.st_mtime_ns)
    ok = _CHECKED.get(marker)
    if ok is None:
        ok = stat.st_size == resource.bytes and digest.matches(
            resource.hash, digest.of_file(path)
        )
        _CHECKED[marker] = ok
    return "" if ok else f"it differs from what {MANIFEST} records"


# -- the catalogue view -----------------------------------------------------------


def with_bundles(
    catalog: Catalog | None,
    bundles: Sequence[Bundle],
    *,
    routes: Catalog | None = None,
) -> Catalog:
    """A catalogue view with the bundles' datasets in place of the catalogue's.

    ``catalog`` None makes a view of the bundles alone, which reads no index.
    ``routes`` is the catalogue the download switch reads a bundled file
    through, when it holds the same bytes under the same key.
    """
    base = catalog or Catalog(location="bundles", descriptor={}, datasets={})
    datasets = dict(base.datasets)
    for bundle in bundles:
        for name in bundle.datasets:
            datasets[name] = bundle.dataset(name)
        for family in bundle.manifest.families:
            if family in datasets:
                continue
            members = [
                datasets[name] for name in bundle.datasets if names.within(name, family)
            ]
            row = {
                k.NAME: family,
                k.TITLE: family,
                k.NAMESPACE: True,
                k.TOTAL_BYTES: sum(member.total_bytes for member in members),
                k.FILE_COUNT: sum(member.file_count for member in members),
            }
            datasets[family] = Dataset(
                family,
                family,
                row,
                Inventory.from_records(family, {k.NAME: family, k.NAMESPACE: True}),
            )
    return dataclasses.replace(
        base,
        datasets=datasets,
        bundles=(*base.bundles, *bundles),
        routes=routes,
    )


# -- create -----------------------------------------------------------------------


@dataclass(frozen=True)
class BundleCreated:
    """What ``bundle create`` wrote."""

    path: Path
    datasets: list[str]
    #: The descriptions it drafted, to be filled in.
    drafted: list[str]


def _datasets_on_disk(root: Path, family: str | None) -> dict[str, Path]:
    """The datasets whose files lie under ``data/``: each directory, a family's members."""
    data = root / DATA_DIR
    if not data.is_dir():
        raise BundleError(
            f"no {DATA_DIR}/ in {root}: put each dataset's files under "
            f"{DATA_DIR}/<dataset>/"
        )
    loose = sorted(p.name for p in data.iterdir() if p.is_file())
    if loose:
        raise BundleError(
            f"{', '.join(loose)} lie directly in {DATA_DIR}/, in no dataset; move "
            f"them into {DATA_DIR}/<dataset>/"
        )
    found = {}
    for directory in sorted(p for p in data.iterdir() if p.is_dir()):
        if family is not None and directory.name == family:
            stray = sorted(p.name for p in directory.iterdir() if p.is_file())
            if stray:
                raise BundleError(
                    f"{', '.join(stray)} lie directly in {DATA_DIR}/{family}/, in no "
                    f"member; move them into {DATA_DIR}/{family}/<member>/"
                )
            for member in sorted(p for p in directory.iterdir() if p.is_dir()):
                found[f"{family}/{member.name}"] = member
        else:
            found[directory.name] = directory
    return found


def _inventory(directory: Path) -> list[dict]:
    """Every file under a dataset's directory, as inventory records."""
    from .files import build_resource, iter_data_files

    return [
        build_resource(path, directory, path.stat().st_size, digest.of_file(path))
        for path in iter_data_files(directory)
    ]


def _documents(root: Path, name: str) -> list[dict]:
    """Every file under ``datasets/<name>/``, nested datasets' aside, as records."""
    base = root / DESCRIPTIONS_DIR / name
    return [
        _record(path, path.relative_to(base).as_posix())
        for path in _files_under(base, nested=set(), name=name)
        if not (path.parent != base and (path.parent / k.DESCRIPTION_FILE).is_file())
    ]


def _draft(root: Path, name: str, template: str, **values: str) -> bool:
    """Write a description draft for ``name`` unless one is there; whether one was written."""
    from .formats import registry

    target = _inside(root, f"{DESCRIPTIONS_DIR}/{name}/{k.DESCRIPTION_FILE}")
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(registry.template(template, name=name, **values).encode("utf-8"))
    return True


def create_bundle(directory: str | Path, *, family: str | None = None) -> BundleCreated:
    """Start a bundle from the data directories under ``directory/data/``.

    Each directory under ``data/`` is a dataset; ``family`` names one whose
    subdirectories are the members of a family, ``<family>/<member>``. Hashes
    every file, drafts a description for each dataset and the family that has
    none, and writes ``bundle.json``. The datasets are ahead of the catalogue
    until it accepts them. Refuses a directory that is a bundle already.
    """
    from .formats.bundle import BundleManifest

    root = Path(directory).expanduser().absolute()
    if (root / MANIFEST).exists():
        raise BundleError(
            f"{root} is a bundle already; record changes with `bundle update`"
        )
    if family is not None:
        _relative(family, "family name")
    found = _datasets_on_disk(root, family)
    if not found:
        raise BundleError(f"no dataset directories under {root / DATA_DIR}")
    drafted = []
    if family is not None and _draft(
        root, family, "family", title=f"The {family} family"
    ):
        drafted.append(family)
    datasets = {}
    for name, data in found.items():
        records = _inventory(data)
        if not records:
            raise BundleError(f"no files under {data}")
        if _draft(
            root,
            name,
            "dataset-bundled",
            description="What these files are, and what they are for.",
        ):
            drafted.append(name)
        datasets[name] = {
            "alignment": None,
            "selection": "all",
            "changes": [],
            k.RESOURCES: records,
            "documents": _documents(root, name),
        }
    families = (
        {family: {"documents": _documents(root, family)}} if family is not None else {}
    )
    manifest = BundleManifest.model_validate(
        {"datasets": datasets, "families": families}
    )
    _write_json(root / MANIFEST, _manifest_document(manifest))
    return BundleCreated(root, sorted(datasets), drafted)


# -- update -----------------------------------------------------------------------


@dataclass(frozen=True)
class BundleUpdate:
    """What ``bundle update`` recorded."""

    path: Path
    #: The changes recorded in this run, by dataset: ``(path, change)``.
    recorded: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    #: The datasets aligned with the catalogue in this run, and the revision.
    aligned: dict[str, int] = field(default_factory=dict)
    #: The datasets taken from the catalogue with ``--from-catalog``.
    taken: list[str] = field(default_factory=list)

    @property
    def changes(self) -> bool:
        return bool(
            self.recorded or self.added or self.dropped or self.aligned or self.taken
        )


def _diff(
    before: Mapping[str, dict],
    now: Mapping[str, dict],
    changes: list[dict],
    *,
    document: bool,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """``changes`` with what differs between ``before`` and ``now`` merged into it.

    Each change is kept against the alignment, by the SHA-256 the file had
    there: a file changed back to those bytes drops its change, and one added
    since the alignment and removed again leaves none.
    """
    mine = {c["path"]: c for c in changes if bool(c.get("document")) == document}
    others = [c for c in changes if bool(c.get("document")) != document]
    found = []
    for path in sorted(set(before) | set(now)):
        old, new = before.get(path), now.get(path)
        if old is not None and new is not None and _same(old[k.HASH], new[k.HASH]):
            continue
        earlier = mine.get(path)
        aligned = earlier["was"] if earlier else (old[k.HASH] if old else None)
        if new is None:
            kind = "removed" if aligned is not None else None
        elif aligned is None:
            kind = "added"
        else:
            kind = None if _same(aligned, new[k.HASH]) else "changed"
        if kind is None:
            mine.pop(path, None)
            found.append((path, "restored" if new is not None else "removed"))
        else:
            mine[path] = {
                "path": path,
                "change": kind,
                "document": document,
                "was": aligned,
            }
            found.append((path, kind))
    return others + [mine[path] for path in sorted(mine)], found


def _same(one: str, other: str) -> bool:
    return digest.expected(one) == digest.expected(other)


def _holds_the_same(
    bundle_root: Path, name: str, entry: Mapping, meta: Mapping, catalog: Catalog
) -> bool:
    """Whether ``catalog`` holds what the bundle holds of ``name``: files, description, terms.

    ``meta`` is the bundle's description of ``name``, its families' inherited
    keys applied.
    """
    dataset = catalog.datasets.get(name)
    if dataset is None or dataset.namespace:
        return False
    try:
        held = {resource.path: resource.hash for resource in dataset.resources.values()}
        descriptor = dataset.inventory.descriptor
    except (IncompleteCatalog, CatalogUnavailable):
        return False
    mine = {record[k.PATH]: record[k.HASH] for record in entry[k.RESOURCES]}
    if entry.get("selection", "all") == "all" and set(mine) != set(held):
        return False
    for path, recorded in mine.items():
        if path not in held or digest.expected(held[path]) != digest.expected(recorded):
            return False
    if _comparable(meta) != _comparable(descriptor):
        return False
    for document in _license_documents(meta):
        try:
            published = dataset.inventory.read_part(document)
        except (IncompleteCatalog, CatalogUnavailable):
            return False
        local = _inside(
            bundle_root, f"{DESCRIPTIONS_DIR}/{name}/{document}"
        ).read_bytes()
        if local != published:
            return False
    return True


def differs_from_catalog(bundle: Bundle, catalog: Catalog) -> dict[str, str]:
    """The aligned datasets whose files, description or terms differ from the catalogue's.

    A dataset with recorded changes is ahead, and one the catalogue does not
    describe is new: neither is listed. What is listed differs although
    nothing was recorded, a description corrected in a patch release, for
    example.
    """
    found = {}
    for name, entry in sorted(bundle.datasets.items()):
        if entry.alignment is None or entry.changes:
            continue
        document = entry.model_dump(mode="json", by_alias=True, exclude_none=True)
        meta = bundle.descriptions[name]
        if not _holds_the_same(bundle.path, name, document, meta, catalog):
            found[name] = (
                "the catalogue holds other files, description or licence documents; "
                f"take its version: {bundle.prog} bundle update {bundle.path} "
                f"--from-catalog {name}"
            )
    return found


def _take_from_catalog(
    root: Path, name: str, entry: dict, catalog: Catalog, roots
) -> dict:
    """Replace a bundled dataset with the catalogue's files of its selection, and its terms."""
    from .retrieval import download

    dataset = catalog.dataset(name)
    descriptor = dataset.inventory.descriptor
    meta = {**description_of(descriptor), k.NAME: name}
    refusal = _refusal(name, meta)
    if refusal:
        raise BundleError(refusal)
    resources = list(dataset.resources.values())
    if entry.get("selection", "all") == "some":
        mine = {record[k.PATH] for record in entry[k.RESOURCES]}
        resources = [resource for resource in resources if resource.path in mine]
    fetched = download(catalog, resources, roots, progressbar=False)
    data = _inside(root, f"{DATA_DIR}/{name}")
    if data.exists():
        shutil.rmtree(data)
    for resource in resources:
        target = _inside(root, f"{DATA_DIR}/{resource.key}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fetched[resource.key], target)
    described = _inside(root, f"{DESCRIPTIONS_DIR}/{name}")
    described.mkdir(parents=True, exist_ok=True)
    (described / k.DESCRIPTION_FILE).write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )
    for document in _license_documents(meta):
        target = _inside(root, f"{DESCRIPTIONS_DIR}/{name}/{document}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(dataset.inventory.read_part(document))
    return {
        "alignment": {"revision": dataset.revision, "release": catalog.version},
        "selection": entry.get("selection", "all"),
        "changes": [],
        k.RESOURCES: [to_record(resource) for resource in resources],
        "documents": _documents(root, name),
    }


def update_bundle(
    directory: str | Path,
    *,
    catalog: Catalog | None = None,
    from_catalog: Sequence[str] = (),
    roots=None,
) -> BundleUpdate:
    """Record the changes to a bundle, and its alignment with ``catalog``.

    Records every changed, added and removed file, the descriptions and
    licence documents included, against each dataset's alignment, and every
    new dataset directory. With ``catalog`` readable, a dataset whose files,
    description and licence documents the catalogue holds is aligned with
    the revision it describes, and its changes are cleared.
    ``from_catalog`` names datasets to replace with the catalogue's files of
    the bundled selection, description and licence documents; ``roots``
    are the caches it reads them through.
    """
    from .formats.bundle import BundleManifest

    root = Path(directory).expanduser().absolute()
    manifest_path = _inside(root, MANIFEST)
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BundleError(
            f"cannot read the bundle manifest {manifest_path}: {error}"
        ) from None
    manifest = _manifest_document(_checked_manifest(document, manifest_path))
    datasets: dict[str, dict] = manifest["datasets"]
    families: dict[str, dict] = manifest["families"]

    unknown = sorted(set(from_catalog) - set(datasets))
    if unknown:
        raise BundleError(
            f"{', '.join(unknown)} is not a dataset of the bundle at {root}"
        )
    if from_catalog and catalog is None:
        raise BundleError("--from-catalog needs the catalogue the package reads")
    taken = []
    for name in from_catalog:
        datasets[name] = _take_from_catalog(root, name, datasets[name], catalog, roots)
        taken.append(name)

    on_disk = _datasets_on_disk(root, None)
    # A family's members lie in its directory: the names the manifest records
    # tell members from datasets.
    expanded = {}
    for top, path in on_disk.items():
        members = {
            name: _inside(root, f"{DATA_DIR}/{name}")
            for name in datasets
            if names.within(name, top) and name != top
        }
        expanded.update(members or {top: path})
    added, dropped = [], []
    recorded: dict[str, list[tuple[str, str]]] = {}
    for name in sorted(set(datasets) - set(expanded)):
        del datasets[name]
        dropped.append(name)
    for name, data in sorted(expanded.items()):
        now_files = {record[k.PATH]: record for record in _inventory(data)}
        now_documents = {record[k.PATH]: record for record in _documents(root, name)}
        if name not in datasets:
            _draft(
                root,
                name,
                "dataset-bundled",
                description="What these files are, and what they are for.",
            )
            datasets[name] = {
                "alignment": None,
                "selection": "all",
                "changes": [],
                k.RESOURCES: list(now_files.values()),
                "documents": _documents(root, name),
            }
            added.append(name)
            continue
        entry = datasets[name]
        if name in taken:
            continue
        before_files = {record[k.PATH]: record for record in entry[k.RESOURCES]}
        before_documents = {record[k.PATH]: record for record in entry["documents"]}
        changes = entry["changes"]
        if entry["alignment"] is not None:
            changes, files_found = _diff(
                before_files, now_files, changes, document=False
            )
            changes, documents_found = _diff(
                before_documents, now_documents, changes, document=True
            )
            found = files_found + documents_found
        else:
            found = [
                (path, "changed")
                for path in sorted(set(before_files) ^ set(now_files) | {
                    p for p in set(before_files) & set(now_files)
                    if before_files[p][k.HASH] != now_files[p][k.HASH]
                })
            ]  # fmt: skip
        entry["changes"] = changes
        entry[k.RESOURCES] = [now_files[path] for path in sorted(now_files)]
        entry["documents"] = [now_documents[path] for path in sorted(now_documents)]
        if found:
            recorded[name] = found
    for family, entry in families.items():
        entry["documents"] = _documents(root, family)

    for name in datasets:
        meta = _read_description(root, name)
        for family in names.ancestors(name):
            if family in families:
                meta = {**_read_description(root, family), **meta}
        refusal = _refusal(name, {**meta, k.NAME: name})
        if refusal:
            raise BundleError(f"the bundle at {root} cannot hold it: {refusal}")

    aligned = {}
    if catalog is not None:
        for name in datasets:
            row = catalog.datasets.get(name)
            if row is not None and (row.access, row.visibility) != (k.PUBLIC, k.PUBLIC):
                raise BundleError(
                    f"{name} is {row.access}/{row.visibility} in the catalogue; a "
                    "bundle holds public data only: drop it from the bundle"
                )
        for name, entry in datasets.items():
            if name in taken:
                continue
            meta = _inheriting(root, name, families)
            if _holds_the_same(root, name, entry, meta, catalog):
                revision = catalog.dataset(name).revision
                if (
                    entry["alignment"]
                    != {"revision": revision, "release": catalog.version}
                    or entry["changes"]
                ):
                    aligned[name] = revision
                entry["alignment"] = {"revision": revision, "release": catalog.version}
                entry["changes"] = []

    checked = BundleManifest.model_validate(
        {"datasets": datasets, "families": families}
    )
    _write_json(manifest_path, _manifest_document(checked))
    return BundleUpdate(root, recorded, added, dropped, aligned, taken)


# -- export -----------------------------------------------------------------------


def export_bundle(
    handle: Collections,
    target: str | Path,
    collections: str | Sequence[str],
    *,
    test: bool = False,
    progressbar: bool = False,
) -> Bundle:
    """Write a new bundle of what ``handle`` reads for ``collections``.

    Read through the handle: its bundles first, then the caches and the
    download, staging excluded; ``test`` selects the test variants. Each
    dataset keeps its description, licence documents and alignment: a bundled
    one as its bundle records them, any other the catalogue's, aligned with the
    revision it describes. Every file's size and SHA-256 is checked as it is
    copied, and downloads use the publication URL of the handle's settings.
    The target must not exist.
    """
    from .formats.bundle import BundleManifest
    from .retrieval import download

    target = Path(target).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise BundleError(f"{target} exists; export into a new directory")
    requested = [collections] if isinstance(collections, str) else list(collections)
    if not requested:
        raise BundleError("name at least one collection to export")
    selected: dict[str, Resource] = {}
    for name in dict.fromkeys(requested):
        resources = handle.resolve(name, test=test)
        if not resources:
            raise BundleError(f"collection {name!r} selects no files")
        for resource in resources:
            selected[resource.key] = resource
    view = handle.view_for(list(selected.values()))
    with_companions, missing = view.with_sidecars(list(selected.values()))
    if missing:
        raise BundleError(f"a companion file is not in the catalogue: {missing[0]}")
    selected = dict(with_companions)
    by_dataset: dict[str, list[Resource]] = {}
    for resource in selected.values():
        by_dataset.setdefault(resource.dataset, []).append(resource)
    _distinct_datasets(by_dataset)

    roots = dataclasses.replace(handle.roots, staging=None)
    fetched = download(
        view, sorted(selected.values(), key=lambda r: r.key), roots, progressbar
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".ethos-bundle-", dir=target.parent))
    try:
        datasets, families = {}, {}
        for name, resources in sorted(by_dataset.items()):
            bundle = view.bundle_of(name)
            if bundle is not None:
                entry = _exported_from_bundle(bundle, name, temporary)
                if len(resources) < len(bundle.inventories[name].resources()):
                    entry["selection"] = "some"
            else:
                entry = _exported_from_catalog(view, name, temporary)
                if len(resources) < view.dataset(name).file_count:
                    entry["selection"] = "some"
            for resource in sorted(resources, key=lambda r: r.key):
                destination = _inside(temporary, f"{DATA_DIR}/{resource.key}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(fetched[resource.key], destination)
                if destination.stat().st_size != resource.bytes or not digest.matches(
                    resource.hash, digest.of_file(destination)
                ):
                    raise BundleError(
                        f"{resource.key} does not match its recorded size and SHA-256"
                    )
            entry[k.RESOURCES] = [
                to_record(resource)
                for resource in sorted(resources, key=lambda r: r.path)
            ]
            entry["documents"] = _documents(temporary, name)
            datasets[name] = entry
            for family in names.ancestors(name):
                if family in view.datasets:
                    families[family] = _exported_family(view, family, temporary)
        manifest = BundleManifest.model_validate(
            {"datasets": datasets, "families": families}
        )
        _write_json(temporary / MANIFEST, _manifest_document(manifest))
        load_bundle(temporary).verify()
        target.mkdir(exist_ok=False)
        try:
            for child in temporary.iterdir():
                child.rename(target / child.name)
        except BaseException:
            shutil.rmtree(target)
            raise
    except FileExistsError:
        raise BundleError(f"{target} exists; export into a new directory") from None
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return load_bundle(target, prog=getattr(handle, "prog", None))


def _exported_from_bundle(bundle: Bundle, name: str, target: Path) -> dict:
    """A bundled dataset's entry and description, as its bundle records them."""
    source = _inside(bundle.path, f"{DESCRIPTIONS_DIR}/{name}")
    shutil.copytree(
        source, _inside(target, f"{DESCRIPTIONS_DIR}/{name}"), dirs_exist_ok=True
    )
    entry = bundle.datasets[name]
    return {
        "alignment": entry.alignment.model_dump() if entry.alignment else None,
        "selection": entry.selection,
        "changes": [change.model_dump() for change in entry.changes],
    }


def _exported_from_catalog(catalog: Catalog, name: str, target: Path) -> dict:
    """A catalogue dataset's entry and description, aligned with the revision it describes."""
    dataset = catalog.dataset(name)
    try:
        meta = {**description_of(dataset.inventory.descriptor), k.NAME: name}
    except EthosDataError as error:
        raise BundleError(
            f"cannot read the description of {name!r}: {error.message}"
        ) from None
    refusal = _refusal(name, meta)
    if refusal:
        raise BundleError(refusal)
    directory = _inside(target, f"{DESCRIPTIONS_DIR}/{name}")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / k.DESCRIPTION_FILE).write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
        newline="\n",
    )
    expected = {
        entry[k.DOCUMENT]: entry.get(k.DOCUMENT_SHA256)
        for entry in meta.get(k.LICENSES) or []
        if isinstance(entry, Mapping) and entry.get(k.DOCUMENT)
    }
    for document in _license_documents(meta):
        try:
            raw = dataset.inventory.read_part(document)
        except (IncompleteCatalog, CatalogUnavailable) as error:
            raise BundleError(
                f"cannot read the licence document {document!r} of {name!r}: "
                f"{error.message}"
            ) from None
        declared = expected.get(document)
        if declared and not digest.matches(declared, digest.of_bytes(raw)):
            raise BundleError(
                f"the licence document {document!r} of {name!r} does not match its "
                "recorded hash"
            )
        destination = _inside(directory, document)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    return {
        "alignment": {"revision": dataset.revision, "release": catalog.version},
        "selection": "all",
        "changes": [],
    }


def _exported_family(catalog: Catalog, family: str, target: Path) -> dict:
    """A family's description, from its bundle or the catalogue."""
    directory = _inside(target, f"{DESCRIPTIONS_DIR}/{family}")
    directory.mkdir(parents=True, exist_ok=True)
    bundle = next((b for b in catalog.bundles if family in b.manifest.families), None)
    if bundle is not None:
        shutil.copyfile(
            _inside(bundle.path, f"{DESCRIPTIONS_DIR}/{family}/{k.DESCRIPTION_FILE}"),
            directory / k.DESCRIPTION_FILE,
        )
    else:
        descriptor = catalog.dataset(family).inventory.descriptor
        (directory / k.DESCRIPTION_FILE).write_text(
            yaml.safe_dump(
                {**description_of(descriptor), k.NAME: family},
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
            newline="\n",
        )
    return {"documents": [_record(directory / k.DESCRIPTION_FILE, k.DESCRIPTION_FILE)]}


def describe_bundle(bundle: Bundle) -> list[str]:
    """One line per dataset: its alignment, selection and state."""
    lines = []
    ahead = bundle.ahead()
    for name, entry in sorted(bundle.datasets.items()):
        aligned = (
            f"revision {entry.alignment.revision}"
            + (f" of {entry.alignment.release}" if entry.alignment.release else "")
            if entry.alignment
            else "not in the catalogue"
        )
        files = len(entry.resources)
        state = f"ahead: {ahead[name]}" if name in ahead else "aligned"
        lines.append(
            f"{name:<40} {files:>5} files  {entry.selection:<4}  {aligned}  {state}"
        )
    return lines
