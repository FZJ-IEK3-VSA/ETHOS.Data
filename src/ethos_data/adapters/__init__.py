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
methods, not a base class. Nothing in this package reads settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["Downloader", "Git", "Store"]


@runtime_checkable
class Store(Protocol):
    """The publication store as a maintainer writes it: dCache through rclone.

    Reading the published bytes back is not part of it: that is what any
    anonymous reader does over HTTP, and the upload checks it that way.
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
    ) -> int:
        """Copy ``paths`` under ``source`` to ``destination``; never overwrite.

        Returns a process-style status: 0 when everything was copied.
        """
        ...

    def sync(self, source: Path, destination: str, *, dry_run: bool) -> int:
        """Make ``destination`` hold exactly the files under ``source``, ``.git`` aside.

        Unlike :meth:`copy` it replaces what is there, for a folder of which
        the store keeps the latest version only. Returns a process-style status.
        """
        ...

    def purge(self, destination: str, *, dry_run: bool) -> int:
        """Delete ``destination`` and everything under it; there is no trash.

        Returns a process-style status: 0 when it is gone.
        """
        ...

    def chmod(self, path: str, mode: int, bearer: str) -> int:
        """Set ``mode`` on a store path; returns the HTTP status."""
        ...

    def locality(self, path: str, bearer: str) -> str:
        """Where the store holds a file: ``ONLINE``, ``NEARLINE`` or both."""
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

        A file already there with the right hash is not fetched again. Raises
        when a file cannot be fetched or does not match its hash.
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
