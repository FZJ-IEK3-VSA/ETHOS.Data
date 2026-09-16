"""Shared data access for ETHOS tools and workflows.

One institute-wide catalogue describes the datasets; each tool declares only
which slices it needs. Because every tool resolves against the same catalogue
into the same cache directory, a dataset used by several tools is downloaded
once.

    import ethos_data

    data = ethos_data.collections("reskit/data/collections.yaml", tool="reskit")
    inputs = data.paths("onshore_wind", test=True)    # {handle: Path}
    files = data.fetch("onshore_wind")                # {key: Path}
    clc = data.catalog.path("landcover/C3S-LC-L4-LCCS-Map-300m-P1Y-2018-v2.1.1.tif")

Two kinds of name, two handles. A **collection** is what a tool's workflow
needs, named once by its maintainer in the tool's ``collections.yaml``;
:func:`collections` loads that file and ``paths`` hands the workflow
``{handle: absolute path}`` without it knowing a single resource key.
``test=True`` selects the small fixtures the maintainer paired with the full
data, so an example runs in seconds and the same code runs on the real inputs.
A **key** (``"<dataset>/<path>"``) names one dataset, folder or file in the
catalogue; :func:`catalog` -- or a handle's ``.catalog``, for the version a tool
pins -- answers those with ``path`` and ``resources``.

A tool builds its handle once, from the file beside its own code, and exposes
the same commands as its own console script with :meth:`Collections.main`;
nothing is registered anywhere. See :func:`collections`.
"""

from __future__ import annotations

from pathlib import Path

from .bundles import Bundle, BundleError, export_bundle, load_bundle
from .access import AccessError, Location, locate
from .catalogs import (
    Catalog,
    CatalogUnavailable,
    Dataset,
    IncompleteCatalog,
    Resource,
    UnknownDataset,
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
)
from .staging import apply_staging, classify_staged, staged_only
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
    "catalog",
    "classify_staged",
    "collections",
    "config_path",
    "config_sources",
    "download",
    "fetch",
    "LinkError",
    "link",
    "unlink",
    "load_catalog",
    "load_collections",
    "local_path",
    "materialize",
    "paths",
    "plan",
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
    "tool_main",
    "unset_dataset_root",
    "unset_option",
    "verify",
]

__version__ = "0.1.1"


def collections(
    path: str | Path,
    *,
    tool: str | None = None,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
) -> Collections:
    """A handle on a collections file: what a tool's workflows need, by name.

    The object a tool builds once, from the file beside its own code, and then
    calls ``fetch``, ``paths``, ``resolve`` and ``plan`` on::

        COLLECTIONS_FILE = Path(__file__).with_name("collections.yaml")
        data = ethos_data.collections(COLLECTIONS_FILE, tool="reskit")
        inputs = data.paths("onshore_wind", test=True)

    ``tool`` is the tool's short name, used in messages and as the default
    name of its command (``reskit-data``; see :meth:`Collections.main`). The
    catalogue is ``catalog`` if given, else ``$ETHOS_DATA_CATALOG`` or a
    configured one, else the version the file pins, else the built-in public
    catalogue -- so a user can repoint every tool at once without any tool
    knowing. ``root`` overrides the public cache directory. The file is read
    once, here, and ``.catalog`` is the catalogue it resolved to, for access
    by key.
    """
    roots = Roots.coerce(root) if root is not None else None
    return load_collections(
        path, catalog=_configured_catalog(catalog), roots=roots, tool=tool
    )


def catalog(
    location: str | Catalog | None = None,
    *,
    root: str | Path | None = None,
) -> Catalog:
    """A handle on a catalogue, for access by key rather than by collection.

    ``location`` is a ``datacatalog.json`` path or URL; without one, the
    catalogue is ``$ETHOS_DATA_CATALOG`` or a configured one, else the
    built-in public catalogue. The staging overlay is applied once, here. A
    tool's pinned catalogue is ``ethos_data.collections(...).catalog``::

        era5 = ethos_data.catalog().path("era5/2015")
        files = ethos_data.catalog().resources("global-wind-atlas-v3")
    """
    roots = Roots.coerce(root)
    if isinstance(location, Catalog):
        return location.overlaid(roots)
    chosen = _configured_catalog(location)
    return load_catalog(chosen or DEFAULT_CATALOG).overlaid(roots)


def tool_main(
    path: str | Path,
    *,
    tool: str | None = None,
    prog: str | None = None,
    catalog: str | None = None,
    argv: list[str] | None = None,
) -> int:
    """The body of a tool's own data command: ``ethos-data``'s collection
    commands bound to the file the tool ships.

    Two lines in the tool make the command::

        # reskit/data/__init__.py
        def main(argv=None):
            return ethos_data.tool_main(COLLECTIONS_FILE, tool="reskit", argv=argv)

        # pyproject.toml
        [project.scripts]
        reskit-data = "reskit.data:main"

    ``list``, ``info``, ``plan``, ``fetch``, ``paths`` and ``verify`` for the
    file's collections, ``path`` and ``ls`` against the catalogue it pins,
    ``bundle`` and ``config``. ``prog`` names the command in help and messages
    (default ``<tool>-data``); ``catalog`` is the tool's own catalogue override,
    applied below ``--catalog`` and above ``$ETHOS_DATA_CATALOG``. The handle
    is built only for the commands that need one, so ``--help`` and ``config
    show`` never load the catalogue.
    """
    from .cli import run_tool

    return run_tool(path, tool=tool, prog=prog, catalog=catalog, argv=argv)


def resolve(
    collection: str,
    collections: str | Path,
    catalog: str | Catalog | None = None,
    *,
    test: bool = False,
) -> list[Resource]:
    """List the resources a collection in the file ``collections`` selects,
    without downloading anything.

    ``test=True`` selects the collection's ``test`` variant where it has one.
    One-call form of ``ethos_data.collections(collections).resolve(...)``.
    """
    return _handle(collections, catalog).resolve(collection, test=test)


def fetch(
    collection: str,
    collections: str | Path,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = True,
    *,
    test: bool = False,
    skip_unavailable: bool | None = None,
) -> DataFiles:
    """Make a collection in the file ``collections`` available locally.

    Returns ``{key: Path}``; see :meth:`Collections.fetch` for the details.
    One-call form of ``ethos_data.collections(collections).fetch(...)`` -- a
    tool that fetches more than once builds the handle instead, so the file
    and the catalogue are read once.
    """
    return _handle(collections, catalog, root).fetch(
        collection,
        test=test,
        progressbar=progressbar,
        skip_unavailable=skip_unavailable,
    )


def paths(
    collection: str,
    collections: str | Path,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = True,
    *,
    test: bool = False,
    skip_unavailable: bool | None = None,
) -> NamedPaths:
    """The inputs a collection names, as ``{handle: absolute Path}``, fetched.

    See :meth:`Collections.paths`. One-call form of
    ``ethos_data.collections(collections).paths(...)``.
    """
    return _handle(collections, catalog, root).paths(
        collection,
        test=test,
        progressbar=progressbar,
        skip_unavailable=skip_unavailable,
    )


def _handle(
    source: str | Path | Collections,
    catalog: str | Catalog | None,
    root: str | Path | None = None,
) -> Collections:
    if isinstance(source, Collections):
        return source
    return collections(source, catalog=catalog, root=root)


def _configured_catalog(catalog: str | Catalog | None) -> str | Catalog | None:
    """An explicit catalogue, else ``$ETHOS_DATA_CATALOG`` or a configured one.

    ``None`` leaves the choice to the collections file's pin, and after that to
    the built-in public catalogue.
    """
    if catalog is not None:
        return catalog
    configured = resolve_catalog()
    return configured[0] if configured else None
