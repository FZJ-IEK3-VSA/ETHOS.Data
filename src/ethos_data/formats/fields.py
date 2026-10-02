"""How a field of a specification says what the tools do with it.

Four properties, read by the code that would otherwise keep its own list:

``published``    ``publish`` keeps the key; without it the key is stripped from
                 the public catalogue (and the leak check looks for it there)
``promoted``     ``build`` copies the key into the dataset's index row, so a
                 reader answers it without loading the descriptor
``user_facing``  printed by ``--meta``, and by the error for a licensed dataset
                 this machine cannot read
``inherited``    a member of a family takes it from the family's
                 ``dataset.yaml`` when it does not set the key itself

They travel in the JSON Schema too, under ``x-ethos``, so a reader of a schema
sees them where it sees the type.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

PROPERTIES = ("published", "promoted", "user_facing", "inherited")


def field(
    alias: str,
    default: Any = None,
    *,
    description: str = "",
    published: bool = True,
    promoted: bool = False,
    user_facing: bool = False,
    inherited: bool = False,
    schema: dict | None = None,
    **kwargs: Any,
) -> Any:
    """A pydantic ``Field`` under the key ``alias``, carrying the four properties."""
    extra: dict[str, Any] = {
        "x-ethos": {
            "published": published,
            "promoted": promoted,
            "user_facing": user_facing,
            "inherited": inherited,
        }
    }
    if schema:
        extra.update(schema)
    return Field(
        default,
        alias=alias,
        description=description,
        json_schema_extra=extra,
        **kwargs,
    )


def properties(model: type[BaseModel], key: str) -> dict[str, bool]:
    """The four properties of the field written ``key`` in a file."""
    for name, info in model.model_fields.items():
        if (info.alias or name) == key:
            extra = info.json_schema_extra
            if isinstance(extra, dict) and isinstance(extra.get("x-ethos"), dict):
                return dict(extra["x-ethos"])
            return dict.fromkeys(PROPERTIES, False) | {"published": True}
    raise KeyError(f"{model.__name__} has no field {key!r}")


def keys_with(model: type[BaseModel], prop: str, value: bool = True) -> tuple[str, ...]:
    """Every key of ``model`` whose property ``prop`` is ``value``, in declaration order."""
    if prop not in PROPERTIES:
        raise ValueError(f"unknown property {prop!r}; one of {PROPERTIES}")
    return tuple(
        info.alias or name
        for name, info in model.model_fields.items()
        if properties(model, info.alias or name)[prop] is value
    )


def keys(model: type[BaseModel]) -> tuple[str, ...]:
    """Every key ``model`` declares, as written in a file."""
    return tuple(info.alias or name for name, info in model.model_fields.items())
