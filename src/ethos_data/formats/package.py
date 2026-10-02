"""The files the build generates: ``datapackage.json``, its shards, ``datacatalog.json``.

Readers trust these files, because the build wrote them; the models are for
typed access, for the JSON Schemas, and for tests. What the build and
``publish`` must compute alike from them, the index row among it, is in
:mod:`.derived`, which needs no pydantic.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from . import keys as k
from .fields import field

__all__ = [
    "CatalogIndex",
    "IndexRow",
    "NamespaceRow",
    "PackageDescriptor",
    "ResourceRecord",
    "ShardEntry",
    "ShardFile",
]


class _Generated(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ResourceRecord(_Generated):
    """One file of a dataset's inventory."""

    name: str
    path: str
    bytes: int
    hash: str = field("hash", description='"sha256:<hex>", the convention pooch reads.')
    mediatype: str = "application/octet-stream"
    sidecars: list[str] = field(
        k.SIDECARS, [], description="Companion files that must travel with this one."
    )
    licenses: list[dict] | None = field(
        k.LICENSES, description="Present only on files a narrowed licence matched."
    )


class ShardEntry(_Generated):
    """One shard of a sharded inventory, as the descriptor lists it."""

    prefix: str
    path: str
    file_count: int = field(k.FILE_COUNT, 0)
    total_bytes: int = field(k.TOTAL_BYTES, 0)


class ShardFile(_Generated):
    """``shards/<prefix>.json``: one shard's resources."""

    name: str
    shard: str = field(k.SHARD, "")
    resources: list[ResourceRecord] = []


class PackageDescriptor(_Generated):
    """``datapackage.json``: a dataset's descriptor with its inventory or shard index."""

    schema_: str = field(k.SCHEMA, k.DATAPACKAGE_PROFILE)
    name: str
    title: str | None = None
    resources: list[ResourceRecord] | None = None
    shard_depth: int | None = field(k.SHARD_DEPTH)
    shards: list[ShardEntry] | None = field(k.SHARDS)
    namespace: bool = field(k.NAMESPACE, False)
    total_bytes: int = field(k.TOTAL_BYTES, 0)
    file_count: int = field(k.FILE_COUNT, 0)


class IndexRow(_Generated):
    """A dataset's row in ``datacatalog.json``: what is known without its descriptor."""

    name: str
    path: str
    title: str = ""
    version: str | int | float | None = None
    access: str = field(k.ACCESS, k.PUBLIC)
    visibility: str = field(k.VISIBILITY, k.PUBLIC)
    total_bytes: int = field(k.TOTAL_BYTES, 0)
    file_count: int = field(k.FILE_COUNT, 0)
    remote_prefix: str | None = field(k.REMOTE_PREFIX)
    license_status: str = field(k.LICENSE_STATUS, k.UNKNOWN)


class NamespaceRow(_Generated):
    """A family's row: a name to list and describe, nothing to fetch."""

    name: str
    path: str
    title: str = ""
    namespace: bool = field(k.NAMESPACE, True)
    total_bytes: int = field(k.TOTAL_BYTES, 0)
    file_count: int = field(k.FILE_COUNT, 0)


class CatalogIndex(_Generated):
    """``datacatalog.json``: ``catalog.yaml``'s keys and one row per dataset."""

    schema_: str = field(k.SCHEMA, k.DATACATALOG_PROFILE)
    name: str
    title: str | None = None
    publication_url: str | None = field(k.PUBLICATION_URL)
    catalog_role: str | None = field(k.CATALOG_ROLE)
    datasets: list[dict] = []
