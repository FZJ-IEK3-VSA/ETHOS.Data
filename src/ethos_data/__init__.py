"""Shared data access for ETHOS tools and workflows.

One institute-wide catalogue describes the datasets; each tool declares only
which slices it needs. Because every tool resolves against the same catalogue
into the same cache directory, a dataset used by several tools is downloaded
once.

    import ethos_data

    inputs = ethos_data.paths("onshore_wind", package="reskit", test=True)
    files = ethos_data.fetch("onshore_wind", package="reskit")
    clc = ethos_data.path("landcover/C3S-LC-L4-LCCS-Map-300m-P1Y-2018-v2.1.1.tif")

``paths`` is the call a workflow wants: the package maintainer names each
input the workflow takes (``era5``, ``gwa_100m``) in its ``collections.yaml``,
and the caller gets ``{name: absolute path}`` without knowing any resource
key. ``test=True`` selects the small fixtures a maintainer paired with the full
data, so an example runs in seconds and the same code runs on the real inputs.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .bundles import Bundle, BundleError, export_bundle, load_bundle
from .access import AccessError, Location, locate
from .catalog import (
    Catalog,
    CatalogUnavailable,
    Dataset,
    IncompleteCatalog,
    Resource,
    UnknownDataset,
    describe_catalog,
    load_catalog,
)
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
from .retrieval import DataFiles, NamedPaths, cache_dir, download, local_path, plan
from .materialize import materialize
from .linking import LinkError, link, unlink
from .selection import (
    CollectionError,
    Collections,
    CollectionsNotFound,
    UnknownCollection,
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
    "CatalogUnavailable",
    "CollectionError",
    "Collections",
    "CollectionsNotFound",
    "DEFAULT_CATALOG",
    "Dataset",
    "AccessError",
    "DataFiles",
    "ENV_VAR",
    "IncompleteCatalog",
    "Location",
    "Finding",
    "NamedPaths",
    "RESTRICTED_ENV_VAR",
    "Resolved",
    "Resource",
    "Roots",
    "STAGING_ENV_VAR",
    "UnknownCollection",
    "UnknownDataset",
    "apply_staging",
    "cache_dir",
    "classify_staged",
    "config_path",
    "config_sources",
    "download",
    "fetch",
    "fetch_one",
    "LinkError",
    "link",
    "unlink",
    "list_resources",
    "load_catalog",
    "load_collections",
    "local_path",
    "materialize",
    "package_collections",
    "path",
    "paths",
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
    collections: str | Path | None = None,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = False,
) -> Path:
    """The absolute local path of a file or folder, fetching it if necessary.

    ``key`` is ``"<dataset>/<path>"`` for one file -- a shapefile brings its
    sidecars along -- or ``"<dataset>/<folder>"``, ``"<dataset>"`` or a dataset
    family for a directory, in which case every file under it is fetched first.
    :func:`list_resources` says what is under a key without fetching.

    The catalogue is ``catalog`` if given, else ``$ETHOS_DATA_CATALOG`` or a
    configured one, else the version ``package``'s collections file -- or the
    file ``collections`` names -- pins, else the built-in public catalogue.
    """
    roots = Roots.coerce(root)
    loaded = _catalog_for(catalog, package, roots, collections=collections)
    name, inner = _split_key(loaded, key)
    resources, target = _select(loaded, name, inner, key)
    files = download(loaded, resources, root=roots, progressbar=progressbar)
    if target is not None:
        if target.key not in files:
            raise AccessError(f"{key!r} is not available on this machine.")
        return Path(os.path.abspath(files[target.key]))
    return Path(os.path.abspath(_directory_of(files, resources, name, inner, key)))


def list_resources(
    key: str,
    *,
    package: str | None = None,
    collections: str | Path | None = None,
    catalog: str | Catalog | None = None,
) -> list[Resource]:
    """The catalogue's files under a key, in key order, without fetching anything.

    The answer to "what is in this dataset, and what do I put after the slash
    to get one file?". ``key`` is a dataset, a family, or ``"<dataset>/<folder>"``;
    for a single file it is that file (with its sidecars). The catalogue is
    chosen exactly as :func:`path` chooses it.
    """
    loaded = _catalog_for(catalog, package, Roots.coerce(None), warn=False,
                          collections=collections)
    name, inner = _split_key(loaded, key)
    resources, _ = _select(loaded, name, inner, key)
    return sorted(resources, key=lambda r: r.key)


def resolve(
    collection: str,
    collections: str | Path | None = None,
    catalog: str | Catalog | None = None,
    *,
    package: str | None = None,
    test: bool = False,
) -> list[Resource]:
    """List the resources a collection selects, without downloading anything.

    ``test=True`` selects the collection's ``test`` variant where it has one.
    """
    source = _collections_file(collections, package)
    return load_collections(source, catalog=_configured_catalog(catalog)).resolve(
        collection, test=test
    )


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
    test: bool = False,
    skip_unavailable: bool | None = None,
) -> DataFiles:
    """Make a collection available locally and return ``{key: Path}``.

    Name the collections with ``package="reskit"`` -- the file an installed
    package registered -- or with ``collections=`` as a path. Keys are
    ``"<dataset>/<resource path>"``. Files already present and matching their
    recorded checksum are not re-downloaded -- including files another tool
    fetched earlier. Datasets with a configured local root are used in place.

    ``test=True`` selects the collection's small ``test`` variant where the
    maintainer defined one; the default is the full data. A collection
    without variants is the same either way. The result's ``.named`` holds the
    collection's ``paths`` as ``{handle: Path}`` -- see :func:`paths`.

    ``skip_unavailable`` decides what happens to licensed data this machine
    cannot reach: ``True`` leaves it out of the result (and out of ``.named``)
    with a warning, ``False`` raises, ``None`` takes the configured answer.
    """
    roots = Roots.coerce(root)
    loaded = load_collections(
        _collections_file(collections, package),
        catalog=_configured_catalog(catalog),
        roots=roots,
    )
    return _fetch_loaded(loaded, collection, test, roots, progressbar, skip_unavailable)


def paths(
    collection: str,
    collections: str | Path | None = None,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = True,
    *,
    package: str | None = None,
    test: bool = False,
    skip_unavailable: bool | None = None,
) -> NamedPaths:
    """The inputs a collection names, as ``{handle: absolute Path}``, fetched.

    A collection's ``paths:`` maps handles the workflow understands to
    catalogue keys -- ``era5: reskit-test-data/era5`` for a folder,
    ``gwa_100m: reskit-test-data/global-wind-atlas/gwa100-like.tif`` for a
    file. This fetches the collection like :func:`fetch` and returns those
    handles resolved to where the data is on this machine, so a workflow is
    fed without its caller knowing a single resource key::

        inputs = ethos_data.paths("onshore_wind", package="reskit", test=True)
        simulate(era5_path=inputs["era5"], gwa_100m_path=inputs["gwa_100m"])

    ``test=True`` selects the collection's ``test`` variant; the handles are
    the same in both variants, so the call above runs unchanged on the full
    data once ``test`` is dropped. A collection that declares no ``paths`` is
    refused here -- :func:`fetch` returns its files by key. Under
    ``skip_unavailable`` a handle whose data this machine cannot reach is left
    out, with a warning naming it, exactly as the file is left out of
    :func:`fetch`'s result.
    """
    files = fetch(
        collection, collections, catalog, root, progressbar,
        package=package, test=test, skip_unavailable=skip_unavailable,
    )
    if not files.named and not files.named.omitted:
        raise CollectionError(
            f"collection {collection!r} declares no named paths -- nothing under 'paths:' in "
            f"its definition. fetch({collection!r}, ...) returns its files by resource key; "
            f"ask the package maintainer to name the workflow's inputs."
        )
    return files.named


def _fetch_loaded(
    loaded: Collections,
    collection: str,
    test: bool,
    roots: Roots,
    progressbar: bool,
    skip_unavailable: bool | None,
) -> DataFiles:
    """Resolve, check, download, name -- the sequence behind ``fetch`` and the CLI.

    One function so the command line cannot drift from the API: whatever
    ``ethos_data.fetch`` refuses before downloading, ``ethos-data fetch``
    refuses too.
    """
    resources = loaded.resolve(collection, test=test)
    # Checked before anything is downloaded: a handle naming a file the
    # collection does not include is a mistake in collections.yaml, and the
    # maintainer should hear about it before a 40 GB transfer, not after.
    targets = _named_targets(loaded, collection, test, resources)
    files = download(
        loaded.catalog,
        resources,
        root=roots,
        progressbar=progressbar,
        skip_unavailable=skip_unavailable,
    )
    files.named = _named_paths(targets, files, collection)
    return files


@dataclass(frozen=True)
class _NamedTarget:
    """One ``paths`` handle, resolved against the catalogue but not yet to disk."""

    handle: str
    key: str
    #: The dataset (or family) the key splits into, and the path inside it.
    dataset: str
    inner: str
    #: Set when the key names one file; then ``under`` is empty.
    file: Resource | None
    #: The collection's selected resources below a folder, dataset or family key.
    under: tuple[Resource, ...]


def _named_targets(
    loaded: Collections, collection: str, test: bool, resources: list[Resource]
) -> list[_NamedTarget]:
    """Check every ``paths`` handle against the catalogue and the selection.

    A handle naming a file must name one the collection includes -- otherwise
    the file it points at would never be fetched. A handle naming a folder must
    have at least one selected file beneath it; the folder is *where the
    collection's files are*, not a request for everything the catalogue holds
    there, so ``era5: reskit-test-data/era5`` with ``files: ["100m_*.nc"]``
    means the directory holding those two files.
    """
    named = loaded.named_keys(collection, test)
    selected = {resource.key: resource for resource in resources}
    targets = []
    for handle, key in named.items():
        try:
            dataset, inner = _split_key(loaded.catalog, key)
        except KeyError as error:
            raise _not_in_catalogue(collection, handle, key, error) from error
        # Answered from the selection first, so that checking a dataset-level
        # handle on a sharded dataset does not pull in every shard the include
        # patterns deliberately avoided. The catalogue is only consulted to
        # tell a mistake in `paths` from a mistake in `include`.
        file = selected.get(key)
        if file is not None:
            targets.append(_NamedTarget(handle, file.key, dataset, inner, file, ()))
            continue
        if inner:
            unselected = loaded.catalog.dataset(dataset).resource_at(inner)
            if unselected is not None:
                raise CollectionError(
                    f"collection {collection!r}: paths.{handle} names the file {key!r}, which "
                    f"the collection does not include; add it under 'include:' "
                    f"(dataset: {dataset}, files: [{unselected.path!r}])"
                )
        prefix = key + "/"
        under = tuple(r for r in resources if r.key.startswith(prefix))
        if not under:
            try:
                _select(loaded.catalog, dataset, inner, key)
            except KeyError as error:
                raise _not_in_catalogue(collection, handle, key, error) from error
            raise CollectionError(
                f"collection {collection!r}: paths.{handle} names the folder {key!r}, but the "
                f"collection includes no file under it; the folder would be empty"
            )
        targets.append(_NamedTarget(handle, key, dataset, inner, None, under))
    return targets


def _not_in_catalogue(collection: str, handle: str, key: str, error: KeyError) -> CollectionError:
    message = error.args[0] if error.args else str(error)
    return CollectionError(
        f"collection {collection!r}: paths.{handle} names {key!r}, which is not in "
        f"the catalogue. {message}"
    )


def _named_paths(targets: list[_NamedTarget], files: DataFiles, collection: str) -> NamedPaths:
    """Where each handle ended up on this machine, read off the fetched files.

    A handle whose data this machine cannot reach is left out and named in a
    warning -- the same contract ``skip_unavailable`` gives the files
    themselves: absent from the mapping, never a path to nothing. Without
    ``skip_unavailable`` the unreachable data has already raised before this.
    """
    named = NamedPaths(collection=collection)
    for target in targets:
        if target.file is not None:
            local = files.get(target.file.key)
            if local is None:
                named.omitted.append(target.handle)
                continue
            named[target.handle] = Path(os.path.abspath(local))
            continue
        available = [r for r in target.under if r.key in files]
        if not available:
            named.omitted.append(target.handle)
            continue
        directory = _directory_of(files, available, target.dataset, target.inner, target.key)
        named[target.handle] = Path(os.path.abspath(directory))
    if named.omitted:
        warnings.warn(
            f"collection {collection!r}: the named path(s) {', '.join(named.omitted)} are not "
            f"available on this machine and have been left out -- the mapping has no entry "
            f"for them.",
            UserWarning,
            stacklevel=4,
        )
    return named


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
    catalog: str | Catalog | None,
    package: str | None,
    roots: Roots,
    warn: bool = True,
    collections: str | Path | None = None,
) -> Catalog:
    """The catalogue a key is looked up in, with the staging overlay applied.

    A package's collections file, or one named directly, contributes only its
    pin -- and only below an explicit or configured catalogue, the same order
    ``fetch`` applies. So ``path`` and ``fetch`` given the same ``-c`` file
    read the same catalogue.
    """
    # Refused whatever catalogue wins: an argument that is silently ignored
    # under one configuration and honoured under another is a bug waiting for
    # the machine where the configuration differs.
    if package is not None and collections is not None:
        raise TypeError("give collections= or package=, not both")
    if isinstance(catalog, Catalog):
        # A view that already carries the overlay -- ``load_collections(...)
        # .catalog`` handed back in -- must not be overlaid, and warned about,
        # again.
        if catalog.staged:
            return catalog
        loaded = catalog
    else:
        location = _configured_catalog(catalog)
        if location is None:
            source = package_collections(package) if package is not None else collections
            if source is not None:
                # The overlay is applied once, below, so that ``warn`` means the
                # same thing whichever way the catalogue was chosen.
                loaded = load_collections(source, roots=roots, include_staging=False).catalog
                return with_staging(loaded, roots, warn=warn)
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
