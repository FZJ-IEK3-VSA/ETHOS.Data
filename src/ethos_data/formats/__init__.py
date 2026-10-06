"""Every file format of ETHOS.Data, specified once.

One specification per standardized file, written as a pydantic model, with
the templates for the files people write and the JSON Schemas generated from
the models. See the decision record "Every file format is specified once".

    from ethos_data import formats

    formats.FORMATS["dataset"].model          # the pydantic model
    formats.template("dataset-minimal", name="x", description="y")
    formats.schema("dataset")                 # the JSON Schema, as a dict
    formats.dataset.check(meta)               # the rules the build enforces
    formats.dataset.lint(meta)                # what the structure adds, as warnings
    formats.index_row(package, path)          # one dataset's datacatalog.json row

The schemas are committed under ``schemas/`` so editors can point at them; a
test fails when one is out of date, and ``python -m ethos_data.formats``
rewrites them.

Importing this package is cheap: :mod:`.keys` and :mod:`.derived` need no
pydantic and load at once, and everything else loads the first time it is
used, so a command that never validates a file never pays for the models.
"""

from __future__ import annotations

import importlib
from typing import Any

from . import derived, keys
from .derived import index_row, license_settled, license_status_of, remote_prefix_of

#: Name -> (module, attribute or None for the module itself).
_LAZY: dict[str, tuple[str, str | None]] = {
    "bundle": (".bundle", None),
    "catalogue": (".catalogue", None),
    "collections_file": (".collections_file", None),
    "dataset": (".dataset", None),
    "package": (".package", None),
    "records": (".records", None),
    "registry": (".registry", None),
    "settings_file": (".settings_file", None),
    "status_file": (".status_file", None),
    "BundleManifest": (".bundle", "BundleManifest"),
    "CatalogIndex": (".package", "CatalogIndex"),
    "CatalogMeta": (".catalogue", "CatalogMeta"),
    "CollectionsFile": (".collections_file", "CollectionsFile"),
    "DatasetDescriptor": (".dataset", "DatasetDescriptor"),
    "MaterializedRecord": (".records", "MaterializedRecord"),
    "NamespaceDescriptor": (".dataset", "NamespaceDescriptor"),
    "PackageDescriptor": (".package", "PackageDescriptor"),
    "SettingsFile": (".settings_file", "SettingsFile"),
    "ShardFile": (".package", "ShardFile"),
    "StatusFile": (".status_file", "StatusFile"),
    "StagingRegistry": (".records", "StagingRegistry"),
    "FORMATS": (".registry", "FORMATS"),
    "Format": (".registry", "Format"),
    "placeholders": (".registry", "placeholders"),
    "schema": (".registry", "schema"),
    "schema_text": (".registry", "schema_text"),
    "schemas_dir": (".registry", "schemas_dir"),
    "template": (".registry", "template"),
    "template_names": (".registry", "template_names"),
    "write_schemas": (".registry", "write_schemas"),
}

__all__ = [
    "FORMATS",
    "BundleManifest",
    "CatalogIndex",
    "CatalogMeta",
    "CollectionsFile",
    "DatasetDescriptor",
    "Format",
    "MaterializedRecord",
    "NamespaceDescriptor",
    "PackageDescriptor",
    "SettingsFile",
    "ShardFile",
    "StagingRegistry",
    "StatusFile",
    "bundle",
    "catalogue",
    "collections_file",
    "dataset",
    "derived",
    "index_row",
    "keys",
    "license_settled",
    "license_status_of",
    "package",
    "placeholders",
    "records",
    "registry",
    "remote_prefix_of",
    "schema",
    "schema_text",
    "schemas_dir",
    "settings_file",
    "status_file",
    "template",
    "template_names",
    "write_schemas",
]
assert set(__all__) == set(_LAZY) | {
    "derived",
    "index_row",
    "keys",
    "license_settled",
    "license_status_of",
    "remote_prefix_of",
}, "every lazy name is exported, and nothing else"


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _LAZY[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    module = importlib.import_module(module_name, __name__)
    value = module if attribute is None else getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
