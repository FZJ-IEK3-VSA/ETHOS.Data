"""dCache, as a maintainer writes it: rclone for bytes, its REST interface for the rest.

The real :class:`~ethos_data.adapters.Store`. Every call here leaves the
machine -- an ``oidc-token`` subprocess, an rclone transfer, an HTTP request to
the DESY frontend or to the public door -- which is why tests pass a
:class:`~ethos_data.adapters.fakes.FakeStore` instead. Every failure raises
:class:`~ethos_data.errors.UploadError`; ``served_each`` returns it in place of
the size of each file it could not read.
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from .. import report
from ..errors import UploadError
from ..formats.catalogue import DCACHE_FRONTEND as FRONTEND

__all__ = ["FRONTEND", "MODE_0755", "READ_BACK_LANES", "DcacheStore"]
MODE_0755 = 493  # dCache wants the mode as a decimal integer, not octal

#: How many files a read-back asks for at once. dCache takes about 2.4 s to
#: answer for a file it has not looked up lately, so one at a time the 3,861
#: files of a tiled dataset took two and a half hours; the time fell in step with
#: the lanes up to 32, the most measured, to five minutes. Each lane keeps its
#: connection open, which saves the TLS handshake of every further request.
READ_BACK_LANES = 32


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Every command this adapter starts, in one place: the one tests refuse."""
    return subprocess.run(command, check=False, **kwargs)


def _capture(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return _run(command, text=True, capture_output=True, **kwargs)


@contextmanager
def _urlopen(request: urllib.request.Request) -> Iterator[http.client.HTTPResponse]:
    """Every HTTP request this adapter makes, closed however it ends.

    An HTTPError holds the response it reports, and with it the connection.
    Left open, it is closed by a garbage collection, with a ResourceWarning, in
    whatever code happens to run then.
    """
    try:
        response = urllib.request.urlopen(request, timeout=60)
    except urllib.error.HTTPError as error:
        error.close()
        raise
    with response:
        yield response


def _namespace(frontend: str, path: str) -> str:
    """The frontend's URL of a path below the VO, percent-encoded for the request line."""
    return f"{frontend}/namespace/{quote(path.lstrip('/'))}"


class DcacheStore:
    """The publication store on dCache, reached through ``remote``."""

    def __init__(self, remote: str = "HIFIS", frontend: str = FRONTEND):
        self.remote = remote
        self.frontend = frontend

    def token(self, profile: str) -> str:
        result = _capture(["oidc-token", profile])
        if result.returncode != 0 or not result.stdout.strip():
            raise UploadError(
                f"could not get a token from `oidc-token {profile}`.\n"
                f"  {result.stderr.strip()}\n"
                "Start the agent and register the profile:\n"
                "    eval $(oidc-agent-service use)\n"
                f"    oidc-gen {profile} --flow=code --client-id=desy-public "
                "--client-secret='' \\\n"
                '        --scope="openid profile offline_access" \\\n'
                "        --iss=https://keycloak.desy.de/auth/realms/production/ \\\n"
                "        --redirect-uri=http://localhost:8080"
            )
        return result.stdout.strip()

    def copy(
        self,
        source: Path,
        destination: str,
        paths: list[str],
        *,
        transfers: int,
    ) -> None:
        """``rclone copy`` of exactly ``paths``: the inventory, not the directory.

        They are the same thing only when nothing else lives under the source;
        with ethos:include or ethos:exclude in play they are not, and copying
        the directory would publish the strays the inventory leaves out --
        silently, since verification only looks for files it knows about.
        """
        # A nested dataset's destination holds a slash, which a filename cannot.
        stem = destination.rsplit(":", 1)[-1].replace("/", "-").replace(os.sep, "-")
        handle, listing_path = tempfile.mkstemp(
            prefix=f"ethos-data-upload-{stem}-", suffix=".txt"
        )
        # rclone reads --files-from as UTF-8, one path per line. Written as bytes
        # because a text-mode write on Windows would end every line CRLF, and
        # rclone would then look for files whose names end in a carriage return.
        with open(handle, "wb") as listing_file:
            listing_file.writelines(f"{path}\n".encode() for path in paths)
        listing = Path(listing_path)
        command = [
            "rclone",
            "copy",
            str(source),
            f"{self.remote}:{destination}",
            "--files-from",
            str(listing),
            "--transfers",
            str(transfers),
            "--checksum",
            # dCache cannot modify a file in place -- a changed file is delete +
            # rewrite. --immutable makes rclone fail loudly if a published file
            # differs, instead of silently republishing under the same path.
            "--immutable",
            "--progress",
        ]
        report.info(f"  ({len(paths)} files listed in {listing})")
        report.info("  $ " + " ".join(command) + "\n")
        try:
            status = _run(command).returncode
        finally:
            listing.unlink(missing_ok=True)
        if status != 0:
            raise UploadError(
                f"rclone exited {status} copying to {self.remote}:{destination}. "
                f"Check that the rclone remote {self.remote!r} exists and that "
                "oidc-agent runs. If a published file changed, --immutable refused "
                "to overwrite it: publish the change at a new path."
            )

    def sync(self, source: Path, destination: str) -> None:
        """``rclone sync``: the destination ends up holding what ``source`` holds."""
        command = [
            "rclone",
            "sync",
            str(source),
            f"{self.remote}:{destination}",
            "--checksum",
            "--exclude",
            ".git/**",
            "--progress",
        ]
        report.info("  $ " + " ".join(command) + "\n")
        status = _run(command).returncode
        if status != 0:
            raise UploadError(
                f"rclone exited {status} syncing {source} to "
                f"{self.remote}:{destination}"
            )

    def purge(self, destination: str) -> None:
        """``rclone purge``: the folder and everything in it, with no trash area."""
        command = ["rclone", "purge", f"{self.remote}:{destination}"]
        report.info("  $ " + " ".join(command) + "\n")
        status = _run(command).returncode
        if status != 0:
            raise UploadError(
                f"rclone exited {status} purging {self.remote}:{destination}"
            )

    def exists(self, destination: str) -> bool:
        """``rclone lsf`` of the folder: whether it lists anything."""
        result = _capture(
            ["rclone", "lsf", "--max-depth", "1", f"{self.remote}:{destination}"]
        )
        # rclone's exit status 3 means "directory not found".
        if result.returncode == 3:
            return False
        if result.returncode != 0:
            raise UploadError(
                f"rclone exited {result.returncode} listing "
                f"{self.remote}:{destination}: {result.stderr.strip()}"
            )
        return bool(result.stdout.strip())

    def chmod(self, path: str, mode: int, bearer: str) -> None:
        request = urllib.request.Request(
            _namespace(self.frontend, path),
            data=json.dumps({"action": "chmod", "mode": mode}).encode(),
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with _urlopen(request):
                return
        except (OSError, ValueError) as error:
            raise UploadError(
                f"chmod {mode:o} {path} failed: {_reason(error)}"
            ) from None

    def locality(self, path: str, bearer: str) -> str:
        """ONLINE (disk) / NEARLINE (tape only) / ONLINE_AND_NEARLINE (both)."""
        url = f"{_namespace(self.frontend, path)}?locality=true"
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {bearer}"}
        )
        try:
            with _urlopen(request) as response:
                return json.load(response).get("fileLocality", "unknown")
        except (OSError, ValueError) as error:
            raise UploadError(
                f"cannot ask where {path} is stored: {_reason(error)}"
            ) from None

    def served(self, url: str) -> int:
        """HEAD ``url`` without credentials; the Content-Length it answers."""
        (found,) = self.served_each([url])
        if isinstance(found, UploadError):
            raise found
        return found

    def served_each(self, urls: list[str]) -> list[int | UploadError]:
        """HEAD each URL without credentials, ``READ_BACK_LANES`` at a time."""
        import requests

        found: list[int | UploadError] = [UploadError("not asked")] * len(urls)
        lanes = min(READ_BACK_LANES, len(urls))

        def lane(first: int) -> None:
            with requests.Session() as session:
                # Without an auth of its own, a session sends the credentials
                # ~/.netrc holds for the host, and a read-back that should prove
                # what anyone can read would prove what the maintainer can.
                session.auth = _anonymous
                for index in range(first, len(urls), lanes):
                    found[index] = _served_on(session, urls[index])

        if lanes:
            with ThreadPoolExecutor(max_workers=lanes) as pool:
                list(pool.map(lane, range(lanes)))
        return found


def _anonymous(request):
    """A requests auth that adds nothing: no header, and no ~/.netrc lookup either."""
    return request


def _served_on(session, url: str) -> int | UploadError:
    """One HEAD on ``session``: the Content-Length, or why the file is not readable."""
    try:
        with session.head(url, timeout=60, allow_redirects=True) as response:
            if response.status_code >= 400:
                return UploadError(
                    f"{url} is not readable: "
                    f"HTTP {response.status_code} {response.reason}"
                )
            return int(response.headers.get("Content-Length", -1))
    except (OSError, ValueError) as error:
        # requests' errors are OSErrors.
        return UploadError(f"{url} is not readable: {error}")


def _reason(error: Exception) -> str:
    """An HTTP status as ``HTTP 401 Unauthorized``; any other failure as it reads."""
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code} {error.reason}"
    return str(getattr(error, "reason", None) or error)
