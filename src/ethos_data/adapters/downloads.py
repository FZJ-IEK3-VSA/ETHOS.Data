"""Downloads from the publication root, hash-checked, through pooch.

The real :class:`~ethos_data.adapters.Downloader`. pooch keeps what it has
fetched and re-fetches a file whose hash no longer matches, so a cache that
was interrupted or tampered with heals on the next fetch.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["PoochDownloader"]


class PoochDownloader:
    """Fetches files with pooch, retrying a failed transfer ``retries`` times."""

    def __init__(self, retries: int = 3):
        self.retries = retries

    def fetch(
        self,
        base_url: str,
        destination: Path,
        files: dict[str, str],
        *,
        progressbar: bool = False,
    ) -> dict[str, Path]:
        import pooch

        puller = pooch.create(
            path=destination,
            base_url=base_url,
            # Frictionless writes "sha256:..."; pooch reads the same "alg:hash"
            # convention, so the manifest value passes straight through.
            registry=dict(files),
            retry_if_failed=self.retries,
        )
        return {
            path: Path(puller.fetch(path, progressbar=progressbar)) for path in files
        }
