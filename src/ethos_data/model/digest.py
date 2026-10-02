"""SHA-256 digests: of a file, and as a catalogue records them.

The one implementation of both. A resource's ``hash`` is recorded as
``sha256:<hex>``, the spelling the build writes and pooch reads; the Data
Package standard also allows a bare digest, and a licence document's
``ethos:document_sha256`` is usually written bare. Whatever compares a file
with a catalogue goes through :func:`expected`, so the spelling of a digest,
prefixed or bare, upper or lower case, never decides whether two equal digests
match.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

__all__ = [
    "ALGORITHM",
    "CHUNK",
    "expected",
    "matches",
    "of_bytes",
    "of_file",
    "recorded",
]

#: The one algorithm the catalogue records.
ALGORITHM = "sha256"
_PREFIX = f"{ALGORITHM}:"
_HEX = re.compile(r"[0-9a-f]{64}")

#: Bytes read per call. Large, so a file of many gigabytes costs few calls;
#: hashlib releases the GIL while it digests a block, so threads hashing
#: different files overlap.
CHUNK = 8 * 1024 * 1024


def of_file(path: str | Path, chunk: int = CHUNK) -> str:
    """The SHA-256 of the file at ``path``, as bare lowercase hex."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def of_bytes(data: bytes) -> str:
    """The SHA-256 of ``data``, as bare lowercase hex."""
    return hashlib.sha256(data).hexdigest()


def recorded(hex_digest: str) -> str:
    """A digest spelled the way the build records it: ``sha256:<hex>``."""
    return _PREFIX + hex_digest.lower()


def expected(value: object) -> str | None:
    """The bare lowercase hex digest a recorded hash stands for, or None.

    Accepts ``sha256:<hex>`` and a bare digest, in either case. None for
    anything else -- nothing recorded, another algorithm, a malformed value --
    which a caller reports as unverifiable rather than as a mismatch: a check
    against it could only ever fail, and repairing the file would not change
    that.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    algorithm, separator, rest = text.partition(":")
    if separator:
        if algorithm != ALGORITHM:
            return None
        text = rest
    return text if _HEX.fullmatch(text) else None


def matches(value: object, digest: str) -> bool:
    """Whether a recorded hash names ``digest``, however either is spelled.

    False when the record is unusable, so an unverifiable file never passes
    as a verified one.
    """
    wanted = expected(value)
    return wanted is not None and wanted == expected(digest)
