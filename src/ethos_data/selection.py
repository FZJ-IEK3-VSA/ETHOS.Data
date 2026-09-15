"""Resolving a tool's collections file into a concrete list of resources.

(Module named ``selection`` rather than ``collections`` so it can never shadow
the standard library module of that name.)

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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .catalog import Catalog, Resource, load_catalog

if TYPE_CHECKING:
    from .config import Roots

__all__ = [
    "COLLECTIONS_FILENAME",
    "ENTRY_POINT_GROUP",
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
    "package_collections",
    "path_matches",
    "registered_packages",
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
    path: Path
    catalog: Catalog
    definitions: dict

    def names(self) -> list[str]:
        return sorted(self.definitions)

    def describe(self, name: str) -> dict:
        """The collection as written -- title and all -- variants included."""
        return self.definitions[self._check(name)]

    def _check(self, name: str) -> str:
        if name not in self.definitions:
            known = ", ".join(self.names()) or "<none>"
            raise UnknownCollection(f"unknown collection {name!r}; this file defines: {known}")
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
) -> Collections:
    """Load a collections file with the configured development overlay.

    The catalogue is ``catalog`` if given, else the file's own ``catalog:`` pin,
    else the built-in public catalogue (``ethos_data.config.DEFAULT_CATALOG``).
    Set ``include_staging=False`` for canonical metadata, for example when
    exporting test fixtures. ``roots`` selects the overlay explicitly; otherwise
    the configured roots apply. A supplied catalogue is not modified.
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
    return Collections(path=path, catalog=resolved, definitions=document.get("collections", {}))


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


#: How a package ships its collections file. The entry point's name is what
#: users type (``package="reskit"``, ``ethos-data -p reskit``); its value names the
#: module whose directory holds ``collections.yaml``:
#:
#:     [project.entry-points."ethos_data.collections"]
#:     reskit = "reskit.data"
#:
#: Registered in the package's own metadata, the file is found from any working
#: directory, in a source checkout and an installed wheel alike -- which is the
#: one job a per-package wrapper module used to exist for.
ENTRY_POINT_GROUP = "ethos_data.collections"
COLLECTIONS_FILENAME = "collections.yaml"


class CollectionsNotFound(LookupError):
    """No collections file where one was asked for: a package name nothing
    registers, or a path with no file behind it."""


def registered_packages() -> dict[str, str]:
    """Installed packages that ship a collections file, as ``{name: module}``.

    Read from package metadata alone, so listing them imports nothing.
    """
    from importlib.metadata import entry_points

    return {
        entry.name: entry.value
        for entry in entry_points().select(group=ENTRY_POINT_GROUP)
    }


def package_collections(package: str) -> Path:
    """The ``collections.yaml`` an installed package registered under ``package``."""
    import importlib.util

    registered = registered_packages()
    if package not in registered:
        known = ", ".join(sorted(registered)) or "none"
        raise CollectionsNotFound(
            f"no installed package ships ETHOS.Data collections under the name "
            f"{package!r} (registered: {known}). A package registers its "
            f"{COLLECTIONS_FILENAME} with an entry point in the "
            f"{ENTRY_POINT_GROUP!r} group."
        )
    module = registered[package].partition(":")[0].strip()
    try:
        spec = importlib.util.find_spec(module)
    except ModuleNotFoundError:
        spec = None
    if spec is None:
        raise CollectionsNotFound(
            f"{package!r} registers the module {module!r}, which cannot be imported here."
        )
    if spec.submodule_search_locations:
        directory = Path(next(iter(spec.submodule_search_locations)))
    else:
        directory = Path(spec.origin).parent
    location = directory / COLLECTIONS_FILENAME
    if not location.is_file():
        raise CollectionsNotFound(
            f"{package!r} registers the module {module!r}, but there is no "
            f"{COLLECTIONS_FILENAME} beside it ({location}). Ship it as package data."
        )
    return location
