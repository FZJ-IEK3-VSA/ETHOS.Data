"""Every format by name, its JSON Schema, and the templates of the files people write."""

from __future__ import annotations

import json
import string
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from pydantic import BaseModel

from . import keys as k
from .bundle import BundleManifest
from .catalogue import CatalogMeta
from .collections_file import CollectionsFile
from .dataset import DatasetDescriptor, NamespaceDescriptor
from .package import CatalogIndex, PackageDescriptor, ShardFile
from .records import MaterializedRecord, StagingRegistry
from .settings_file import SettingsFile

__all__ = [
    "FORMATS",
    "Format",
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
        Format("bundle", "bundle.json", BundleManifest, "tool",
               "A repository copy of catalogue data."),
        Format("staging", k.STAGING_REGISTRY_FILE, StagingRegistry, "tool",
               "Who staged which directory, and why."),
        Format("materialized", k.MATERIALIZED_RECORD_FILE, MaterializedRecord, "tool",
               "Where a materialised cache entry was copied from."),
    )
}  # fmt: skip


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


def template_names() -> list[str]:
    """The templates the package ships, without their ``.yaml`` suffix."""
    folder = resources.files(__package__) / "templates"
    return sorted(
        entry.name.removesuffix(".yaml")
        for entry in folder.iterdir()
        if entry.name.endswith(".yaml")
    )


def _template_text(name: str) -> str:
    folder = resources.files(__package__) / "templates"
    return (folder / f"{name}.yaml").read_text(encoding="utf-8")


def template(template_name: str, /, **values: str) -> str:
    """A template's text with its ``${placeholders}`` filled in.

    Every placeholder the template names must be given; a template that would
    be written with a ``${...}`` left in it is a bug in the caller.
    """
    return _Template(_template_text(template_name)).substitute(values)


def placeholders(template_name: str) -> set[str]:
    """The names a template expects, for callers and tests."""
    return {
        match.group("braced")
        for match in _Template.pattern.finditer(_template_text(template_name))
        if match.group("braced")
    }
