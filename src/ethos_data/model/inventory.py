"""One dataset's descriptor and inventory, read on demand: the one inventory reader.

A generated catalogue describes each dataset in a ``datapackage.json``: its
descriptor, and its inventory, one record per file. A small inventory sits
inline, under ``resources``. A large one is split into shards,
``shards/<prefix>.json``, one per directory prefix of ``ethos:shard_depth``
segments, which the descriptor lists under ``ethos:shards``.

:class:`Inventory` reads one dataset through the :class:`PartReader` it is
handed -- a checkout, HTTPS, the metadata cache in front of HTTPS, a tree in
memory -- and does no input or output of its own. It reads the descriptor on
first access and each shard at most once, when a request needs it: one shard
for a path; for patterns, only the shards they can reach; every shard for the
whole inventory. The build splits an inventory by the rules here, so the
writer and the reader cannot disagree.
"""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Protocol

from ..errors import EthosDataError, IncompleteCatalog
from ..formats import keys as k
from .resource import Resource, extras_of, from_record, to_record

__all__ = [
    "ROOT_SHARD",
    "SHARD_DIR",
    "Inventory",
    "PartReader",
    "shard_could_match",
    "shard_key",
    "shard_path",
    "split_into_shards",
]

#: The shard of the files at the dataset root, above any shard directory.
ROOT_SHARD = "_root"
#: Where a dataset's shards live, beside its ``datapackage.json``.
SHARD_DIR = "shards"


class PartReader(Protocol):
    """Reads the files of a generated catalogue: what every metadata source is."""

    def read(self, location: str) -> bytes:
        """The bytes at ``location``; IncompleteCatalog when nothing is there."""
        ...

    def join(self, base: str, relative: str) -> str:
        """Where ``relative`` lies, relative to the file at ``base``."""
        ...


# -- the shard rules the build shares ----------------------------------------


def shard_key(relative_path: str, depth: int) -> str:
    """Which shard a resource path belongs to.

    Keyed on the *directory* prefix, so every file in a directory lands in the
    same shard as its neighbours -- which is what makes shapefile sidecars and
    a tile's variables resolvable without touching a second shard.
    """
    directories = relative_path.split("/")[:-1]
    return "/".join(directories[:depth]) or ROOT_SHARD


def shard_path(prefix: str) -> str:
    """Where one shard lives, relative to the dataset's ``datapackage.json``."""
    return f"{SHARD_DIR}/{prefix}.json"


def split_into_shards(records: Iterable[dict], depth: int) -> dict[str, list[dict]]:
    """Group an inventory's records by shard, in a stable order."""
    shards: dict[str, list[dict]] = {}
    for record in records:
        shards.setdefault(shard_key(record[k.PATH], depth), []).append(record)
    return {prefix: shards[prefix] for prefix in sorted(shards)}


def shard_could_match(prefix: str, pattern: str) -> bool:
    """Could any path in the shard ``prefix`` match ``pattern``?

    Conservative by construction: it may say yes for a shard that turns out to
    hold no match (the caller globs properly afterwards), but never no for a
    shard that holds one. A wrong no would silently drop files from a
    selection, which is far worse than one extra read.
    """
    parts = [] if prefix == ROOT_SHARD else prefix.split("/")
    patterns = pattern.split("/")
    if not parts:
        # The root shard's files have no directory component at all, so only a
        # single-segment pattern can name one, or a pattern starting with
        # ``**``, which absorbs zero segments.
        return len(patterns) == 1 or patterns[0] == "**"
    while parts:
        if not patterns:
            # The pattern describes a shallower path than this shard's prefix.
            return False
        head = patterns[0]
        if head == "**":
            return True  # absorbs any number of segments, these included
        if not fnmatch.fnmatchcase(parts[0], head):
            return False
        parts, patterns = parts[1:], patterns[1:]
    # Files in a shard sit *below* its prefix directory, so a pattern that ran
    # out exactly at the prefix is one segment too short to match any of them.
    return bool(patterns)


# -- the reader ---------------------------------------------------------------


class Inventory:
    """One dataset's descriptor and the records of its files, read on demand.

    Built over a part reader and the location of the dataset's
    ``datapackage.json``; or, for bundles and staging, from records or
    resources already in hand, when it reads nothing. ``where`` names the
    catalogue the dataset belongs to, for messages. A part that is not there
    raises :class:`~ethos_data.errors.IncompleteCatalog`, naming the dataset,
    the part and its location; ``missing(part, location)`` words it otherwise,
    as a maintainer command does.
    """

    def __init__(
        self,
        dataset: str,
        reader: PartReader | None = None,
        location: str = "",
        *,
        where: str = "",
        missing: Callable[[str, str], EthosDataError] | None = None,
    ) -> None:
        self.dataset = dataset
        self.location = location
        self._reader = reader
        self._where = where
        self._missing_as = missing
        self._descriptor: dict | None = None
        self._resources: dict[str, Resource] = {}
        # Narrowed licences and other per-file keys, kept apart so a large
        # inventory holds no second copy of its ordinary records.
        self._extras: dict[str, dict] = {}
        # Paths in the order they were written, per shard (inline: one list).
        self._order: dict[str, list[str]] = {}
        self._shards: dict[str, str] = {}
        self._loaded: set[str] = set()
        self._depth = 0

    @classmethod
    def from_records(cls, dataset: str, descriptor: Mapping) -> Inventory:
        """The inventory a descriptor holds inline, as a bundle carries it."""
        inventory = cls(dataset)
        inventory._take(descriptor)
        return inventory

    @classmethod
    def from_resources(
        cls, dataset: str, descriptor: Mapping, resources: Iterable[Resource]
    ) -> Inventory:
        """An inventory of resources made elsewhere, as staging makes them."""
        inventory = cls(dataset)
        inventory._descriptor = dict(descriptor)
        order = inventory._order.setdefault(ROOT_SHARD, [])
        for resource in resources:
            inventory._resources[resource.path] = resource
            order.append(resource.path)
        return inventory

    # -- the descriptor -----------------------------------------------------

    @property
    def descriptor(self) -> dict:
        """The ``datapackage.json``; for a sharded dataset, without the inventory."""
        self._ensure()
        return self._descriptor

    @property
    def sharded(self) -> bool:
        self._ensure()
        return bool(self._shards)

    @property
    def pending_shards(self) -> list[str]:
        """The shards the descriptor lists that have not been read yet."""
        self._ensure()
        return sorted(set(self._shards) - self._loaded)

    def shard_files(self) -> list[str]:
        """Each shard's location, relative to ``datapackage.json``, in shard order."""
        self._ensure()
        return list(self._shards.values())

    # -- the inventory ------------------------------------------------------

    def resources(self) -> dict[str, Resource]:
        """Every resource, by path. For a sharded dataset this reads every shard."""
        self._read_shards(self.pending_shards)
        return self._resources

    def matching(self, patterns: list[str]) -> dict[str, Resource]:
        """Resources from only the shards that ``patterns`` can reach.

        A superset of the matches: the caller globs them. Inline, the whole
        inventory.
        """
        self._ensure()
        self._read_shards(
            [
                prefix
                for prefix in self._shards
                if any(shard_could_match(prefix, pattern) for pattern in patterns)
            ]
        )
        return self._resources

    def at(self, path: str) -> Resource | None:
        """The resource at ``path``, reading only the shard that can hold it."""
        self._ensure()
        key = shard_key(path, self._depth)
        if key in self._shards:
            self._read_shards([key])
        return self._resources.get(path)

    def record(self, path: str) -> dict | None:
        """The record of the file at ``path`` as written, narrowed licences included."""
        resource = self.at(path)
        if resource is None:
            return None
        return to_record(resource, self._extras.get(path))

    def records(self) -> list[dict]:
        """Every record as written, in inventory order."""
        self.resources()
        return [
            to_record(self._resources[path], self._extras.get(path))
            for shard in self._order.values()
            for path in shard
        ]

    def read_part(self, relative: str) -> bytes:
        """A file beside ``datapackage.json``, such as an archived licence."""
        return self._part(f"file {relative!r}", relative)

    # -- reading ------------------------------------------------------------

    def _ensure(self) -> None:
        """Read the descriptor, once."""
        if self._descriptor is None:
            self._take(json.loads(self._part("descriptor (datapackage.json)", "")))

    def _take(self, descriptor: Mapping) -> None:
        self._depth = int(descriptor.get(k.SHARD_DEPTH, 0))
        self._shards = {
            entry[k.PREFIX]: entry[k.PATH] for entry in descriptor.get(k.SHARDS, [])
        }
        self._descriptor = dict(descriptor)
        if not self._shards:
            self._absorb(ROOT_SHARD, descriptor.get(k.RESOURCES, []))

    def _read_shards(self, prefixes: list[str]) -> None:
        for prefix in prefixes:
            if prefix in self._loaded:
                continue
            shard = json.loads(self._part(f"shard {prefix!r}", self._shards[prefix]))
            self._absorb(prefix, shard.get(k.RESOURCES, []))
            self._loaded.add(prefix)

    def _absorb(self, shard: str, records: list[dict]) -> None:
        order = self._order.setdefault(shard, [])
        for record in records:
            resource = from_record(self.dataset, record)
            extras = extras_of(record)
            if extras:
                self._extras[resource.path] = extras
            self._resources[resource.path] = resource
            order.append(resource.path)

    def _part(self, what: str, relative: str) -> bytes:
        """One part's bytes; a missing one is named with the dataset and where."""
        if self._reader is None or not self.location:
            raise self._missing(what, self.location or "(no location)")
        location = (
            self._reader.join(self.location, relative) if relative else self.location
        )
        try:
            return self._reader.read(location)
        except IncompleteCatalog:
            raise self._missing(what, location) from None

    def _missing(self, what: str, location: str) -> EthosDataError:
        if self._missing_as is not None:
            return self._missing_as(what, location)
        listed = f" under {self._where}" if self._where else ""
        return IncompleteCatalog(
            f"dataset {self.dataset!r} is listed in the catalogue index{listed} but "
            f"its {what} is missing: {location}\n"
            "The catalogue copy is incomplete or stale -- an index from one revision "
            "paired with descriptors from another. Deploy or republish the complete "
            "tree for that revision; copying the index alone is not enough. If you "
            "did not choose this catalogue, `ethos-data config show` says where the "
            "setting came from."
        )
