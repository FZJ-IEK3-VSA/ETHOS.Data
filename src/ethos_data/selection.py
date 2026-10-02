"""A tool's collections file, resolved into resources and fetched on demand.

(Module named ``selection`` rather than ``collections`` so it can never shadow
the standard library module of that name, nor the :func:`ethos_data.collections`
factory that builds the handle defined here.)

:class:`Collections` is the object a tool builds once -- from the file beside
its own code, via :func:`ethos_data.collections` -- and then calls ``fetch``,
``paths``, ``resolve`` and ``plan`` on. Its ``catalog`` attribute is the
catalogue the settings choose within the file's release bounds, for access by
key. ``main`` runs the collection
commands as the tool's own console script (``<tool>-data``), so the tool ships
a file and two lines of code and nothing has to be registered anywhere.

A collections file names slices of the shared catalogue; it never repeats file
paths, sizes or checksums. That is deliberate -- if two tools each carried their
own inventory they would drift, and the public cache would stop deduplicating.

Two things a collection may carry beyond its selection, both for the same
reason -- a workflow's code should not have to know resource keys:

**Named paths.** ``paths:`` maps a handle the workflow understands to a key in
the catalogue -- one file, or a folder, dataset or family -- and
:func:`ethos_data.paths` hands back ``{handle: absolute local path}`` once the
data is there. The maintainer who wrote the collection is the one who knows
that the workflow's ``gwa_100m_path`` argument wants
``reskit-test-data/global-wind-atlas/gwa100-like.tif``; nobody else should
need to.

**Variants.** A collection may be written twice, under ``test:`` and
``full:`` -- a small selection that makes an example or a test run in seconds,
and the real inputs. Both carry the same handles, checked, so code written
against one runs unchanged against the other; the caller only flips ``test=``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from . import report, retrieval
from .catalogs import (
    Catalog,
    Resource,
    check_release,
    directory_of,
    load_catalog,
    select_key,
    split_key,
)
from .errors import (
    CollectionError,
    IncompleteCatalog,
    UnknownCollection,
    UnknownDataset,
    UnknownKey,
)
from .formats import keys as k
from .model.patterns import path_matches
from .retrieval import DataFiles, NamedPaths

if TYPE_CHECKING:
    from .config import Roots, Settings
    from .formats.collections_file import Collection, Selection
    from .model.versions import Bounds

__all__ = [
    "COLLECTIONS_FILENAME",
    "PATHS_KEY",
    "VARIANTS",
    "VARIANT_FULL",
    "VARIANT_TEST",
    "Collections",
    "load_collections",
    "variant_name",
]

#: The two shapes a collection may come in. ``test`` is the small selection an
#: example or a test suite runs on in seconds; ``full`` is the real thing. They
#: are the only two, deliberately: the caller's switch is one boolean, and a
#: workflow needs exactly the promise that these two are interchangeable.
VARIANT_TEST = k.VARIANT_TEST
VARIANT_FULL = k.VARIANT_FULL
VARIANTS = k.VARIANTS

#: Handles a workflow asks for by name, mapped to catalogue keys.
PATHS_KEY = "paths"


def variant_name(test: bool) -> str:
    """The variant a ``test=`` flag selects."""
    return VARIANT_TEST if test else VARIANT_FULL


@dataclass
class Collections:
    """A collections file, loaded: what a tool's workflows need, by name.

    Built by :func:`ethos_data.collections` (or :func:`load_collections`) and
    kept for the life of the process -- the file is read once and the
    catalogue loaded once, whatever the number of ``fetch`` calls after.
    """

    path: Path
    catalog: Catalog
    definitions: dict
    #: The tool whose file this is (``"mytool"``), for messages and as the
    #: default name of its command; None for a file named on its own.
    tool: str | None = None
    #: The cache roots the staging overlay was built for; None means the
    #: ones in :attr:`settings`.
    roots: Roots | None = None
    #: The settings this handle uses, read once when it was built.
    _settings: Settings | None = field(default=None, repr=False)
    #: Each collection checked through its model, when it is first used.
    _checked: dict[str, Collection] = field(default_factory=dict, repr=False)

    @property
    def settings(self) -> Settings:
        """The settings file, the catalogue and its version, the caches, and their sources.

        Read once, when the handle was built, and used by every later call, so
        a script reads the same catalogue and caches from start to finish.
        ``print(data.settings)`` reports them next to a script's results.
        """
        if self._settings is None:
            from .config import read_settings

            self._settings = read_settings().with_catalog(
                self.catalog.location, "loaded directly", self.catalog.version
            )
        return self._settings

    def names(self) -> list[str]:
        return sorted(self.definitions)

    def describe(self, name: str) -> Collection:
        """The collection -- title and all, variants included -- checked through its model.

        Checked when it is first used, so a mistake in one collection is
        reported with every problem in it and their places, and leaves the
        other collections in the file usable.
        """
        name = self._check(name)
        if name not in self._checked:
            self._checked[name] = _checked(name, self.definitions[name])
        return self._checked[name]

    def _check(self, name: str) -> str:
        if name not in self.definitions:
            known = ", ".join(self.names()) or "<none>"
            owner = f"{self.tool} defines" if self.tool else "this file defines"
            raise UnknownCollection(f"unknown collection {name!r}; {owner}: {known}")
        return name

    def variants(self, name: str) -> tuple[str, ...]:
        """The variants a collection defines, ``test`` first; empty for a plain one."""
        return self.describe(name).variants()

    def definition(self, name: str, test: bool = False) -> Selection:
        """The selection a fetch resolves: the collection's own, or one variant's.

        A plain collection answers the same whatever ``test`` says -- a test
        suite's fixtures *are* its test data, and there is nothing else to
        switch to. A collection with variants must have the one asked for; a
        silent fall-back to the other would either download the full inputs
        under a test or, worse, run a real calculation on the fixtures.
        """
        collection = self.describe(name)
        found = collection.variants()
        if not found:
            return collection
        wanted = variant_name(test)
        if wanted not in found:
            raise _VariantError(name, f"has no {wanted} variant")
        return getattr(collection, wanted)

    def named_keys(
        self, name: str, test: bool = False, _seen: frozenset[str] = frozenset()
    ) -> dict[str, str]:
        """The collection's ``paths``: ``{handle: catalogue key}``, not yet on disk.

        Handles are inherited through ``extends`` and a collection's own entry
        wins over anything inherited. Two parents that hand down the same handle
        with different keys are an error unless the child settles it, because
        picking one silently would hand a workflow the wrong raster.
        """
        name = self._check(name)
        seen = _seen | {name}
        definition = self.definition(name, test)
        own = {handle: key.strip("/") for handle, key in definition.paths.items()}
        merged: dict[str, str] = {}
        origin: dict[str, str] = {}
        for parent in definition.extends:
            if parent in seen:
                continue  # the cycle is reported by resolve(); do not double up
            for handle, key in self.named_keys(parent, test, seen).items():
                if handle in merged and merged[handle] != key and handle not in own:
                    raise CollectionError(
                        f"collection {name!r} inherits paths.{handle} from both "
                        f"{origin[handle]!r} ({merged[handle]}) and {parent!r} ({key}); "
                        f"define paths.{handle} in {name!r} to say which is meant"
                    )
                merged[handle] = key
                origin[handle] = parent
        merged.update(own)
        return merged

    def check_variants(self, name: str) -> None:
        """Refuse variants that do not offer the same handles.

        The one promise ``test`` and ``full`` make is that code written against
        either runs against the other. A handle present in one and absent from
        the other breaks that promise at the worst moment -- on the machine
        that has the full data, long after the example passed on the fixtures.
        """
        if len(self.variants(name)) < 2:
            return
        offered = {
            variant: set(self.named_keys(name, variant == VARIANT_TEST))
            for variant in VARIANTS
        }
        if offered[VARIANT_TEST] == offered[VARIANT_FULL]:
            return
        clauses = []
        for variant in VARIANTS:
            other = VARIANT_FULL if variant == VARIANT_TEST else VARIANT_TEST
            only = sorted(offered[variant] - offered[other])
            if len(only) == 1:
                clauses.append(
                    f"named path {only[0]!r} is in its {variant} variant only"
                )
            elif only:
                listed = ", ".join(repr(handle) for handle in only)
                clauses.append(
                    f"named paths {listed} are in its {variant} variant only"
                )
        raise _VariantError(name, *clauses, named_path=True)

    def resolve(self, name: str, test: bool = False) -> list[Resource]:
        """Expand a collection (and anything it extends) into resources.

        Selection is by glob against the resource path. Shapefile sidecars are
        pulled in automatically -- a .shp without its .dbf/.shx is unreadable,
        and expecting every collections file to spell that out invites bugs.

        ``test`` picks the variant of a collection that has them; it passes
        down through ``extends``, so a test selection is built from its
        parents' test selections. A plain parent is the same either way. A
        variant missing from a collection reached through ``extends`` is
        reported as that: the collection asked for extends one whose variant
        is missing.
        """
        try:
            return self._resolve(name, test)
        except _VariantError as problem:
            if problem.collection == name:
                raise
            raise CollectionError(
                f"collection {name!r} extends {problem.collection!r}, {problem.clause}"
            ) from None

    def _resolve(
        self, name: str, test: bool, _seen: frozenset[str] = frozenset()
    ) -> list[Resource]:
        name = self._check(name)
        if name in _seen:
            chain = " -> ".join([*sorted(_seen), name])
            raise CollectionError(f"circular 'extends' in collections file: {chain}")
        seen = _seen | {name}
        # The definition first, so a mistake in *this* collection's shape is
        # reported as such and not wrapped as a failed variant comparison.
        definition = self.definition(name, test)
        # Every collection on the way, not only the one asked for: a plain
        # `all` that extends a lopsided `onshore_wind` would otherwise hand a
        # workflow different handles per variant, which is the one thing the
        # check exists to prevent. Free for a collection without variants.
        self.check_variants(name)
        selected: dict[str, Resource] = {}

        for parent in definition.extends:
            for resource in self._resolve(parent, test, seen):
                selected[resource.key] = resource

        for rule in definition.include:
            # One rule may name a family or a glob, so it can reach several
            # datasets. `files:` patterns are matched against each one's own
            # resource paths -- a member's paths are relative to the member, not
            # to the family, so `dataset: reskit-test-data` with
            # `files: ["era5/*.nc"]` selects nothing while
            # `dataset: reskit-test-data/era5` with `files: ["*.nc"]` selects
            # what you meant.
            try:
                datasets = self.catalog.matching_datasets(rule.dataset)
            except UnknownDataset as error:
                raise UnknownDataset(f"collection {name!r}: {error.message}") from None
            for dataset in datasets:
                if dataset.superseded_by:
                    report.warning(
                        f"collection {name!r} reads {dataset.name!r}, which "
                        f"{', '.join(dataset.superseded_by)} supersedes: a newer "
                        "version of the data with another layout and other keys."
                    )
                patterns = rule.files or ["**"]
                # resources_matching narrows a sharded dataset to the shards these
                # patterns can reach; the glob below is still the real filter.
                matched = [
                    resource
                    for resource in list(dataset.inventory.matching(patterns).values())
                    if any(path_matches(resource.path, p) for p in patterns)
                ]
                # A sidecar the inventory lacks is left out: the files that are
                # there are still the ones the rule asked for.
                with_companions, _ = self.catalog.with_sidecars(matched)
                selected.update(with_companions)

        return sorted(selected.values(), key=lambda r: r.key)

    # -- Fetching ------------------------------------------------------------

    def select(self, name: str, test: bool = False) -> list[Resource]:
        """The resources a collection selects, its ``paths`` handles checked against them.

        What every command resolves first: a handle naming a file the
        collection does not include is a mistake in the collections file, and
        is refused here, before anything is reported or moved.
        """
        resources = self.resolve(name, test=test)
        self._named_targets(name, test, resources)
        return resources

    def fetch(
        self,
        name: str,
        *,
        test: bool = False,
        root: Roots | str | Path | None = None,
        progressbar: bool = True,
        fetch: bool = True,
    ) -> DataFiles:
        """Make a collection available locally and return ``{key: Path}``.

        Keys are ``"<dataset>/<resource path>"``. Files already present and
        matching their recorded checksum are not re-downloaded -- including
        files another tool fetched earlier. Datasets with a configured local
        root are used in place.

        ``test=True`` selects the collection's small ``test`` variant where the
        maintainer defined one; the default is the full data. A collection
        without variants is the same either way. The result's ``.named`` holds
        the collection's ``paths`` as ``{handle: Path}`` -- see :meth:`paths`.

        Every input is required: licensed data this machine cannot read raises
        :class:`~ethos_data.errors.AccessError` before anything is downloaded,
        describing the dataset and how to register a copy.

        ``fetch=False`` downloads nothing and contacts no store: every file is
        returned where it is on this machine, and one that is not raises
        :class:`~ethos_data.errors.NotFetched`, naming the path it belongs at.
        """
        roots = self._roots(root)
        resources = self.resolve(name, test=test)
        self._refuse_unpublished(resources)
        # Checked before anything is downloaded: a handle naming a file the
        # collection does not include is a mistake in collections.yaml, and the
        # maintainer should hear about it before a 40 GB transfer, not after.
        targets = self._named_targets(name, test, resources)
        files = retrieval.download(
            self.catalog,
            resources,
            root=roots,
            progressbar=progressbar,
            fetch=fetch,
        )
        files.named = self._named_paths(targets, files, name)
        return files

    def paths(
        self,
        name: str,
        *,
        test: bool = False,
        root: Roots | str | Path | None = None,
        progressbar: bool = True,
        fetch: bool = True,
    ) -> NamedPaths:
        """The inputs a collection names, as ``{handle: absolute Path}``, fetched.

        A collection's ``paths:`` maps handles the workflow understands to
        catalogue keys -- ``era5: reskit-test-data/era5`` for a folder,
        ``gwa_100m: reskit-test-data/global-wind-atlas/gwa100-like.tif`` for a
        file. This fetches the collection like :meth:`fetch` and returns those
        handles resolved to where the data is on this machine, so a workflow
        is fed without its caller knowing a single resource key::

            inputs = data.paths("onshore_wind", test=True)
            simulate(era5_path=inputs["era5"], gwa_100m_path=inputs["gwa_100m"])

        ``test=True`` selects the collection's ``test`` variant; the handles
        are the same in both variants, so the call above runs unchanged on the
        full data once ``test`` is dropped. A collection that declares no
        ``paths`` is refused here -- :meth:`fetch` returns its files by key.
        ``fetch=False`` resolves the handles without downloading anything, and
        raises :class:`~ethos_data.errors.NotFetched` for a file that is not on
        this machine, naming the path the same call with ``fetch=True`` puts it.
        """
        files = self.fetch(
            name,
            test=test,
            root=root,
            progressbar=progressbar,
            fetch=fetch,
        )
        if not files.named:
            raise CollectionError(
                f"collection {name!r} declares no named paths -- nothing under 'paths:' in "
                f"its definition. fetch({name!r}) returns its files by resource key; "
                f"ask the {self.tool or 'collections file'} maintainer to name the "
                f"workflow's inputs."
            )
        return files.named

    def plan(
        self,
        name: str,
        *,
        test: bool = False,
        root: Roots | str | Path | None = None,
    ) -> dict:
        """What fetching a collection would do, without touching the network.

        The report :func:`ethos_data.plan` builds: what is already cached,
        what would be downloaded and how many bytes, what is used in place.
        """
        return retrieval.plan(
            self.catalog,
            self.resolve(name, test=test),
            self._roots(root),
        )

    def prepare(
        self,
        name: str,
        *,
        test: bool = False,
        root: Roots | str | Path | None = None,
    ) -> dict:
        """The plan of a fetch about to start, after the checks the fetch makes.

        The collection is selected, its ``paths`` checked, and restricted data
        this account cannot read, or a file with nowhere to download it from,
        is refused here, before anything is downloaded: what is reported next
        is a fetch that starts. The plan is :func:`ethos_data.plan`'s.
        """
        from .access import locate

        resources = self.select(name, test=test)
        roots = self._roots(root)
        report = retrieval.plan(self.catalog, resources, roots)
        if report["unavailable"]:
            locate(self.catalog, resources, roots)  # raises the refusal
        return report

    def resolve_every(self) -> tuple[list[Resource], list[tuple[str, str]]]:
        """Every collection in every variant, and what could not be resolved.

        What is on disk is one cache, and a file a test variant selects is as
        much a file to check as one a full variant does. A collection or
        variant that cannot be resolved -- a dataset this catalogue does not
        describe, say -- is listed as ``(label, reason)`` and left out, rather
        than stopping the rest. The resources are in key order, each once.
        """
        resources: dict[str, Resource] = {}
        skipped: list[tuple[str, str]] = []
        for name in self.names():
            try:
                variants = self.variants(name) or (None,)
            except CollectionError as error:
                skipped.append((name, _first_line(error)))
                continue
            for variant in variants:
                label = name if variant is None else f"{name} [{variant}]"
                try:
                    selected = self.resolve(name, test=variant == VARIANT_TEST)
                except (UnknownDataset, IncompleteCatalog, CollectionError) as error:
                    skipped.append((label, _first_line(error)))
                    continue
                for resource in selected:
                    resources[resource.key] = resource
        return sorted(resources.values(), key=lambda r: r.key), skipped

    def main(self, argv: list[str] | None = None, *, prog: str | None = None) -> int:
        """Run the collection commands bound to this file, from a built handle.

        ``show``, ``fetch`` and ``verify`` for the collections in this file,
        resolved against the catalogue the settings choose within its release
        bounds, plus ``bundle``, ``staging`` and ``config``. A single catalogue key is ``ethos-data``'s to hand out.
        ``prog`` names the command in help and messages; the default is
        ``<tool>-data``.

        For a tool's console script use :func:`ethos_data.tool_main`, which
        builds the handle only for the commands that need one, so ``--help``
        and ``config show`` do not load the catalogue.
        """
        from .cli import run_tool

        return run_tool(self.path, tool=self.tool, prog=prog, argv=argv, loaded=self)

    def _roots(self, root: Roots | str | Path | None) -> Roots:
        from .config import Roots

        if isinstance(root, Roots):
            return root
        base = self.roots if self.roots is not None else self.settings.roots
        return base if root is None else base.with_public(root)

    def _named_targets(
        self, name: str, test: bool, resources: list[Resource]
    ) -> list[_NamedTarget]:
        """Check every ``paths`` handle against the catalogue and the selection.

        A handle naming a file must name one the collection includes --
        otherwise the file it points at would never be fetched. A handle naming
        a folder must have at least one selected file beneath it; the folder is
        *where the collection's files are*, not a request for everything the
        catalogue holds there, so ``era5: reskit-test-data/era5`` with
        ``files: ["100m_*.nc"]`` means the directory holding those two files.
        Run by the CLI's ``show`` and ``fetch --plan`` too, so a mistake in
        ``paths`` is flagged before anybody tries to fetch.
        """
        named = self.named_keys(name, test)
        selected = {resource.key: resource for resource in resources}
        targets = []
        for handle, key in named.items():
            try:
                dataset, inner = split_key(self.catalog, key)
            except KeyError as error:
                raise _not_in_catalogue(name, error) from error
            # Answered from the selection first, so that checking a dataset-level
            # handle on a sharded dataset does not pull in every shard the include
            # patterns deliberately avoided. The catalogue is only consulted to
            # tell a mistake in `paths` from a mistake in `include`.
            file = selected.get(key)
            if file is not None:
                targets.append(_NamedTarget(handle, file.key, dataset, inner, file, ()))
                continue
            if inner:
                unselected = self.catalog.dataset(dataset).inventory.at(inner)
                if unselected is not None:
                    raise CollectionError(
                        f"collection {name!r}: paths.{handle} names the file {key!r}, which "
                        f"the collection does not include; add it under 'include:' "
                        f"(dataset: {dataset}, files: [{unselected.path!r}])"
                    )
            prefix = key + "/"
            under = tuple(r for r in resources if r.key.startswith(prefix))
            if not under:
                try:
                    select_key(self.catalog, dataset, inner, key)
                except KeyError as error:
                    raise _not_in_catalogue(name, error) from error
                raise CollectionError(
                    f"collection {name!r}: paths.{handle} names the folder {key!r}, but the "
                    f"collection includes no file under it; the folder would be empty"
                )
            targets.append(_NamedTarget(handle, key, dataset, inner, None, under))
        return targets

    @staticmethod
    def _named_paths(
        targets: list[_NamedTarget], files: DataFiles, name: str
    ) -> NamedPaths:
        """Where each handle ended up on this machine, read off the fetched files.

        Every file is there: a fetch that could not provide one has raised
        before this, so every handle the collection defines is in the mapping.
        """
        named = NamedPaths(collection=name)
        for target in targets:
            if target.file is not None:
                named[target.handle] = Path(os.path.abspath(files[target.file.key]))
                continue
            directory = directory_of(
                files, target.under, target.dataset, target.inner, target.key
            )
            named[target.handle] = Path(os.path.abspath(directory))
        return named


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


def _first_line(error: BaseException) -> str:
    """An error's message, first line only, as a list of what was skipped shows it."""
    message = getattr(error, "message", None) or (error.args[0] if error.args else "")
    return str(message).splitlines()[0] if message else type(error).__name__


def _not_in_catalogue(collection: str, error: KeyError) -> KeyError:
    """The not-found a ``paths`` key met, naming the collection that asked."""
    message = getattr(error, "message", None) or (error.args[0] if error.args else "")
    kind = (
        type(error) if isinstance(error, (UnknownDataset, UnknownKey)) else UnknownKey
    )
    return kind(f"collection {collection!r}: {message}")


class _VariantError(CollectionError):
    """A collection's variant is missing, or its variants name different paths.

    Keeps the collection and the clause apart, so that a collection that
    extends this one can say so: "collection 'all' extends 'onshore_wind',
    which has no test variant".
    """

    def __init__(self, collection: str, *clauses: str, named_path: bool = False):
        self.collection = collection
        if named_path:
            self.clause = ", and ".join(f"whose {clause}" for clause in clauses)
            own = f"collection {collection!r}: " + ", and ".join(
                f"the {clause}" for clause in clauses
            )
        else:
            self.clause = ", and ".join(f"which {clause}" for clause in clauses)
            own = f"collection {collection!r} " + ", and ".join(clauses)
        super().__init__(own)


def load_collections(
    path: str | Path,
    catalog: str | Catalog | None = None,
    *,
    include_staging: bool = True,
    roots: Roots | None = None,
    tool: str | None = None,
    settings: Settings | None = None,
    bundles: Sequence = (),
    download: bool | None = None,
) -> Collections:
    """Load a collections file with the configured development overlay.

    The catalogue is ``catalog`` if given, else ``$ETHOS_DATA_CATALOG`` or the
    settings file's, else the public catalogue at the release the file's
    bounds select: :meth:`~ethos_data.config.Settings.choose_catalog`. A
    catalogue outside the bounds raises
    :class:`~ethos_data.errors.CatalogVersionError`, naming both.
    Set ``include_staging=False`` for canonical metadata, for example when
    exporting test fixtures. ``roots`` selects the overlay explicitly; otherwise
    the configured roots apply. A supplied catalogue is not modified. ``tool``
    names the tool whose file this is, for messages and its command's name.

    :func:`ethos_data.collections` is the same with ``root=`` and the settings
    read for it. ``settings`` is the snapshot the handle keeps; by default the
    settings are read here, once.

    ``bundles`` are the bundle directories the package ships: their datasets
    are read from them first, before staging is laid over them, unless
    ``download`` -- by default ``$ETHOS_DATA_DOWNLOAD`` -- asks for the
    catalogue route.
    """
    from .bundles import Bundle, load_bundle, with_bundles
    from .config import download_requested, read_settings

    path = Path(path).expanduser().resolve()
    bounds, definitions = _read(path)
    if settings is None:
        settings = read_settings()
    if roots is None:
        roots = settings.roots

    if isinstance(catalog, Catalog):
        resolved = catalog
        source = (
            resolved._settings.catalog_source if resolved._settings else "passed in"
        )
    else:
        location, source = settings.choose_catalog(
            explicit=str(catalog) if catalog else None, bounds=bounds
        )
        resolved = load_catalog(location, settings=settings)
    if bounds is not None:
        check_release(resolved, bounds, path.name)
    settings = settings.with_catalog(resolved.location, source, resolved.version)
    if not isinstance(catalog, Catalog):
        # Loaded here, so it is this handle's: a catalogue passed in is not
        # modified, and keeps the settings it already has.
        resolved._settings = settings

    base = resolved
    download = download_requested(download)
    loaded = tuple(
        bundle if isinstance(bundle, Bundle) else load_bundle(bundle)
        for bundle in bundles
    )
    if loaded and not download:
        resolved = with_bundles(resolved, loaded)
    if include_staging:
        from .staging import with_staging

        resolved = with_staging(resolved, roots)
    return Collections(
        path=path,
        catalog=resolved,
        definitions=definitions,
        tool=tool,
        roots=roots,
        _settings=settings,
        bundles=loaded,
        download=download,
        base_catalog=base,
    )


def _read(path: Path) -> tuple[Bounds | None, dict]:
    """A collections file's release bounds, checked, and its collections as written.

    The bounds are checked through their model here, since they choose the
    catalogue; each collection is checked when it is first used.
    """
    from pydantic import ValidationError

    from .formats.collections_file import CatalogBounds
    from .formats.fields import describe

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise CollectionError(
            f"{path} must contain a YAML mapping, got {type(document).__name__}"
        )
    collections = document.get("collections") or {}
    if not isinstance(collections, dict):
        raise CollectionError(
            f"{path}: collections must be a mapping of names to collections, "
            f"got {type(collections).__name__}"
        )
    if document.get("catalog") is None:
        return None, collections
    try:
        bounds = CatalogBounds.model_validate(document["catalog"]).bounds()
    except ValidationError as error:
        problems = "".join(f"\n  {line}" for line in describe(error, ("catalog",)))
        raise CollectionError(
            f"{path} is not a valid collections file:{problems}"
        ) from None
    return bounds, collections


def _checked(name: str, definition: object) -> Collection:
    """One collection, checked through its model: every problem, with its place."""
    from pydantic import ValidationError

    from .formats.collections_file import Collection
    from .formats.fields import describe

    try:
        return Collection.model_validate(definition)
    except ValidationError as error:
        raise CollectionError(
            "\n".join(f"collection {name!r}: {line}" for line in describe(error))
        ) from None


#: The conventional name of the file a tool ships beside its data module.
COLLECTIONS_FILENAME = "collections.yaml"
