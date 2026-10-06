"""Maintainer-side tooling: describing, publishing and uploading a catalogue.

Consumers of the catalogue never import this package -- ``ethos_data`` itself
stays a read-only library.  What lives here is the other half of the same
contract: the code that *writes* the descriptors ``ethos_data.catalogs`` reads.

Keeping both halves in one distribution is the point.  The ``ethos:`` extensions
-- shapefile sidecars, shard layout, access classes -- are a format, and a
format with its writer in one repository and its reader in another drifts
silently: the reader grows a feature, the writer never emits it, and nothing
fails loudly enough to notice.

The command line entry point is ``ethos-data catalog`` (see :mod:`.cli`).  ``upload``
and ``check-store`` additionally need ``rclone`` and ``oidc-agent`` on PATH;
they pull in no extra Python dependencies, which is why there is no separate
install extra to remember.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import yaml

from ..adapters.metadata import FileSource
from ..errors import CatalogueRootError, DescriptorError, LinkError
from ..formats import keys as k
from ..formats.keys import CATALOG_ROLE as ROLE_KEY
from ..formats.keys import ROLE_PUBLISHED, ROLE_SOURCE
from ..model.inventory import SHARD_DIR, Inventory

CATALOG_MARKER = "catalog.yaml"
#: Present in a *generated* catalogue too, so it can never identify a source one.
GENERATED_MARKER = "datacatalog.json"


def catalogue_role(path: Path) -> str | None:
    """The role a directory's ``datacatalog.json`` declares, if it has one.

    Read rather than inferred: an index without a ``catalog.yaml`` beside it
    may be a published catalogue or a source checkout someone half-deleted, and
    says nothing about a catalogue that is neither.
    """
    index = path / GENERATED_MARKER
    if not index.is_file():
        return None
    try:
        return json.loads(index.read_text(encoding="utf-8")).get(ROLE_KEY) or None
    except (OSError, ValueError):
        return None


def _source_catalogue_near(path: Path) -> Path | None:
    """A sibling that *is* a source catalogue, to name in an error message."""
    try:
        siblings = sorted(p for p in path.parent.iterdir() if p.is_dir())
    except OSError:
        return None
    return next((p for p in siblings if (p / CATALOG_MARKER).is_file()), None)


def _refuse(path: Path, searched_upward: bool) -> CatalogueRootError:
    """Explain why this directory cannot be worked on, as specifically as possible."""
    role = catalogue_role(path)
    has_index = (path / GENERATED_MARKER).is_file()
    if role != ROLE_PUBLISHED and not (role is None and has_index):
        where = f"{path} or any parent directory" if searched_upward else str(path)
        return CatalogueRootError(
            f"no {CATALOG_MARKER} in {where}.\n"
            "Run this from inside a catalogue checkout, or pass --catalog-root."
        )

    if role:
        says = f"it declares {ROLE_KEY}: {role!r}"
    else:
        says = f"it has {GENERATED_MARKER} but no {CATALOG_MARKER}"

    source = _source_catalogue_near(path)
    where_to_go = str(source) if source else "<the source catalogue>"

    return CatalogueRootError(
        f"{path} is a {ROLE_PUBLISHED} catalogue, not a {ROLE_SOURCE} one ({says}).\n"
        "It carries the published output only -- no dataset.yaml and no source_dir -- so there "
        "are no local bytes to build, upload or publish from, and anything you change in it is "
        "overwritten by the next `ethos-data catalog publish`.\n\n"
        "Work in the source catalogue and republish:\n"
        f"    cd {where_to_go}\n"
        "    ethos-data catalog upload <dataset>\n"
        f"    ethos-data catalog publish {path}"
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


#: The hand-written description of one dataset, in its directory under
#: ``datasets/``.
DESCRIPTOR = "dataset.yaml"


def _read_mapping(path: Path) -> dict:
    """A hand-written YAML file as its keys and values; an empty file has none."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise DescriptorError(f"{path} is not valid YAML: {error}") from None
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise DescriptorError(
            f"{path} must hold keys and their values, not a {type(document).__name__}."
        )
    return document


def read_descriptor(dataset_dir: Path) -> dict:
    """A dataset's ``dataset.yaml``, as every command reads it.

    One reader, so an empty file means the same to all of them: a descriptor
    with no keys, which the build then refuses for what it lacks.
    """
    return _read_mapping(dataset_dir / DESCRIPTOR)


def read_catalog_meta(catalog_root: Path) -> dict:
    """The catalogue's ``catalog.yaml``, read as :func:`read_descriptor` reads."""
    return _read_mapping(catalog_root / CATALOG_MARKER)


def source_dir_of(dataset_dir: Path, meta: Mapping) -> Path | None:
    """Where a dataset's bytes are read from, or None if it states no ``source_dir``.

    Resolved against the dataset's own directory, never the current one, so a
    relative ``source_dir`` means the same thing to every command wherever it
    runs: otherwise an upload could take its bytes from somewhere the build
    never saw. Only a relative one is resolved, and only to make it absolute.
    An absolute one is used as written, symbolic links and all: when it names
    the curated namespace, that is the path worth recording, because it stays
    correct when the storage behind it moves.
    """
    raw = meta.get(k.SOURCE_DIR)
    if not raw:
        return None
    source = Path(str(raw)).expanduser()
    if not source.is_absolute():
        source = (dataset_dir / source).resolve()
    return source


#: Set on a namespace node's generated descriptor. A namespace has no files of
#: its own -- it exists to name a family and to carry the metadata its members
#: share -- so tools must not treat it as something to download.
NAMESPACE_KEY = k.NAMESPACE


def __getattr__(name: str):
    """``INHERITED_KEYS``, from the dataset.yaml specification, on first use.

    The keys a nested dataset takes from the namespace above it when it does
    not state its own: those the specification marks ``inherited``. A key may
    be inherited only if inheriting it cannot *weaken* a claim -- `homepage` and
    `ethos:contact` are descriptive, `ethos:attribution` can only add a duty.
    `licenses`, `ethos:access`, `ethos:visibility`, `ethos:origin` and
    `source_dir` are deliberately not: a child states them or it does not build.

    Resolved lazily because every command imports this package, and the
    specification's models are only worth loading when a descriptor is read.
    """
    if name == "INHERITED_KEYS":
        from ..formats import dataset

        return dataset.INHERITED
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def iter_dataset_dirs(root: Path) -> list[Path]:
    """Every directory under ``datasets/`` holding a dataset.yaml, at any depth.

    Nesting is what lets one dataset be described as a family of smaller ones:
    ``datasets/reskit-test-data/dataset.yaml`` names the family and
    ``datasets/reskit-test-data/era5/dataset.yaml`` one member of it, addressed
    as ``reskit-test-data/era5``.

    Recursion does not stop at the first dataset.yaml -- that is the whole point,
    a dataset directory may contain more of them. It does skip ``shards/``,
    which holds generated shard files and never a dataset.
    """
    found: list[Path] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("dataset.yaml")):
        if SHARD_DIR in path.relative_to(root).parts:
            continue
        found.append(path.parent)
    return found


def dataset_name_for(root: Path, dataset_dir: Path) -> str:
    """A dataset's name: its path relative to ``datasets/``, slash-separated.

    For a top-level dataset this is just the directory name. For a nested one it is ``parent/child``, which is also its
    cache path, its default remote prefix, and how a collections file addresses
    it -- one string, meaning the same thing everywhere.
    """
    return dataset_dir.relative_to(root).as_posix()


def is_namespace(dataset_dir: Path) -> bool:
    """Whether this dataset directory has dataset directories inside it."""
    return any(
        child.is_dir() and (child / "dataset.yaml").is_file()
        for child in dataset_dir.iterdir()
    )


def parent_chain(root: Path, dataset_dir: Path) -> list[Path]:
    """Enclosing dataset directories, outermost first."""
    chain: list[Path] = []
    current = dataset_dir.parent
    while current != root and root in current.parents or current == root:
        if current == root:
            break
        if (current / "dataset.yaml").is_file():
            chain.append(current)
        current = current.parent
    return list(reversed(chain))


def source_dir_for(name: str, catalog_root: str | Path | None = None) -> Path:
    """The ``source_dir`` a source catalogue records for this dataset.

    It lives in the dataset's ``status.yaml`` and nowhere else -- not in
    ``datapackage.json``, not in any ``datacatalog.json``. Reading it means
    reading the checkout, exactly as ``catalog build`` and ``catalog upload``
    do; ``catalog_root`` names it, or it is searched for upward from the
    current directory.

    ``ethos-data link`` and ``materialize`` ask it when they are given no
    directory; reading a checkout is catalogue maintenance, so the data-access
    services take the answer, not the question.
    """
    try:
        root = resolve_catalog_root(
            str(catalog_root) if catalog_root is not None else None
        )
    except CatalogueRootError as error:
        # `resolve_catalog_root` is written for the maintainer commands, which
        # exit on a missing checkout. Here it is one way of answering a question,
        # so it becomes the same error every other failure in this module raises.
        raise LinkError(error.message) from None
    dataset_dir = datasets_dir(root) / name
    descriptor = dataset_dir / "dataset.yaml"
    if not descriptor.is_file():
        raise LinkError(f"no dataset called {name!r} in {datasets_dir(root)}")
    from .status import build_input

    source = build_input(dataset_dir, read_descriptor(dataset_dir), name).source_dir
    if source is None:
        raise LinkError(
            f"{name} has no source_dir left in {dataset_dir}, so there is nothing "
            "to link from: its inventory is final, and its authoritative copy is "
            f"elsewhere. Name the directory instead:\n    ethos-data link {name} "
            f"/path/to/{name}"
        )
    return source


def inventory_of(name: str, dataset_dir: Path) -> Inventory:
    """A dataset's generated descriptor and inventory in a checkout.

    Read by the one inventory reader, as a data user reads it, so a maintainer
    command sees exactly the resources a reader sees. A descriptor or shard
    that is not there means a build is due, and says so.
    """

    def missing(part: str, location: str) -> DescriptorError:
        return DescriptorError(
            f"{name}: its {part} is missing: {location}. Run:\n"
            f"    ethos-data catalog build {name}"
        )

    return Inventory(
        name,
        FileSource(),
        (dataset_dir / "datapackage.json").as_posix(),
        missing=missing,
    )
