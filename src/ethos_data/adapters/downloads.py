"""Downloads from the publication root, hash-checked, through pooch.

The real :class:`~ethos_data.adapters.Downloader`. pooch keeps what it has
fetched and re-fetches a file whose hash no longer matches, so a cache that
was interrupted or tampered with heals on the next fetch.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import DownloadError
from ..model import digest

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
            # A recorded hash may be spelled prefixed or bare, in either case;
            # pooch is handed one spelling. A hash that is not SHA-256 cannot
            # be checked: the file is fetched as it is, and `verify` reports it.
            registry={path: _sha256(recorded) for path, recorded in files.items()},
            retry_if_failed=self.retries,
        )
        found = {}
        for path in files:
            try:
                found[path] = Path(puller.fetch(path, progressbar=progressbar))
            except (OSError, ValueError) as error:
                # requests' errors are OSErrors; a hash that does not
                # match after the retries is pooch's ValueError.
                url = f"{base_url.rstrip('/')}/{path}"
                raise DownloadError(f"cannot download {url}: {error}") from error
        return found


def _sha256(recorded: str) -> str | None:
    wanted = digest.expected(recorded)
    return None if wanted is None else digest.recorded(wanted)
