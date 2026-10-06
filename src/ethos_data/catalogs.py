"""Loading the ETHOS.Data catalogue and its Frictionless Data Packages.

Loading is **lazy**: ``load_catalog`` reads only ``datacatalog.json`` -- the
small index -- and pulls a dataset's ``datapackage.json`` the first time
something actually asks for its files.  That matters once a dataset is large:
the ERA5 inventory alone is ~64 MB and 170k resources, and without laziness
every ``ethos-data`` invocation would download and parse it just to answer a
question about a different dataset.

Everything the index already knows -- byte total, file count, access class,
remote prefix, licence status -- is answered from the index and never triggers a
fetch, so ``ethos-data ls`` and access checks stay free.

A large dataset may additionally be **sharded**: its ``datapackage.json`` carries
an ``ethos:shards`` index instead of a ``resources`` array, and the inventory is
split across ``shards/<prefix>.json`` files, one per directory prefix of
``ethos:shard_depth`` segments.  Selecting ``4/6/5/**`` then parses the 664
resources of that one tile rather than all 170k.  Sharding is transparent: ask
for ``.resources`` and every shard is pulled in, exactly as before.
"""

from __future__ import annotations

import fnmatch
import gzip
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .errors import (
    AccessError,
    CatalogUnavailable,
    CatalogVersionError,
    IncompleteCatalog,
    UnknownDataset,
    UnknownKey,
)
from .formats import keys
from .formats.derived import (
    license_status_of,
    remote_prefix_of,
    resource_url,
)
from .model import digest, names
from .model.resource import Resource, extras_of, from_record, to_record, with_sidecars
from .model.versions import Bounds, Version, releases

if TYPE_CHECKING:
    from .config import Roots, Settings

__all__ = [
    "LICENSE_RESOLVED",
    "Catalog",
    "Dataset",
    "catalog_for",
    "directory_of",
    "load_catalog",
    "select_key",
    "split_key",
]

#: The one value of ``ethos:license_status`` that means somebody has read the
#: upstream terms. Anything else -- "unresolved", "unknown", absent -- is a
#: question nobody has answered yet. The rule itself, :func:`license_settled`,
#: is the format's, shared with the half of the tooling that writes.
LICENSE_RESOLVED = keys.RESOLVED


#: Refs that move.  A catalogue fetched from one of these must not be cached
#: forever, or development against the internal catalogue silently goes stale.
_MOVING_REF = re.compile(r"/(?:refs/heads/)?(?:main|master|HEAD|latest|dev|develop)/")

NO_CACHE_ENV = "ETHOS_CATALOG_NO_CACHE"


def _pinned(url: str) -> bool:
    """Whether this URL names an immutable version, and may be cached forever."""
    if os.environ.get(NO_CACHE_ENV):
        return False
    return not _MOVING_REF.search(url)


def _cache_path(url: str) -> Path:
    # Imported here: config pulls in platformdirs, and catalog.py is imported by
    # tooling that only wants the dataclasses.
    from .config import read_settings

    folder = digest.of_bytes(url.encode())[:16]
    public = read_settings().roots.public
    return public / ".catalog" / folder / url.rsplit("/", 1)[-1]


def _read(location: str) -> tuple[str, str]:
    """Return (text, base location) for a local path or an http(s) URL.

    Descriptors fetched from a version-pinned URL are cached on disk and reused,
    and the request asks for gzip -- these files compress ~40x, and without the
    header urllib sends ``Accept-Encoding: identity``.
    """
    if not location.startswith(("http://", "https://")):
        path = Path(location).expanduser().resolve()
        return path.read_text(encoding="utf-8"), path.parent.as_posix() + "/"

    base = location.rsplit("/", 1)[0] + "/"
    cacheable = _pinned(location)
    cached = _cache_path(location) if cacheable else None

    if cached is not None and cached.is_file():
        return cached.read_text(encoding="utf-8"), base

    request = urllib.request.Request(location, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    text = raw.decode("utf-8")

    if cached is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-rename: two processes racing must never see a half file.
        temporary = cached.with_suffix(cached.suffix + f".{os.getpid()}.part")
        # Both arguments are load-bearing: the descriptor came off the wire as
        # UTF-8 with LF, and the cached copy has to be the same file. Left to its
        # defaults write_text encodes with the locale codec and rewrites every
        # newline as CRLF on Windows, so the same catalogue would cache
        # differently depending on which machine fetched it.
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(cached)
    return text, base


def _read_binary(location: str) -> bytes:
    """The bytes at a local path or an http(s) URL, undecoded and uncached.

    Separate from ``_read`` because not every file a descriptor points at is
    text: an archived licence is whatever the licensor published, and the ESA
    CCI terms sheet is a PDF. Nothing here is cached -- these are read once,
    when a bundle is exported, not on the path any ordinary read takes.
    """
    if not location.startswith(("http://", "https://")):
        return Path(location).expanduser().resolve().read_bytes()
    # No Accept-Encoding: gzip here. These are already-compressed formats, so
    # the header buys nothing and only adds a branch that has to be right.
    with urllib.request.urlopen(location, timeout=60) as response:
        return response.read()


#: Shard holding files that sit at the dataset root, above any shard directory.
ROOT_SHARD = "_root"

#: Declares what kind of catalogue a descriptor is, so tools and error messages
#: never have to infer it from which files happen to be lying around.
ROLE_KEY = keys.CATALOG_ROLE
#: Hand-written, holds dataset.yaml and source_dir; the thing you edit and upload from.
ROLE_SOURCE = keys.ROLE_SOURCE
#: Generated by `ethos-data catalog publish`; metadata only, overwritten on every publish.
ROLE_PUBLISHED = keys.ROLE_PUBLISHED
CATALOG_ROLES = keys.CATALOG_ROLES


def _missing_part(
    dataset: str, what: str, location: str, index_base: str
) -> IncompleteCatalog:
    return IncompleteCatalog(
        f"dataset {dataset!r} is listed in the catalogue index under {index_base} but its "
        f"{what} is missing: {location}\n"
        f"The catalogue copy is incomplete or stale -- an index from one revision paired with "
        f"descriptors from another. Deploy or republish the complete tree for that revision; "
        f"copying the index alone is not enough. If you did not choose this catalogue, "
        f"`ethos-data config show` says where the setting came from."
    )


def _read_part(dataset: str, what: str, location: str, index_base: str) -> str:
    """``_read`` for a descriptor or shard, turning "not there" into a diagnosis."""
    try:
        return _read(location)[0]
    except FileNotFoundError as error:
        raise _missing_part(dataset, what, location, index_base) from error
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise _missing_part(dataset, what, location, index_base) from error
        raise


def shard_key(relative_path: str, depth: int) -> str:
    """Which shard a resource path belongs to.

    Keyed on the *directory* prefix, so every file in a directory lands in the
    same shard as its neighbours -- which is what makes shapefile sidecars and
    a tile's variables resolvable without touching a second shard.
    """
    directories = relative_path.split("/")[:-1]
    return "/".join(directories[:depth]) or ROOT_SHARD


def _shard_could_match(prefix: str, pattern: str) -> bool:
    """Could any path under ``prefix`` match ``pattern``?

    Conservative by construction: it may say yes for a shard that turns out to
    contain nothing matching (the caller filters properly afterwards), but it
    must never say no for a shard that does. Saying no wrongly would silently
    drop files from a collection, which is far worse than one extra fetch.
    """
    parts = [] if prefix == ROOT_SHARD else prefix.split("/")
    patterns = pattern.split("/")
    if not parts:
        # The root shard is the one whose files have no directory component at
        # all, so only a single-segment pattern can name one -- or a pattern
        # starting with ``**``, which absorbs zero segments. The general rule
        # below cannot express this: it reasons about files sitting *below* a
        # prefix directory, and these sit at the top instead. Without the
        # distinction every selection drags the root shard in, whatever it asked
        # for.
        return len(patterns) == 1 or patterns[0] == "**"
    while parts:
        if not patterns:
            # The pattern describes a shallower path than this shard's prefix.
            return False
        head = patterns[0]
        if head == "**":
            return True  # absorbs any number of segments, including these
        if not fnmatch.fnmatchcase(parts[0], head):
            return False
        parts, patterns = parts[1:], patterns[1:]
    # Files in a shard sit *below* its prefix directory, so a pattern that ran
    # out exactly at the prefix is one segment too short to match any of them.
    return bool(patterns)


def _join(base: str, relative: str) -> str:
    if base.startswith(("http://", "https://")):
        return urllib.parse.urljoin(base, relative)
    return (Path(base) / relative).as_posix()


@dataclass
class Dataset:
    """A dataset in the catalogue, loaded on demand.

    ``entry`` is the cheap row from ``datacatalog.json``.  ``descriptor`` and
    ``resources`` fetch the dataset's ``datapackage.json`` on first access; the
    properties above them answer from ``entry`` and never do.
    """

    name: str
    title: str
    entry: dict = field(default_factory=dict)
    base: str = ""
    _descriptor: dict | None = field(default=None, repr=False)
    _resources: dict[str, Resource] = field(default_factory=dict, repr=False)
    # Keep licence/provenance extensions without retaining a duplicate full
    # inventory: large shards can contain millions of ordinary Resource rows.
    _resource_extras: dict[str, dict] = field(default_factory=dict, repr=False)
    _shards: dict[str, dict] = field(default_factory=dict, repr=False)
    _loaded_shards: set[str] = field(default_factory=set, repr=False)
    _shard_depth: int = field(default=0, repr=False)
    _package_base: str = field(default="", repr=False)

    # -- answered from the index; never triggers a fetch ---------------------

    @property
    def loaded(self) -> bool:
        """Whether the complete inventory is in memory."""
        return self._descriptor is not None and not self.pending_shards

    @property
    def sharded(self) -> bool:
        return bool(self._shards)

    @property
    def pending_shards(self) -> list[str]:
        """Shards described by the descriptor but not yet fetched."""
        return sorted(set(self._shards) - self._loaded_shards)

    @property
    def namespace(self) -> bool:
        """Whether this is a family name rather than a dataset with files.

        A namespace has members -- ``reskit-test-data`` for
        ``reskit-test-data/era5`` and its siblings -- and nothing of its own to
        download. Answered from the index row, so asking never costs a fetch.
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
        if keys.TOTAL_BYTES in self.entry:
            return self.entry[keys.TOTAL_BYTES]
        return sum(r.bytes for r in self.resources.values())

    @property
    def file_count(self) -> int:
        if keys.FILE_COUNT in self.entry:
            return self.entry[keys.FILE_COUNT]
        return len(self.resources)

    @property
    def remote_prefix(self) -> str:
        if keys.REMOTE_PREFIX in self.entry:
            return self.entry[keys.REMOTE_PREFIX]
        return remote_prefix_of({**self.descriptor, keys.NAME: self.name})

    @property
    def license_status(self) -> str:
        """ "resolved" once somebody has read the upstream terms.

        Promoted into the index by the build so that listing a catalogue does
        not have to load every descriptor to warn about licensing.
        """
        if keys.LICENSE_STATUS in self.entry:
            return self.entry[keys.LICENSE_STATUS]
        return license_status_of(self.descriptor)

    # -- these pull the datapackage in --------------------------------------

    @property
    def descriptor(self) -> dict:
        """The datapackage.json.  Cheap for a sharded dataset -- no inventory."""
        if self._descriptor is None:
            self.load()
        return self._descriptor

    @property
    def resources(self) -> dict[str, Resource]:
        """The complete inventory.  For a sharded dataset this pulls every shard.

        Prefer :meth:`resources_matching` where the patterns are known -- that is
        the whole reason sharding exists.
        """
        self.load()
        self._load_shards(self.pending_shards)
        return self._resources

    def load(self) -> None:
        """Fetch and parse this dataset's datapackage.json.  Idempotent.

        For a sharded dataset this reads only the shard index; the inventory
        itself arrives shard by shard.
        """
        if self._descriptor is not None:
            return
        if not self.entry.get(keys.PATH):
            raise ValueError(
                f"dataset {self.name!r} has no 'path' in the catalogue index, so its "
                "file inventory cannot be located."
            )
        location = _join(self.base, self.entry[keys.PATH])
        package = json.loads(
            _read_part(self.name, "descriptor (datapackage.json)", location, self.base)
        )
        # Shard paths are relative to the dataset directory, not the catalogue root.
        self._package_base = location.rsplit("/", 1)[0] + "/"
        self._shard_depth = int(package.get(keys.SHARD_DEPTH, 0))
        self._shards = {
            entry[keys.PREFIX]: entry for entry in package.get(keys.SHARDS, [])
        }
        self._descriptor = package
        if not self._shards:
            self._absorb(package.get(keys.RESOURCES, []))

    def resources_matching(self, patterns: list[str]) -> dict[str, Resource]:
        """Resources from the shards that could possibly match ``patterns``.

        Returns a superset -- the caller still globs properly. On an unsharded
        dataset this is just the whole inventory.
        """
        self.load()
        if not self._shards:
            return self._resources
        wanted = [
            prefix
            for prefix in self._shards
            if any(_shard_could_match(prefix, pattern) for pattern in patterns)
        ]
        self._load_shards(wanted)
        return self._resources

    def resource_at(self, path: str) -> Resource | None:
        """One resource by path, loading only the shard that can hold it.

        Used for shapefile sidecars, which live beside their .shp and therefore
        always land in the same shard -- no second fetch in practice.
        """
        self.load()
        if self._shards:
            key = shard_key(path, self._shard_depth)
            if key in self._shards:
                self._load_shards([key])
        return self._resources.get(path)

    def resource_descriptor(self, path: str) -> dict | None:
        """One original resource record, including licence/provenance overrides.

        Loads only the shard that can contain this resource, as resource_at
        does. Returning a copy lets snapshot exporters retain extension fields
        without mutating the canonical inventory.
        """
        resource = self.resource_at(path)
        if resource is None:
            return None
        return to_record(resource, self._resource_extras.get(path))

    def _load_shards(self, prefixes: list[str]) -> None:
        for prefix in prefixes:
            if prefix in self._loaded_shards:
                continue
            entry = self._shards[prefix]
            location = _join(self._package_base, entry[keys.PATH])
            shard = json.loads(
                _read_part(self.name, f"shard {prefix!r}", location, self.base)
            )
            self._absorb(shard.get(keys.RESOURCES, []))
            self._loaded_shards.add(prefix)

    def _absorb(self, items: list[dict]) -> None:
        for item in items:
            resource = from_record(self.name, item)
            extras = extras_of(item)
            if extras:
                self._resource_extras[resource.path] = extras
            self._resources[resource.path] = resource


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
    def role(self) -> str:
        """``source``, ``published``, or "" for a catalogue predating the key."""
        return self.descriptor.get(keys.CATALOG_ROLE, "")

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
            resources, lambda dataset, path: self.dataset(dataset).resource_at(path)
        )

    def matching_datasets(self, pattern: str) -> list[Dataset]:
        """Datasets a collections file's ``dataset:`` field selects.

        An exact name wins outright, and a namespace name expands to its members
        -- which is what makes a family usable as one thing. Otherwise the string
        is treated as a glob over dataset names, so ``reskit-test-data/*`` picks
        the members explicitly and ``*-landcover`` picks across families.
        """
        from .selection import path_matches

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

    def base_url_for(self, dataset: Dataset) -> str:
        """Root under which this dataset's resource paths resolve.

        Single point of URL construction, so a per-dataset override (a mirror)
        only has to be honoured here.
        """
        return resource_url(self.publication_url, dataset.remote_prefix)

    def url_for(self, resource: Resource) -> str:
        return self.base_url_for(self.dataset(resource.dataset)) + resource.path

    def load_all(self) -> None:
        """Force every descriptor in.  For catalogue validation tooling only."""
        for dataset in self.datasets.values():
            dataset.load()

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
    loaded = load_catalog(location)
    loaded._settings = settings.with_catalog(location, source, loaded.version)
    return loaded


def releases_of(catalog: Catalog) -> list[Version]:
    """The releases a published index lists, its own included, oldest first."""
    names = list(catalog.descriptor.get(keys.RELEASES) or [])
    if catalog.version:
        names.append(catalog.version)
    return releases(names)


def public_releases() -> list[Version]:
    """The releases the public catalogue's ``main`` index lists, oldest first."""
    from .config import DEFAULT_CATALOG

    return releases_of(load_catalog(DEFAULT_CATALOG))


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


def load_catalog(location: str) -> Catalog:
    """Load a datacatalog.json.  Dataset inventories are fetched on first use.

    ``location`` is a local path or an http(s) URL pointing at datacatalog.json.
    Raises :class:`CatalogUnavailable` when there is nothing to read there.
    """
    try:
        text, base = _read(location)
    except (FileNotFoundError, urllib.error.URLError) as error:
        # HTTPError is a URLError: a 404 for a release tag nobody has cut
        # arrives here too, and reads as "HTTP Error 404: Not Found" -- which
        # says nothing about *which* URL.
        reason = getattr(error, "reason", None) or error
        if isinstance(error, urllib.error.HTTPError):
            reason = f"HTTP {error.code} {error.reason}"
        raise CatalogUnavailable(
            f"cannot read the catalogue index at {location}: {reason}\n"
            f"Use another catalogue for this run with --catalog / catalog=, for this "
            f"shell with $ETHOS_DATA_CATALOG, or for good with "
            f"`ethos-data config set-catalog <datacatalog.json>`."
        ) from error
    descriptor = json.loads(text)

    datasets = {
        entry[keys.NAME]: Dataset(
            name=entry[keys.NAME],
            title=entry.get(keys.TITLE, ""),
            entry=entry,
            base=base,
        )
        for entry in descriptor.get(keys.DATASETS, [])
    }
    return Catalog(location=location, descriptor=descriptor, datasets=datasets)


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
    resource = dataset.resource_at(inner)
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
        for p, r in dataset.resources_matching([prefix + "**"]).items()
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
