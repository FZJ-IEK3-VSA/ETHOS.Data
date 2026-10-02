"""Catalogue releases, ``vYYYY.MM.N``, and the bounds a collections file sets on them.

``N`` counts the releases within a month, so ``v2026.09.2`` is the second
release of September 2026. Versions compare component by component, as
numbers: ``v2026.09.10`` follows ``v2026.09.9``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from ..formats import keys as k

__all__ = ["Bounds", "Version"]

_PATTERN = re.compile(r"v(\d{4})\.(\d{2})\.(\d+)")


@dataclass(frozen=True, order=True)
class Version:
    """One catalogue release."""

    year: int
    month: int
    number: int

    @classmethod
    def parse(cls, text: object) -> Version:
        """The release ``text`` names, or ValueError saying how releases are written."""
        match = _PATTERN.fullmatch(text.strip()) if isinstance(text, str) else None
        if match is None or not 1 <= int(match[2]) <= 12 or int(match[3]) < 1:
            raise ValueError(
                f"{text!r} is not a catalogue release; releases are numbered "
                "vYYYY.MM.N, such as v2026.09.2"
            )
        return cls(int(match[1]), int(match[2]), int(match[3]))

    def __str__(self) -> str:
        return f"v{self.year:04d}.{self.month:02d}.{self.number}"


@dataclass(frozen=True)
class Bounds:
    """The catalogue releases a collections file works with.

    ``exact`` alone, or ``minimum`` and an optional ``maximum``: a package that
    must resolve to the same bytes release after release names one release,
    every other package the range it was tested with.
    """

    minimum: Version | None = None
    maximum: Version | None = None
    exact: Version | None = None

    @classmethod
    def from_document(cls, value: Mapping) -> Bounds:
        """The bounds a collections file's ``catalog:`` mapping sets, or ValueError."""
        known = {k.MIN_VERSION, k.MAX_VERSION, k.EXACT_VERSION}
        unknown = sorted(set(value) - known)
        if unknown:
            raise ValueError(
                f"catalog: takes {', '.join(sorted(known))}; "
                f"{', '.join(unknown)} is not one of them"
            )
        parsed = {key: Version.parse(value[key]) for key in known if key in value}
        exact = parsed.get(k.EXACT_VERSION)
        minimum = parsed.get(k.MIN_VERSION)
        maximum = parsed.get(k.MAX_VERSION)
        if exact is not None and (minimum or maximum):
            raise ValueError(
                f"catalog: {k.EXACT_VERSION} names one release, so it cannot be "
                f"combined with {k.MIN_VERSION} or {k.MAX_VERSION}"
            )
        if exact is None and minimum is None:
            raise ValueError(
                f"catalog: needs {k.MIN_VERSION}, the oldest release the package was "
                f"tested with, or {k.EXACT_VERSION}"
            )
        if minimum and maximum and maximum < minimum:
            raise ValueError(
                f"catalog: {k.MAX_VERSION} {maximum} is older than {k.MIN_VERSION} {minimum}"
            )
        return cls(minimum, maximum, exact)

    def admits(self, version: Version) -> bool:
        """Whether ``version`` is a release these bounds accept."""
        if self.exact is not None:
            return version == self.exact
        if self.minimum is not None and version < self.minimum:
            return False
        return self.maximum is None or version <= self.maximum

    def __str__(self) -> str:
        if self.exact is not None:
            return f"{k.EXACT_VERSION} {self.exact}"
        text = f"{k.MIN_VERSION} {self.minimum}"
        return f"{text} and {k.MAX_VERSION} {self.maximum}" if self.maximum else text
