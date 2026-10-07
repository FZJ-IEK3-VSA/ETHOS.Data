"""The external systems ETHOS.Data talks to, each behind a port with a fake.

The adapter layer of the four-layer decision. Code that needs dCache, a
download, git or catalogue metadata asks for the port's methods and is handed
an implementation:

==================  =========================================  ===========================
Port                Real adapters                              Fake, for tests
==================  =========================================  ===========================
``Store``           :class:`.dcache.DcacheStore`               :class:`.fakes.FakeStore`
``Downloader``      :class:`.downloads.PoochDownloader`        :class:`.fakes.FakeDownloader`
``Git``             :class:`.git.GitRepository`                :class:`.fakes.FakeGit`
``MetadataSource``  :class:`.metadata.FileSource`,             :class:`.fakes.MemorySource`
                    :class:`.metadata.HttpSource`,
                    :class:`.metadata.CachedSource`
==================  =========================================  ===========================

The ports are :class:`typing.Protocol` classes: an implementation needs the
methods, not a base class. Nothing in this package reads settings. A port
returns data and raises a typed error when it fails; none returns a status.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..model.inventory import PartReader

if TYPE_CHECKING:
    from ..errors import UploadError

__all__ = ["Downloader", "Git", "MetadataSource", "Store"]


@runtime_checkable
class Store(Protocol):
    """The publication store as a maintainer writes it, and reads it back.

    Every failure raises :class:`~ethos_data.errors.UploadError`, naming what
    failed and where.
    """

    def token(self, profile: str) -> str:
        """A bearer token for the store's REST interface, from the named profile."""
        ...

    def copy(
        self,
        source: Path,
        destination: str,
        paths: list[str],
        *,
        transfers: int,
    ) -> None:
        """Copy ``paths`` under ``source`` to ``destination``; never overwrite."""
        ...

    def sync(self, source: Path, destination: str) -> None:
        """Make ``destination`` hold exactly the files under ``source``, ``.git`` aside.

        Unlike :meth:`copy` it replaces what is there, for a folder of which
        the store keeps the latest version only.
        """
        ...

    def purge(self, destination: str) -> None:
        """Delete ``destination`` and everything under it; the store has no trash."""
        ...

    def exists(self, destination: str) -> bool:
        """Whether ``destination`` holds anything."""
        ...

    def chmod(self, path: str, mode: int, bearer: str) -> None:
        """Set ``mode`` on a store path."""
        ...

    def locality(self, path: str, bearer: str) -> str:
        """Where the store holds a file: ``ONLINE``, ``NEARLINE`` or both."""
        ...

    def served(self, url: str) -> int:
        """The size the server reports for ``url``, read anonymously.

        What any reader gets, without credentials: a file that is not
        world-readable, or not there, raises.
        """
        ...

    def served_each(self, urls: list[str]) -> list[int | UploadError]:
        """:meth:`served` for many URLs at once, in their order.

        For each URL the size, or the :class:`~ethos_data.errors.UploadError`
        that :meth:`served` raises for it. A batch reports every file it asked
        about: raising on the first that is not readable would hide what the
        others answer.
        """
        ...


@runtime_checkable
class Downloader(Protocol):
    """Fetches published files into a directory, checking each against its hash."""

    def fetch(
        self,
        base_url: str,
        destination: Path,
        files: dict[str, str],
        *,
        progressbar: bool = False,
    ) -> dict[str, Path]:
        """Make each ``{path: hash}`` of ``files`` available under ``destination``.

        A file already there with the right hash is not fetched again. A file
        that cannot be fetched, or does not match its hash, raises
        :class:`~ethos_data.errors.DownloadError`, naming its URL.
        """
        ...


@runtime_checkable
class Git(Protocol):
    """A git checkout, as a release commits, tags and pushes it and a server updates it."""

    def is_clean(self) -> bool:
        """Whether the working tree has no uncommitted changes."""
        ...

    def tag_names(self) -> list[str]:
        """Every tag of the repository."""
        ...

    def fetch(self, remote: str) -> None:
        """Fetch ``remote``'s branches and tags."""
        ...

    def fast_forward(self, ref: str) -> None:
        """Move the checkout to ``ref``, refusing anything but a fast-forward."""
        ...

    def show(self, ref: str, path: str) -> str | None:
        """The text of ``path`` at ``ref``; None when ``ref`` has no such file."""
        ...

    def changed(self, ref: str) -> list[str]:
        """The paths that differ between ``ref`` and the working tree, committed or not."""
        ...

    def head(self) -> str:
        """The commit checked out."""
        ...

    def commit(self, message: str) -> str:
        """Commit every change; returns the new commit."""
        ...

    def tag(self, name: str, message: str) -> None:
        """Create an annotated tag at the commit checked out."""
        ...

    def push(self, remote: str, *refs: str) -> None:
        """Push ``refs`` to ``remote``."""
        ...


@runtime_checkable
class MetadataSource(PartReader, Protocol):
    """Where the files of a generated catalogue are read: the index, descriptors, shards.

    The part reader the inventory reader is handed. A location with nothing
    there raises :class:`~ethos_data.errors.IncompleteCatalog`; one that
    cannot be reached raises :class:`~ethos_data.errors.CatalogUnavailable`.
    """

    def read(self, location: str) -> bytes:
        """The bytes of the catalogue file at ``location``."""
        ...

    def join(self, base: str, relative: str) -> str:
        """Where ``relative`` lies, relative to the file at ``base``."""
        ...
