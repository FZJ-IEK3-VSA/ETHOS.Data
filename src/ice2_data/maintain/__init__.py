"""Maintainer-side tooling: describing, publishing and uploading a catalogue.

Consumers of the catalogue never import this package -- ``ice2_data`` itself
stays a read-only library.  What lives here is the other half of the same
contract: the code that *writes* the descriptors ``ice2_data.catalog`` reads.

Keeping both halves in one distribution is the point.  The ``ice2:`` extensions
-- shapefile sidecars, shard layout, access classes -- are a format, and a
format with its writer in one repository and its reader in another drifts
silently: the reader grows a feature, the writer never emits it, and nothing
fails loudly enough to notice.

The command line entry point is ``ice2-catalog`` (see :mod:`.cli`).  ``upload``
and ``check-access`` additionally need ``rclone`` and ``oidc-agent`` on PATH;
they pull in no extra Python dependencies, which is why there is no separate
install extra to remember.
"""

from __future__ import annotations

from pathlib import Path

CATALOG_MARKER = "catalog.yaml"


def find_catalog_root(start: Path | None = None) -> Path:
    """The nearest enclosing catalogue checkout, searching upward from ``start``.

    A catalogue is identified by its hand-written ``catalog.yaml``; the generated
    ``datacatalog.json`` is not a marker, because a half-built checkout that has
    one but not the other is exactly when a clear error matters most.
    """
    here = (start or Path.cwd()).expanduser().resolve()
    for candidate in (here, *here.parents):
        if (candidate / CATALOG_MARKER).is_file():
            return candidate
    raise SystemExit(
        f"no {CATALOG_MARKER} in {here} or any parent directory.\n"
        "Run this from inside a catalogue checkout, or pass --catalog-root."
    )


def datasets_dir(catalog_root: Path) -> Path:
    return catalog_root / "datasets"
