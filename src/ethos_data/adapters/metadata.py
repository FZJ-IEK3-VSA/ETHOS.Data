"""Where catalogue metadata is read from: files, HTTPS, the metadata cache, memory.

The real :class:`~ethos_data.adapters.MetadataSource` adapters. Each answers
the bytes of one catalogue file at a location, and where a part lies relative
to another, for paths and URLs alike. A location with nothing there raises
:class:`~ethos_data.errors.IncompleteCatalog`; one that cannot be reached
raises :class:`~ethos_data.errors.CatalogUnavailable`. Both messages read
``<location>: <reason>``.
"""

from __future__ import annotations

import gzip
import os
import posixpath
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from ..errors import CatalogUnavailable, IncompleteCatalog
from ..model import digest
from ..model.inventory import PartReader

__all__ = ["CachedSource", "FileSource", "HttpSource", "MemorySource", "moving"]

#: Refs that move. Metadata read through one must not be kept, or work against
#: a development branch silently goes stale.
_MOVING_REF = re.compile(r"/(?:refs/heads/)?(?:main|master|HEAD|latest|dev|develop)/")


def moving(location: str) -> bool:
    """Whether ``location`` names a moving ref, such as ``main``, and may change."""
    return bool(_MOVING_REF.search(location))


class FileSource:
    """Catalogue files on a filesystem: a checkout, the served checkout, a copy."""

    def read(self, location: str) -> bytes:
        try:
            return Path(location).expanduser().read_bytes()
        except FileNotFoundError as error:
            raise IncompleteCatalog(f"{location}: {error.strerror}") from error
        except OSError as error:
            raise CatalogUnavailable(f"{location}: {error}") from error

    def join(self, base: str, relative: str) -> str:
        return (Path(base).expanduser().parent / relative).as_posix()


class HttpSource:
    """Catalogue files over HTTP(S), asking for gzip: they compress forty-fold."""

    def __init__(self, timeout: float = 60):
        self.timeout = timeout

    def read(self, location: str) -> bytes:
        request = urllib.request.Request(location, headers={"Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as error:
            reason = f"HTTP {error.code} {error.reason}"
            if error.code == 404:
                raise IncompleteCatalog(f"{location}: {reason}") from error
            raise CatalogUnavailable(f"{location}: {reason}") from error
        except (OSError, ValueError) as error:
            reason = getattr(error, "reason", None) or error
            raise CatalogUnavailable(f"{location}: {reason}") from error

    def join(self, base: str, relative: str) -> str:
        return urllib.parse.urljoin(base, relative)


class CachedSource:
    """A source with the metadata cache in front of it.

    Keeps what it reads in ``directory`` for good, unless the location names a
    moving ref: a release tag's metadata never changes, so there is nothing to
    invalidate. Writes go through a temporary file and a rename, because two
    processes racing must never see half a file.
    """

    def __init__(self, source: PartReader, directory: str | Path):
        self.source = source
        self.directory = Path(directory)

    def read(self, location: str) -> bytes:
        if moving(location):
            return self.source.read(location)
        kept = self._path(location)
        if kept.is_file():
            return kept.read_bytes()
        data = self.source.read(location)
        kept.parent.mkdir(parents=True, exist_ok=True)
        temporary = kept.with_suffix(kept.suffix + f".{os.getpid()}.part")
        temporary.write_bytes(data)
        temporary.replace(kept)
        return data

    def join(self, base: str, relative: str) -> str:
        return self.source.join(base, relative)

    def _path(self, location: str) -> Path:
        folder = digest.of_bytes(location.encode())[:16]
        return self.directory / folder / location.rsplit("/", 1)[-1]


class MemorySource:
    """A catalogue tree held in memory, by location; also the fake of the port.

    ``reads`` lists every location read, in order, so a test can tell which
    parts a request needed.
    """

    def __init__(self, files: Mapping[str, bytes | str] | None = None):
        self.files = {
            location: data.encode("utf-8") if isinstance(data, str) else data
            for location, data in (files or {}).items()
        }
        self.reads: list[str] = []

    def read(self, location: str) -> bytes:
        self.reads.append(location)
        if location not in self.files:
            raise IncompleteCatalog(f"{location}: not in this tree")
        return self.files[location]

    def join(self, base: str, relative: str) -> str:
        return posixpath.normpath(posixpath.join(posixpath.dirname(base), relative))
