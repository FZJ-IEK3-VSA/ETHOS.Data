"""``collections.yaml``: a package's selection of catalogue data, by workflow.

The structure only. Resolving a collection, its variants, ``extends`` and its
named paths against a catalogue is :mod:`ethos_data.selection`'s job, which
reports a mistake in one collection without hiding the others.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Collection", "CollectionsFile", "IncludeRule", "Selection", "lint"]


class _Part(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class IncludeRule(_Part):
    """One ``include`` entry: a dataset, family or glob, and the files to take from it."""

    dataset: str = Field(description="A dataset or family name, or a glob over names.")
    files: list[str] | None = Field(
        None, description="Globs against each dataset's paths; omit for every file."
    )


class Selection(_Part):
    """What a collection, or one of its variants, selects."""

    extends: list[str] = Field([], description="Other collections in this file.")
    include: list[IncludeRule] = Field([], description="The data this collection adds.")
    paths: dict[str, str] = Field(
        {}, description="Handle to catalogue key, for the workflow's arguments."
    )


class Collection(Selection):
    """One collection; written plainly, or twice under ``test:`` and ``full:``."""

    title: str | None = Field(None, description="One line, shown by `show`.")
    test: Selection | None = Field(None, description="The small selection for tests.")
    full: Selection | None = Field(None, description="The real inputs; the default.")


class CollectionsFile(_Part):
    """The whole file: the catalogue it reads and its collections."""

    catalog: str | None = Field(
        None,
        description="The catalogue location; a relative path is relative to this file.",
    )
    collections: dict[str, Collection] = Field(
        {}, description="Collection name to definition."
    )


_SELECTION_KEYS = set(Selection.model_fields)
_COLLECTION_KEYS = set(Collection.model_fields)


def lint(document: dict) -> list[str]:
    """Keys the format does not define, which are ignored and usually typos."""
    warnings = [
        f"{key} is not a key of collections.yaml; it is ignored"
        for key in document
        if key not in CollectionsFile.model_fields
    ]
    for name, definition in (document.get("collections") or {}).items():
        if not isinstance(definition, dict):
            continue
        for key in definition:
            if key not in _COLLECTION_KEYS:
                warnings.append(
                    f"collections.{name}.{key} is not a key of a collection"
                )
        for variant in ("test", "full"):
            body = definition.get(variant)
            if isinstance(body, dict):
                for key in body:
                    if key not in _SELECTION_KEYS:
                        warnings.append(
                            f"collections.{name}.{variant}.{key} is not a key of a variant"
                        )
    return warnings
