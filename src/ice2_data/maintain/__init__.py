"""Maintainer-side tooling: describing, publishing and uploading a catalogue.

Consumers of the catalogue never import this package -- ``ice2_data`` itself
stays a read-only library.  What lives here is the other half of the same
contract: the code that *writes* the descriptors ``ice2_data.catalog`` reads.

Keeping both halves in one distribution is the point.  The ``ice2:`` extensions
-- shapefile sidecars, shard layout, access classes -- are a format, and a
format with its writer in one repository and its reader in another drifts
silently: the reader grows a feature, the writer never emits it, and nothing
fails loudly enough to notice.

The command line entry point is ``ice2-data catalog`` (see :mod:`.cli`).  ``upload``
and ``check-store`` additionally need ``rclone`` and ``oidc-agent`` on PATH;
they pull in no extra Python dependencies, which is why there is no separate
install extra to remember.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..catalog import ROLE_KEY, ROLE_PUBLISHED, ROLE_SOURCE

CATALOG_MARKER = "catalog.yaml"
#: Present in a *generated* catalogue too, so it can never identify a source one.
GENERATED_MARKER = "datacatalog.json"


def catalogue_role(path: Path) -> str | None:
    """The role a directory's ``datacatalog.json`` declares, if it has one.

    Read rather than inferred. The old guess -- index present, ``catalog.yaml``
    absent -- happened to be right, but it could not tell a published catalogue
    from a source checkout someone had half-deleted, and it had nothing to say
    about a catalogue that is neither.
    """
    index = path / GENERATED_MARKER
    if not index.is_file():
        return None
    try:
        return json.loads(index.read_text()).get(ROLE_KEY) or None
    except (OSError, ValueError):
        return None


def _source_catalogue_near(path: Path) -> Path | None:
    """A sibling that *is* a source catalogue, to name in an error message."""
    try:
        siblings = sorted(p for p in path.parent.iterdir() if p.is_dir())
    except OSError:
        return None
    return next((p for p in siblings if (p / CATALOG_MARKER).is_file()), None)


def _refuse(path: Path, searched_upward: bool) -> SystemExit:
    """Explain why this directory cannot be worked on, as specifically as possible."""
    role = catalogue_role(path)
    has_index = (path / GENERATED_MARKER).is_file()
    if role != ROLE_PUBLISHED and not (role is None and has_index):
        where = f"{path} or any parent directory" if searched_upward else str(path)
        return SystemExit(
            f"no {CATALOG_MARKER} in {where}.\n"
            "Run this from inside a catalogue checkout, or pass --catalog-root."
        )

    if role:
        says = f"it declares {ROLE_KEY}: {role!r}"
    else:
        says = f"it has {GENERATED_MARKER} but no {CATALOG_MARKER}"

    source = _source_catalogue_near(path)
    where_to_go = str(source) if source else "<the source catalogue>"

    return SystemExit(
        f"{path} is a {ROLE_PUBLISHED} catalogue, not a {ROLE_SOURCE} one ({says}).\n"
        "It carries the published output only -- no dataset.yaml and no source_dir -- so there "
        "are no local bytes to build, upload or publish from, and anything you change in it is "
        "overwritten by the next `ice2-data catalog publish`.\n\n"
        "Work in the source catalogue and republish:\n"
        f"    cd {where_to_go}\n"
        "    ice2-data catalog upload <dataset>\n"
        f"    ice2-data catalog publish {path}"
    )


def find_catalog_root(start: Path | None = None) -> Path:
    """The nearest enclosing catalogue checkout, searching upward from ``start``.

    A catalogue is identified by its hand-written ``catalog.yaml``; the generated
    ``datacatalog.json`` is not a marker, because a published catalogue has one
    of those too and must never be mistaken for a source one.
    """
    here = (start or Path.cwd()).expanduser().resolve()
    for candidate in (here, *here.parents):
        if (candidate / CATALOG_MARKER).is_file():
            return candidate
    raise _refuse(here, searched_upward=True)


def resolve_catalog_root(explicit: str | None, start: Path | None = None) -> Path:
    """The catalogue to act on: ``--catalog-root`` if given, else the enclosing one."""
    if explicit is None:
        return find_catalog_root(start)
    path = Path(explicit).expanduser().resolve()
    if not (path / CATALOG_MARKER).is_file():
        raise _refuse(path, searched_upward=False)
    return path


def datasets_dir(catalog_root: Path) -> Path:
    return catalog_root / "datasets"


def resources_of(package: dict, dataset_dir: Path) -> list[dict]:
    """Every resource in a dataset, whether its inventory is inline or sharded.

    A sharded descriptor carries an ``ice2:shards`` index instead of
    ``resources``; the inventory lives in ``manifests/<prefix>.json`` beside it.
    Shared by the manifest builder (freezing an uploaded dataset's inventory
    without re-reading source_dir) and the uploader (finding what to copy and
    verify) so the two can never disagree about what a sharded package contains.
    """
    if "resources" in package:
        return package["resources"]
    resources: list[dict] = []
    for shard in package.get("ice2:shards", []):
        shard_file = dataset_dir / shard["path"]
        if not shard_file.is_file():
            raise SystemExit(
                f"{package['name']}: shard {shard['path']} is missing. Run:\n"
                f"    ice2-data catalog build {package['name']}"
            )
        resources.extend(json.loads(shard_file.read_text())["resources"])
    return resources
