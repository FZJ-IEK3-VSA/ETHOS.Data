"""The reference tables of File formats, rendered from the specifications.

    from ethos_data.formats import reference

    reference.table("dataset")            # a format's keys, as a Markdown table
    reference.table("package:IndexRow")   # a part of one, by its model
    reference.formats()                   # every format: file, writer, schema
    reference.states(), reference.steps() # the lifecycle status.yaml records

A key's type, default and description are written once, in its model; the
tables are made from the model's JSON Schema, so they say what the schemas
say. The documentation renders them when it is built (``docs/hooks/formats.py``
and :func:`render`), which is why they cannot drift from the code.

Nested parts are flattened into the table with the paths a reader writes:
``licenses[].name`` for a key of each list entry, ``ethos:embargo.until`` for
a key of a mapping, ``collections.<name>.title`` for a key under any name. A
part met a second time is not spelled out again; its row points at the first.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from ..model.versions import BOUND_PATTERN, RELEASE_PATTERN
from .registry import FORMATS, schema

__all__ = ["formats", "render", "states", "steps", "table"]

#: Where the committed schemas are served, for links to them.
SCHEMA_URL = (
    "https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data/main/"
    "src/ethos_data/formats/schemas/{name}.schema.json"
)

#: How a field's four properties read in a table, when they differ from the default.
_PROPERTIES = (
    ("published", False, "Never published."),
    ("promoted", True, "In the index row."),
    ("user_facing", True, "Shown to users."),
    ("inherited", True, "Inherited from the family."),
)


@dataclass(frozen=True)
class _Row:
    key: str
    type: str
    default: str
    text: str


def table(spec: str | type[BaseModel]) -> str:
    """The keys of a format, or of a model of one, as a Markdown table.

    ``spec`` is a format's name from :data:`~.registry.FORMATS`, a model, or
    ``"<module>:<Class>"`` naming a model in this package, such as
    ``"package:IndexRow"``.
    """
    document = _schema_of(spec)
    walk = _Walk(document.get("$defs", {}))
    rows = list(walk.rows(document, ""))
    lines = ["| Key | Type | Default | Description |", "|---|---|---|---|"]
    lines += [
        f"| `{row.key}` | {_cell(row.type)} | {_cell(row.default)} | {_cell(row.text)} |"
        for row in rows
    ]
    return "\n".join(lines) + "\n"


def formats() -> str:
    """Every format the package specifies: its file, who writes it, its schema."""
    lines = ["| File | Written by | | Schema |", "|---|---|---|---|"]
    for spec in FORMATS.values():
        writer = "a person" if spec.written_by == "person" else "the tools"
        name = f"{spec.name}.schema.json"
        link = f"[`{name}`]({SCHEMA_URL.format(name=spec.name)})"
        lines.append(
            f"| `{spec.filename}` | {writer} | {_cell(spec.summary)} | {link} |"
        )
    return "\n".join(lines) + "\n"


def states() -> str:
    """The states of a dataset, what each means, and the steps that lead into it."""
    from ..model import lifecycle

    lines = ["| State | Means | Reached by |", "|---|---|---|"]
    for state in lifecycle.STATES:
        into = (
            ["`add`, which writes the first status file"]
            if state == lifecycle.DRAFT
            else []
        )
        by_origin: dict[tuple[str, ...], list[str]] = {}
        for step in lifecycle.STEPS.values():
            before = tuple(
                each
                for each in lifecycle.STATES
                if step.leads.get(each) == state and each != state
            )
            if before:
                by_origin.setdefault(before, []).append(step.name)
        for before, names in by_origin.items():
            into.append(f"{_names(names)} from {_names(list(before))}")
        lines.append(
            f"| `{state}` | {_cell(lifecycle.MEANING[state])} | {'; '.join(into)} |"
        )
    return "\n".join(lines) + "\n"


def steps() -> str:
    """Every step a command takes, the states it is allowed in, and where it leads."""
    from ..model import lifecycle

    lines = ["| Step | Command | Allowed in | Leads to |", "|---|---|---|---|"]
    for step in lifecycle.STEPS.values():
        allowed = [state for state in lifecycle.STATES if step.allows(state)]
        by_target: dict[str, list[str]] = {}
        for state in allowed:
            if step.leads[state] != state:
                by_target.setdefault(step.leads[state], []).append(state)
        moves = [
            f"{_names(before)} → `{target}`" for target, before in by_target.items()
        ]
        if any(step.leads[state] == state for state in allowed):
            moves.append("otherwise the same state" if moves else "the same state")
        lines.append(
            f"| `{step.name}` | `{step.command}` | {_names(allowed)} | {', '.join(moves)} |"
        )
    return "\n".join(lines) + "\n"


def render(what: str, argument: str | None = None) -> str:
    """One generated block, by the name a documentation page asks for it with.

    ``table <spec>``, ``formats``, ``states`` or ``steps``; see the functions
    of the same names. Raises :class:`ValueError` for anything else.
    """
    if what == "table":
        if not argument:
            raise ValueError("`table` needs a format or a model, as in `table dataset`")
        return table(argument)
    blocks = {"formats": formats, "states": states, "steps": steps}
    if what not in blocks or argument:
        raise ValueError(
            f"unknown block {' '.join(filter(None, (what, argument)))!r}; one of "
            "`table <format>`, `formats`, `states`, `steps`"
        )
    return blocks[what]()


# -- the walk over a schema -----------------------------------------------------------


class _Walk:
    """One table's rows; remembers which parts it has spelled out, and where."""

    def __init__(self, definitions: dict[str, Any]) -> None:
        self.definitions = definitions
        self.spelled: dict[str, str] = {}

    def rows(self, node: dict[str, Any], prefix: str) -> Iterator[_Row]:
        required = set(node.get("required", ()))
        properties = node.get("properties") or {}
        if not properties and isinstance(node.get("additionalProperties"), dict):
            # A file that is one mapping of names, as the staging registry.
            yield from self._children(node, prefix.rstrip("."))
            return
        for key, prop in properties.items():
            path = f"{prefix}{key}"
            yield _Row(
                path,
                self._type(prop, path),
                "required" if key in required else _default(prop),
                self._text(prop),
            )
            yield from self._children(prop, path)

    def _children(self, prop: dict[str, Any], path: str) -> Iterator[_Row]:
        for suffix, reference in _parts(prop):
            if reference in self.spelled:
                continue
            # At the top of a file that is one mapping, the names come first.
            prefix = f"{path}{suffix}".lstrip(".")
            self.spelled[reference] = prefix.removesuffix(".")
            yield from self.rows(self.definitions[reference], prefix)

    def _type(self, prop: dict[str, Any], path: str) -> str:
        """The type in words; a part spelled out elsewhere says where."""
        described = _type(prop)
        for suffix, reference in _parts(prop):
            first = self.spelled.get(reference)
            here = f"{path}{suffix}".removesuffix(".")
            if first is not None and first != here:
                return f"{described}, as `{first}`"
        return described

    def _text(self, prop: dict[str, Any]) -> str:
        text = prop.get("description") or ""
        if not text:
            for _, reference in _parts(prop):
                text = self.definitions[reference].get("description") or ""
                break
        text = " ".join(_rst_to_markdown(text).split())
        properties = prop.get("x-ethos") or {}
        tags = [
            tag
            for name, value, tag in _PROPERTIES
            if name in properties and properties[name] is value
        ]
        if tags:
            text = f"{text} *{' '.join(tags)}*".strip()
        return text


def _parts(prop: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """The nested parts ``prop`` holds: (path suffix, definition name) pairs."""
    reference = prop.get("$ref")
    if reference:
        yield ".", _definition(reference)
        return
    for alternative in [*prop.get("anyOf", ()), *prop.get("allOf", ())]:
        yield from _parts(alternative)
    items = prop.get("items")
    if isinstance(items, dict):
        for suffix, name in _parts(items):
            yield f"[]{suffix}", name
    extra = prop.get("additionalProperties")
    if isinstance(extra, dict):
        for suffix, name in _parts(extra):
            yield f".<name>{suffix}", name


def _definition(reference: str) -> str:
    return reference.rsplit("/", 1)[-1]


def _type(prop: dict[str, Any]) -> str:
    if "enum" in prop:
        return _names(prop["enum"], "or")
    if "const" in prop:
        return f"`{prop['const']}`"
    if "$ref" in prop:
        return "mapping"
    alternatives = [
        option
        for option in [*prop.get("anyOf", ()), *prop.get("allOf", ())]
        if option.get("type") != "null"
    ]
    if alternatives:
        kinds = []
        for option in alternatives:
            kind = _type(option | {k: v for k, v in prop.items() if k == "pattern"})
            if kind not in kinds:
                kinds.append(kind)
        if "integer" in kinds and "number" in kinds:
            kinds.remove("integer")
        return " or ".join(kinds)
    kind = prop.get("type")
    if kind == "array":
        items = prop.get("items") or {}
        if "enum" in items:
            return f"list, each {_names(items['enum'], 'or')}"
        return f"list of {_plural(_type(items))}" if items else "list"
    if kind == "object":
        extra = prop.get("additionalProperties")
        if isinstance(extra, dict) and extra:
            return f"mapping of name to {_type(extra)}"
        return "mapping"
    if kind == "string" and prop.get("pattern") == RELEASE_PATTERN:
        return "`vMAJOR.MINOR.PATCH`"
    if kind == "string" and prop.get("pattern") == BOUND_PATTERN:
        return "`vMAJOR.MINOR.PATCH`, or a prefix: `vMAJOR`, `vMAJOR.MINOR`"
    return {"string": "string", "integer": "integer", "number": "number",
            "boolean": "boolean"}.get(kind, "any")  # fmt: skip


def _plural(kind: str) -> str:
    if kind in ("string", "integer", "number", "boolean", "mapping"):
        return f"{kind}s"
    return f"{kind} values"


def _default(prop: dict[str, Any]) -> str:
    if "default" not in prop:
        return ""
    value = prop["default"]
    if value is None or value == [] or value == {} or value == "":
        return ""
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    return f"`{value}`"


def _names(values: list, last: str = "or") -> str:
    quoted = [f"`{value}`" for value in values]
    if len(quoted) <= 2:
        return f" {last} ".join(quoted)
    return f"{', '.join(quoted[:-1])} {last} {quoted[-1]}"


def _rst_to_markdown(text: str) -> str:
    """Docstrings use reST's double backticks; a table cell wants Markdown's single ones."""
    return text.replace("``", "`")


_CODE = re.compile(r"(`[^`]*`)")


def _cell(text: str) -> str:
    """Text safe in a table cell: no pipe ends the cell, no ``<name>`` reads as HTML."""
    parts = _CODE.split(text)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            part = part.replace("<", "&lt;").replace(">", "&gt;")
        parts[index] = part.replace("|", "\\|")
    return "".join(parts)


def _schema_of(spec: str | type[BaseModel]) -> dict[str, Any]:
    if _is_model(spec):
        return spec.model_json_schema(by_alias=True)
    if spec in FORMATS:
        return schema(spec)
    module_name, _, class_name = str(spec).partition(":")
    if not class_name:
        raise ValueError(
            f"unknown format {spec!r}; one of {', '.join(FORMATS)}, or "
            "`<module>:<Class>` for a model of one"
        )
    try:
        module = importlib.import_module(f".{module_name}", __package__)
    except ImportError:
        module = None
    model = getattr(module, class_name, None)
    if _is_model(model):
        return model.model_json_schema(by_alias=True)
    raise ValueError(f"no model {class_name} in ethos_data.formats.{module_name}")


def _is_model(candidate: object) -> bool:
    return isinstance(candidate, type) and issubclass(candidate, BaseModel)
