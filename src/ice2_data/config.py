"""Where the shared cache lives, and how that gets decided.

The cache location is resolved from several sources so that it can be set once
and then forgotten -- per user, per environment, or site-wide -- while still
being overridable for a single job. First match wins:

    1. an explicit argument        fetch(..., root=...) / --root
    2. $ICE2_DATA_DIR              per-shell, per-SLURM-job, CI
    3. project file                ./ice2-data.yaml, searched upward from the cwd
    4. user config                 per-user config directory (all platforms)
    5. environment config          <sys.prefix>/etc/ice2-data/config.yaml
    6. site config                 machine-wide config directory
    7. built-in default            the per-user OS cache directory

Nothing has to be configured: layer 7 works on Linux, macOS and Windows alike.

Layer 3 is for people who want the setting to be *visible*. It is an ordinary
file sitting next to the work it belongs to, found by walking up from the
current directory the way git finds .git, and it can be committed so a whole
team shares one answer.

Every lookup records *where* the value came from, because "why is my data going
there?" is the question people actually ask.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import platformdirs
import yaml

__all__ = [
    "SCOPES",
    "dataset_roots",
    "set_dataset_root",
    "unset_dataset_root",
    "CONFIG_FILENAME",
    "ENV_VAR",
    "Resolved",
    "config_path",
    "find_project_config",
    "writable_config_path",
    "config_sources",
    "load_config",
    "resolve_cache_dir",
    "resolve_catalog",
    "resolve_collections",
    "resolve_publication_url",
    "set_option",
    "unset_option",
]

ENV_VAR = "ICE2_DATA_DIR"
CONFIG_FILENAME = "config.yaml"
PROJECT_FILENAME = "ice2-data.yaml"
APP = "ice2-data"

#: Config scopes, highest precedence first.
SCOPES = ("project", "user", "environment", "site")


@dataclass(frozen=True)
class Resolved:
    """A resolved setting plus a human-readable account of where it came from."""

    value: Path
    source: str

    def __str__(self) -> str:
        return f"{self.value}  (from {self.source})"


def find_project_config(start: Path | None = None) -> Path | None:
    """Nearest ice2-data.yaml at or above ``start`` (default: the cwd).

    Searched the way git finds .git, so it works from anywhere inside a project.
    """
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / PROJECT_FILENAME
        if candidate.is_file():
            return candidate
    return None


def config_path(scope: str = "user") -> Path:
    """Location of the config file for a given scope.

    For the project scope this is the file that would be *written* -- one in the
    current directory. Reading uses find_project_config(), which searches upward.
    """
    if scope == "project":
        return Path.cwd() / PROJECT_FILENAME
    if scope == "user":
        return Path(platformdirs.user_config_dir(APP)) / CONFIG_FILENAME
    if scope == "environment":
        return Path(sys.prefix) / "etc" / APP / CONFIG_FILENAME
    if scope == "site":
        return Path(platformdirs.site_config_dir(APP)) / CONFIG_FILENAME
    raise ValueError(f"unknown scope {scope!r}; expected one of {', '.join(SCOPES)}")


def writable_config_path(scope: str = "user") -> Path:
    """The file a write should land in.

    For the project scope, update an existing ice2-data.yaml found above the cwd
    rather than shadowing it with a second one in a subdirectory.
    """
    if scope == "project":
        return find_project_config() or config_path("project")
    return config_path(scope)


def config_sources() -> list[tuple[str, Path, bool]]:
    """Every config file we consult, in precedence order, with existence flags."""
    sources = []
    for scope in SCOPES:
        if scope == "project":
            found = find_project_config()
            sources.append((scope, found or config_path(scope), found is not None))
        else:
            path = config_path(scope)
            sources.append((scope, path, path.is_file()))
    return sources


#: Settings merged entry-by-entry rather than replaced wholesale. A site-wide
#: dataset_roots must survive a user adding one root of their own.
MERGED_KEYS = ("dataset_roots",)


def load_config() -> tuple[dict, dict[str, str]]:
    """Merge the config files. Returns (settings, provenance per key)."""
    merged: dict = {}
    origin: dict[str, str] = {}
    # Reverse order so that higher-precedence scopes overwrite lower ones.
    for scope, path, exists in reversed(config_sources()):
        if not exists:
            continue
        try:
            document = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as error:
            raise ValueError(f"{path} is not valid YAML: {error}") from None
        if not isinstance(document, dict):
            raise ValueError(f"{path} must contain a YAML mapping, got {type(document).__name__}")
        for key, value in document.items():
            if key in MERGED_KEYS and isinstance(value, dict):
                combined = dict(merged.get(key) or {})
                combined.update(value)
                merged[key] = combined
                for entry in value:
                    origin[f"{key}.{entry}"] = f"{scope} config {path}"
            else:
                merged[key] = value
            origin[key] = f"{scope} config {path}"
    return merged, origin


def resolve_cache_dir(explicit: str | Path | None = None) -> Resolved:
    """Work out the cache directory and say where the answer came from."""
    if explicit is not None:
        return Resolved(Path(explicit).expanduser(), "explicit argument")

    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Resolved(Path(from_env).expanduser(), f"${ENV_VAR}")

    settings, origin = load_config()
    if settings.get("cache_dir"):
        return Resolved(Path(str(settings["cache_dir"])).expanduser(), origin["cache_dir"])

    return Resolved(Path(platformdirs.user_cache_dir(APP)), "built-in default (OS cache directory)")


def dataset_roots() -> dict[str, str]:
    """Per-dataset local roots for this machine.

    A dataset listed here is read where it lies and never downloaded -- used for
    licensed data, for data staged centrally on the HPC, and for data that has
    simply not been uploaded yet.
    """
    settings, _ = load_config()
    roots = settings.get("dataset_roots") or {}
    if not isinstance(roots, dict):
        raise ValueError("dataset_roots must be a mapping of dataset name -> path")
    return {str(k): str(v) for k, v in roots.items()}


def set_dataset_root(dataset: str, path: str, scope: str = "user") -> Path:
    config_file = writable_config_path(scope)
    document = yaml.safe_load(config_file.read_text()) if config_file.is_file() else {}
    document = document or {}
    document.setdefault("dataset_roots", {})[dataset] = str(Path(path).expanduser())
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        "# ice2-data configuration. See `ice2-data config show`.\n"
        + yaml.safe_dump(document, default_flow_style=False, sort_keys=True)
    )
    return config_file


def unset_dataset_root(dataset: str, scope: str = "user") -> Path | None:
    config_file = writable_config_path(scope)
    if not config_file.is_file():
        return None
    document = yaml.safe_load(config_file.read_text()) or {}
    if dataset not in (document.get("dataset_roots") or {}):
        return None
    del document["dataset_roots"][dataset]
    if not document["dataset_roots"]:
        del document["dataset_roots"]
    if document:
        config_file.write_text(
            "# ice2-data configuration. See `ice2-data config show`.\n"
            + yaml.safe_dump(document, default_flow_style=False, sort_keys=True)
        )
    else:
        config_file.unlink()
    return config_file


def resolve_publication_url(catalog_default: str = "") -> tuple[str, str]:
    """Where to fetch bytes from, allowing a site override of the catalogue value.

    The catalogue names DESY's compatible, redirect-free door, which is right for
    anonymous public users. CI and bulk transfers want the high-throughput door
    instead -- uncapped, but it redirects to a pool host on a high port, so it
    needs an environment that permits outbound connections there.
    """
    # Deliberately NOT a Path: pathlib collapses the "//" in "https://host".
    from_env = os.environ.get("ICE2_PUBLICATION_URL")
    if from_env:
        return from_env, "$ICE2_PUBLICATION_URL"
    settings, origin = load_config()
    if settings.get("publication_url"):
        return str(settings["publication_url"]), origin["publication_url"]
    return catalog_default, "catalogue"


def resolve_catalog(explicit: str | None = None) -> tuple[str, str] | None:
    """Optional default catalogue location, resolved the same way as cache_dir.

    Returns ``None`` if nothing is configured, so a caller falls back to
    whatever a collections.yaml pins for itself via its own ``catalog:`` key.

    Deliberately returns a plain string rather than a ``Resolved`` -- a
    catalogue location is as often an http(s) URL as a local path, and
    ``pathlib.Path`` collapses the "//" in "https://", which would silently
    corrupt it (see resolve_publication_url for the same issue).
    """
    if explicit:
        return explicit, "explicit argument"
    settings, origin = load_config()
    catalog = settings.get("catalog")
    if not catalog:
        return None
    catalog = str(catalog)
    if not catalog.startswith(("http://", "https://")):
        catalog = str(Path(catalog).expanduser())
    return catalog, origin["catalog"]


def resolve_collections(explicit: str | None = None) -> tuple[str, str] | None:
    """Optional default collections-file location, same precedence as catalog.

    Unlike a catalogue, a collections file is always local -- there is no
    URL form -- so this always resolves to a filesystem path.
    """
    if explicit:
        return explicit, "explicit argument"
    settings, origin = load_config()
    collections = settings.get("collections")
    if not collections:
        return None
    return str(Path(str(collections)).expanduser()), origin["collections"]


def set_option(key: str, value: str, scope: str = "user") -> Path:
    """Write one setting into the config file for a scope."""
    path = writable_config_path(scope)
    document = {}
    if path.is_file():
        document = yaml.safe_load(path.read_text()) or {}
    document[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# ice2-data configuration. See `ice2-data config show`.\n"
        + yaml.safe_dump(document, default_flow_style=False, sort_keys=True)
    )
    return path


def unset_option(key: str, scope: str = "user") -> Path | None:
    path = writable_config_path(scope)
    if not path.is_file():
        return None
    document = yaml.safe_load(path.read_text()) or {}
    if key not in document:
        return None
    del document[key]
    if document:
        path.write_text(
            "# ice2-data configuration. See `ice2-data config show`.\n"
            + yaml.safe_dump(document, default_flow_style=False, sort_keys=True)
        )
    else:
        path.unlink()
    return path
