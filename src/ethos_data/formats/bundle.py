"""``bundle.json``: what a bundle holds, as :mod:`ethos_data.bundles` writes it.

A bundle is a directory in a repository: the files of a selection of
catalogue datasets under ``data/<dataset>/<path>``, each dataset's
description and licence documents under ``datasets/<dataset>/``, and this
manifest. For each dataset it records the catalogue revision the dataset was
last aligned with (none for a dataset the catalogue does not describe yet)
and the release it was taken from, which is only shown; whether it holds
every file or a selection; the changes recorded since the alignment; and
every file's size and SHA-256, the descriptions and licence documents
included. One specification: ``bundle create``, ``bundle update`` and
``bundle export`` write it, and :func:`ethos_data.load_bundle` reads it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import keys as k
from .package import ResourceRecord

__all__ = [
    "DATA_DIR",
    "DESCRIPTIONS_DIR",
    "FILENAME",
    "FORMAT",
    "Alignment",
    "BundleManifest",
    "BundledDataset",
    "BundledFamily",
    "Change",
    "DocumentRecord",
]

FILENAME = k.BUNDLE_FILE
FORMAT = k.BUNDLE_FORMAT
DATA_DIR = k.BUNDLE_DATA_DIR
DESCRIPTIONS_DIR = k.BUNDLE_DESCRIPTIONS_DIR


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Alignment(_Record):
    """The catalogue revision a bundled dataset was last aligned with."""

    revision: int = Field(
        ge=1, description="The dataset's revision in the catalogue; 1 for the first."
    )
    release: str | None = Field(
        None, description="The catalogue release it was taken from; only shown."
    )


class DocumentRecord(_Record):
    """A description or licence document under ``datasets/<dataset>/``."""

    path: str = Field(description="Relative to the dataset's description directory.")
    bytes: int = Field(ge=0)
    hash: str = Field(description='"sha256:<hex>".')


class Change(_Record):
    """One change ``bundle update`` recorded since the alignment."""

    path: str = Field(
        description="The file's path in the dataset, or the document's in its "
        "description directory."
    )
    change: Literal["changed", "added", "removed"]
    document: bool = Field(
        False, description="A description or licence document, not a data file."
    )
    was: str | None = Field(
        None,
        description="The SHA-256 at the alignment, for a changed or removed file.",
    )


class BundledDataset(_Record):
    """One dataset the bundle holds."""

    alignment: Alignment | None = Field(
        None,
        description="The catalogue revision last aligned with; null for a dataset "
        "the catalogue does not describe yet.",
    )
    selection: Literal["all", "some"] = Field(
        "all", description="Whether the bundle holds every file of the dataset."
    )
    changes: list[Change] = Field(
        [], description="The changes recorded since the alignment."
    )
    resources: list[ResourceRecord] = Field(
        description="Every file under data/<dataset>/, with its size and SHA-256."
    )
    documents: list[DocumentRecord] = Field(
        [],
        description="The description, dataset.yaml, and the licence documents.",
    )


class BundledFamily(_Record):
    """A family whose members the bundle holds: its own description."""

    documents: list[DocumentRecord] = Field(
        description="The family's dataset.yaml, and any licence document it names."
    )


class BundleManifest(_Record):
    """``bundle.json``."""

    format: Literal["ethos-data-bundle"] = FORMAT
    datasets: dict[str, BundledDataset] = Field(
        description="Each dataset by its name; a member of a family is <family>/<member>."
    )
    families: dict[str, BundledFamily] = Field(
        {}, description="The families of the bundled members, by name."
    )
