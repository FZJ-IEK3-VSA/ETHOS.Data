"""``catalog remove``: take datasets out of the catalogue, metadata first, bytes after.

    ethos-data catalog remove old-dataset --reason "accepted by mistake" --dry-run
    ethos-data catalog remove old-dataset --reason "accepted by mistake"
    ethos-data catalog release v2.0.0 --public ../ETHOS.Data-Catalogue --push
    ethos-data catalog remove old-dataset --purge --dry-run
    ethos-data catalog remove old-dataset --purge

Removing is the reverse of publishing: metadata first, bytes second, because
a catalogue that points at deleted bytes breaks every reader half-way. The
first half takes two stages:

``withdraw``   record every dataset named -- a family stands for its members --
               as withdrawn, with the reason
``index``      rebuild the index, and the families above them, without them

A withdrawn dataset is left out of every later build and of the public
catalogue. Its description, inventory and status file stay where they are,
and so do its cache entries and its bytes on dCache, until a major release is
recorded after the removal: the releases of the current major made before it
still describe the dataset. ``--purge`` is the second half:

``check``      every dataset named is withdrawn, a major release is recorded
               after its removal, no other dataset shares its folder on the
               store, and this account may write every cache that holds it
``cache``      unlink the links recorded, delete the copies the caches own
``store``      delete its folder on the store
``tombstone``  delete its directory but its ``status.yaml``, which records it
               purged and keeps its name from being given to other bytes; a
               family left with no members goes too
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..adapters import Store
from ..config import Roots
from ..errors import ConfigurationError, MaintenanceError, UploadError
from ..formats import keys as k
from ..formats.catalogue import StoreSettings, store_of
from ..formats.derived import object_folder, object_url
from ..formats.status_file import StatusFile
from ..model import lifecycle
from ..model.versions import FIRST, MAJOR, Version
from . import (
    dataset_name_for,
    datasets_dir,
    inventory_of,
    is_namespace,
    read_catalog_meta,
    read_descriptor,
)
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "PURGE", "Removal", "RemoveResult", "run"]


@dataclass
class Removal:
    """The datasets ``remove`` was asked to take out, and why."""

    catalog_root: Path
    names: list[str]
    reason: str = ""
    #: The publication store, for ``--purge``; the one catalog.yaml names by default.
    store: Store | None = None
    #: The account's caches, where ``--purge`` looks for entries nobody recorded.
    roots: Roots | None = None
    #: Each dataset to withdraw, by name, with its directory: set by ``withdraw``.
    datasets: list[tuple[str, Path]] = field(default_factory=list)
    #: Each dataset to purge, with its status: set by the purge's ``check``.
    purging: list[tuple[str, Path, StatusFile]] = field(default_factory=list)
    settings: StoreSettings = field(default_factory=StoreSettings)
    publication_url: str = ""
    #: The datasets this run withdrew, for their notices.
    withdrawn: list[str] = field(default_factory=list)


class Withdraw:
    name = "withdraw"

    def plan(self, removal: Removal) -> list[Action]:
        removal.datasets = dataset_status.datasets(removal.catalog_root, removal.names)
        if not removal.datasets:
            raise MaintenanceError(
                f"{', '.join(removal.names)} has no dataset with files to remove"
            )
        actions = []
        for name, directory in removal.datasets:
            meta = read_descriptor(directory)
            status = dataset_status.build_input(directory, meta, name).status
            if status.state == lifecycle.WITHDRAWN:
                continue
            lifecycle.step("remove", status.state, name)
            actions.append(
                Action(
                    f"withdraw {name}, {status.state}", self._withdraw(removal, name)
                )
            )
        return actions

    @staticmethod
    def _withdraw(removal: Removal, name: str):
        def withdraw() -> None:
            directory = dataset_status.dataset_dir_in(removal.catalog_root, name)
            dataset_status.take(
                directory,
                dataset_status.read(directory),
                "remove",
                dataset=name,
                note=removal.reason or None,
            )
            removal.withdrawn.append(name)

        return withdraw


class Index:
    name = "index"

    def plan(self, removal: Removal) -> list[Action]:
        families = sorted(
            {
                dataset_name_for(datasets_dir(removal.catalog_root), parent)
                for _, directory in removal.datasets
                for parent in directory.parents
                if parent.is_relative_to(datasets_dir(removal.catalog_root))
                and parent != datasets_dir(removal.catalog_root)
                and (parent / "dataset.yaml").is_file()
                and is_namespace(parent)
            }
        )
        text = "rebuild the index" + (f" and {', '.join(families)}" if families else "")

        def rebuild() -> None:
            from . import manifest

            if families:
                manifest.run(removal.catalog_root, families)
            manifest.write_index(removal.catalog_root)

        def gone() -> str:
            index = json.loads(
                (removal.catalog_root / "datacatalog.json").read_text(encoding="utf-8")
            )
            listed = {row.get("name") for row in index.get("datasets", [])}
            still = [name for name, _ in removal.datasets if name in listed]
            return f"the index still lists {', '.join(still)}" if still else ""

        return [Action(text, rebuild, gone)]


class Released:
    name = "check"

    def plan(self, removal: Removal) -> list[Action]:
        root = removal.catalog_root
        removal.datasets = dataset_status.datasets(root, removal.names)
        if not removal.datasets:
            raise MaintenanceError(
                f"{', '.join(removal.names)} has no dataset with files to purge"
            )
        meta = read_catalog_meta(root)
        removal.settings = store_of(meta)
        removal.publication_url = (meta.get(k.PUBLICATION_URL) or "").rstrip("/")
        current = meta.get(k.VERSION)
        major = Version.parse(current).next(MAJOR) if current else FIRST
        for name, directory in removal.datasets:
            status = dataset_status.checked_status(directory, name, "purge")
            if dataset_status.major_release_after(status, "remove") is None:
                raise MaintenanceError(
                    f"{name} was withdrawn, but no major release is recorded after its "
                    "removal: the releases of the current major describe it, and its "
                    "bytes stay until the next one. Purge it after\n"
                    f"    ethos-data catalog release {major} --public DIR"
                )
            self._writable(name, status)
            removal.purging.append((name, directory, status))
        self._shared(removal)
        self._unrecorded(removal)
        if removal.store is None:
            from ..adapters.dcache import DcacheStore

            removal.store = DcacheStore(
                removal.settings.remote, removal.settings.frontend
            )
        return []

    @staticmethod
    def _writable(name: str, status: StatusFile) -> None:
        """Refuse an entry in a cache this account cannot write, before deleting any."""
        for copy in status.copies:
            if copy.kind not in (k.COPY_LINKED, k.COPY_MATERIALIZED):
                continue
            entry = Path(copy.location)
            if not (entry.exists() or entry.is_symlink()):
                continue
            owned = copy.kind == k.COPY_MATERIALIZED and entry.is_dir()
            if not os.access(entry.parent, os.W_OK) or (
                owned and not os.access(entry, os.W_OK)
            ):
                raise MaintenanceError(
                    f"{name}: its entry {entry} lies in {entry.parent}, which this "
                    "account cannot write, so nothing was deleted. Whoever purges "
                    "needs write access to every cache that holds the dataset."
                )

    def _unrecorded(self, removal: Removal) -> None:
        """Report the entries in the account's caches that no copy records."""
        if removal.roots is None:
            return
        caches = (removal.roots.public, *removal.roots.restricted)
        for name, _, status in removal.purging:
            recorded = {copy.location for copy in status.copies}
            for cache in caches:
                entry = Path(cache) / name
                if (entry.exists() or entry.is_symlink()) and str(
                    entry
                ) not in recorded:
                    report.info(
                        f"  {self.name:<12} {name}: {entry} is not recorded, so it is "
                        "not deleted; remove it by hand if it holds this dataset"
                    )

    @staticmethod
    def _shared(removal: Removal) -> None:
        """Refuse a folder on the store that another dataset's copy lies in, or around."""
        purged = {name for name, _, _ in removal.purging}
        others = []
        for name, directory in dataset_status.datasets(removal.catalog_root, []):
            status = dataset_status.read(directory) if name not in purged else None
            if status is not None:
                others += [
                    (name, copy.location.rstrip("/") + "/")
                    for copy in status.copies
                    if copy.kind == k.COPY_UPLOADED
                ]
        for name, _, status in removal.purging:
            for copy in status.copies:
                if copy.kind != k.COPY_UPLOADED:
                    continue
                folder = copy.location.rstrip("/") + "/"
                for other, location in others:
                    if location.startswith(folder) or folder.startswith(location):
                        raise MaintenanceError(
                            f"{name}'s folder on the store, {folder}, holds or lies in "
                            f"{other}'s, {location}; purging it would delete bytes "
                            "that are still in the catalogue"
                        )


class CacheEntries:
    name = "cache"

    def plan(self, removal: Removal) -> list[Action]:
        actions = []
        for name, _, status in removal.purging:
            for copy in status.copies:
                entry = Path(copy.location)
                if copy.kind == k.COPY_LINKED:
                    if entry.is_symlink():
                        actions.append(Action(f"unlink {entry}", entry.unlink))
                    elif entry.exists():
                        raise MaintenanceError(
                            f"{name}: {entry} was recorded as a link and is a real "
                            "directory now; find out who made it before deleting it"
                        )
                elif copy.kind == k.COPY_MATERIALIZED:
                    if entry.is_symlink():
                        raise MaintenanceError(
                            f"{name}: {entry} was recorded as a copy the cache owns "
                            "and is a link now; find out who made it"
                        )
                    if entry.is_dir():
                        actions.append(
                            Action(
                                f"delete {entry}, the copy the cache owns",
                                lambda entry=entry: shutil.rmtree(entry),
                            )
                        )
        return actions


class StoreBytes:
    name = "store"

    def plan(self, removal: Removal) -> list[Action]:
        actions = []
        root_url = removal.publication_url
        published_root = root_url.rsplit("/", 1)[-1]
        for name, directory, status in removal.purging:
            for copy in status.copies:
                if copy.kind != k.COPY_UPLOADED:
                    continue
                folder = copy.location.rstrip("/")
                if not root_url or not folder.startswith(root_url + "/"):
                    raise MaintenanceError(
                        f"{name}: its copy at {copy.location} is not under the "
                        f"publication root {root_url or '(none in catalog.yaml)'}"
                    )
                first = f"{published_root}/{folder[len(root_url) + 1 :]}"
                # The folder of every revision the dataset had: an earlier
                # release may name any of them.
                for revision in range(1, status.revision + 1):
                    destination = object_folder(first, revision)
                    if not removal.store.exists(destination):
                        report.info(
                            f"  {self.name:<12} {destination} holds nothing any more"
                        )
                        continue
                    actions.append(
                        Action(
                            f"purge {removal.settings.remote}:{destination} on the "
                            "store",
                            lambda destination=destination: removal.store.purge(
                                destination
                            ),
                            self._gone(removal, name, directory, folder, revision),
                        )
                    )
        return actions

    @staticmethod
    def _gone(removal: Removal, name: str, directory: Path, folder: str, revision: int):
        """Whether one revision's folder is served after its purge, by a file it held."""

        def gone() -> str:
            held = [
                record
                for record in inventory_of(name, directory).records()
                if int(record.get(k.REVISION, 1)) == revision
            ]
            if not held:
                return ""
            url = object_url(folder, held[0])
            try:
                removal.store.served(url)
            except UploadError:
                return ""
            return f"{url} is served after the purge"

        return gone


class Tombstone:
    name = "tombstone"

    def plan(self, removal: Removal) -> list[Action]:
        actions = [
            Action(
                f"delete datasets/{name}/ but its {dataset_status.STATUS}, and record "
                "it purged",
                self._bury(name, directory),
            )
            for name, directory, _ in removal.purging
        ]
        root = datasets_dir(removal.catalog_root)
        families = sorted(
            {
                parent
                for _, directory, _ in removal.purging
                for parent in directory.parents
                if parent.is_relative_to(root)
                and parent != root
                and (parent / "dataset.yaml").is_file()
            },
            key=lambda path: -len(path.parts),
        )
        buried = {directory for _, directory, _ in removal.purging}
        for family in families:
            left = [
                member
                for member in family.rglob("dataset.yaml")
                if member.parent != family and member.parent not in buried
            ]
            if not left:
                name = dataset_name_for(root, family)
                actions.append(
                    Action(
                        f"delete the family {name}, which has no members left",
                        lambda family=family: _forget_family(family),
                    )
                )

        def reindex() -> None:
            from . import manifest

            manifest.write_index(removal.catalog_root)

        actions.append(Action("rebuild the index", reindex))
        return actions

    @staticmethod
    def _bury(name: str, directory: Path):
        def bury() -> None:
            for child in directory.iterdir():
                if child.name == dataset_status.STATUS:
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            dataset_status.take(
                directory, dataset_status.read(directory), "purge", dataset=name
            )

        return bury


def _forget_family(family: Path) -> None:
    """A family's own files, its description and descriptor; its members' tombstones stay."""
    for generated in ("dataset.yaml", "datapackage.json"):
        (family / generated).unlink(missing_ok=True)


PIPELINE: Pipeline[Removal] = Pipeline("remove", [Withdraw(), Index()])
PURGE: Pipeline[Removal] = Pipeline(
    "purge", [Released(), CacheEntries(), StoreBytes(), Tombstone()]
)


@dataclass(frozen=True)
class RemoveResult:
    """The datasets ``catalog remove`` withdrew, or would withdraw."""

    datasets: list[str]
    #: Whether the status files and the index were written: not for a dry run.
    written: bool

    @property
    def ok(self) -> bool:
        return True


@report.reported
def run(
    catalog_root: Path,
    names: list[str],
    *,
    reason: str = "",
    purge: bool = False,
    dry_run: bool = False,
    store: Store | None = None,
    roots: Roots | None = None,
) -> RemoveResult:
    """Withdraw ``names`` -- datasets or families -- or, with ``purge``, delete them.

    Withdrawing rebuilds the index without them. Purging deletes their cache
    entries, their bytes on ``store`` -- the one catalog.yaml names by default
    -- and their directories, once a major release is recorded after their
    removal. It reports the entries in the caches ``roots`` names, the
    account's by default, that no copy records.
    """
    if purge and roots is None:
        from ..config import read_settings

        try:
            roots = read_settings().roots
        except ConfigurationError:
            roots = None
    removal = Removal(catalog_root, list(names), reason, store, roots)
    (PURGE if purge else PIPELINE).run(removal, dry_run=dry_run)
    if purge and not dry_run:
        report.info(
            "\nPurged. Commit the deletion and merge it; the status files that stay "
            "record it, and keep the names from being given to other bytes."
        )
    elif not dry_run:
        report.info(
            "\nCommit the withdrawal, merge it and release the catalogue: a "
            "withdrawal needs a minor release. Their cache entries and their bytes "
            "on dCache stay until a major release is recorded after the removal; "
            "then --purge deletes them. Tell the packages that read them:"
        )
        _notices(removal)
    return RemoveResult([name for name, _ in removal.datasets], not dry_run)


def _notices(removal: Removal) -> None:
    """Draft the removal notice of every dataset withdrawn, for the packages that read it."""
    from .. import handoffs

    for name, directory in removal.datasets:
        status = dataset_status.read(directory)
        if status is None:
            continue
        reason = next(
            (e.note for e in reversed(status.history) if e.step == "remove"), ""
        )
        package = directory / "datapackage.json"
        replacement = (
            json.loads(package.read_text("utf-8")).get(k.SUPERSEDED_BY, [])
            if package.is_file()
            else []
        )
        report.info(
            "\n"
            + handoffs.removal_notice(
                name, reason or "", dataset_status.releases(status)[0], replacement
            ).rstrip()
        )
