"""The external systems ETHOS.Data talks to, each behind a port with a fake.

The adapter layer of the four-layer decision. Code that needs dCache, a
download or git asks for the port's methods and is handed an implementation:

=============  ====================================  ===========================
Port           Real adapter                          Fake, for tests
=============  ====================================  ===========================
``Store``      :class:`.dcache.DcacheStore`          :class:`.fakes.FakeStore`
``Downloader`` :class:`.downloads.PoochDownloader`   :class:`.fakes.FakeDownloader`
``Git``        :class:`.git.GitRepository`           :class:`.fakes.FakeGit`
=============  ====================================  ===========================

The ports are :class:`typing.Protocol` classes: an implementation needs the
methods, not a base class. Nothing in this package reads settings. A port
returns data and raises a typed error when it fails; none returns a status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["Downloader", "Git", "Store"]


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
        dry_run: bool,
    ) -> None:
        """Copy ``paths`` under ``source`` to ``destination``; never overwrite."""
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
    """A git checkout, as a release commits, tags and pushes it."""

    def is_clean(self) -> bool:
        """Whether the working tree has no uncommitted changes."""
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
