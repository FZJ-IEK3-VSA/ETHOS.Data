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

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

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


def _entry(entry: object, *names: str) -> str:
    """One source or licence as a line: its name, and where it lives."""
    if not isinstance(entry, Mapping):
        return str(entry)
    name = next((str(entry[key]) for key in names if entry.get(key)), "")
    where = str(entry.get(k.PATH) or "")
    if name and where:
        return f"{name} ({where})"
    return name or where


def reader_description(package: Mapping) -> list[str]:
    """A dataset's full description, as the lines ``--meta`` prints.

    The keys the dataset.yaml specification marks user-facing, each as far as
    the descriptor records it -- what the data is, where it came from, under
    which terms, why it is restricted and how to obtain it, and whom to ask --
    with the access class and the origin.
    """
    lines: list[str] = []
    heading = str(package.get(k.TITLE) or package.get(k.NAME) or "")
    version = package.get(k.VERSION)
    if version:
        heading = f"{heading}  (version {version})" if heading else f"version {version}"
    if heading:
        lines.append(heading)
    if package.get(k.DESCRIPTION):
        lines.append(str(package[k.DESCRIPTION]).strip())

    rows: list[tuple[str, str]] = [("access", str(package.get(k.ACCESS, k.PUBLIC)))]
    if package.get(k.ORIGIN):
        rows.append(("origin", str(package[k.ORIGIN])))
    if package.get(k.HOMEPAGE):
        rows.append(("homepage", str(package[k.HOMEPAGE])))
    for source in package.get(k.SOURCES) or []:
        rows.append(("source", _entry(source, k.TITLE)))
    for licence in package.get(k.LICENSES) or []:
        rows.append(("licence", _entry(licence, k.TITLE, k.NAME)))
    if package.get(k.ATTRIBUTION):
        rows.append(("attribution", str(package[k.ATTRIBUTION]).strip()))
    if package.get(k.RESTRICTION):
        rows.append(("restricted", str(package[k.RESTRICTION]).strip()))
    upstream = package.get(k.UPSTREAM)
    if isinstance(upstream, Mapping) and upstream.get("status"):
        note = str(upstream.get("note") or "").strip()
        rows.append(
            (
                "upstream",
                f"{upstream['status']}: {note}" if note else str(upstream["status"]),
            )
        )
    if package.get(k.CONTACT):
        rows.append(("contact", str(package[k.CONTACT]).strip()))

    width = max((len(label) for label, _ in rows), default=0)
    for label, value in rows:
        first, *rest = value.splitlines() or [""]
        lines.append(f"{label:<{width}}  {first}")
        lines.extend(f"{'':<{width}}  {line}" for line in rest)
    return lines


def object_folder(remote_prefix: str, revision: int = 1) -> str:
    """The store's folder for the files published in one revision of a dataset.

    ``<remote_prefix>`` for the first revision and ``<remote_prefix>@<revision>``
    for a later one: published objects never change, so a file whose bytes
    changed in a revision is published beside the old ones, not over them.
    """
    return remote_prefix if revision <= 1 else f"{remote_prefix}@{revision}"


def object_url(dataset_url: str, record: Mapping) -> str:
    """Where the store serves one resource record, ``dataset_url`` its first folder.

    The path is percent-encoded. A file name may hold a space, which a request
    line may not: ``urllib`` refuses such a URL outright, and a read-back of
    ``Supplementary material.txt`` stopped the upload of every dataset after it.
    """
    revision = int(record.get(k.REVISION, 1))
    base = dataset_url.rstrip("/")
    folder = base if revision <= 1 else f"{base}@{revision}"
    return f"{folder}/{quote(record[k.PATH])}"


def resource_url(publication_url: str, remote_prefix: str, path: str = "") -> str:
    """Where the published store serves a file: ``<publication_url>/<remote_prefix>/<path>``.

    Without ``path``, the dataset's folder, with its trailing slash. The one
    spelling of the rule, for the reader that downloads a file, the bundle
    export that copies it and the upload that reads it back.
    """
    return f"{publication_url.rstrip('/')}/{remote_prefix}/{path}"


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
        **{
            key: package[key]
            for key in (k.REVISION, k.SUPERSEDES, k.SUPERSEDED_BY)
            if package.get(key)
        },
    }
