"""``catalog remove``: take datasets out of the catalogue, metadata first, bytes after.

    ethos-data catalog remove old-dataset --reason "accepted by mistake" --dry-run
    ethos-data catalog remove old-dataset --reason "accepted by mistake"
    ethos-data catalog release v2026.10.2 --public ../ETHOS.Data-Catalogue --push
    ethos-data catalog remove old-dataset --purge --dry-run
    ethos-data catalog remove old-dataset --purge

Removing is the reverse of publishing: metadata first, bytes second, because
a catalogue that points at deleted bytes breaks every reader half-way. The
first half takes two stages:

``withdraw``   record every dataset named -- a family stands for its members --
               as withdrawn, with the reason
``index``      rebuild the index, and the families above them, without them

A withdrawn dataset is left out of every later build and of the public
catalogue; its description, inventory and status file stay where they are,
and so do its cache entries and its bytes. ``--purge`` is the second half,
once a release without the dataset is recorded:

``check``      every dataset named is withdrawn, a release since says it is
               gone, and no other dataset shares its folder on the store
``cache``      unlink the links recorded, delete the copies the caches own
``store``      delete its folder on the store
``tombstone``  delete its directory but its ``status.yaml``, which records it
               purged and keeps its name from being given to other bytes; a
               family left with no members goes too
"""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..adapters import Store
from ..errors import MaintenanceError
from ..formats import keys as k
from ..formats.catalogue import StoreSettings, store_of
from ..formats.status_file import StatusFile
from ..model import lifecycle
from . import dataset_name_for, datasets_dir, is_namespace, read_catalog_meta
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "PURGE", "Removal", "run"]


@dataclass
class Removal:
    """The datasets ``remove`` was asked to take out, and why."""

    catalog_root: Path
    names: list[str]
    reason: str = ""
    #: The publication store, for ``--purge``; the one catalog.yaml names by default.
    store: Store | None = None
    #: Each dataset to withdraw, by name, with its directory: set by ``withdraw``.
    datasets: list[tuple[str, Path]] = field(default_factory=list)
    #: Each dataset to purge, with its status: set by the purge's ``check``.
    purging: list[tuple[str, Path, StatusFile]] = field(default_factory=list)
    settings: StoreSettings = field(default_factory=StoreSettings)
    publication_url: str = ""


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
            status = dataset_status.read(directory)
            if status is None:
                raise MaintenanceError(
                    f"{name} has no {dataset_status.STATUS} yet to record the removal "
                    f"in. Write one from its dataset.yaml with\n"
                    f"    ethos-data catalog migrate {name}"
                )
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

            if families and manifest.run(removal.catalog_root, families):
                raise MaintenanceError(f"rebuilding {', '.join(families)} failed")
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
        for name, directory in removal.datasets:
            status = dataset_status.read(directory)
            if status is None:
                raise MaintenanceError(
                    f"{name} has no {dataset_status.STATUS}; withdraw it first with\n"
                    f"    ethos-data catalog remove {name}"
                )
            lifecycle.step("purge", status.state, name)
            if dataset_status.released_since(status, "remove") is None:
                raise MaintenanceError(
                    f"{name} was withdrawn, but no release without it is recorded "
                    "yet, so readers may still be served a catalogue that lists it. "
                    "Release first:\n    ethos-data catalog release VERSION --public DIR"
                )
            removal.purging.append((name, directory, status))
        self._shared(removal)
        return []

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
                destination = f"{published_root}/{folder[len(root_url) + 1 :]}"
                actions.append(
                    Action(
                        f"purge {removal.settings.remote}:{destination} on the store",
                        self._purge(removal, destination),
                        self._gone(directory, folder),
                    )
                )
        return actions

    @staticmethod
    def _purge(removal: Removal, destination: str):
        def purge() -> None:
            if removal.store is None:
                from ..adapters.dcache import DcacheStore

                removal.store = DcacheStore(
                    removal.settings.remote, removal.settings.frontend
                )
            if removal.store.purge(destination, dry_run=False):
                raise MaintenanceError(f"purging {destination} on the store failed")

        return purge

    @staticmethod
    def _gone(directory: Path, folder: str):
        def gone() -> str:
            package = json.loads((directory / "datapackage.json").read_text("utf-8"))
            from . import resources_of

            resources = resources_of(package, directory)
            if not resources:
                return ""
            url = f"{folder}/{resources[0][k.PATH]}"
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, method="HEAD"), timeout=60
                ):
                    return f"{url} is still served"
            except (urllib.error.URLError, OSError):
                return ""

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


@report.reported
def run(
    catalog_root: Path,
    names: list[str],
    *,
    reason: str = "",
    purge: bool = False,
    dry_run: bool = False,
    store: Store | None = None,
) -> int:
    """Withdraw ``names`` -- datasets or families -- or, with ``purge``, delete them.

    Withdrawing rebuilds the index without them. Purging deletes their cache
    entries, their bytes on ``store`` -- the one catalog.yaml names by default
    -- and their directories, once a release without them is recorded.
    """
    removal = Removal(catalog_root, list(names), reason, store)
    (PURGE if purge else PIPELINE).run(removal, dry_run=dry_run)
    if dry_run:
        return 0
    if purge:
        report.info(
            "\nPurged. Commit the deletion; the status files that stay record it, "
            "and keep the names from being given to other bytes."
        )
    else:
        report.info(
            "\nRelease the catalogue without them; then delete their cache entries "
            "and bytes with --purge."
        )
    return 0
