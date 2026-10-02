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


_ACCESS_ENUM = {"enum": list(k.ACCESS_CLASSES)}


class ResourceRecord(_Generated):
    """One file of a dataset's inventory."""

    name: str = field(
        k.NAME, ..., description="Unique within the dataset; derived from the path."
    )
    path: str = field(
        k.PATH, ..., description="Relative to the dataset's folder, with `/`."
    )
    bytes: int = field(k.BYTES, ..., description="The file's size.")
    hash: str = field(
        k.HASH,
        description="`sha256:<hex>`, the convention pooch reads; a bare digest is read the same.",
    )
    mediatype: str = field(
        k.MEDIATYPE, k.DEFAULT_MEDIATYPE, description="The file's media type."
    )
    sidecars: list[str] = field(
        k.SIDECARS, [], description="Companion files that must travel with this one."
    )
    licenses: list[dict] | None = field(
        k.LICENSES, description="Present only on files a narrowed licence matched."
    )
    revision: int | None = field(
        k.REVISION,
        description="The revision the file's bytes were published in, when not the first.",
    )


class ShardEntry(_Generated):
    """One shard of a sharded inventory, as the descriptor lists it."""

    prefix: str = field(
        k.PREFIX,
        ...,
        description="The directory the shard holds; `_root` for top-level files.",
    )
    path: str = field(
        k.PATH, ..., description="The shard's file, relative to the dataset's."
    )
    file_count: int = field(k.FILE_COUNT, 0, description="The files in the shard.")
    total_bytes: int = field(k.TOTAL_BYTES, 0, description="Their size together.")


class ShardFile(_Generated):
    """``shards/<prefix>.json``: one shard's resources."""

    name: str = field(k.NAME, ..., description="The dataset's name.")
    shard: str = field(k.SHARD, "", description="The prefix this shard holds.")
    resources: list[ResourceRecord] = field(
        k.RESOURCES, [], description="The shard's files."
    )


class PackageDescriptor(_Generated):
    """``datapackage.json``: a dataset's descriptor with its inventory or shard index."""

    schema_: str = field(
        k.SCHEMA, k.DATAPACKAGE_PROFILE, description="The Data Package profile."
    )
    name: str = field(k.NAME, ..., description="The dataset's name.")
    title: str | None = field(k.TITLE, description="From `dataset.yaml`.")
    resources: list[ResourceRecord] | None = field(
        k.RESOURCES, description="Every file of the dataset, unless it is sharded."
    )
    shard_depth: int | None = field(
        k.SHARD_DEPTH,
        description="With `ethos:shards`: the depth the inventory is split at.",
    )
    shards: list[ShardEntry] | None = field(
        k.SHARDS, description="Instead of `resources`: the shards of the inventory."
    )
    namespace: bool = field(
        k.NAMESPACE, False, description="A family's descriptor: no files of its own."
    )
    total_bytes: int = field(k.TOTAL_BYTES, 0, description="The size of all files.")
    file_count: int = field(k.FILE_COUNT, 0, description="How many files there are.")
    revision: int | None = field(
        k.REVISION,
        description="Which revision of the dataset this is, when not the first.",
    )
    superseded_by: list[str] | None = field(
        k.SUPERSEDED_BY,
        description="The datasets whose ethos:supersedes names this one.",
    )


class IndexRow(_Generated):
    """A dataset's row in ``datacatalog.json``: what is known without its descriptor."""

    name: str = field(k.NAME, ..., description="The dataset's name.")
    path: str = field(
        k.PATH, ..., description="Its `datapackage.json`, relative to the index."
    )
    title: str = field(k.TITLE, "", description="Its title.")
    version: str | int | float | None = field(
        k.VERSION,
        description="The publisher's release string; absent when none is recorded.",
    )
    access: str = field(
        k.ACCESS, k.PUBLIC, description="Who may read the bytes.", schema=_ACCESS_ENUM
    )
    visibility: str = field(
        k.VISIBILITY,
        k.PUBLIC,
        description="Whether the published catalogue lists it.",
        schema={"enum": list(k.VISIBILITIES)},
    )
    total_bytes: int = field(k.TOTAL_BYTES, 0, description="The size of all its files.")
    file_count: int = field(k.FILE_COUNT, 0, description="How many files it has.")
    remote_prefix: str | None = field(
        k.REMOTE_PREFIX, description="Its folder on the store."
    )
    license_status: str = field(
        k.LICENSE_STATUS,
        k.UNKNOWN,
        description="Whether somebody has read its terms.",
        schema={"enum": list(k.LICENSE_STATUSES)},
    )
    revision: int | None = field(
        k.REVISION,
        description="The revision this release names, when not the first; the cache "
        "entry is `<name>@<revision>`.",
    )
    supersedes: str | None = field(k.SUPERSEDES, description="The dataset it replaces.")
    superseded_by: list[str] | None = field(
        k.SUPERSEDED_BY, description="The datasets that replace it."
    )


class NamespaceRow(_Generated):
    """A family's row: a name to list and describe, nothing to fetch."""

    name: str = field(k.NAME, ..., description="The family's name.")
    path: str = field(
        k.PATH, ..., description="Its `datapackage.json`, relative to the index."
    )
    title: str = field(k.TITLE, "", description="Its title.")
    namespace: bool = field(k.NAMESPACE, True, description="Always true: a family.")
    total_bytes: int = field(
        k.TOTAL_BYTES, 0, description="Its members' size together."
    )
    file_count: int = field(k.FILE_COUNT, 0, description="Its members' files together.")


class CatalogIndex(_Generated):
    """``datacatalog.json``: ``catalog.yaml``'s keys and one row per dataset."""

    schema_: str = field(
        k.SCHEMA, k.DATACATALOG_PROFILE, description="The Data Catalog profile."
    )
    name: str = field(
        k.NAME, ..., description="From `catalog.yaml`, as are the keys below."
    )
    title: str | None = field(k.TITLE, description="A short human-readable title.")
    description: str | None = field(
        k.DESCRIPTION, description="What the catalogue is for."
    )
    publication_url: str | None = field(
        k.PUBLICATION_URL, description="Root of the public data store."
    )
    contact: str | None = field(k.CONTACT, description="Team or username.")
    catalog_role: str | None = field(
        k.CATALOG_ROLE,
        description="`source` in the source catalogue; `publish` writes `published`.",
        schema={"enum": list(k.CATALOG_ROLES)},
    )
    version: str | None = field(
        k.VERSION,
        description="The release this index is.",
        schema={"pattern": r"^v\d{4}\.\d{2}\.\d+$"},
    )
    releases: list[str] | None = field(
        k.RELEASES,
        description="In the published index: every public release, oldest first, this one included.",
    )
    datasets: list[dict] = field(
        k.DATASETS, [], description="One row per dataset and per family."
    )
