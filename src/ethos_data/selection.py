"""A tool's collections file, resolved into resources and fetched on demand.

(Module named ``selection`` rather than ``collections`` so it can never shadow
the standard library module of that name, nor the :func:`ethos_data.collections`
factory that builds the handle defined here.)

:class:`Collections` is the object a tool builds once -- from the file beside
its own code, via :func:`ethos_data.collections` -- and then calls ``fetch``,
``paths``, ``resolve`` and ``plan`` on. Its ``catalog`` attribute is the
catalogue the file pins, for access by key. ``main`` runs the collection
commands as the tool's own console script (``reskit-data``), so the tool ships
a file and two lines of code and nothing has to be registered anywhere.

A collections file names slices of the shared catalogue; it never repeats file
paths, sizes or checksums. That is deliberate -- if two tools each carried their
own inventory they would drift, and the shared cache would stop deduplicating.

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

import fnmatch
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from . import retrieval
from .catalogs import (
    Catalog,
    Resource,
    directory_of,
    load_catalog,
    select_key,
    split_key,
)
from .retrieval import DataFiles, NamedPaths

if TYPE_CHECKING:
    from .config import Roots

__all__ = [
    "COLLECTIONS_FILENAME",
    "PATHS_KEY",
    "SELECTION_KEYS",
    "VARIANTS",
    "VARIANT_FULL",
    "VARIANT_TEST",
    "CollectionError",
    "Collections",
    "CollectionsNotFound",
    "UnknownCollection",
    "catalog_pin",
    "load_collections",
    "path_matches",
    "variant_name",
]

#: The two shapes a collection may come in. ``test`` is the small selection an
#: example or a test suite runs on in seconds; ``full`` is the real thing. They
#: are the only two, deliberately: the caller's switch is one boolean, and a
#: workflow needs exactly the promise that these two are interchangeable.
VARIANT_TEST = "test"
VARIANT_FULL = "full"
VARIANTS = (VARIANT_TEST, VARIANT_FULL)

#: Handles a workflow asks for by name, mapped to catalogue keys.
PATHS_KEY = "paths"
#: The keys that describe *what a collection selects*. They sit either at the
#: top of a collection or inside each of its variants -- never in both places,
#: because then nobody could say which one a fetch would use.
SELECTION_KEYS = ("extends", "include", PATHS_KEY)


def variant_name(test: bool) -> str:
    """The variant a ``test=`` flag selects."""
    return VARIANT_TEST if test else VARIANT_FULL


class UnknownCollection(KeyError):
    """A name the collections file does not define.

    Subclasses KeyError so ``except KeyError`` handlers written against the
    old behaviour keep working; the CLI catches the specific type to print a
    message rather than a traceback.
    """


class CollectionError(ValueError):
    """A collection is defined in a way that cannot be resolved.

    A maintainer's mistake in ``collections.yaml`` -- a variant that does not
    exist, selection keys both inside and outside the variants, a ``paths``
    handle naming a file the collection does not include, or two variants that
    disagree about which handles they offer. Subclasses ValueError, which is
    what the circular-``extends`` check always raised.
    """


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
    #: The tool whose file this is (``"reskit"``), for messages and as the
    #: default name of its command; None for a file named on its own.
    tool: str | None = None
    #: The cache roots the staging overlay was built for; None means the
    #: configured ones, resolved when a call needs them.
    roots: Roots | None = None

    def names(self) -> list[str]:
        return sorted(self.definitions)

    def describe(self, name: str) -> dict:
        """The collection as written -- title and all -- variants included."""
        return self.definitions[self._check(name)]

    def _check(self, name: str) -> str:
        if name not in self.definitions:
            known = ", ".join(self.names()) or "<none>"
            owner = f"{self.tool} defines" if self.tool else "this file defines"
            raise UnknownCollection(f"unknown collection {name!r}; {owner}: {known}")
        if not isinstance(self.definitions[name], dict):
            raise CollectionError(
                f"collection {name!r} must be a mapping (title, include, ...), "
                f"got {type(self.definitions[name]).__name__}"
            )
        return name

    def variants(self, name: str) -> tuple[str, ...]:
        """The variants a collection defines, ``test`` first; empty for a plain one."""
        definition = self.definitions[self._check(name)]
        return tuple(variant for variant in VARIANTS if variant in definition)

    def definition(self, name: str, test: bool = False) -> dict:
        """The selection a fetch resolves: the collection's own, or one variant's.

        A plain collection answers the same whatever ``test`` says -- a test
        suite's fixtures *are* its test data, and there is nothing else to
        switch to. A collection with variants must have the one asked for; a
        silent fall-back to the other would either download the full inputs
        under a test or, worse, run a real calculation on the fixtures.
        """
        name = self._check(name)
        definition = self.definitions[name]
        found = self.variants(name)
        if not found:
            return definition
        mixed = [key for key in SELECTION_KEYS if key in definition]
        if mixed:
            raise CollectionError(
                f"collection {name!r} has {', '.join(mixed)} at the top level and also the "
                f"variant(s) {', '.join(found)}; move every selection key inside "
                f"{' / '.join(f'{v}:' for v in VARIANTS)}"
            )
        wanted = variant_name(test)
        if wanted not in found:
            raise CollectionError(
                f"collection {name!r} has no {wanted!r} variant (it defines: {', '.join(found)}). "
                + ("Pass test=True (or --test) for its test data."
                   if wanted == VARIANT_FULL else
                   "It has no small test selection; ask for the full data.")
            )
        selected = definition[wanted]
        if not isinstance(selected, dict):
            raise CollectionError(
                f"collection {name!r}: {wanted}: must be a mapping (include, extends, paths), "
                f"got {type(selected).__name__}"
            )
        return selected

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
        own = self._paths_of(name, definition)
        merged: dict[str, str] = {}
        origin: dict[str, str] = {}
        for parent in definition.get("extends", []) or []:
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

    def _include_rules(self, name: str, definition: dict) -> list[dict]:
        """The ``include`` entries, checked for shape.

        A string where a list was meant, or an entry without ``dataset``, used
        to surface as a TypeError or KeyError from deep inside the glob loop --
        a traceback that hid every other collection in ``ethos-data list``.
        """
        rules = definition.get("include", []) or []
        if not isinstance(rules, list):
            raise CollectionError(
                f"collection {name!r}: include must be a list of {{dataset, files}} entries, "
                f"got {type(rules).__name__}"
            )
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("dataset"), str):
                raise CollectionError(
                    f"collection {name!r}: every include entry needs a 'dataset' name "
                    f"(and optionally 'files'), got {rule!r}"
                )
            files = rule.get("files")
            if files is not None and (
                not isinstance(files, list) or not all(isinstance(f, str) for f in files)
            ):
                raise CollectionError(
                    f"collection {name!r}: include.files for {rule['dataset']!r} must be a "
                    f"list of glob strings, got {files!r}"
                )
        return rules

    def _paths_of(self, name: str, definition: dict) -> dict[str, str]:
        entries = definition.get(PATHS_KEY) or {}
        if not isinstance(entries, dict):
            raise CollectionError(
                f"collection {name!r}: {PATHS_KEY} must be a mapping of handle -> "
                f"<dataset>/<file or folder>, got {type(entries).__name__}"
            )
        for handle, key in entries.items():
            if not isinstance(handle, str) or not handle:
                raise CollectionError(f"collection {name!r}: {PATHS_KEY} handles must be names")
            if not isinstance(key, str) or not key.strip("/"):
                raise CollectionError(
                    f"collection {name!r}: {PATHS_KEY}.{handle} must be a key such as "
                    f"'<dataset>/<file>' or '<dataset>/<folder>', got {key!r}"
                )
        return {handle: key.strip("/") for handle, key in entries.items()}

    def check_variants(self, name: str) -> None:
        """Refuse variants that do not offer the same handles.

        The one promise ``test`` and ``full`` make is that code written against
        either runs against the other. A handle present in one and absent from
        the other breaks that promise at the worst moment -- on the machine
        that has the full data, long after the example passed on the fixtures.
        """
        if len(self.variants(name)) < 2:
            return
        offered = {}
        for variant in VARIANTS:
            try:
                offered[variant] = set(self.named_keys(name, variant == VARIANT_TEST))
            except CollectionError as error:
                # The caller may have asked for the *other* variant, and the
                # inner message then gives advice ("pass test=True") that
                # contradicts what they typed. Say what was being compared.
                raise CollectionError(
                    f"collection {name!r}: its {variant!r} variant cannot be resolved, so its "
                    f"test and full variants cannot be compared: {error.args[0]}"
                ) from error
        if offered[VARIANT_TEST] == offered[VARIANT_FULL]:
            return
        differences = []
        for variant in VARIANTS:
            other = VARIANT_FULL if variant == VARIANT_TEST else VARIANT_TEST
            only = sorted(offered[variant] - offered[other])
            if only:
                differences.append(f"only in {variant}: {', '.join(only)}")
        raise CollectionError(
            f"collection {name!r}: its test and full variants must name the same paths "
            f"({'; '.join(differences)}), or code written against one will not run "
            f"against the other"
        )

    def resolve(
        self, name: str, test: bool = False, _seen: frozenset[str] = frozenset()
    ) -> list[Resource]:
        """Expand a collection (and anything it extends) into resources.

        Selection is by glob against the resource path. Shapefile sidecars are
        pulled in automatically -- a .shp without its .dbf/.shx is unreadable,
        and expecting every collections file to spell that out invites bugs.

        ``test`` picks the variant of a collection that has them; it passes
        down through ``extends``, so a test selection is built from its
        parents' test selections. A plain parent is the same either way.
        """
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

        for parent in definition.get("extends", []) or []:
            for resource in self.resolve(parent, test, seen):
                selected[resource.key] = resource

        for rule in self._include_rules(name, definition):
            # One rule may name a family or a glob, so it can reach several
            # datasets. `files:` patterns are matched against each one's own
            # resource paths -- a member's paths are relative to the member, not
            # to the family, so `dataset: reskit-test-data` with
            # `files: ["era5/*.nc"]` selects nothing while
            # `dataset: reskit-test-data/era5` with `files: ["*.nc"]` selects
            # what you meant.
            for dataset in self.catalog.matching_datasets(rule["dataset"]):
                patterns = rule.get("files") or ["**"]
                # resources_matching narrows a sharded dataset to the shards these
                # patterns can reach; the glob below is still the real filter.
                for resource in list(dataset.resources_matching(patterns).values()):
                    if not any(path_matches(resource.path, p) for p in patterns):
                        continue
                    selected[resource.key] = resource
                    for sidecar in resource.sidecars:
                        companion = dataset.resource_at(sidecar)
                        if companion is not None:
                            selected[companion.key] = companion

        return sorted(selected.values(), key=lambda r: r.key)

    # -- Fetching ------------------------------------------------------------

    def fetch(
        self,
        name: str,
        *,
        test: bool = False,
        root: Roots | str | Path | None = None,
        progressbar: bool = True,
        skip_unavailable: bool | None = None,
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

        ``skip_unavailable`` decides what happens to licensed data this machine
        cannot reach: ``True`` leaves it out of the result (and out of
        ``.named``) with a warning, ``False`` raises, ``None`` takes the
        configured answer.
        """
        roots = self._roots(root)
        resources = self.resolve(name, test=test)
        # Checked before anything is downloaded: a handle naming a file the
        # collection does not include is a mistake in collections.yaml, and the
        # maintainer should hear about it before a 40 GB transfer, not after.
        targets = self._named_targets(name, test, resources)
        files = retrieval.download(
            self.catalog,
            resources,
            root=roots,
            progressbar=progressbar,
            skip_unavailable=skip_unavailable,
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
        skip_unavailable: bool | None = None,
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
        Under ``skip_unavailable`` a handle whose data this machine cannot
        reach is left out, with a warning naming it, exactly as the file is
        left out of :meth:`fetch`'s result.
        """
        files = self.fetch(
            name, test=test, root=root, progressbar=progressbar,
            skip_unavailable=skip_unavailable,
        )
        if not files.named and not files.named.omitted:
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
        skip_unavailable: bool | None = None,
    ) -> dict:
        """What fetching a collection would do, without touching the network.

        The report :func:`ethos_data.plan` builds: what is already cached,
        what would be downloaded and how many bytes, what is used in place.
        """
        return retrieval.plan(
            self.catalog, self.resolve(name, test=test), self._roots(root), skip_unavailable
        )

    def main(self, argv: list[str] | None = None, *, prog: str | None = None) -> int:
        """Run the collection commands bound to this file, from a built handle.

        ``list``, ``info``, ``plan``, ``fetch``, ``paths`` and ``verify`` for
        the collections in this file, ``path`` and ``ls`` against the catalogue
        it pins, ``bundle`` and ``config`` -- the same commands ``ethos-data``
        offers for a file named with ``-c``, without the ``-c``. ``prog`` names
        the command in help and messages; the default is ``<tool>-data``.

        For a tool's console script use :func:`ethos_data.tool_main`, which
        builds the handle only for the commands that need one, so ``--help``
        and ``config show`` do not load the catalogue.
        """
        from .cli import run_tool

        return run_tool(self.path, tool=self.tool, prog=prog, argv=argv, loaded=self)

    def _roots(self, root: Roots | str | Path | None) -> Roots:
        from .config import Roots

        if root is not None:
            return Roots.coerce(root)
        return self.roots if self.roots is not None else Roots.coerce(None)

    def _named_targets(self, name: str, test: bool, resources: list[Resource]) -> list[_NamedTarget]:
        """Check every ``paths`` handle against the catalogue and the selection.

        A handle naming a file must name one the collection includes --
        otherwise the file it points at would never be fetched. A handle naming
        a folder must have at least one selected file beneath it; the folder is
        *where the collection's files are*, not a request for everything the
        catalogue holds there, so ``era5: reskit-test-data/era5`` with
        ``files: ["100m_*.nc"]`` means the directory holding those two files.
        Run by the CLI's ``list``, ``info`` and ``plan`` too, so a mistake in
        ``paths`` is flagged before anybody tries to fetch.
        """
        named = self.named_keys(name, test)
        selected = {resource.key: resource for resource in resources}
        targets = []
        for handle, key in named.items():
            try:
                dataset, inner = split_key(self.catalog, key)
            except KeyError as error:
                raise _not_in_catalogue(name, handle, key, error) from error
            # Answered from the selection first, so that checking a dataset-level
            # handle on a sharded dataset does not pull in every shard the include
            # patterns deliberately avoided. The catalogue is only consulted to
            # tell a mistake in `paths` from a mistake in `include`.
            file = selected.get(key)
            if file is not None:
                targets.append(_NamedTarget(handle, file.key, dataset, inner, file, ()))
                continue
            if inner:
                unselected = self.catalog.dataset(dataset).resource_at(inner)
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
                    raise _not_in_catalogue(name, handle, key, error) from error
                raise CollectionError(
                    f"collection {name!r}: paths.{handle} names the folder {key!r}, but the "
                    f"collection includes no file under it; the folder would be empty"
                )
            targets.append(_NamedTarget(handle, key, dataset, inner, None, under))
        return targets

    @staticmethod
    def _named_paths(targets: list[_NamedTarget], files: DataFiles, name: str) -> NamedPaths:
        """Where each handle ended up on this machine, read off the fetched files.

        A handle whose data this machine cannot reach is left out and named in
        a warning -- the same contract ``skip_unavailable`` gives the files
        themselves: absent from the mapping, never a path to nothing. Without
        ``skip_unavailable`` the unreachable data has already raised before this.
        """
        named = NamedPaths(collection=name)
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
            directory = directory_of(files, available, target.dataset, target.inner, target.key)
            named[target.handle] = Path(os.path.abspath(directory))
        if named.omitted:
            warnings.warn(
                f"collection {name!r}: the named path(s) {', '.join(named.omitted)} are not "
                f"available on this machine and have been left out -- the mapping has no entry "
                f"for them.",
                UserWarning,
                stacklevel=4,
            )
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


def _not_in_catalogue(collection: str, handle: str, key: str, error: KeyError) -> CollectionError:
    message = error.args[0] if error.args else str(error)
    return CollectionError(
        f"collection {collection!r}: paths.{handle} names {key!r}, which is not in "
        f"the catalogue. {message}"
    )


def path_matches(path: str, pattern: str) -> bool:
    """Glob a resource path with proper directory semantics.

    ``*`` matches within one path segment; ``**`` matches any number of
    segments. Plain ``fnmatch`` would let ``*.tif`` match ``sub/dir/x.tif``,
    which quietly pulls in far more than a collections file asked for.

    Public because the manifest writer selects files with the same rule -- see
    ``maintain.manifest.select``. A dataset's ``ethos:include`` and a collection's
    ``files:`` have to mean the same thing by the same code, or a pattern that
    picks a file in one place would miss it in the other.
    """
    return _match_segments(path.split("/"), pattern.split("/"))


def _match_segments(parts: list[str], patterns: list[str]) -> bool:
    if not patterns:
        return not parts
    head, rest = patterns[0], patterns[1:]
    if head == "**":
        if not rest:
            return True
        return any(_match_segments(parts[i:], rest) for i in range(len(parts) + 1))
    if not parts or not fnmatch.fnmatchcase(parts[0], head):
        return False
    return _match_segments(parts[1:], rest)


def load_collections(
    path: str | Path,
    catalog: str | Catalog | None = None,
    *,
    include_staging: bool = True,
    roots: Roots | None = None,
    tool: str | None = None,
) -> Collections:
    """Load a collections file with the configured development overlay.

    The catalogue is ``catalog`` if given, else the file's own ``catalog:`` pin,
    else the built-in public catalogue (``ethos_data.config.DEFAULT_CATALOG``).
    Set ``include_staging=False`` for canonical metadata, for example when
    exporting test fixtures. ``roots`` selects the overlay explicitly; otherwise
    the configured roots apply. A supplied catalogue is not modified. ``tool``
    names the tool whose file this is, for messages and its command's name.

    :func:`ethos_data.collections` is the same with the configured catalogue
    override (``$ETHOS_DATA_CATALOG``, ``config set-catalog``) applied first,
    which is what a tool wants.
    """
    path = Path(path).expanduser().resolve()
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    if isinstance(catalog, Catalog):
        resolved = catalog
    else:
        location = catalog or catalog_pin(path, document)
        if location is None:
            # No pin: the public catalogue, so a collections file that selects
            # only public data works with nothing configured anywhere.
            from .config import DEFAULT_CATALOG

            location = DEFAULT_CATALOG
        resolved = load_catalog(str(location))

    if include_staging:
        from .staging import with_staging

        resolved = with_staging(resolved, roots)
    return Collections(
        path=path, catalog=resolved, definitions=document.get("collections", {}),
        tool=tool, roots=roots,
    )


def catalog_pin(path: str | Path, document: dict | None = None) -> str | None:
    """The catalogue a collections file pins for itself, or None if it does not.

    A relative path is resolved against the file, not the caller's working
    directory -- the pin belongs to the file. Shared with the commands that take
    a *key* rather than a collection (``path``, ``ls``), so that ``-c`` means
    the same catalogue for them as for ``fetch``.
    """
    path = Path(path).expanduser().resolve()
    if document is None:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    location = document.get("catalog")
    if not location:
        return None
    # Retain compatibility with legacy '@ref' suffixes by stripping them.
    # Remote revisions must be part of the URL itself; this does not
    # rewrite a Git host's branch/tag segment.
    location = str(location)
    if not Path(location).exists() and "@" in location.rsplit("/", 1)[-1]:
        location = location.rsplit("@", 1)[0]
    if not location.startswith(("http://", "https://")):
        location = str((path.parent / location).resolve())
    return location


#: The conventional name of the file a tool ships beside its data module.
COLLECTIONS_FILENAME = "collections.yaml"


class CollectionsNotFound(LookupError):
    """No collections file where one was asked for: a path with no file behind
    it, or a command run where none is configured and none lies in the current
    directory."""
