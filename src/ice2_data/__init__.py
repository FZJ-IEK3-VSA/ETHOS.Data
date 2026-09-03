"""Shared data access for ICE-2 scientific software.

One institute-wide catalogue describes the datasets; each tool declares only
which slices it needs. Because every tool resolves against the same catalogue
into the same cache directory, a dataset used by several tools is downloaded
once.

    from ice2_data import fetch
    paths = fetch("onshore_wind_era5_europe", collections="collections.yaml")
"""

from __future__ import annotations

from pathlib import Path

from .access import AccessError, Location, locate
from .catalog import Catalog, Dataset, Resource, load_catalog
from .config import (
    ENV_VAR,
    Resolved,
    config_path,
    config_sources,
    dataset_roots,
    find_project_config,
    resolve_cache_dir,
    set_dataset_root,
    set_option,
    unset_dataset_root,
    unset_option,
)
from .fetch import DataFiles, cache_dir, download, local_path, plan
from .selection import Collections, load_collections

__all__ = [
    "Catalog",
    "Collections",
    "Dataset",
    "AccessError",
    "DataFiles",
    "ENV_VAR",
    "Location",
    "Resolved",
    "Resource",
    "cache_dir",
    "config_path",
    "config_sources",
    "download",
    "fetch",
    "fetch_one",
    "load_catalog",
    "load_collections",
    "local_path",
    "plan",
    "resolve",
    "dataset_roots",
    "find_project_config",
    "locate",
    "resolve_cache_dir",
    "set_dataset_root",
    "set_option",
    "unset_dataset_root",
    "unset_option",
]

__version__ = "0.1.0"


def resolve(collection: str, collections: str | Path, catalog: str | Catalog | None = None) -> list[Resource]:
    """List the resources a collection selects, without downloading anything."""
    return load_collections(collections, catalog=catalog).resolve(collection)


def fetch_one(
    key: str,
    catalog: str | Catalog,
    root: str | Path | None = None,
    progressbar: bool = False,
) -> Path:
    """Make a single named resource available and return its path.

    ``key`` is ``"<dataset>/<resource path>"`` -- the same key ``fetch`` returns.
    Useful when a workflow needs one known file rather than a whole collection.
    """
    loaded = catalog if isinstance(catalog, Catalog) else load_catalog(catalog)
    dataset_name, _, resource_path = key.partition("/")
    dataset = loaded.dataset(dataset_name)
    resource = dataset.resource_at(resource_path)
    if resource is None:
        raise KeyError(
            f"{key!r} is not in the catalogue. "
            f"{dataset_name!r} has {dataset.file_count} resources; "
            f"e.g. {', '.join(list(dataset.resources)[:3])}"
        )
    files = download(loaded, [resource], root=Path(root).expanduser() if root else None,
                     progressbar=progressbar)
    return files[resource.key]


def fetch(
    collection: str,
    collections: str | Path,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = True,
) -> DataFiles:
    """Make a collection available locally and return ``{key: Path}``.

    Keys are ``"<dataset>/<resource path>"``. Files already present and matching
    their recorded checksum are not re-downloaded -- including files another tool
    fetched earlier. Datasets with a configured local root are used in place.
    """
    loaded = load_collections(collections, catalog=catalog)
    resources = loaded.resolve(collection)
    return download(
        loaded.catalog,
        resources,
        root=Path(root).expanduser() if root else None,
        progressbar=progressbar,
    )
