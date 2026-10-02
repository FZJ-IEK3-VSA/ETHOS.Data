"""Loading the ETHOS.Data catalogue: its index, and each dataset's inventory on demand.

Loading is **lazy**: ``load_catalog`` reads only ``datacatalog.json`` -- the
small index -- and a dataset's ``datapackage.json`` the first time something
asks for its files. That matters once a dataset is large: the ERA5 inventory
alone is ~64 MB and 170k resources, and without laziness every ``ethos-data``
invocation would download and parse it just to answer a question about a
different dataset.

Everything the index row knows -- byte total, file count, access class,
remote prefix, licence status -- is answered from the row and never triggers a
read, so ``ethos-data ls`` and access checks stay free. The descriptor and the
inventory, inline or in shards, are read by the one inventory reader,
:class:`~ethos_data.model.inventory.Inventory`, through the metadata source
the catalogue was loaded from.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .adapters import MetadataSource
from .adapters.metadata import CachedSource, FileSource, HttpSource
from .errors import (
    AccessError,
    CatalogUnavailable,
    CatalogVersionError,
    IncompleteCatalog,
    UnknownDataset,
    UnknownKey,
)
from .formats import keys
from .formats.derived import object_folder, resource_url
from .model import names
from .model.inventory import Inventory
from .model.patterns import path_matches
from .model.resource import Resource, with_sidecars
from .model.versions import Bounds, Version, releases

if TYPE_CHECKING:
    from .config import Roots, Settings

__all__ = [
    "NO_CACHE_ENV",
    "Catalog",
    "Dataset",
    "catalog_for",
    "directory_of",
    "load_catalog",
    "metadata_source",
    "select_key",
    "split_key",
]

#: Set to read catalogue metadata over HTTPS without the metadata cache.
NO_CACHE_ENV = "ETHOS_CATALOG_NO_CACHE"


def metadata_source(location: str, settings: Settings | None = None) -> MetadataSource:
    """Where a catalogue at ``location`` is read from.

    The files on disk for a path. For a URL, HTTPS with the metadata cache in
    front, in the public cache of ``settings`` (read when not given), unless
    ``ETHOS_CATALOG_NO_CACHE`` is set.
    """
    if not location.startswith(("http://", "https://")):
        return FileSource()
    if os.environ.get(NO_CACHE_ENV):
        return HttpSource()
    if settings is None:
        from .config import read_settings

        settings = read_settings()
    return CachedSource(HttpSource(), settings.roots.public / ".catalog")


@dataclass
class Dataset:
    """A dataset in the catalogue: its row in the index, and its inventory.

    The properties answer from ``entry``, the row ``datacatalog.json`` carries,
    and never read the descriptor. ``descriptor``, ``resources`` and the
    lookups of ``inventory`` read it on first use.
    """

    name: str
    title: str
    entry: dict
    inventory: Inventory

    # -- answered from the index row ---------------------------------------

    @property
    def namespace(self) -> bool:
        """Whether this is a family name rather than a dataset with files.

        A namespace has members -- ``reskit-test-data`` for
        ``reskit-test-data/era5`` and its siblings -- and nothing of its own to
        download.
        """
        return bool(self.entry.get(keys.NAMESPACE, False))

    @property
    def access(self) -> str:
        return self.entry.get(keys.ACCESS, keys.PUBLIC)

    @property
    def visibility(self) -> str:
        return self.entry.get(keys.VISIBILITY, keys.PUBLIC)

    @property
    def total_bytes(self) -> int:
        return self.entry[keys.TOTAL_BYTES]

    @property
    def file_count(self) -> int:
        return self.entry[keys.FILE_COUNT]

    @property
    def remote_prefix(self) -> str:
        return self.entry[keys.REMOTE_PREFIX]

    @property
    def revision(self) -> int:
        """Which revision of the dataset this catalogue names; 1 for the first."""
        return int(self.entry.get(keys.REVISION, 1))

    @property
    def entry_name(self) -> str:
        """Where this revision lies in a cache: the name, or ``<name>@<revision>``."""
        return names.entry(self.name, self.revision)

    @property
    def supersedes(self) -> str | None:
        """The dataset this one replaces, with another layout and other keys."""
        return self.entry.get(keys.SUPERSEDES)

    @property
    def superseded_by(self) -> list[str]:
        """The datasets that replace this one; empty while none does."""
        return list(self.entry.get(keys.SUPERSEDED_BY) or [])

    @property
    def license_status(self) -> str:
        """``resolved`` once somebody has read the upstream terms."""
        return self.entry.get(keys.LICENSE_STATUS, keys.UNKNOWN)

    # -- read through the inventory ----------------------------------------

    @property
    def descriptor(self) -> dict:
        """The ``datapackage.json``; for a sharded dataset, without the inventory."""
        return self.inventory.descriptor

    @property
    def resources(self) -> dict[str, Resource]:
        """The complete inventory, by path. For a sharded dataset, every shard.

        Prefer ``inventory.matching(patterns)`` where the patterns are known --
        that is the whole reason sharding exists.
        """
        return self.inventory.resources()


@dataclass
class Catalog:
    location: str
    descriptor: dict
    datasets: dict[str, Dataset]
    #: Set on the view :func:`ethos_data.staging.with_staging` returns, so a
    #: catalogue handed back into the API is not overlaid -- and warned about --
    #: a second time.
    staged: bool = False
    #: The settings this handle uses, read once; see :attr:`settings`.
    _settings: Settings | None = field(default=None, repr=False)

    @property
    def settings(self) -> Settings:
        """The settings file, this catalogue, the caches, and where each came from.

        Read when first needed, then kept: every later call of this handle uses
        the same caches and publication URL, whatever changes in the
        environment meanwhile. ``print(catalog.settings)`` reports them.
        """
        if self._settings is None:
            from .config import read_settings

            self._settings = read_settings().with_catalog(
                self.location, "loaded directly", self.version
            )
        return self._settings

    @property
    def version(self) -> str | None:
        """The catalogue release this index records, if it records one."""
        version = self.descriptor.get(keys.VERSION)
        return str(version) if version else None

    @property
    def name(self) -> str:
        return self.descriptor.get(keys.NAME, "")

    @property
    def role(self) -> str | None:
        """``source`` or ``published``; None when the index does not say."""
        return self.descriptor.get(keys.CATALOG_ROLE)

    @property
    def publication_url(self) -> str:
        """Base URL for bytes, honouring a local override.

        Defaults to whatever the catalogue declares; ETHOS_PUBLICATION_URL or a
        `publication_url` setting can point at a different DESY door without
        the catalogue changing. Taken from :attr:`settings`, so read once.
        """
        override = self.settings.publication_url
        default = self.descriptor.get(keys.PUBLICATION_URL, "")
        return (override or default).rstrip("/")

    def members_of(self, name: str) -> list[Dataset]:
        """The datasets that carry files under a family name, innermost included.

        ``reskit-test-data`` yields its members; ``reskit-test-data/era5`` yields
        itself. Nested namespaces are skipped -- only things with an inventory
        come back -- so a caller can treat the result as "what to fetch".
        """
        members = [
            dataset
            for key, dataset in self.datasets.items()
            if names.within(key, name) and not dataset.namespace
        ]
        return sorted(members, key=lambda d: d.name)

    def with_sidecars(
        self, resources: list[Resource]
    ) -> tuple[dict[str, Resource], list[str]]:
        """``resources`` with every sidecar they need, and the sidecars not found.

        Each companion is looked up in the dataset of the file naming it,
        loading only the shard that can hold it. See
        :func:`ethos_data.model.resource.with_sidecars`.
        """
        return with_sidecars(
            resources, lambda dataset, path: self.dataset(dataset).inventory.at(path)
        )

    def matching_datasets(self, pattern: str) -> list[Dataset]:
        """Datasets a collections file's ``dataset:`` field selects.

        An exact name wins outright, and a namespace name expands to its members
        -- which is what makes a family usable as one thing. Otherwise the string
        is treated as a glob over dataset names, so ``reskit-test-data/*`` picks
        the members explicitly and ``*-landcover`` picks across families.
        """
        if pattern in self.datasets:
            found = self.members_of(pattern)
            if found:
                return found
            # Named exactly, but it is an empty namespace. Return it so the
            # caller's own "matched nothing" reporting fires, rather than
            # pretending the name was unknown.
            return [self.datasets[pattern]]
        matched = [
            dataset
            for key, dataset in self.datasets.items()
            if not dataset.namespace and path_matches(key, pattern)
        ]
        if matched:
            return sorted(matched, key=lambda d: d.name)
        # No match at all: let dataset() raise, so the error names the catalogue
        # and lists what it does have.
        return [self.dataset(pattern)]

    def dataset(self, name: str) -> Dataset:
        try:
            return self.datasets[name]
        except KeyError:
            raise UnknownDataset(not_found(name)) from None

    def base_url_for(self, dataset: Dataset, revision: int = 1) -> str:
        """The folder under which the files of one revision of this dataset resolve.

        Single point of URL construction, so a per-dataset override (a mirror)
        only has to be honoured here. A file is served from the folder of the
        revision its bytes were published in, ``revision`` here.
        """
        return resource_url(
            self.publication_url, object_folder(dataset.remote_prefix, revision)
        )

    def url_for(self, resource: Resource) -> str:
        dataset = self.dataset(resource.dataset)
        return self.base_url_for(dataset, resource.revision) + resource.path

    # -- Access by key -----------------------------------------------------
    #
    # The catalogue is the place to ask for one dataset, folder or file by its
    # key; a collections file (:class:`ethos_data.Collections`) is the place to
    # ask for what a tool's workflow needs by name. ``ethos_data.catalog()``
    # builds a handle for the configured catalogue; ``Collections.catalog`` is
    # the one a tool reads within its collections file's release bounds.

    def _roots(self, root: Roots | str | Path | None) -> Roots:
        """The roots of :attr:`settings`, or of one call that names its own."""
        from .config import Roots

        if root is None:
            return self.settings.roots
        if isinstance(root, Roots):
            return root
        return self.settings.roots.with_public(root)

    def overlaid(self, roots: Roots | None = None, warn: bool = True) -> Catalog:
        """This catalogue with the staging overlay applied, once.

        A view :func:`ethos_data.staging.with_staging` already returned comes
        back unchanged, so a catalogue handed around the API is never overlaid
        -- and warned about -- a second time.
        """
        if self.staged:
            return self
        from .staging import with_staging

        return with_staging(self, roots, warn=warn)

    def resources(self, key: str) -> list[Resource]:
        """The files under a key, in key order, without fetching anything.

        The answer to "what is in this dataset, and what do I put after the
        slash to get one file?". ``key`` is a dataset, a family, or
        ``"<dataset>/<folder>"``; for a single file it is that file, with its
        sidecars.
        """
        catalog = self.overlaid(warn=False)
        name, inner = split_key(catalog, key)
        found, _ = select_key(catalog, name, inner, key)
        return sorted(found, key=lambda r: r.key)

    def path(
        self,
        key: str,
        *,
        root: Roots | str | Path | None = None,
        progressbar: bool = False,
        fetch: bool = True,
    ) -> Path:
        """The absolute local path of a file or folder, fetching it if necessary.

        ``key`` is ``"<dataset>/<path>"`` for one file -- a shapefile brings
        its sidecars along -- or ``"<dataset>/<folder>"``, ``"<dataset>"`` or
        a dataset family for a directory, in which case every file under it is
        fetched first. :meth:`resources` says what is under a key without
        fetching. Files already in the cache are not downloaded again.
        ``fetch=False`` downloads nothing, and raises
        :class:`~ethos_data.errors.NotFetched` for a file that is not here.
        """
        from .retrieval import download

        roots = self._roots(root)
        catalog = self.overlaid(roots)
        name, inner = split_key(catalog, key)
        found, target = select_key(catalog, name, inner, key)
        files = download(
            catalog, found, root=roots, progressbar=progressbar, fetch=fetch
        )
        if target is not None:
            if target.key not in files:
                raise AccessError(f"{key!r} is not available on this machine.")
            return Path(os.path.abspath(files[target.key]))
        return Path(os.path.abspath(directory_of(files, found, name, inner, key)))


def catalog_for(settings: Settings, *, explicit: str | None = None) -> Catalog:
    """The catalogue ``settings`` choose, loaded, and keeping those settings.

    The one place a catalogue handle is opened from settings, so the choice
    follows :meth:`~ethos_data.config.Settings.choose_catalog` everywhere.
    """
    location, source = settings.choose_catalog(explicit=explicit)
    loaded = load_catalog(location, settings=settings)
    loaded._settings = settings.with_catalog(location, source, loaded.version)
    return loaded


def releases_of(catalog: Catalog) -> list[Version]:
    """The releases a published index lists, its own included, oldest first."""
    names = list(catalog.descriptor.get(keys.RELEASES) or [])
    if catalog.version:
        names.append(catalog.version)
    return releases(names)


def public_releases(settings: Settings | None = None) -> list[Version]:
    """The releases the public catalogue's ``main`` index lists, oldest first."""
    from .config import DEFAULT_CATALOG

    return releases_of(load_catalog(DEFAULT_CATALOG, settings=settings))


def check_release(catalog: Catalog, bounds: Bounds, file_name: str) -> None:
    """Refuse a catalogue that is not a release ``bounds`` accept, naming both."""
    where = f"catalogue at {catalog.location}"
    advice = (
        "Read a catalogue release within the bounds with --catalog / catalog=, "
        "or ask the package's maintainers to widen them."
    )
    if not catalog.version:
        raise CatalogVersionError(
            f"the {where} records no release, but {file_name} accepts only {bounds}.\n"
            f"{advice}"
        )
    try:
        release = Version.parse(catalog.version)
    except ValueError:
        raise CatalogVersionError(
            f"the {where} records release {catalog.version!r}, which is not of the form "
            f"vMAJOR.MINOR.PATCH; {file_name} accepts only {bounds}.\n{advice}"
        ) from None
    if not bounds.admits(release):
        raise CatalogVersionError(
            f"the {where} is release {release}, but {file_name} accepts only "
            f"{bounds}.\n{advice}"
        )


def load_catalog(
    location: str,
    *,
    source: MetadataSource | None = None,
    settings: Settings | None = None,
) -> Catalog:
    """Load a datacatalog.json. Each dataset's inventory is read on first use.

    ``location`` is a local path or an http(s) URL pointing at datacatalog.json;
    ``source`` is where it and every descriptor and shard are read from,
    :func:`metadata_source` by default, with the metadata cache of
    ``settings``. Raises :class:`CatalogUnavailable` when there is no index to
    read there.
    """
    index = location
    if source is None:
        source = metadata_source(location, settings)
        if isinstance(source, FileSource):
            # Absolute, so the inventories read later do not depend on the
            # working directory of the moment.
            index = Path(location).expanduser().resolve().as_posix()
    try:
        descriptor = json.loads(source.read(index))
    except (IncompleteCatalog, CatalogUnavailable) as error:
        # A 404 for a release tag nobody has cut arrives here too.
        reason = error.message.removeprefix(f"{index}: ")
        raise CatalogUnavailable(
            f"cannot read the catalogue index at {location}: {reason}\n"
            f"Use another catalogue for this run with --catalog / catalog=, for this "
            f"shell with $ETHOS_DATA_CATALOG, or for good with "
            f"`ethos-data config set-catalog <datacatalog.json>`."
        ) from error

    datasets = {
        entry[keys.NAME]: Dataset(
            name=entry[keys.NAME],
            title=entry.get(keys.TITLE, ""),
            entry=entry,
            inventory=Inventory(
                entry[keys.NAME],
                source,
                source.join(index, entry[keys.PATH]) if entry.get(keys.PATH) else "",
                where=index,
            ),
        )
        for entry in descriptor.get(keys.DATASETS, [])
    }
    loaded = Catalog(location=location, descriptor=descriptor, datasets=datasets)
    if settings is not None:
        loaded._settings = settings.with_catalog(
            location, "loaded directly", loaded.version
        )
    return loaded


def not_found(name: str) -> str:
    """The one answer for a dataset the catalogue in use does not describe.

    A mistyped name and a dataset the catalogue does not publish look the same
    from here, so they get the same answer, which lists nothing: release
    notices announce what was withdrawn.
    """
    return (
        f"the dataset {name!r} cannot be found. "
        "Maybe it was mistyped, or it is not published."
    )


def split_key(catalog: Catalog, key: str) -> tuple[str, str]:
    """Split a key into the dataset it names and the path inside that dataset.

    Dataset names can contain "/" themselves -- ``reskit-test-data/era5`` is a
    member of the ``reskit-test-data`` family -- so the longest dataset name
    that prefixes the key wins, not whatever precedes the first slash.
    """
    key = key.strip("/")
    if key in catalog.datasets:
        return key, ""
    for name in reversed(names.ancestors(key)):
        dataset = catalog.datasets.get(name)
        if dataset is not None and not dataset.namespace:
            return name, key[len(name) + 1 :]
    first = key.split("/", 1)[0]
    catalog.dataset(first)  # an unknown name raises
    # A family, and none of its members starts the key: the member it names
    # is the dataset that cannot be found.
    raise UnknownDataset(not_found("/".join(key.split("/")[:2])))


def select_key(
    catalog: Catalog, name: str, inner: str, key: str
) -> tuple[list[Resource], Resource | None]:
    """The resources to fetch for a key, and the one file it names, if it names one."""
    if not inner:
        found = [
            r for member in catalog.members_of(name) for r in member.resources.values()
        ]
        if not found:
            raise UnknownKey(f"{key!r} has no files in the catalogue")
        return found, None
    dataset = catalog.dataset(name)
    resource = dataset.inventory.at(inner)
    if resource is not None:
        # A sidecar the record names but the inventory lacks is left out, as
        # a collection leaves it out: the file is still the one asked for.
        with_companions, _ = catalog.with_sidecars([resource])
        return list(with_companions.values()), resource
    # Not a file, so a folder -- matched on a directory boundary, so that
    # "merra-like" means the folder and not also the sibling "merra-like.nc4".
    prefix = inner + "/"
    under = [
        r
        for p, r in dataset.inventory.matching([prefix + "**"]).items()
        if p.startswith(prefix)
    ]
    if not under:
        raise UnknownKey(f"{key!r} cannot be found in the dataset {name!r}.")
    return sorted(under, key=lambda r: r.key), None


def directory_of(
    files: Mapping[str, Path],
    resources: list[Resource],
    name: str,
    inner: str,
    key: str,
) -> Path:
    """Where a folder, a dataset or a family ended up on this machine.

    Read off the files themselves rather than off a root setting: a dataset may
    come from the public cache, a restricted cache or staging, and each
    returned path already says which.
    """
    found = set()
    for resource in resources:
        local = files.get(resource.key)
        if local is None:
            continue
        # Up from the file to its dataset's directory, then from a member up to
        # the family the key named (reskit-test-data/era5 -> reskit-test-data).
        levels = (
            len(PurePosixPath(resource.path).parts)
            + resource.dataset.count("/")
            - name.count("/")
        )
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
