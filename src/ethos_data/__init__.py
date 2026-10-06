"""Shared data access for ETHOS tools and workflows.

One institute-wide catalogue describes the datasets; each tool declares only
which slices it needs. Because every tool resolves against the same catalogue
into the same cache directory, a dataset used by several tools is downloaded
once.

    import ethos_data

    data = ethos_data.collections("mytool/data/collections.yaml", tool="mytool")
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
catalogue; :func:`catalog` -- or a handle's ``.catalog``, for the release a
tool's bounds admit -- answers those with ``path`` and ``resources``.

A tool builds its handle once, from the file beside its own code, and exposes
the same commands as its own console script with :meth:`Collections.main`;
nothing is registered anywhere. See :func:`collections`.
"""

from __future__ import annotations

from pathlib import Path

from .access import Location, locate
from .bundles import Bundle, export_bundle, load_bundle
from .catalogs import (
    Catalog,
    Dataset,
    catalog_for,
    load_catalog,
)
from .config import (
    CATALOG_ENV_VAR,
    CONFIG_ENV_VAR,
    DEFAULT_CATALOG,
    ENV_VAR,
    RESTRICTED_ENV_VAR,
    STAGING_ENV_VAR,
    Roots,
    Settings,
    add_restricted_cache,
    config_path,
    read_settings,
    remove_restricted_cache,
    set_cache,
    set_option,
    unset_option,
)
from .errors import (
    AccessError,
    BundleError,
    CatalogueRootError,
    CatalogUnavailable,
    CatalogVersionError,
    CollectionError,
    ConfigurationError,
    DescriptorError,
    DownloadError,
    EthosDataError,
    IncompleteCatalog,
    LinkError,
    MaintenanceError,
    NotFetched,
    PublishError,
    StagingError,
    TransitionError,
    UnknownCollection,
    UnknownDataset,
    UnknownKey,
    UploadError,
)
from .linking import link, unlink
from .materialize import materialize
from .model.resource import Resource
from .retrieval import DataFiles, NamedPaths, download, plan
from .selection import Collections, load_collections
from .selftest import EXAMPLE_COLLECTIONS, run_selftest
from .staging import classify_staged, staged_only
from .verify import Finding, repair, verify

__all__ = [
    "CatalogueRootError",
    "ConfigurationError",
    "DescriptorError",
    "DownloadError",
    "EthosDataError",
    "MaintenanceError",
    "NotFetched",
    "PublishError",
    "StagingError",
    "TransitionError",
    "UnknownKey",
    "UploadError",
    "Bundle",
    "BundleError",
    "export_bundle",
    "load_bundle",
    "CATALOG_ENV_VAR",
    "CONFIG_ENV_VAR",
    "Catalog",
    "CatalogUnavailable",
    "CatalogVersionError",
    "CollectionError",
    "Collections",
    "DEFAULT_CATALOG",
    "EXAMPLE_COLLECTIONS",
    "Dataset",
    "AccessError",
    "DataFiles",
    "ENV_VAR",
    "IncompleteCatalog",
    "Location",
    "Finding",
    "NamedPaths",
    "RESTRICTED_ENV_VAR",
    "Resource",
    "Roots",
    "STAGING_ENV_VAR",
    "Settings",
    "UnknownCollection",
    "UnknownDataset",
    "catalog",
    "classify_staged",
    "collections",
    "config_path",
    "download",
    "fetch",
    "LinkError",
    "link",
    "unlink",
    "load_catalog",
    "load_collections",
    "materialize",
    "paths",
    "plan",
    "read_settings",
    "repair",
    "resolve",
    "run_selftest",
    "locate",
    "staged_only",
    "add_restricted_cache",
    "remove_restricted_cache",
    "set_cache",
    "set_option",
    "tool_main",
    "unset_option",
    "verify",
]

__version__ = "0.2.1"


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
        data = ethos_data.collections(COLLECTIONS_FILE, tool="mytool")
        inputs = data.paths("onshore_wind", test=True)

    ``tool`` is the tool's short name, used in messages and as the default
    name of its command (``<tool>-data``; see :meth:`Collections.main`). The
    catalogue is ``catalog`` if given, else ``$ETHOS_DATA_CATALOG`` or a
    configured one, else the public catalogue at the newest release the file's
    bounds admit -- so a user can repoint every tool at once without any tool
    knowing. A catalogue outside the bounds raises
    :class:`~ethos_data.errors.CatalogVersionError`. ``root`` overrides the
    public cache directory. The file and the
    settings are read once, here: ``.settings`` reports what every later call
    uses, and ``.catalog`` is the catalogue it resolved to, for access by key.
    """
    settings = read_settings(
        root=root, catalog=catalog if isinstance(catalog, str) else None
    )
    return load_collections(
        path,
        catalog=catalog if isinstance(catalog, Catalog) else None,
        roots=settings.roots,
        tool=tool,
        settings=settings,
    )


def catalog(
    location: str | Catalog | None = None,
    *,
    root: str | Path | None = None,
) -> Catalog:
    """A handle on a catalogue, for access by key rather than by collection.

    ``location`` is a ``datacatalog.json`` path or URL; without one, the
    catalogue is ``$ETHOS_DATA_CATALOG`` or a configured one, else the
    built-in public catalogue. The settings are read and the staging overlay
    is applied once, here; ``.settings`` reports them. The catalogue a tool
    reads within its release bounds is ``ethos_data.collections(...).catalog``::

        era5 = ethos_data.catalog().path("era5/2015")
        files = ethos_data.catalog().resources("global-wind-atlas-v3")
    """
    if isinstance(location, Catalog):
        roots = location.settings.roots if root is None else location._roots(root)
        return location.overlaid(roots)
    loaded = catalog_for(read_settings(root=root, catalog=location))
    return loaded.overlaid(loaded.settings.roots)


def tool_main(
    path: str | Path,
    *,
    tool: str | None = None,
    prog: str | None = None,
    catalog: str | None = None,
    argv: list[str] | None = None,
) -> int:
    """The body of a tool's data command, bound to its shipped collections file.

    Two lines in the tool make the command::

        # mytool/data/__init__.py
        def main(argv=None):
            return ethos_data.tool_main(COLLECTIONS_FILE, tool="mytool", argv=argv)

        # pyproject.toml
        [project.scripts]
        mytool-data = "mytool.data:main"

    ``show``, ``fetch`` and ``verify`` for the file's collections, against the
    catalogue the settings choose within its bounds, plus ``bundle``,
    ``staging`` and ``config``. A single
    catalogue key belongs to ``ethos-data``, not here -- which is what keeps
    this to six commands whatever the tool.
    ``prog`` names the command in help and messages
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
    fetch: bool = True,
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
        fetch=fetch,
    )


def paths(
    collection: str,
    collections: str | Path,
    catalog: str | Catalog | None = None,
    root: str | Path | None = None,
    progressbar: bool = True,
    *,
    test: bool = False,
    fetch: bool = True,
) -> NamedPaths:
    """The inputs a collection names, as ``{handle: absolute Path}``, fetched.

    See :meth:`Collections.paths`. One-call form of
    ``ethos_data.collections(collections).paths(...)``.
    """
    return _handle(collections, catalog, root).paths(
        collection,
        test=test,
        progressbar=progressbar,
        fetch=fetch,
    )


def _handle(
    source: str | Path | Collections,
    catalog: str | Catalog | None,
    root: str | Path | None = None,
) -> Collections:
    if isinstance(source, Collections):
        return source
    return collections(source, catalog=catalog, root=root)
