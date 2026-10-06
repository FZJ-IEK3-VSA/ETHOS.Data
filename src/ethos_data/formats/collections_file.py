"""``collections.yaml``: a package's selection of catalogue data, by workflow.

The structure and the rules within one collection. :mod:`ethos_data.selection`
reads the file through these models, one collection at a time, so a mistake in
one collection is reported without hiding the others; resolving a collection,
its variants, ``extends`` and its named paths against a catalogue is its job.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..model.versions import BOUND_PATTERN, Bounds, Prefix
from . import keys as k

__all__ = [
    "CatalogBounds",
    "Collection",
    "CollectionsFile",
    "IncludeRule",
    "Selection",
    "lint",
]

#: The keys that say what a collection selects: at its top level, or inside
#: each of its variants, never both.
_SELECTING = ("extends", "include", "paths")


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

    @field_validator("paths")
    @classmethod
    def _keys_named(cls, paths: dict[str, str]) -> dict[str, str]:
        for handle, key in paths.items():
            if not handle:
                raise ValueError("a handle must be a name")
            if not key.strip("/"):
                raise ValueError(
                    f"{handle} must be a key such as '<dataset>/<file>' or "
                    f"'<dataset>/<folder>', got {key!r}"
                )
        return paths


class Collection(Selection):
    """One collection; written plainly, or twice under ``test:`` and ``full:``."""

    title: str | None = Field(None, description="One line, shown by `show`.")
    test: Selection | None = Field(None, description="The small selection for tests.")
    full: Selection | None = Field(None, description="The real inputs; the default.")

    @model_validator(mode="after")
    def _selects_in_one_place(self) -> Collection:
        variants = self.variants()
        mixed = [key for key in _SELECTING if key in self.model_fields_set]
        if variants and mixed:
            raise ValueError(
                f"{', '.join(mixed)} at the top level and also the variant(s) "
                f"{', '.join(variants)}; move every selection key inside "
                f"{' / '.join(f'{v}:' for v in k.VARIANTS)}"
            )
        return self

    def variants(self) -> tuple[str, ...]:
        """The variants this collection defines, ``test`` first; empty for a plain one."""
        return tuple(v for v in k.VARIANTS if getattr(self, v) is not None)


def _bound(description: str) -> object:
    return Field(
        None, description=description, json_schema_extra={"pattern": BOUND_PATTERN}
    )


class CatalogBounds(_Part):
    """The catalogue releases a package works with: one exactly, or a range.

    Each version is a release, ``v1.2.0``, or a prefix of one, ``v1.3`` or
    ``v1``: as ``min_version`` its first release, as ``max_version`` its last,
    as ``exact_version`` every one of them.
    """

    min_version: str | None = _bound("The oldest release the package was tested with.")
    max_version: str | None = _bound("Refuse anything newer.")
    exact_version: str | None = _bound("The release, or the releases, to resolve to.")

    @field_validator(k.MIN_VERSION, k.MAX_VERSION, k.EXACT_VERSION)
    @classmethod
    def _a_release(cls, value: str | None) -> str | None:
        if value is not None:
            Prefix.parse(value)
        return value

    @model_validator(mode="after")
    def _consistent(self) -> CatalogBounds:
        self.bounds()
        return self

    def bounds(self) -> Bounds:
        """The bounds these keys set."""
        return Bounds.from_document(self.model_dump(exclude_none=True))


class CollectionsFile(_Part):
    """The whole file: the catalogue releases it accepts and its collections."""

    catalog: CatalogBounds | None = Field(
        None, description="The catalogue releases the package works with."
    )
    collections: dict[str, Collection] = Field(
        {}, description="Collection name to definition."
    )


_SELECTION_KEYS = set(Selection.model_fields)
_COLLECTION_KEYS = set(Collection.model_fields)
_BOUND_KEYS = set(CatalogBounds.model_fields)


def lint(document: dict) -> list[str]:
    """Keys the format does not define, which are ignored and usually typos."""
    warnings = [
        f"{key} is not a key of collections.yaml; it is ignored"
        for key in document
        if key not in CollectionsFile.model_fields
    ]
    bounds = document.get("catalog")
    if isinstance(bounds, dict):
        warnings.extend(
            f"catalog.{key} is not a release bound"
            for key in bounds
            if key not in _BOUND_KEYS
        )
    for name, definition in (document.get("collections") or {}).items():
        if not isinstance(definition, dict):
            continue
        for key in definition:
            if key not in _COLLECTION_KEYS:
                warnings.append(
                    f"collections.{name}.{key} is not a key of a collection"
                )
        for variant in k.VARIANTS:
            body = definition.get(variant)
            if isinstance(body, dict):
                for key in body:
                    if key not in _SELECTION_KEYS:
                        warnings.append(
                            f"collections.{name}.{variant}.{key} is not a key of a variant"
                        )
    return warnings
