"""dCache, as a maintainer writes it: rclone for bytes, its REST interface for the rest.

The real :class:`~ethos_data.adapters.Store`. Every call here leaves the
machine -- an ``oidc-token`` subprocess, an rclone transfer, an HTTP request to
the DESY frontend -- which is why tests pass a :class:`FakeStore` instead.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .. import report
from ..errors import UploadError

__all__ = ["FRONTEND", "MODE_0755", "DcacheStore"]

FRONTEND = "https://hifis-storage-web.desy.de/api/v1"
MODE_0755 = 493  # dCache wants the mode as a decimal integer, not octal


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Every command this adapter starts, in one place: the one tests refuse."""
    return subprocess.run(command, check=False, **kwargs)


def _capture(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return _run(command, text=True, capture_output=True, **kwargs)


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
                f"    oidc-gen {profile} --flow=code --client-id=desy-public \\\n"
                "        --scope='openid profile offline_access' \\\n"
                "        --iss=https://keycloak.desy.de/auth/realms/production/ \\\n"
                "        --redirect-uri=http://localhost:4242"
            )
        return result.stdout.strip()

    def copy(
        self,
        source: Path,
        destination: str,
        paths: list[str],
        *,
        transfers: int,
        dry_run: bool,
    ) -> int:
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
            "--progress" if not dry_run else "--dry-run",
        ]
        report.info(f"  ({len(paths)} files listed in {listing})")
        report.info("  $ " + " ".join(command) + "\n")
        try:
            return _run(command).returncode
        finally:
            listing.unlink(missing_ok=True)

    def chmod(self, path: str, mode: int, bearer: str) -> int:
        request = urllib.request.Request(
            f"{self.frontend}/namespace/{path.lstrip('/')}",
            data=json.dumps({"action": "chmod", "mode": mode}).encode(),
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def locality(self, path: str, bearer: str) -> str:
        """ONLINE (disk) / NEARLINE (tape only) / ONLINE_AND_NEARLINE (both)."""
        url = f"{self.frontend}/namespace/{path.lstrip('/')}?locality=true"
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {bearer}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response).get("fileLocality", "unknown")
        except Exception as error:  # noqa: BLE001 - network shapes vary
            return f"unknown ({error})"
