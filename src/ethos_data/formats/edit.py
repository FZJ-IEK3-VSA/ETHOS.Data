"""Edits to a file a person wrote, line by line, keeping everything else as it was.

A ``dataset.yaml`` carries comments and an order its author chose, which a
load and dump would lose. A command that has to take keys out of one removes
their lines and checks that the rest reads the same.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import yaml

__all__ = ["without_keys"]


def without_keys(text: str, keys: Iterable[str]) -> str:
    """``text`` without the top-level ``keys`` and the indented lines continuing them.

    Raises ValueError when the result does not read as ``text`` less those keys,
    which a key written in a form the line rule does not recognise would cause.
    """
    keys = list(keys)
    patterns = [
        re.compile(rf"(?:{re.escape(key)}|\"{re.escape(key)}\"|'{re.escape(key)}')\s*:")
        for key in keys
    ]
    kept: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if not line.strip():
            skipping = False
        elif line[:1] not in (" ", "\t"):
            skipping = any(pattern.match(line) for pattern in patterns)
        if not skipping:
            kept.append(line)
    edited = "".join(kept)
    expected = {
        key: value
        for key, value in (yaml.safe_load(text) or {}).items()
        if key not in keys
    }
    if (yaml.safe_load(edited) or {}) != expected:
        raise ValueError(f"{', '.join(keys)} cannot be removed line by line")
    return edited
