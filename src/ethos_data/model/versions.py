"""Catalogue releases, ``vMAJOR.MINOR.PATCH``, and the bounds a collections file sets on them.

A release is three decimal numbers without leading zeros, such as ``v1.2.0``.
Releases compare part by part, as numbers: ``v1.10.0`` follows ``v1.9.3``.

A bound may name a prefix, ``v1`` or ``v1.3``. As ``min_version`` it stands for
the first release that starts with it, as ``max_version`` for the last, and as
``exact_version`` for every one of them: ``exact_version: v1.3`` admits every
``v1.3.x``, the same bytes with the newest metadata.

The level of a release says what changed since the one before: a patch
changes metadata only, a minor release changes data, and a major release is
a retention epoch, after which withdrawn data may be purged. The first
release is ``v1.0.0``; every later one is the next patch, minor or major of
the last, at or above the level its changes need.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..formats import keys as k

__all__ = [
    "BOUND_PATTERN",
    "FIRST",
    "LEVELS",
    "MAJOR",
    "MINOR",
    "PATCH",
    "RELEASE_PATTERN",
    "Bounds",
    "Prefix",
    "Version",
    "admissible",
    "releases",
]

PATCH, MINOR, MAJOR = "patch", "minor", "major"
#: The levels of a release, smallest first.
LEVELS = (PATCH, MINOR, MAJOR)

_NUMBER = "(0|[1-9][0-9]*)"
#: A release, as the formats and the reader match it: ``v1.2.0``.
RELEASE_PATTERN = rf"^v{_NUMBER}\.{_NUMBER}\.{_NUMBER}$"
#: A release or a prefix of one, as a bound names it: ``v1``, ``v1.3``, ``v1.3.0``.
BOUND_PATTERN = rf"^v{_NUMBER}(\.{_NUMBER}){{0,2}}$"

_RELEASE = re.compile(RELEASE_PATTERN)
_BOUND = re.compile(BOUND_PATTERN)


def _numbers(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text[1:].split("."))


@dataclass(frozen=True, order=True)
class Version:
    """One catalogue release."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: object) -> Version:
        """The release ``text`` names, or ValueError saying how releases are written."""
        if not isinstance(text, str) or _RELEASE.fullmatch(text) is None:
            raise ValueError(
                f"{text!r} is not a catalogue release; releases are numbered "
                "vMAJOR.MINOR.PATCH, such as v1.2.0"
            )
        return cls(*_numbers(text))

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    @property
    def is_major(self) -> bool:
        """Whether this is a major release, ``vN.0.0``."""
        return self.minor == 0 and self.patch == 0

    def next(self, level: str) -> Version:
        """The release after this one at ``level``: patch, minor or major."""
        if level == PATCH:
            return Version(self.major, self.minor, self.patch + 1)
        if level == MINOR:
            return Version(self.major, self.minor + 1, 0)
        if level == MAJOR:
            return Version(self.major + 1, 0, 0)
        raise ValueError(f"{level!r} is not a release level; one of {LEVELS}")


#: The first release of a catalogue.
FIRST = Version(1, 0, 0)


def admissible(last: Version | None, level: str) -> list[Version]:
    """The releases that may follow ``last`` when the changes need ``level``.

    Smallest first. The first release, after none, is :data:`FIRST` alone.
    """
    if last is None:
        return [FIRST]
    return [last.next(each) for each in LEVELS[LEVELS.index(level) :]]


@dataclass(frozen=True)
class Prefix:
    """A release, or the releases starting with ``v1`` or ``v1.3``, as a bound names them."""

    parts: tuple[int, ...]

    @classmethod
    def parse(cls, text: object) -> Prefix:
        """The prefix ``text`` names, or ValueError saying how bounds are written."""
        if not isinstance(text, str) or _BOUND.fullmatch(text) is None:
            raise ValueError(
                f"{text!r} is not a catalogue release or a prefix of one; "
                "a bound is written v1.2.0, v1.2 or v1"
            )
        return cls(_numbers(text))

    def release(self) -> Version | None:
        """The one release this names, when it names one in full."""
        return Version(*self.parts) if len(self.parts) == 3 else None

    def head(self, version: Version) -> tuple[int, ...]:
        """The first parts of ``version``, as many as this prefix has."""
        return (version.major, version.minor, version.patch)[: len(self.parts)]

    def __str__(self) -> str:
        return "v" + ".".join(map(str, self.parts))


@dataclass(frozen=True)
class Bounds:
    """The catalogue releases a collections file works with.

    ``exact`` alone, or ``minimum`` and an optional ``maximum``: a package that
    must resolve to the same bytes names one release or one ``v1.3``, every
    other package the range it was tested with.
    """

    minimum: Prefix | None = None
    maximum: Prefix | None = None
    exact: Prefix | None = None

    @classmethod
    def from_document(cls, value: Mapping) -> Bounds:
        """The bounds a collections file's ``catalog:`` mapping sets, or ValueError."""
        known = (k.MIN_VERSION, k.MAX_VERSION, k.EXACT_VERSION)
        parsed = {
            key: Prefix.parse(value[key]) for key in known if value.get(key) is not None
        }
        exact = parsed.get(k.EXACT_VERSION)
        minimum = parsed.get(k.MIN_VERSION)
        maximum = parsed.get(k.MAX_VERSION)
        if exact is not None and (minimum or maximum):
            raise ValueError(
                f"{k.EXACT_VERSION} cannot be combined with {k.MIN_VERSION} or "
                f"{k.MAX_VERSION}"
            )
        if exact is None and minimum is None:
            raise ValueError(
                f"needs {k.MIN_VERSION}, the oldest release the package was tested "
                f"with, or {k.EXACT_VERSION}"
            )
        if minimum and maximum:
            shared = min(len(minimum.parts), len(maximum.parts))
            if maximum.parts[:shared] < minimum.parts[:shared]:
                raise ValueError(
                    f"{k.MAX_VERSION} {maximum} is older than {k.MIN_VERSION} {minimum}"
                )
        return cls(minimum, maximum, exact)

    def admits(self, version: Version) -> bool:
        """Whether ``version`` is a release these bounds accept."""
        if self.exact is not None:
            return self.exact.head(version) == self.exact.parts
        if self.minimum is not None and self.minimum.head(version) < self.minimum.parts:
            return False
        return self.maximum is None or self.maximum.head(version) <= self.maximum.parts

    def release(self) -> Version | None:
        """The one release these bounds admit, when ``exact_version`` names it in full."""
        return self.exact.release() if self.exact is not None else None

    def newest(self, releases: Iterable[Version]) -> Version | None:
        """The newest of ``releases`` these bounds admit, or None."""
        return max((r for r in releases if self.admits(r)), default=None)

    def __str__(self) -> str:
        if self.exact is not None:
            return f"{k.EXACT_VERSION} {self.exact}"
        text = f"{k.MIN_VERSION} {self.minimum}"
        return f"{text} and {k.MAX_VERSION} {self.maximum}" if self.maximum else text


def releases(names: Iterable[object]) -> list[Version]:
    """The distinct releases among ``names``, oldest first; any other name is left out."""
    found = set()
    for name in names:
        try:
            found.add(Version.parse(name))
        except ValueError:
            continue
    return sorted(found)
