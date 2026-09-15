"""Resolving a tool's collections file into a concrete list of resources.

(Module named ``selection`` rather than ``collections`` so it can never shadow
the standard library module of that name.)

A collections file names slices of the shared catalogue; it never repeats file
paths, sizes or checksums. That is deliberate -- if two tools each carried their
own inventory they would drift, and the shared cache would stop deduplicating.
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
    "Collections",
    "CollectionsNotFound",
    "load_collections",
    "package_collections",
    "path_matches",
    "registered_packages",
]


@dataclass
class Collections:
    path: Path
    catalog: Catalog
    definitions: dict

    def names(self) -> list[str]:
        return sorted(self.definitions)

    def describe(self, name: str) -> dict:
        return self.definitions[self._check(name)]

    def _check(self, name: str) -> str:
        if name not in self.definitions:
            known = ", ".join(self.names()) or "<none>"
            raise KeyError(f"unknown collection {name!r}; this file defines: {known}")
        return name

    def resolve(self, name: str, _seen: frozenset[str] = frozenset()) -> list[Resource]:
        """Expand a collection (and anything it extends) into resources.

        Selection is by glob against the resource path. Shapefile sidecars are
        pulled in automatically -- a .shp without its .dbf/.shx is unreadable,
        and expecting every collections file to spell that out invites bugs.
        """
        name = self._check(name)
        if name in _seen:
            chain = " -> ".join([*sorted(_seen), name])
            raise ValueError(f"circular 'extends' in collections file: {chain}")
        seen = _seen | {name}

        definition = self.definitions[name]
        selected: dict[str, Resource] = {}

        for parent in definition.get("extends", []):
            for resource in self.resolve(parent, seen):
                selected[resource.key] = resource

        for rule in definition.get("include", []):
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
        location = catalog or document.get("catalog")
        if location:
            # Retain compatibility with legacy '@ref' suffixes by stripping them.
            # Remote revisions must be part of the URL itself; this does not
            # rewrite a Git host's branch/tag segment.
            location = str(location)
            if not Path(location).exists() and "@" in location.rsplit("/", 1)[-1]:
                location = location.rsplit("@", 1)[0]
            if not location.startswith(("http://", "https://")):
                location = str((path.parent / location).resolve())
        else:
            # No pin: the public catalogue, so a collections file that selects
            # only public data works with nothing configured anywhere.
            from .config import DEFAULT_CATALOG

            location = DEFAULT_CATALOG
        resolved = load_catalog(location)

    if include_staging:
        from .staging import with_staging

        resolved = with_staging(resolved, roots)
    return Collections(path=path, catalog=resolved, definitions=document.get("collections", {}))


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
