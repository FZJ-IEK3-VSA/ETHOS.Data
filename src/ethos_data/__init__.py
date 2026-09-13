"""Shared data access for ETHOS tools and workflows.

One institute-wide catalogue describes the datasets; each tool declares only
which slices it needs. Because every tool resolves against the same catalogue
into the same cache directory, a dataset used by several tools is downloaded
once.

    import ethos_data

    placements = ethos_data.path("reskit-test-data/placements/turbine_placements.csv")
    files = ethos_data.fetch("onshore_wind", package="reskit")
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from .bundles import Bundle, BundleError, export_bundle, load_bundle
from .access import AccessError, Location, locate
from .catalog import Catalog, Dataset, Resource, UnknownDataset, describe_catalog, load_catalog
from .config import (
    CATALOG_ENV_VAR,
    DEFAULT_CATALOG,
    ENV_VAR,
    RESTRICTED_ENV_VAR,
    STAGING_ENV_VAR,
    Resolved,
    Roots,
    config_path,
    config_sources,
    dataset_roots,
    find_project_config,
    resolve_cache_dir,
    resolve_catalog,
    resolve_public_cache,
    resolve_restricted_cache,
    resolve_roots,
    resolve_skip_unavailable,
    resolve_staging_cache,
    set_dataset_root,
    set_option,
    unset_dataset_root,
    unset_option,
)
from .retrieval import DataFiles, cache_dir, download, local_path, plan
from .materialize import materialize
from .selection import (
    Collections,
    CollectionsNotFound,
    load_collections,
    package_collections,
    registered_packages,
)
from .staging import apply_staging, classify_staged, staged_only, with_staging
from .verify import Finding, repair, verify

__all__ = [
    "Bundle",
    "BundleError",
    "export_bundle",
    "load_bundle",
    "CATALOG_ENV_VAR",
    "Catalog",
    "Collections",
    "CollectionsNotFound",
    "DEFAULT_CATALOG",
    "Dataset",
    "AccessError",
    "DataFiles",
    "ENV_VAR",
    "Location",
    "Finding",
    "RESTRICTED_ENV_VAR",
    "Resolved",
    "Resource",
    "Roots",
    "STAGING_ENV_VAR",
    "UnknownDataset",
    "apply_staging",
    "cache_dir",
    "classify_staged",
    "config_path",
    "config_sources",
    "download",
    "fetch",
    "fetch_one",
    "load_catalog",
    "load_collections",
    "local_path",
    "materialize",
    "package_collections",
    "path",
    "plan",
    "registered_packages",
    "repair",
    "resolve",
    "resolve_public_cache",
    "resolve_restricted_cache",
    "resolve_roots",
    "resolve_skip_unavailable",
    "resolve_staging_cache",
    "dataset_roots",
    "find_project_config",
    "locate",
    "resolve_cache_dir",
    "set_dataset_root",
    "staged_only",
    "set_option",
    "unset_dataset_root",
    "unset_option",
    "verify",
]

__version__ = "0.1.0"


def path(
    key: str,
    *,
    package: str | None = None,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = False,
) -> Path:
    """The absolute local path of a file or folder, fetching it if necessary.

    ``key`` is ``"<dataset>/<path>"`` for one file -- a shapefile brings its
    sidecars along -- or ``"<dataset>/<folder>"``, ``"<dataset>"`` or a dataset
    family for a directory, in which case every file under it is fetched first.

    The catalogue is ``catalog`` if given, else ``$ETHOS_DATA_CATALOG`` or a
    configured one, else the version ``package``'s collections file pins, else
    the built-in public catalogue.
    """
    roots = Roots.coerce(root)
    loaded = _catalog_for(catalog, package, roots)
    name, inner = _split_key(loaded, key)
    resources, target = _select(loaded, name, inner, key)
    files = download(loaded, resources, root=roots, progressbar=progressbar)
    if target is not None:
        if target.key not in files:
            raise AccessError(f"{key!r} is not available on this machine.")
        return Path(os.path.abspath(files[target.key]))
    return Path(os.path.abspath(_directory_of(files, resources, name, inner, key)))


def resolve(
    collection: str,
    collections: str | Path | None = None,
    catalog: str | Catalog | None = None,
    *,
    package: str | None = None,
) -> list[Resource]:
    """List the resources a collection selects, without downloading anything."""
    source = _collections_file(collections, package)
    return load_collections(source, catalog=_configured_catalog(catalog)).resolve(collection)


def fetch_one(
    key: str,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = False,
) -> Path:
    """Make a single named resource available and return its path.

    ``key`` is ``"<dataset>/<resource path>"`` -- the same key ``fetch`` returns.
    :func:`path` does the same and also accepts folders.
    """
    roots = Roots.coerce(root)
    loaded = _catalog_for(catalog, None, roots, warn=False)
    name, inner = _split_key(loaded, key)
    dataset = loaded.dataset(name)
    resource = dataset.resource_at(inner) if inner else None
    if resource is None:
        raise KeyError(
            f"{key!r} is not in the catalogue. "
            f"{name!r} has {dataset.file_count} resources; "
            f"e.g. {', '.join(list(dataset.resources)[:3])}"
        )
    files = download(loaded, [resource], root=roots, progressbar=progressbar)
    return files[resource.key]


def fetch(
    collection: str,
    collections: str | Path | None = None,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = True,
    *,
    package: str | None = None,
) -> DataFiles:
    """Make a collection available locally and return ``{key: Path}``.

    Name the collections with ``package="reskit"`` -- the file an installed
    package registered -- or with ``collections=`` as a path. Keys are
    ``"<dataset>/<resource path>"``. Files already present and matching their
    recorded checksum are not re-downloaded -- including files another tool
    fetched earlier. Datasets with a configured local root are used in place.
    """
    roots = Roots.coerce(root)
    loaded = load_collections(
        _collections_file(collections, package),
        catalog=_configured_catalog(catalog),
        roots=roots,
    )
    resources = loaded.resolve(collection)
    return download(
        loaded.catalog,
        resources,
        root=roots,
        progressbar=progressbar,
    )


def _collections_file(collections: str | Path | None, package: str | None) -> str | Path:
    if collections is not None and package is not None:
        raise TypeError("give collections= or package=, not both")
    if package is not None:
        return package_collections(package)
    if collections is None:
        raise TypeError(
            "say which collections to use: package='reskit' for the ones an "
            "installed package ships, or collections='collections.yaml' for a file"
        )
    return collections


def _configured_catalog(catalog: str | Catalog | None) -> str | Catalog | None:
    """An explicit catalogue, else ``$ETHOS_DATA_CATALOG`` or a configured one.

    ``None`` leaves the choice to the collections file's pin, and after that to
    the built-in public catalogue.
    """
    if catalog is not None:
        return catalog
    configured = resolve_catalog()
    return configured[0] if configured else None


def _catalog_for(
    catalog: str | Catalog | None, package: str | None, roots: Roots, warn: bool = True
) -> Catalog:
    """The catalogue a key is looked up in, with the staging overlay applied."""
    if isinstance(catalog, Catalog):
        loaded = catalog
    else:
        location = _configured_catalog(catalog)
        if location is None and package is not None:
            return load_collections(package_collections(package), roots=roots).catalog
        loaded = load_catalog(location or DEFAULT_CATALOG)
    return with_staging(loaded, roots, warn=warn)


def _split_key(catalog: Catalog, key: str) -> tuple[str, str]:
    """Split a key into the dataset it names and the path inside that dataset.

    Dataset names can contain "/" themselves -- ``reskit-test-data/era5`` is a
    member of the ``reskit-test-data`` family -- so the longest dataset name
    that prefixes the key wins, not whatever precedes the first slash.
    """
    key = key.strip("/")
    if key in catalog.datasets:
        return key, ""
    parts = key.split("/")
    for cut in range(len(parts) - 1, 0, -1):
        name = "/".join(parts[:cut])
        dataset = catalog.datasets.get(name)
        if dataset is not None and not dataset.namespace:
            return name, "/".join(parts[cut:])
    catalog.dataset(parts[0])  # an unknown name raises, listing what there is
    members = ", ".join(d.name for d in catalog.members_of(parts[0])) or "none"
    raise UnknownDataset(
        f"{key!r} names no dataset in the {describe_catalog(catalog.descriptor, catalog.location)}: "
        f"{parts[0]!r} is a family, and none of its members ({members}) starts the key."
    )


def _select(
    catalog: Catalog, name: str, inner: str, key: str
) -> tuple[list[Resource], Resource | None]:
    """The resources to fetch for a key, and the one file it names, if it names one."""
    if not inner:
        resources = [r for member in catalog.members_of(name) for r in member.resources.values()]
        if not resources:
            raise KeyError(f"{key!r} has no files in the catalogue")
        return resources, None
    dataset = catalog.dataset(name)
    resource = dataset.resource_at(inner)
    if resource is not None:
        sidecars = [dataset.resource_at(sidecar) for sidecar in resource.sidecars]
        return [resource, *(s for s in sidecars if s is not None)], resource
    # Not a file, so a folder -- matched on a directory boundary, so that
    # "merra-like" means the folder and not also the sibling "merra-like.nc4".
    prefix = inner + "/"
    under = [r for p, r in dataset.resources_matching([prefix + "**"]).items()
             if p.startswith(prefix)]
    if not under:
        raise KeyError(
            f"{key!r} is not in the catalogue: {name!r} has no file or folder {inner!r}"
        )
    return sorted(under, key=lambda r: r.key), None


def _directory_of(
    files: DataFiles, resources: list[Resource], name: str, inner: str, key: str
) -> Path:
    """Where a folder, a dataset or a family ended up on this machine.

    Read off the files themselves rather than off a root setting: a dataset may
    come from the public cache, the restricted cache, staging or its own root,
    and each returned path already says which.
    """
    found = set()
    for resource in resources:
        local = files.get(resource.key)
        if local is None:
            continue
        # Up from the file to its dataset's directory, then from a member up to
        # the family the key named (reskit-test-data/era5 -> reskit-test-data).
        levels = len(PurePosixPath(resource.path).parts) + resource.dataset.count("/") - name.count("/")
        directory = Path(local)
        for _ in range(levels):
            directory = directory.parent
        found.add(directory)
    if not found:
        raise AccessError(f"nothing under {key!r} is available on this machine.")
    if len(found) > 1:
        raise AccessError(
            f"{key!r} is spread over {len(found)} directories "
            f"({', '.join(sorted(map(str, found)))}); ask for its members one at a time, "
            f"or use fetch() for the individual files."
        )
    base = found.pop()
    return base / inner if inner else base
