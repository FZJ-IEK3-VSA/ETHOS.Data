"""What a descriptor's keys add up to, computed one way for every reader and writer.

Plain functions over plain mappings, with no pydantic behind them, so the
reader's hot path can use them without importing the models:

* :func:`index_row`, a dataset's row in ``datacatalog.json``, for the source
  index and the published one alike;
* :func:`license_status_of` and :func:`license_settled`, what the licence
  question looks like for a descriptor;
* :func:`remote_prefix_of`, the folder a dataset's bytes live in on the store.
"""

from __future__ import annotations

from typing import Any

from . import keys as k

__all__ = ["index_row", "license_settled", "license_status_of", "remote_prefix_of"]


def license_status_of(package: dict) -> str:
    """``resolved`` once a licence is recorded, else what the descriptor says, else unknown.

    A present ``licenses`` list settles it: the build already rejects an entry
    that names no licence. Promoted into the index so that warning about
    licensing costs no descriptor read.
    """
    if package.get(k.LICENSES):
        return k.RESOLVED
    return package.get(k.LICENSE_STATUS, k.UNKNOWN)


def license_settled(meta: dict) -> bool:
    """Whether a descriptor states terms somebody has actually checked.

    The rule :func:`license_status_of` applies, asked of a plain mapping -- a
    ``dataset.yaml``, a ``datapackage.json`` or an index row -- so the half of
    the tooling that writes can refuse to distribute a dataset before the
    question has been answered.
    """
    return license_status_of(meta) == k.RESOLVED


def remote_prefix_of(package: dict) -> str:
    """The dataset's folder on the published store: its own prefix, else its name."""
    return package.get(k.REMOTE_PREFIX) or package[k.NAME]


def index_row(package: dict, path: str) -> dict[str, Any]:
    """The row ``datacatalog.json`` carries for this descriptor, ``path`` relative to it.

    One function for the source index and the published one, so a reader of
    either finds the same keys. A family's row has no access class, remote
    prefix or licence status: it has no bytes for any of those to be about.
    """
    if package.get(k.NAMESPACE):
        return {
            k.NAME: package[k.NAME],
            k.PATH: path,
            k.TITLE: package.get(k.TITLE, ""),
            k.NAMESPACE: True,
            k.TOTAL_BYTES: package[k.TOTAL_BYTES],
            k.FILE_COUNT: package[k.FILE_COUNT],
        }
    return {
        k.NAME: package[k.NAME],
        k.PATH: path,
        k.TITLE: package.get(k.TITLE, ""),
        # Omitted rather than blanked: absent means nobody recorded a release.
        **({k.VERSION: package[k.VERSION]} if package.get(k.VERSION) else {}),
        k.ACCESS: package.get(k.ACCESS, k.PUBLIC),
        k.VISIBILITY: package.get(k.VISIBILITY, k.PUBLIC),
        k.TOTAL_BYTES: package[k.TOTAL_BYTES],
        k.FILE_COUNT: package[k.FILE_COUNT],
        k.REMOTE_PREFIX: remote_prefix_of(package),
        k.LICENSE_STATUS: license_status_of(package),
    }
