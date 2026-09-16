"""Loading the ETHOS.Data catalogue and its Frictionless Data Packages.

Loading is **lazy**: ``load_catalog`` reads only ``datacatalog.json`` -- the
small index -- and pulls a dataset's ``datapackage.json`` the first time
something actually asks for its files.  That matters once a dataset is large:
the ERA5 inventory alone is ~64 MB and 170k resources, and without laziness
every ``ethos-data`` invocation would download and parse it just to answer a
question about a different dataset.

Everything the index already knows -- byte total, file count, access class,
remote prefix, licence status -- is answered from the index and never triggers a
fetch, so ``ethos-data list`` and access checks stay free.

A large dataset may additionally be **sharded**: its ``datapackage.json`` carries
an ``ethos:shards`` index instead of a ``resources`` array, and the inventory is
split across ``manifests/<prefix>.json`` files, one per directory prefix of
``ethos:shard_depth`` segments.  Selecting ``4/6/5/**`` then parses the 664
resources of that one tile rather than all 170k.  Sharding is transparent: ask
for ``.resources`` and every shard is pulled in, exactly as before.
"""

from __future__ import annotations

import fnmatch
import gzip
import hashlib
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

if TYPE_CHECKING:
    from .config import Roots

__all__ = [
    "LICENSE_RESOLVED",
    "Catalog",
    "CatalogUnavailable",
    "Dataset",
    "IncompleteCatalog",
    "Resource",
    "UnknownDataset",
    "directory_of",
    "license_settled",
    "load_catalog",
    "select_key",
    "split_key",
]

#: The one value of ``ethos:license_status`` that means somebody has read the
#: upstream terms. Anything else -- "unresolved", "unknown", absent -- is a
#: question nobody has answered yet.
LICENSE_RESOLVED = "resolved"


def license_settled(meta: dict) -> bool:
    """Whether a descriptor states terms somebody has actually checked.

    The same rule :attr:`Dataset.license_status` applies, asked of a plain
    mapping -- a hand-written ``dataset.yaml`` or a generated
    ``datapackage.json`` -- so that the half of the tooling that *writes* can
    refuse to distribute a dataset before the question has been answered.

    A ``licenses`` entry settles it: the builder already rejects one that names
    no licence. Otherwise only an explicit ``resolved`` does, because the
    default has to be "nobody has looked" rather than "nothing applies".
    """
    if meta.get("licenses"):
        return True
    return meta.get("ethos:license_status") == LICENSE_RESOLVED

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
    from .config import resolve_cache_dir

    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    return resolve_cache_dir().value / ".catalog" / digest / url.rsplit("/", 1)[-1]


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


#: Shard holding files that sit at the dataset root, above any shard directory.
ROOT_SHARD = "_root"

#: Declares what kind of catalogue a descriptor is, so tools and error messages
#: never have to infer it from which files happen to be lying around.
ROLE_KEY = "ethos:catalog_role"
#: Hand-written, holds dataset.yaml and source_dir; the thing you edit and upload from.
ROLE_SOURCE = "source"
#: Generated by `ethos-data catalog publish`; metadata only, overwritten on every publish.
ROLE_PUBLISHED = "published"
CATALOG_ROLES = (ROLE_SOURCE, ROLE_PUBLISHED)


def describe_catalog(descriptor: dict, location: str = "") -> str:
    """A short human name for a catalogue, for use in error messages.

    Both catalogues share a ``name`` -- the public one is a subset view of the
    same catalogue, not a different one -- so the role is what distinguishes
    them, and it is the thing a reader needs to know when a dataset is absent.
    """
    name = descriptor.get("name") or "catalogue"
    role = descriptor.get(ROLE_KEY)
    label = f"{role} catalogue {name!r}" if role else f"catalogue {name!r}"
    return f"{label} ({location})" if location else label


class UnknownDataset(KeyError):
    """A collection names a dataset this catalogue does not describe.

    Usually a withdrawn dataset rather than a typo: a collections file pinned to
    an older catalogue keeps working, and only breaks when it is repointed at a
    newer one that no longer publishes what it asks for. Subclasses KeyError so
    existing ``except KeyError`` handlers keep working; the CLI catches this
    specific type so a genuine bug still surfaces as a traceback.
    """


class CatalogUnavailable(OSError):
    """The catalogue index itself could not be read.

    Distinct from :class:`IncompleteCatalog`, which is about a dataset the index
    promised: here there is no index. The common cause is not a network fault
    but a pin -- a collections file naming a tag or a repository that does not
    exist (yet, or any more) -- and the person hitting it usually did not write
    that pin, so the message says how to point at another catalogue.
    """


class IncompleteCatalog(FileNotFoundError):
    """The index lists a dataset whose descriptor or shard is not where it says.

    Loading is lazy, so this surfaces long after the index was read -- on the
    first fetch that touches the dataset -- and a bare FileNotFoundError at that
    point names a path the user never typed and gives no hint that the
    *catalogue copy* is the problem. It happens when a tree is deployed
    piecemeal, or an index from one revision sits beside descriptors from
    another (a dataset renamed on disk after the index was generated, say).
    Subclasses FileNotFoundError so existing ``except OSError`` handlers still
    catch it.
    """


def _missing_part(dataset: str, what: str, location: str, index_base: str) -> IncompleteCatalog:
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
        return bool(self.entry.get("ethos:namespace", False))

    @property
    def access(self) -> str:
        return self.entry.get("ethos:access", "public")

    @property
    def visibility(self) -> str:
        return self.entry.get("ethos:visibility", "public")

    @property
    def total_bytes(self) -> int:
        if "ethos:total_bytes" in self.entry:
            return self.entry["ethos:total_bytes"]
        return sum(r.bytes for r in self.resources.values())

    @property
    def file_count(self) -> int:
        if "ethos:file_count" in self.entry:
            return self.entry["ethos:file_count"]
        return len(self.resources)

    @property
    def remote_prefix(self) -> str:
        if "ethos:remote_prefix" in self.entry:
            return self.entry["ethos:remote_prefix"]
        return self.descriptor.get("ethos:remote_prefix", self.name)

    @property
    def license_status(self) -> str:
        """"resolved" once somebody has read the upstream terms.

        Promoted into the index by build_manifest.py so that listing a catalogue
        does not have to load every descriptor to warn about licensing.
        """
        if "ethos:license_status" in self.entry:
            return self.entry["ethos:license_status"]
        if self.descriptor.get("licenses"):
            return "resolved"
        return self.descriptor.get("ethos:license_status", "unknown")

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
        if not self.entry.get("path"):
            raise ValueError(
                f"dataset {self.name!r} has no 'path' in the catalogue index, so its "
                "file inventory cannot be located."
            )
        location = _join(self.base, self.entry["path"])
        package = json.loads(_read_part(self.name, "descriptor (datapackage.json)", location, self.base))
        # Shard paths are relative to the dataset directory, not the catalogue root.
        self._package_base = location.rsplit("/", 1)[0] + "/"
        self._shard_depth = int(package.get("ethos:shard_depth", 0))
        self._shards = {entry["prefix"]: entry for entry in package.get("ethos:shards", [])}
        self._descriptor = package
        if not self._shards:
            self._absorb(package.get("resources", []))

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
        record = {
            "name": resource.name, "path": resource.path, "bytes": resource.bytes,
            "hash": resource.hash, "mediatype": resource.mediatype,
            **self._resource_extras.get(path, {}),
        }
        if resource.sidecars:
            record["ethos:sidecars"] = list(resource.sidecars)
        return record

    def _load_shards(self, prefixes: list[str]) -> None:
        for prefix in prefixes:
            if prefix in self._loaded_shards:
                continue
            entry = self._shards[prefix]
            location = _join(self._package_base, entry["path"])
            shard = json.loads(_read_part(self.name, f"shard {prefix!r}", location, self.base))
            self._absorb(shard.get("resources", []))
            self._loaded_shards.add(prefix)

    def _absorb(self, items: list[dict]) -> None:
        for item in items:
            extras = {key: value for key, value in item.items()
                      if key not in {"name", "path", "bytes", "hash", "mediatype", "ethos:sidecars"}}
            if extras:
                self._resource_extras[item["path"]] = extras
            self._resources[item["path"]] = Resource(
                dataset=self.name,
                name=item["name"],
                path=item["path"],
                bytes=item["bytes"],
                hash=item["hash"],
                mediatype=item.get("mediatype", "application/octet-stream"),
                sidecars=tuple(item.get("ethos:sidecars", ())),
            )


@dataclass
class Catalog:
    location: str
    descriptor: dict
    datasets: dict[str, Dataset]
    #: Set on the view :func:`ethos_data.staging.with_staging` returns, so a
    #: catalogue handed back into the API is not overlaid -- and warned about --
    #: a second time.
    staged: bool = False

    @property
    def name(self) -> str:
        return self.descriptor.get("name", "")

    @property
    def role(self) -> str:
        """``source``, ``published``, or "" for a catalogue predating the key."""
        return self.descriptor.get(ROLE_KEY, "")

    @property
    def publication_url(self) -> str:
        """Base URL for bytes, honouring a local override.

        Defaults to whatever the catalogue declares; ETHOS_PUBLICATION_URL or a
        `publication_url` config key can point at a different DESY door without
        the catalogue changing.
        """
        from .config import resolve_publication_url

        default = self.descriptor.get("ethos:publication_url", "")
        return resolve_publication_url(default)[0].rstrip("/")

    def members_of(self, name: str) -> list[Dataset]:
        """The datasets that carry files under a family name, innermost included.

        ``reskit-test-data`` yields its members; ``reskit-test-data/era5`` yields
        itself. Nested namespaces are skipped -- only things with an inventory
        come back -- so a caller can treat the result as "what to fetch".
        """
        prefix = f"{name}/"
        members = [
            dataset for key, dataset in self.datasets.items()
            if (key == name or key.startswith(prefix)) and not dataset.namespace
        ]
        return sorted(members, key=lambda d: d.name)

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
            dataset for key, dataset in self.datasets.items()
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
            known = ", ".join(sorted(self.datasets)) or "<none>"
            where = describe_catalog(self.descriptor, self.location)
            hint = ""
            if self.role == ROLE_PUBLISHED:
                # By far the likeliest cause: it was published once and later
                # withdrawn, so the collections file is not wrong, just newer
                # than the catalogue it is pointed at -- or older than it.
                hint = ("\nIf it used to exist, it has been withdrawn from publication. "
                        "Pin an older catalogue, or ask the maintainers to republish it.")
            raise UnknownDataset(
                f"unknown dataset {name!r}: the {where} does not describe it.\n"
                f"It has: {known}.{hint}"
            ) from None

    def base_url_for(self, dataset: Dataset) -> str:
        """Root under which this dataset's resource paths resolve.

        Single point of URL construction, so a per-dataset override (a mirror)
        only has to be honoured here.
        """
        return f"{self.publication_url}/{dataset.remote_prefix}/"

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
    # the one a tool's collections file pins.

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
    ) -> Path:
        """The absolute local path of a file or folder, fetching it if necessary.

        ``key`` is ``"<dataset>/<path>"`` for one file -- a shapefile brings
        its sidecars along -- or ``"<dataset>/<folder>"``, ``"<dataset>"`` or
        a dataset family for a directory, in which case every file under it is
        fetched first. :meth:`resources` says what is under a key without
        fetching. Files already in the cache are not downloaded again.
        """
        from .access import AccessError
        from .config import Roots
        from .retrieval import download

        roots = Roots.coerce(root)
        catalog = self.overlaid(roots)
        name, inner = split_key(catalog, key)
        found, target = select_key(catalog, name, inner, key)
        files = download(catalog, found, root=roots, progressbar=progressbar)
        if target is not None:
            if target.key not in files:
                raise AccessError(f"{key!r} is not available on this machine.")
            return Path(os.path.abspath(files[target.key]))
        return Path(os.path.abspath(directory_of(files, found, name, inner, key)))


def load_catalog(location: str) -> Catalog:
    """Load a datacatalog.json.  Dataset inventories are fetched on first use.

    ``location`` is a local path or an http(s) URL pointing at datacatalog.json.
    Raises :class:`CatalogUnavailable` when there is nothing to read there.
    """
    try:
        text, base = _read(location)
    except (FileNotFoundError, urllib.error.URLError) as error:
        # HTTPError is a URLError: a 404 for a tag nobody has cut yet arrives
        # here too, and reads as "HTTP Error 404: Not Found" -- which says
        # nothing about *which* URL, or that a pin chose it.
        reason = getattr(error, "reason", None) or error
        if isinstance(error, urllib.error.HTTPError):
            reason = f"HTTP {error.code} {error.reason}"
        raise CatalogUnavailable(
            f"cannot read the catalogue index at {location}: {reason}\n"
            f"If a collections file pinned this location, its pin may name a revision or "
            f"repository that does not exist (yet). Use another catalogue for this run with "
            f"--catalog / catalog=, for this shell with $ETHOS_DATA_CATALOG, or for good with "
            f"`ethos-data config set-catalog <datacatalog.json>`."
        ) from error
    descriptor = json.loads(text)

    datasets = {
        entry["name"]: Dataset(
            name=entry["name"],
            title=entry.get("title", ""),
            entry=entry,
            base=base,
        )
        for entry in descriptor.get("datasets", [])
    }
    return Catalog(location=location, descriptor=descriptor, datasets=datasets)


def split_key(catalog: Catalog, key: str) -> tuple[str, str]:
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


def select_key(
    catalog: Catalog, name: str, inner: str, key: str
) -> tuple[list[Resource], Resource | None]:
    """The resources to fetch for a key, and the one file it names, if it names one."""
    if not inner:
        found = [r for member in catalog.members_of(name) for r in member.resources.values()]
        if not found:
            raise KeyError(f"{key!r} has no files in the catalogue")
        return found, None
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


def directory_of(
    files: Mapping[str, Path], resources: list[Resource], name: str, inner: str, key: str
) -> Path:
    """Where a folder, a dataset or a family ended up on this machine.

    Read off the files themselves rather than off a root setting: a dataset may
    come from the public cache, the restricted cache, staging or its own root,
    and each returned path already says which.
    """
    from .access import AccessError

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
