"""One glob semantics for every pattern over resource paths.

A collection's ``files:`` and a dataset's ``ethos:include`` and
``ethos:exclude`` mean the same thing by the same code: a pattern that picks a
file when the inventory is built picks it when a collection is resolved.
"""

from __future__ import annotations

import fnmatch

__all__ = ["path_matches"]


def path_matches(path: str, pattern: str) -> bool:
    """Glob a resource path with proper directory semantics.

    ``*`` matches within one path segment; ``**`` matches any number of
    segments, none included. Plain ``fnmatch`` would let ``*.tif`` match
    ``sub/dir/x.tif``, which quietly pulls in far more than a pattern asked for.
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
