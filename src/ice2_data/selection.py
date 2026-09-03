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

import yaml

from .catalog import Catalog, Resource, load_catalog

__all__ = ["Collections", "load_collections"]


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
            dataset = self.catalog.dataset(rule["dataset"])
            patterns = rule.get("files") or ["**"]
            # resources_matching narrows a sharded dataset to the shards these
            # patterns can reach; the glob below is still the real filter.
            for resource in list(dataset.resources_matching(patterns).values()):
                if not any(_matches(resource.path, p) for p in patterns):
                    continue
                selected[resource.key] = resource
                for sidecar in resource.sidecars:
                    companion = dataset.resource_at(sidecar)
                    if companion is not None:
                        selected[companion.key] = companion

        return sorted(selected.values(), key=lambda r: r.key)


def _matches(path: str, pattern: str) -> bool:
    """Glob a resource path with proper directory semantics.

    ``*`` matches within one path segment; ``**`` matches any number of
    segments. Plain ``fnmatch`` would let ``*.tif`` match ``sub/dir/x.tif``,
    which quietly pulls in far more than a collections file asked for.
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


def load_collections(path: str | Path, catalog: str | Catalog | None = None) -> Collections:
    """Load a collections.yaml, resolving the catalogue it pins."""
    path = Path(path).expanduser().resolve()
    document = yaml.safe_load(path.read_text()) or {}

    if isinstance(catalog, Catalog):
        resolved = catalog
    else:
        location = catalog or document.get("catalog")
        if not location:
            raise ValueError(f"{path} has no 'catalog:' key and none was supplied")
        # A '@ref' suffix pins a catalogue version. Local paths ignore it; for a
        # git host it selects the tag, which is what makes a tool reproducible.
        location = str(location)
        if not Path(location).exists() and "@" in location.rsplit("/", 1)[-1]:
            location = location.rsplit("@", 1)[0]
        if not location.startswith(("http://", "https://")):
            location = str((path.parent / location).resolve())
        resolved = load_catalog(location)

    return Collections(path=path, catalog=resolved, definitions=document.get("collections", {}))
