"""Stand-ins for the external systems, for tests and rehearsals.

Each records what it was asked to do and does it locally: a
:class:`FakeStore` copies into a directory or a callback, a
:class:`FakeDownloader` serves bytes it was given, a :class:`FakeGit` keeps
its commits and tags in lists. None of them touches the network or runs a
command.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..model import digest

__all__ = ["FakeDownloader", "FakeGit", "FakeStore"]


@dataclass
class FakeStore:
    """A publication store that keeps what it is sent.

    ``put(destination, path, data)`` receives every copied file, when given:
    a test serving the store over HTTP passes its own ``put`` so the anonymous
    read-back that follows an upload finds the bytes.
    """

    put: Callable[[str, str, bytes], None] | None = None
    #: Receives every purged destination, when given, to delete what ``put`` sent.
    remove: Callable[[str], None] | None = None
    #: The status ``copy``, ``sync`` and ``purge`` return, to rehearse a failure.
    copy_status: int = 0
    #: What ``locality`` answers.
    where: str = "ONLINE"
    copies: list[dict] = field(default_factory=list)
    syncs: list[dict] = field(default_factory=list)
    purges: list[str] = field(default_factory=list)
    chmods: list[tuple[str, int]] = field(default_factory=list)
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
        dry_run: bool,
    ) -> int:
        self.copies.append(
            {
                "source": Path(source),
                "destination": destination,
                "paths": list(paths),
                "transfers": transfers,
                "dry_run": dry_run,
            }
        )
        if not dry_run and self.copy_status == 0 and self.put is not None:
            for path in paths:
                self.put(destination, path, (Path(source) / path).read_bytes())
        return self.copy_status

    def sync(self, source: Path, destination: str, *, dry_run: bool) -> int:
        source = Path(source)
        paths = sorted(
            p.relative_to(source).as_posix()
            for p in source.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(source).parts
        )
        self.syncs.append(
            {
                "source": source,
                "destination": destination,
                "paths": paths,
                "dry_run": dry_run,
            }
        )
        if not dry_run and self.copy_status == 0:
            if self.remove is not None:
                self.remove(destination)
            if self.put is not None:
                for path in paths:
                    self.put(destination, path, (source / path).read_bytes())
        return self.copy_status

    def purge(self, destination: str, *, dry_run: bool) -> int:
        if not dry_run and self.copy_status == 0:
            self.purges.append(destination)
            if self.remove is not None:
                self.remove(destination)
        return self.copy_status

    def chmod(self, path: str, mode: int, bearer: str) -> int:
        self.chmods.append((path, mode))
        return 200

    def locality(self, path: str, bearer: str) -> str:
        return self.where


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
                    raise OSError(f"nothing is served at {url}")
                data = self.served[url]
                if not digest.matches(recorded, digest.of_bytes(data)):
                    raise ValueError(f"{url} does not match its recorded hash")
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
