"""Stand-ins for the external systems, for tests and rehearsals.

Each records what it was asked to do and does it locally: a
:class:`FakeStore` keeps what it is sent and reads it back, a
:class:`FakeDownloader` serves bytes it was given, a :class:`FakeGit` keeps
its commits and tags in lists, and a :class:`MemorySource` holds a catalogue
tree in memory. None of them touches the network or runs a command, and each
fails with the typed error its port names.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from ..errors import DownloadError, UploadError
from ..model import digest
from .metadata import MemorySource

__all__ = ["FakeDownloader", "FakeGit", "FakeStore", "MemorySource"]


@dataclass
class FakeStore:
    """A publication store that keeps what it is sent, and reads it back.

    ``objects`` holds every copied file by its store path,
    ``<destination>/<path>``; a test may add some before an upload that only
    verifies. :meth:`served` answers a URL that ends in a store path, the way
    the public door serves the publication root. ``put(destination, path,
    data)`` also receives every copied file, when given: a test serving the
    store over HTTP passes its own, so a later download finds the bytes.
    """

    put: Callable[[str, str, bytes], None] | None = None
    #: Receives every purged or replaced destination, when given, to delete what
    #: ``put`` sent there.
    remove: Callable[[str], None] | None = None
    #: The rclone status to rehearse a failed transfer with; 0 copies.
    copy_status: int = 0
    #: Whether anonymous reads succeed: False rehearses a missing chmod.
    readable: bool = True
    #: What ``locality`` answers.
    where: str = "ONLINE"
    objects: dict[str, bytes] = field(default_factory=dict)
    copies: list[dict] = field(default_factory=list)
    syncs: list[dict] = field(default_factory=list)
    purges: list[str] = field(default_factory=list)
    chmods: list[tuple[str, int]] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)

    def token(self, profile: str) -> str:
        self.tokens.append(profile)
        return "fake-token"

    def copy(
        self,
        source: Path,
        destination: str,
        paths: list[str],
        *,
        transfers: int,
    ) -> None:
        self.copies.append(
            {
                "source": Path(source),
                "destination": destination,
                "paths": list(paths),
                "transfers": transfers,
            }
        )
        if self.copy_status:
            raise UploadError(
                f"rclone exited {self.copy_status} copying to {destination}."
            )
        for path in paths:
            data = (Path(source) / path).read_bytes()
            self.objects[f"{destination}/{path}"] = data
            if self.put is not None:
                self.put(destination, path, data)

    def sync(self, source: Path, destination: str) -> None:
        source = Path(source)
        paths = sorted(
            p.relative_to(source).as_posix()
            for p in source.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(source).parts
        )
        self.syncs.append(
            {"source": source, "destination": destination, "paths": paths}
        )
        if self.copy_status:
            raise UploadError(
                f"rclone exited {self.copy_status} syncing {source} to {destination}"
            )
        self._forget(destination)
        for path in paths:
            data = (source / path).read_bytes()
            self.objects[f"{destination}/{path}"] = data
            if self.put is not None:
                self.put(destination, path, data)

    def purge(self, destination: str) -> None:
        if self.copy_status:
            raise UploadError(f"rclone exited {self.copy_status} purging {destination}")
        self.purges.append(destination)
        self._forget(destination)

    def exists(self, destination: str) -> bool:
        return any(path.startswith(f"{destination}/") for path in self.objects)

    def _forget(self, destination: str) -> None:
        for path in [p for p in self.objects if p.startswith(f"{destination}/")]:
            del self.objects[path]
        if self.remove is not None:
            self.remove(destination)

    def chmod(self, path: str, mode: int, bearer: str) -> None:
        self.chmods.append((path, mode))

    def locality(self, path: str, bearer: str) -> str:
        return self.where

    def served(self, url: str) -> int:
        self.reads.append(url)
        if self.readable:
            # The store decodes the percent-encoded path of the request.
            asked = unquote(url)
            for path, data in self.objects.items():
                if asked.endswith(f"/{path}"):
                    return len(data)
        status = "HTTP 404 Not Found" if self.readable else "HTTP 401 Unauthorized"
        raise UploadError(f"{url} is not readable: {status}")


@dataclass
class FakeDownloader:
    """Serves the bytes it was given, by URL, checking them as a download would."""

    served: Mapping[str, bytes] = field(default_factory=dict)
    fetched: list[str] = field(default_factory=list)

    def fetch(
        self,
        base_url: str,
        destination: Path,
        files: dict[str, str],
        *,
        progressbar: bool = False,
    ) -> dict[str, Path]:
        found = {}
        for path, recorded in files.items():
            target = Path(destination) / path
            if not (
                target.is_file() and digest.matches(recorded, digest.of_file(target))
            ):
                url = f"{base_url.rstrip('/')}/{path}"
                if url not in self.served:
                    raise DownloadError(f"cannot download {url}: HTTP 404 Not Found")
                data = self.served[url]
                if not digest.matches(recorded, digest.of_bytes(data)):
                    raise DownloadError(
                        f"cannot download {url}: it does not match its recorded hash"
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                self.fetched.append(url)
            found[path] = target
        return found


@dataclass
class FakeGit:
    """A checkout that records its commits, tags, pushes, fetches and fast-forwards."""

    clean: bool = True
    commits: list[str] = field(default_factory=list)
    tags: list[tuple[str, str]] = field(default_factory=list)
    pushes: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    fetches: list[str] = field(default_factory=list)
    forwards: list[str] = field(default_factory=list)
    #: Tags the remote has, which ``fetch`` brings in.
    remote_tags: list[str] = field(default_factory=list)
    #: The text of each file at a tag, by ``(tag, path)``, for ``show``.
    files: dict[tuple[str, str], str] = field(default_factory=dict)
    #: The paths ``changed`` reports, whatever the tag.
    changes: list[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return self.clean

    def tag_names(self) -> list[str]:
        return [name for name, _ in self.tags]

    def fetch(self, remote: str) -> None:
        self.fetches.append(remote)
        for name in self.remote_tags:
            if name not in self.tag_names():
                self.tags.append((name, ""))

    def fast_forward(self, ref: str) -> None:
        self.forwards.append(ref)

    def show(self, ref: str, path: str) -> str | None:
        return self.files.get((ref, path))

    def changed(self, ref: str) -> list[str]:
        return list(self.changes)

    def head(self) -> str:
        return f"commit-{len(self.commits)}"

    def commit(self, message: str) -> str:
        self.commits.append(message)
        self.clean = True
        return self.head()

    def tag(self, name: str, message: str) -> None:
        self.tags.append((name, message))

    def push(self, remote: str, *refs: str) -> None:
        self.pushes.append((remote, refs))
