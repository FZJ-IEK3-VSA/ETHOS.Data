"""Dataset names, the families they form, and paths inside a dataset.

A dataset's name is its path below ``datasets/``: ``era5`` at the top,
``reskit-test-data/era5`` for a member of the ``reskit-test-data`` family. The
same string is its cache path, its default remote prefix and how a collections
file names it. So every rule about names is here once: which are safe to use
as paths, which lie inside a family, which dataset a key starts with, and
which two names would put their files in the same directory.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath, PureWindowsPath

__all__ = ["ancestors", "nested", "relative", "within"]


def relative(value: object, what: str = "path") -> PurePosixPath:
    """``value`` as a relative path that stays where it is put, or ValueError.

    The rule for a dataset name, a resource path, a sidecar and a licence
    document alike: forward slashes, no absolute path or drive, and no empty,
    ``.`` or ``..`` segment. The spelling is checked before PurePath would
    quietly normalise ``a//b`` or ``./a`` into something acceptable, so a path
    reads the same to every tool, and a file is never placed somewhere its
    record does not say.
    """
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).drive
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ValueError(f"unsafe {what}: {value!r}; expected a relative path")
    return PurePosixPath(value)


def ancestors(name: str) -> list[str]:
    """The families ``name`` lies in, outermost first: ``a/b/c`` gives ``a``, ``a/b``."""
    parts = name.split("/")
    return ["/".join(parts[:depth]) for depth in range(1, len(parts))]


def within(name: str, family: str) -> bool:
    """Whether ``name`` is ``family`` itself or lies anywhere inside it.

    On a segment boundary, so ``era5-land`` is not inside ``era5``.
    """
    return name == family or name.startswith(family + "/")


def nested(names: Iterable[str]) -> tuple[str, str] | None:
    """The first name, in name order, that lies inside another, and that other.

    Two such datasets cannot both keep their files under
    ``<root>/<name>/<path>``: with ``a`` and ``a/b`` together, ``a/b/x.tif`` is
    the place for two different files.
    """
    present = set(names)
    for name in sorted(present):
        for ancestor in ancestors(name):
            if ancestor in present:
                return name, ancestor
    return None
