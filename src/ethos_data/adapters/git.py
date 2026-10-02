"""A git checkout, through the ``git`` command line.

The real :class:`~ethos_data.adapters.Git`, for the release that commits,
tags and pushes a catalogue. Every method runs ``git`` in the checkout and
raises :class:`~ethos_data.errors.MaintenanceError` with git's own message
when it fails.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..errors import MaintenanceError

__all__ = ["GitRepository"]


class GitRepository:
    """The checkout at ``root``."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise MaintenanceError(
                f"`git {' '.join(arguments)}` failed in {self.root}:\n"
                f"  {result.stderr.strip() or result.stdout.strip()}"
            )
        return result.stdout.strip()

    def is_clean(self) -> bool:
        return not self._git("status", "--porcelain")

    def tag_names(self) -> list[str]:
        return self._git("tag", "--list").split()

    def fetch(self, remote: str) -> None:
        self._git("fetch", "--tags", remote)

    def fast_forward(self, ref: str) -> None:
        self._git("merge", "--ff-only", ref)

    def head(self) -> str:
        return self._git("rev-parse", "HEAD")

    def commit(self, message: str) -> str:
        self._git("add", "--all")
        self._git("commit", "--message", message)
        return self.head()

    def tag(self, name: str, message: str) -> None:
        self._git("tag", "--annotate", name, "--message", message)

    def push(self, remote: str, *refs: str) -> None:
        self._git("push", remote, *refs)
