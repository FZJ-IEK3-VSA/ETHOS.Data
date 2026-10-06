"""Every format by name, its JSON Schema, and the templates of the files people write.

Two kinds of template, filled in by one engine: the files people write,
``templates/<name>.yaml``, and the handoffs between roles,
``templates/handoffs/<name>.md``.
"""

from __future__ import annotations

import json
import string
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from pydantic import BaseModel

from . import bundle
from . import keys as k
from .catalogue import CatalogMeta
from .collections_file import CollectionsFile
from .dataset import DatasetDescriptor, NamespaceDescriptor
from .fields import keys_with
from .package import CatalogIndex, PackageDescriptor, ShardFile
from .records import MaterializedRecord, StagingRegistry
from .settings_file import SettingsFile
from .status_file import StatusFile

__all__ = [
    "FORMATS",
    "Format",
    "handoff",
    "handoff_names",
    "placeholders",
    "schema",
    "schema_text",
    "schemas_dir",
    "template",
    "template_names",
    "write_schemas",
]


@dataclass(frozen=True)
class Format:
    """One standardized file: what it is called, who writes it, and its model."""

    name: str
    filename: str
    model: type[BaseModel]
    #: ``person`` for a file somebody writes by hand, ``tool`` for a generated one.
    written_by: str
    summary: str


FORMATS: dict[str, Format] = {
    f.name: f
    for f in (
        Format("dataset", "dataset.yaml", DatasetDescriptor, "person",
               "One dataset's description, in the source catalogue or a proposal."),
        Format("namespace", "dataset.yaml", NamespaceDescriptor, "person",
               "A family's description: a name and the keys its members inherit."),
        Format("catalog", "catalog.yaml", CatalogMeta, "person",
               "A source catalogue's name, contact and publication root."),
        Format("status", "status.yaml", StatusFile, "tool",
               "Where a dataset stands: its state, build input, copies and history."),
        Format("collections", "collections.yaml", CollectionsFile, "person",
               "A package's selection of catalogue data, by workflow."),
        Format("settings", "config.yaml", SettingsFile, "tool",
               "Where data lies on one machine, written by `config set-*`."),
        Format("datapackage", "datapackage.json", PackageDescriptor, "tool",
               "A dataset's generated descriptor and inventory."),
        Format("shard", "shards/<prefix>.json", ShardFile, "tool",
               "One shard of a sharded inventory."),
        Format("datacatalog", "datacatalog.json", CatalogIndex, "tool",
               "The generated index: catalog.yaml's keys and one row per dataset."),
        Format("bundle", bundle.FILENAME, bundle.BundleManifest, "tool",
               "What a bundle holds: its datasets, their alignment and changes."),
        Format("staging", k.STAGING_REGISTRY_FILE, StagingRegistry, "tool",
               "Who staged which directory, and why."),
        Format("materialized", k.MATERIALIZED_RECORD_FILE, MaterializedRecord, "tool",
               "Where a materialised cache entry was copied from."),
    )
}  # fmt: skip


def unpublished_keys() -> tuple[str, ...]:
    """Every key any format marks unpublished, each once, in registry order."""
    found: dict[str, None] = {}
    for fmt in FORMATS.values():
        for key in keys_with(fmt.model, "published", False):
            found.setdefault(key, None)
    return tuple(found)


def schema(name: str) -> dict:
    """The JSON Schema of a format, generated from its model."""
    spec = FORMATS[name]
    generated = spec.model.model_json_schema(by_alias=True)
    generated["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    generated["title"] = spec.filename
    generated["description"] = spec.summary
    return generated


def schemas_dir() -> Path:
    """Where the committed schemas live, beside this module."""
    return Path(__file__).with_name("schemas")


def schema_text(name: str) -> str:
    return json.dumps(schema(name), indent=2, ensure_ascii=False) + "\n"


def write_schemas(target: Path | None = None) -> list[Path]:
    """Write every format's schema to ``<target>/<name>.schema.json``; returns the paths."""
    directory = target or schemas_dir()
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name in FORMATS:
        path = directory / f"{name}.schema.json"
        path.write_text(schema_text(name), encoding="utf-8", newline="\n")
        written.append(path)
    return written


class _Template(string.Template):
    """Only ``${braced}`` names are placeholders.

    So the ``$schema`` of the yaml-language-server line, and any other dollar
    sign a template's prose or example values contain, is left as written.
    """

    pattern = r"""
    \$(?:
      (?P<escaped>(?!))                      |
      (?P<named>(?!))                        |
      {(?P<braced>[_a-z][_a-z0-9]*)}         |
      (?P<invalid>(?!))
    )
    """


def _names(folder: str, suffix: str) -> list[str]:
    found = resources.files(__package__).joinpath(*folder.split("/"))
    return sorted(
        entry.name.removesuffix(suffix)
        for entry in found.iterdir()
        if entry.name.endswith(suffix)
    )


def _text(folder: str, name: str, suffix: str) -> str:
    found = resources.files(__package__).joinpath(*folder.split("/"))
    return (found / f"{name}{suffix}").read_text(encoding="utf-8")


def template_names() -> list[str]:
    """The templates the package ships, without their ``.yaml`` suffix."""
    return _names("templates", ".yaml")


def _template_text(name: str) -> str:
    return _text("templates", name, ".yaml")


def template(template_name: str, /, **values: str) -> str:
    """A template's text with its ``${placeholders}`` filled in.

    Every placeholder the template names must be given; a template that would
    be written with a ``${...}`` left in it is a bug in the caller.
    """
    return _Template(_template_text(template_name)).substitute(values)


def handoff_names() -> list[str]:
    """The handoffs there are templates for, without their ``.md`` suffix."""
    return _names("templates/handoffs", ".md")


def handoff(handoff_name: str, /, **values: str) -> str:
    """A handoff's text with its ``${placeholders}`` filled in; every one must be given."""
    return _Template(_text("templates/handoffs", handoff_name, ".md")).substitute(
        values
    )


def placeholders(template_name: str) -> set[str]:
    """The names a template expects, for callers and tests."""
    return {
        match.group("braced")
        for match in _Template.pattern.finditer(_template_text(template_name))
        if match.group("braced")
    }
