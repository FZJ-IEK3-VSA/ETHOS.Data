"""One file of a dataset, the record a descriptor keeps for it, its companions.

The one reader and the one writer of a ``resources`` record: the catalogue,
its shards and a bundle hold the same records, and a file read from any of
them is the same :class:`Resource`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from ..formats import keys as k
from . import digest
from .names import relative

__all__ = [
    "CORE_KEYS",
    "Resource",
    "checked",
    "extras_of",
    "from_record",
    "to_record",
    "with_sidecars",
]

#: The keys a :class:`Resource` holds. Any other key of a record, a narrowed
#: licence or provenance, travels beside it as an extra.
CORE_KEYS = (k.NAME, k.PATH, k.BYTES, k.HASH, k.MEDIATYPE, k.SIDECARS)


@dataclass(frozen=True)
class Resource:
    """One file in a dataset, as described by the Data Package descriptor."""

    dataset: str
    name: str
    path: str
    bytes: int
    hash: str
    mediatype: str
    sidecars: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Logical identity: stable across tools, and the cache path."""
        return f"{self.dataset}/{self.path}"


def from_record(dataset: str, record: Mapping) -> Resource:
    """The resource a generated record describes.

    Trusts the record, because the build wrote it: one inventory holds 170,000
    of them, and reading one must cost no more than its keys. A record nobody
    vouches for goes through :func:`checked`.
    """
    return Resource(
        dataset=dataset,
        name=record[k.NAME],
        path=record[k.PATH],
        bytes=record[k.BYTES],
        hash=record[k.HASH],
        mediatype=record.get(k.MEDIATYPE, k.DEFAULT_MEDIATYPE),
        sidecars=tuple(record.get(k.SIDECARS, ())),
    )


def extras_of(record: Mapping) -> dict:
    """The keys of a record that a :class:`Resource` does not hold."""
    return {key: value for key, value in record.items() if key not in CORE_KEYS}


def to_record(resource: Resource, extras: Mapping | None = None) -> dict:
    """The record a descriptor keeps for ``resource``, with ``extras`` after it."""
    record = {
        k.NAME: resource.name,
        k.PATH: resource.path,
        k.BYTES: resource.bytes,
        k.HASH: resource.hash,
        k.MEDIATYPE: resource.mediatype,
        **(extras or {}),
    }
    if resource.sidecars:
        record[k.SIDECARS] = list(resource.sidecars)
    return record


def checked(dataset: str, record: object) -> Resource:
    """:func:`from_record` for a record nobody vouches for, or ValueError.

    A bundle's records are committed to a package repository and may have been
    edited by hand. Before a file is placed or trusted by one, its record must
    say where the file is, how big it is and what it hashes to, and every path
    in it must stay inside the dataset.
    """
    try:
        name, path, size, recorded = (
            record[k.NAME],
            record[k.PATH],
            record[k.BYTES],
            record[k.HASH],
        )
    except (KeyError, TypeError):
        raise ValueError(f"incomplete resource metadata for {dataset!r}") from None
    relative(path, "resource path")
    if (
        not isinstance(name, str)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
    ):
        raise ValueError(f"invalid resource metadata for {dataset}/{path}")
    if digest.expected(recorded) is None:
        raise ValueError(f"{dataset}/{path} needs its catalogue sha256 hash")
    sidecars = record.get(k.SIDECARS, [])
    if not isinstance(sidecars, list):
        # A ValueError like every other refusal here: the record is bad data,
        # and the caller turns each refusal into its own error.
        raise ValueError(f"invalid sidecars for {dataset}/{path}")  # noqa: TRY004
    for sidecar in sidecars:
        relative(sidecar, "sidecar path")
    return from_record(dataset, record)


def with_sidecars(
    resources: Iterable[Resource],
    resource_at: Callable[[str, str], Resource | None],
) -> tuple[dict[str, Resource], list[str]]:
    """``resources`` and every companion they need, and the companions not found.

    A shapefile is unreadable without its ``.shx`` and ``.dbf``, so a file
    never travels without the sidecars its record names, nor they without
    theirs. ``resource_at(dataset, path)`` looks a companion up in the dataset
    of the file that names it.

    Returns the resources by key, and the keys of companions that a record
    names but no record describes. What a missing companion means is the
    caller's to decide: a bundle refuses it, a selection takes what there is.
    """
    found: dict[str, Resource] = {}
    pending: list[Resource] = []
    for resource in resources:
        if resource.key not in found:
            found[resource.key] = resource
            pending.append(resource)
    missing: list[str] = []
    while pending:
        resource = pending.pop()
        for sidecar in resource.sidecars:
            key = f"{resource.dataset}/{sidecar}"
            if key in found or key in missing:
                continue
            companion = resource_at(resource.dataset, sidecar)
            if companion is None:
                missing.append(key)
                continue
            found[companion.key] = companion
            pending.append(companion)
    return found, missing
