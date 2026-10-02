"""Where the caches and the catalogue are, for one person on one machine.

There are three roots, and a user is expected to set at most two of them:

    public_cache       public and internal data -- a namespace of symbolic
                       links to data already on this machine, plus real
                       directories for anything downloaded from dCache
    restricted_cache   licensed data, held as real files we own and can make
                       read-only; never downloaded, never written to
    staging_cache      optional: work in progress that is not in the catalogue
                       yet, shadowing it during development

Deliberately *not* one setting per dataset. A cache shared by a whole institute
has to be configurable in one line, or people will not configure it at all.
Which root a dataset comes from follows from its access class, and whether it is
read in place follows from whether its entry in the root is a symbolic link --
both facts already available without anybody writing them down.

``dataset_roots`` survives as a per-dataset escape hatch for somebody working
offline from a private copy. Normal users never touch it.

Each setting is resolved from the first of:

    1. an explicit argument        fetch(..., root=...) / --root, catalog= / --catalog
    2. an environment variable     $ETHOS_DATA_DIR, $ETHOS_RESTRICTED_DIR, ...
    3. the settings file           the file $ETHOS_DATA_CONFIG names, else the
                                   one in the account
    4. the built-in default        the per-user cache directory (public cache only)

One file, in the account, because a script has to find the same settings however
it is started: from its own folder or another, from an editor, a notebook or a
batch job, in whichever Python environment. Earlier releases also read an
``ethos-data.yaml`` found from the working directory, a file inside the Python
environment and a machine-wide file. Each of them depended on something other
than the person and the machine, so they are ignored now, and ``config show``
names any it finds. ``$ETHOS_DATA_CONFIG`` replaces the account's file rather
than merging with it, so a CI job or a test run is isolated from the account it
runs under.

Nothing has to be configured for public data: layer 4 works on Linux, macOS and
Windows alike. The restricted and staging roots have *no* built-in default on
purpose -- where licensed bytes land is a decision somebody has to make out
loud, and staging is opt-in by nature.

Every lookup records *where* the value came from, because "why is my data going
there?" is the question people actually ask. :class:`Settings` is all of them,
read once; it is what a handle keeps for the life of a script.
"""

from __future__ import annotations

import getpass
import os
import stat
import sys
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

import platformdirs
import yaml

from .errors import ConfigurationError
from .formats import keys as k

__all__ = [
    "dataset_roots",
    "set_dataset_root",
    "unset_dataset_root",
    "CONFIG_ENV_VAR",
    "CONFIG_FILENAME",
    "ENV_VAR",
    "RESTRICTED_ENV_VAR",
    "STAGING_ENV_VAR",
    "PUBLIC_CACHE_KEY",
    "LEGACY_CACHE_KEY",
    "RESTRICTED_CACHE_KEY",
    "STAGING_CACHE_KEY",
    "Resolved",
    "Roots",
    "Settings",
    "account_config_path",
    "catalog_index",
    "config_path",
    "ignored_config_files",
    "load_config",
    "read_settings",
    "resolve_cache_dir",
    "resolve_public_cache",
    "resolve_restricted_cache",
    "resolve_staging_cache",
    "resolve_roots",
    "resolve_catalog",
    "resolve_collections",
    "resolve_publication_url",
    "set_option",
    "unset_option",
    "unreachable",
    "CATALOG_ENV_VAR",
    "DEFAULT_CATALOG",
    "PUBLIC_RELEASE_URL",
]

#: The public catalogue, used whenever nothing else names one -- so that public
#: data needs no configuration at all. It follows a moving branch; a package
#: that must resolve to the same bytes release after release pins a version in
#: its own collections file instead.
DEFAULT_CATALOG = "https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/main/datacatalog.json"
#: Where the public catalogue keeps one release: the tag of that release.
PUBLIC_RELEASE_URL = "https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/{version}/datacatalog.json"
#: Point every tool in one shell or job at another catalogue -- the internal one,
#: say -- without editing a file. Wins over the settings file and over the
#: version a collections file pins; an explicit ``catalog=`` / ``--catalog``
#: wins over it. One variable for every package, where each used to need its own.
CATALOG_ENV_VAR = "ETHOS_DATA_CATALOG"
#: A settings file to read instead of the one in the account -- for a CI job, a
#: container, a lesson, or a team's file on a shared machine. Replaces the
#: account's file; nothing is merged.
CONFIG_ENV_VAR = "ETHOS_DATA_CONFIG"

#: The public cache. Named for the era when there was only one root; kept
#: because it is in scripts, job files and people's shell profiles.
ENV_VAR = "ETHOS_DATA_DIR"
RESTRICTED_ENV_VAR = "ETHOS_RESTRICTED_DIR"
STAGING_ENV_VAR = "ETHOS_STAGING_DIR"
PUBLICATION_URL_ENV_VAR = "ETHOS_PUBLICATION_URL"

PUBLIC_CACHE_KEY = "public_cache"
#: What ``public_cache`` used to be called. Still read, so an existing settings
#: file keeps working; ``config set-cache`` writes ``public_cache``.
LEGACY_CACHE_KEY = "cache_dir"
RESTRICTED_CACHE_KEY = "restricted_cache"
STAGING_CACHE_KEY = "staging_cache"
CATALOG_KEY = "catalog"
PUBLICATION_URL_KEY = "publication_url"
DATASET_ROOTS_KEY = "dataset_roots"
#: Settings earlier releases read and this one ignores, with why. A workflow
#: cannot run without one of its inputs, so nothing lets it leave one out.
RETIRED_KEYS = {"skip_unavailable": "every input is required"}
RETIRED_ENV_VARS = {"ETHOS_SKIP_UNAVAILABLE": "every input is required"}

CONFIG_FILENAME = "config.yaml"
APP = "ethos-data"
#: The project file earlier releases searched for upward from the working
#: directory; looked for only to say that it is ignored.
_PROJECT_FILENAME = "ethos-data.yaml"

#: Where the account's settings file is, the source a value read from it names.
ACCOUNT = "your account"


@dataclass(frozen=True)
class Resolved:
    """A resolved setting plus a human-readable account of where it came from."""

    value: Path
    source: str

    def __str__(self) -> str:
        return f"{self.value}  (from {self.source})"


@dataclass(frozen=True)
class Roots:
    """The three cache roots, resolved together with their provenance.

    Passed around as one object so that adding a root later does not mean
    changing every signature between the command line and ``locate()``.
    ``datasets`` are the per-dataset roots of the escape hatch, by name.
    """

    public: Path
    restricted: Path | None = None
    staging: Path | None = None
    public_source: str = ""
    restricted_source: str = ""
    staging_source: str = ""
    datasets: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def coerce(cls, value: Roots | str | Path | None) -> Roots:
        """Accept a Roots, a bare path meaning "the public cache", or nothing.

        The bare-path form is what keeps ``fetch(root=...)`` and ``--root``
        working unchanged: they always meant the public cache, and still do.
        """
        if isinstance(value, cls):
            return value
        if value is None:
            return resolve_roots()
        return resolve_roots().with_public(value)

    def with_public(self, value: str | Path) -> Roots:
        """These roots with the public cache named explicitly, for one call or handle."""
        return replace(
            self, public=Path(value).expanduser(), public_source="explicit argument"
        )

    def for_access(self, access: str) -> Path | None:
        """The root a dataset of this access class is read from."""
        return self.restricted if access == k.RESTRICTED else self.public


# -- the settings file ---------------------------------------------------------


def account_config_path() -> Path:
    """The settings file in the account: one per person and machine.

    ``~/.config/ethos-data/config.yaml`` on Linux (``$XDG_CONFIG_HOME``
    respected), ``%LOCALAPPDATA%\\ethos-data\\config.yaml`` on Windows and
    ``~/Library/Application Support/ethos-data/config.yaml`` on macOS.
    """
    return Path(platformdirs.user_config_dir(APP, appauthor=False)) / CONFIG_FILENAME


def _legacy_account_config_path() -> Path | None:
    """Where the account's file was before, on Windows only; read for one release.

    platformdirs repeats the application name as its author on Windows unless
    told not to, which put the file in ``ethos-data\\ethos-data\\``.
    """
    old = Path(platformdirs.user_config_dir(APP)) / CONFIG_FILENAME
    return None if old == account_config_path() else old


def config_path() -> Path:
    """The settings file in effect: the one ``$ETHOS_DATA_CONFIG`` names, else the account's.

    This is the file every ``config set-*`` and ``unset-*`` writes to. It may
    not exist yet; :func:`load_config` says what that means.
    """
    named = os.environ.get(CONFIG_ENV_VAR)
    return Path(named).expanduser() if named else account_config_path()


def _config_source() -> str:
    """Why :func:`config_path` is the file in effect."""
    return f"${CONFIG_ENV_VAR}" if os.environ.get(CONFIG_ENV_VAR) else ACCOUNT


def _missing_named_file(path: Path) -> ConfigurationError:
    return ConfigurationError(
        f"${CONFIG_ENV_VAR} names {path}, which does not exist.\n"
        f"Create it with a setter, such as `ethos-data config set-public-cache DIR`, "
        f"or unset {CONFIG_ENV_VAR} to use the settings file in your account."
    )


def _file_to_read() -> Path | None:
    """The file settings are read from, or None if there is none.

    A file ``$ETHOS_DATA_CONFIG`` names must exist: a mistyped path would
    otherwise quietly read as "nothing set". The account's file may be absent,
    and then nothing is set. On Windows the account's file at its old location
    is read while there is none at the new one, with a warning that names it.
    """
    path = config_path()
    if path.is_file():
        return path
    if os.environ.get(CONFIG_ENV_VAR):
        raise _missing_named_file(path)
    legacy = _legacy_account_config_path()
    if legacy is not None and legacy.is_file():
        warnings.warn(
            f"read the settings from their old location, {legacy}; move the file to "
            f"{path}, where this and every later release looks for it",
            UserWarning,
            stacklevel=3,
        )
        return legacy
    return None


def _read_document(path: Path) -> dict:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ConfigurationError(f"{path} is not valid YAML: {error}") from None
    if not isinstance(document, dict):
        raise ConfigurationError(
            f"{path} must contain a YAML mapping, got {type(document).__name__}"
        )
    return document


def load_config() -> tuple[dict, dict[str, str]]:
    """The settings file's values, and where each came from.

    One file, so the provenance of every key is the same file; it is kept per
    key because the resolvers report it per value.
    """
    path = _file_to_read()
    if path is None:
        return {}, {}
    document = _read_document(path)
    where = f"settings file {path}"
    origin = {key: where for key in document}
    roots = document.get(DATASET_ROOTS_KEY)
    if isinstance(roots, dict):
        origin.update({f"{DATASET_ROOTS_KEY}.{name}": where for name in roots})
    return document, origin


def ignored_config_files(start: Path | None = None) -> list[tuple[str, Path]]:
    """Settings files earlier releases read and this one ignores, where they exist.

    Named by ``config show``, so somebody who wrote one is told why it no longer
    applies, rather than left to wonder.
    """
    in_effect = config_path().resolve()
    found: list[tuple[str, Path]] = []
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / _PROJECT_FILENAME
        if candidate.is_file():
            found.append(
                ("a project file, found from the working directory", candidate)
            )
            break
    found.append(
        (
            "the file in the Python environment",
            Path(sys.prefix) / "etc" / APP / CONFIG_FILENAME,
        )
    )
    for site in dict.fromkeys(
        (
            Path(platformdirs.site_config_dir(APP)) / CONFIG_FILENAME,
            Path(platformdirs.site_config_dir(APP, appauthor=False)) / CONFIG_FILENAME,
        )
    ):
        found.append(("the machine-wide file", site))
    return [
        (what, path)
        for what, path in found
        if path.is_file() and path.resolve() != in_effect
    ]


#: Prefixes every settings file we write, so somebody who opens one knows what it is.
CONFIG_HEADER = "# ethos-data settings. See `ethos-data config show`.\n"


def _write(path: Path, document: dict) -> None:
    """Write the settings file: UTF-8, LF, on every platform.

    Both arguments are load-bearing. Left to its defaults ``write_text`` encodes
    with the *locale* codec -- cp1252 on a German Windows, which cannot spell a
    cache path containing anything outside it -- and rewrites every "\\n" as
    "\\r\\n", so the same settings would read differently on another machine.
    """
    text = CONFIG_HEADER + yaml.safe_dump(
        document, default_flow_style=False, sort_keys=True
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _editable() -> tuple[Path, dict]:
    """The settings file to change, and what it holds now.

    A setter may create the file, even one ``$ETHOS_DATA_CONFIG`` names; that is
    how such a file comes to exist. On Windows a file still at the old location
    is carried over, so the first change moves it.
    """
    path = config_path()
    if path.is_file():
        return path, _read_document(path)
    legacy = None if os.environ.get(CONFIG_ENV_VAR) else _legacy_account_config_path()
    if legacy is not None and legacy.is_file():
        return path, _read_document(legacy)
    return path, {}


def _existing() -> tuple[Path, dict] | None:
    """The settings file to remove a value from, or None if there is none.

    Removing needs no file to exist, except that a file ``$ETHOS_DATA_CONFIG``
    names must: only a setter creates one.
    """
    path = config_path()
    if not path.is_file() and os.environ.get(CONFIG_ENV_VAR):
        raise _missing_named_file(path)
    path, document = _editable()
    return (path, document) if document else None


def set_option(key: str, value: object) -> Path:
    """Write one setting into the settings file in effect, creating it if need be."""
    path, document = _editable()
    document[key] = value
    _write(path, document)
    return path


def unset_option(key: str) -> Path | None:
    """Remove one setting from the settings file in effect; None if it was not set."""
    found = _existing()
    if found is None or key not in found[1]:
        return None
    path, document = found
    del document[key]
    # Kept even when it is left empty: a file $ETHOS_DATA_CONFIG names has to
    # go on existing, and an empty one in the account means what none does.
    _write(path, document)
    return path


def set_dataset_root(dataset: str, path: str) -> Path:
    config_file, document = _editable()
    roots = document.get(DATASET_ROOTS_KEY) or {}
    roots[dataset] = str(Path(path).expanduser())
    document[DATASET_ROOTS_KEY] = roots
    _write(config_file, document)
    return config_file


def unset_dataset_root(dataset: str) -> Path | None:
    found = _existing()
    if found is None or dataset not in (found[1].get(DATASET_ROOTS_KEY) or {}):
        return None
    config_file, document = found
    del document[DATASET_ROOTS_KEY][dataset]
    if not document[DATASET_ROOTS_KEY]:
        del document[DATASET_ROOTS_KEY]
    _write(config_file, document)
    return config_file


# -- resolving each setting --------------------------------------------------------


def _from_file(
    keys: tuple[str, ...], settings: dict, origin: dict[str, str]
) -> Resolved | None:
    """First of ``keys`` the settings file sets, with its provenance."""
    for key in keys:
        if settings.get(key):
            return Resolved(Path(str(settings[key])).expanduser(), origin[key])
    return None


def _default_public_cache() -> Resolved:
    """The per-user cache directory; on Windows the old one while it is still used."""
    default = Path(platformdirs.user_cache_dir(APP, appauthor=False))
    legacy = Path(platformdirs.user_cache_dir(APP))
    if legacy != default and legacy.is_dir() and not default.exists():
        return Resolved(
            legacy, f"built-in default, at its old location; move it to {default}"
        )
    return Resolved(default, "built-in default, the per-user cache directory")


def _public(explicit, settings: dict, origin: dict[str, str]) -> Resolved:
    if explicit is not None:
        return Resolved(Path(explicit).expanduser(), "explicit argument")
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Resolved(Path(from_env).expanduser(), f"${ENV_VAR}")
    found = _from_file((PUBLIC_CACHE_KEY, LEGACY_CACHE_KEY), settings, origin)
    return found if found is not None else _default_public_cache()


def _optional_root(
    explicit, variable: str, key: str, settings: dict, origin: dict[str, str]
) -> Resolved | None:
    if explicit is not None:
        return Resolved(Path(explicit).expanduser(), "explicit argument")
    from_env = os.environ.get(variable)
    if from_env:
        return Resolved(Path(from_env).expanduser(), f"${variable}")
    return _from_file((key,), settings, origin)


def _dataset_roots(settings: dict) -> dict[str, str]:
    roots = settings.get(DATASET_ROOTS_KEY) or {}
    if not isinstance(roots, dict):
        raise ConfigurationError(
            f"{DATASET_ROOTS_KEY} must be a mapping of dataset name -> path"
        )
    return {str(name): str(path) for name, path in roots.items()}


def _roots(public, settings: dict, origin: dict[str, str]) -> Roots:
    resolved_public = _public(public, settings, origin)
    restricted = _optional_root(
        None, RESTRICTED_ENV_VAR, RESTRICTED_CACHE_KEY, settings, origin
    )
    staging = _optional_root(None, STAGING_ENV_VAR, STAGING_CACHE_KEY, settings, origin)
    return Roots(
        public=resolved_public.value,
        restricted=restricted.value if restricted else None,
        staging=staging.value if staging else None,
        public_source=resolved_public.source,
        restricted_source=restricted.source if restricted else "",
        staging_source=staging.source if staging else "",
        datasets=_dataset_roots(settings),
    )


def _catalog(
    explicit: str | None, settings: dict, origin: dict[str, str]
) -> tuple[str, str] | None:
    if explicit:
        return explicit, "explicit argument"
    from_env = os.environ.get(CATALOG_ENV_VAR)
    if from_env:
        if not from_env.startswith(("http://", "https://")):
            from_env = str(Path(from_env).expanduser())
        return from_env, f"${CATALOG_ENV_VAR}"
    catalog = settings.get(CATALOG_KEY)
    if not catalog:
        return None
    catalog = str(catalog)
    if not catalog.startswith(("http://", "https://")):
        catalog = str(Path(catalog).expanduser())
    return catalog, origin[CATALOG_KEY]


def _publication_url(settings: dict, origin: dict[str, str]) -> tuple[str, str] | None:
    # Deliberately NOT a Path: pathlib collapses the "//" in "https://host".
    from_env = os.environ.get(PUBLICATION_URL_ENV_VAR)
    if from_env:
        return from_env, f"${PUBLICATION_URL_ENV_VAR}"
    if settings.get(PUBLICATION_URL_KEY):
        return str(settings[PUBLICATION_URL_KEY]), origin[PUBLICATION_URL_KEY]
    return None


def resolve_public_cache(explicit: str | Path | None = None) -> Resolved:
    """Where public and internal data is read from, and downloaded into."""
    return _public(explicit, *load_config())


def resolve_restricted_cache(explicit: str | Path | None = None) -> Resolved | None:
    """Where licensed data lives on this machine, or None if nobody has said.

    No built-in default, deliberately. Restricted bytes landing somewhere by
    accident is exactly the failure this package exists to prevent, so the
    absence of a setting is reported as a question rather than guessed at.
    """
    return _optional_root(
        explicit, RESTRICTED_ENV_VAR, RESTRICTED_CACHE_KEY, *load_config()
    )


def resolve_staging_cache(explicit: str | Path | None = None) -> Resolved | None:
    """Where work-in-progress data lives, or None if staging is not in use.

    Opt-in by design: an unset staging root means the catalogue is the only
    thing that can answer for a dataset, which is what you want everywhere
    except on the machine where somebody is preparing new data.
    """
    return _optional_root(explicit, STAGING_ENV_VAR, STAGING_CACHE_KEY, *load_config())


def resolve_roots(public: str | Path | None = None) -> Roots:
    """All three roots at once, each with its provenance, and the per-dataset ones."""
    return _roots(public, *load_config())


def resolve_cache_dir(explicit: str | Path | None = None) -> Resolved:
    """The public cache. Retained under its old name for existing callers."""
    return resolve_public_cache(explicit)


def current_user() -> str:
    """Who is running this, for the provenance records that say so.

    ``$USER`` is a POSIX convention; Windows sets ``$USERNAME`` instead, so
    reading ``$USER`` directly signed every Windows-written provenance record
    with an empty string. ``getpass.getuser`` knows both, and falls back to the
    password database. An unattended account may have neither, and a provenance
    record with no name is still worth writing -- so this reports "" rather
    than raising, exactly as the environment lookup it replaces did.
    """
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return ""


def dataset_roots() -> dict[str, str]:
    """Per-dataset local roots for this machine.

    The escape hatch, not the main road: a dataset listed here is read where it
    lies and never downloaded, whatever the three roots say. Use it for a
    private copy on a laptop; on a shared machine, put a symbolic link in the
    public cache instead, which needs no per-user configuration at all.
    """
    return _dataset_roots(load_config()[0])


def resolve_publication_url(catalog_default: str = "") -> tuple[str, str]:
    """Where to fetch bytes from, allowing a local override of the catalogue value.

    The catalogue names DESY's compatible, redirect-free door, which is right for
    anonymous public users. CI and bulk transfers want the high-throughput door
    instead -- uncapped, but it redirects to a pool host on a high port, so it
    needs an environment that permits outbound connections there.
    """
    found = _publication_url(*load_config())
    return found if found is not None else (catalog_default, "catalogue")


def resolve_catalog(explicit: str | None = None) -> tuple[str, str] | None:
    """Optional catalogue override: explicit, then $ETHOS_DATA_CATALOG, then the file.

    Returns ``None`` if nothing is set, so a caller falls back to whatever a
    collections.yaml pins for itself via its own ``catalog:`` key, and after that
    to ``DEFAULT_CATALOG``.

    Deliberately returns a plain string rather than a ``Resolved`` -- a
    catalogue location is as often an http(s) URL as a local path, and
    ``pathlib.Path`` collapses the "//" in "https://", which would silently
    corrupt it (see resolve_publication_url for the same issue).
    """
    return _catalog(explicit, *load_config())


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


# -- answers about paths, for whoever shows the settings -----------------------------


def unreachable(path: Path) -> str | None:
    """Why ``path`` is not a usable directory, or None when it is one.

    To ``Path.is_dir()`` a cache on a network drive that is not mounted looks
    exactly like a cache nobody has created yet: both are ``False``. The person
    reading ``config show`` needs the difference, so the reason is spelled out
    -- a drive that is not connected, a path that does not exist, or whatever
    the operating system said when it tried.
    """
    try:
        info = os.stat(path)
    except OSError as error:
        if path.drive and not os.path.exists(path.anchor):
            return f"drive {path.drive} is not connected"
        if isinstance(error, FileNotFoundError):
            return "does not exist"
        return f"cannot be reached ({error.strerror or error})"
    return None if stat.S_ISDIR(info.st_mode) else "is not a directory"


def catalog_index(location: str) -> str:
    """A catalogue location fit to be set, so a typo fails now, not on the next
    unrelated command with a stack trace three frames from the actual cause.

    Also accepts a directory and fills in ``datacatalog.json`` -- the mistake
    of pointing at the catalogue repo itself rather than its generated index
    is common enough to just handle.
    """
    if location.startswith(("http://", "https://")):
        return location
    candidate = Path(location).expanduser()
    if candidate.is_dir():
        auto = candidate / "datacatalog.json"
        if auto.is_file():
            return str(auto)
        raise ConfigurationError(
            f"{candidate} is a directory with no datacatalog.json in it.\n"
            "Point at the generated index file itself, e.g.:\n"
            f"    ethos-data config set-catalog {auto}"
        )
    if not candidate.is_file():
        raise ConfigurationError(
            f"no such file: {candidate}\n"
            "Expected the generated datacatalog.json inside a catalogue checkout "
            "-- not catalog.yaml (that's hand-written metadata, not the loadable index)."
        )
    return str(candidate)


# -- every setting at once ----------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """Every setting, read once, with where each value came from.

    What a handle keeps for the life of a script, so a script that changes
    directory or environment half-way keeps the catalogue and caches it began
    with. ``print(settings)`` names the settings file, the catalogue and its
    version, the caches and the source of each, ready to be recorded next to
    results; :meth:`as_dict` gives the same as plain values.

    ``catalog`` is the catalogue override from the settings alone until a
    handle fills in the catalogue it actually uses, from a collections file's
    pin or the built-in default.
    """

    file: Path
    file_source: str
    file_exists: bool
    roots: Roots
    catalog: str | None = None
    catalog_source: str = ""
    catalog_version: str | None = None
    publication_url: str | None = None
    publication_url_source: str = ""
    ignored: tuple[tuple[str, Path], ...] = ()
    #: Settings of an earlier release that are set but no longer read, with why.
    retired: tuple[tuple[str, str], ...] = ()

    def choose_catalog(
        self,
        *,
        explicit: str | None = None,
        pin: str | None = None,
        pin_source: str = "a collections file's pin",
    ) -> tuple[str, str]:
        """The catalogue to read, and why: one order for every handle and command.

        An explicit location; then ``$ETHOS_DATA_CATALOG`` or the settings
        file, as these settings read them; then a collections file's pin; then
        the public catalogue, so that public data needs nothing configured.
        """
        if explicit:
            return explicit, "explicit argument"
        if self.catalog is not None:
            return self.catalog, self.catalog_source
        if pin is not None:
            return pin, pin_source
        return DEFAULT_CATALOG, "built-in public catalogue"

    def with_catalog(
        self, location: str, source: str, version: str | None = None
    ) -> Settings:
        """These settings with the catalogue a handle actually uses."""
        return replace(
            self, catalog=location, catalog_source=source, catalog_version=version
        )

    def with_public(self, value: str | Path) -> Settings:
        """These settings with the public cache named explicitly."""
        return replace(self, roots=self.roots.with_public(value))

    def as_dict(self) -> dict:
        """Every value and its source, as strings, for a results file."""

        def cache(path: Path | None, source: str) -> dict | None:
            return None if path is None else {"path": str(path), "source": source}

        roots = self.roots
        return {
            "settings_file": {
                "path": str(self.file),
                "source": self.file_source,
                "exists": self.file_exists,
            },
            "catalog": None
            if self.catalog is None
            else {
                "location": self.catalog,
                "source": self.catalog_source,
                "version": self.catalog_version,
            },
            "public_cache": cache(roots.public, roots.public_source),
            "restricted_cache": cache(roots.restricted, roots.restricted_source),
            "staging_cache": cache(roots.staging, roots.staging_source),
            "publication_url": None
            if self.publication_url is None
            else {"url": self.publication_url, "source": self.publication_url_source},
            "dataset_roots": dict(roots.datasets),
        }

    def rows(self) -> list[tuple[str, str]]:
        """``(label, value)`` per line of the report, in the order it prints."""
        roots = self.roots
        file = f"{self.file}  ({self.file_source}"
        file += ")" if self.file_exists else "; not created yet, nothing set)"
        rows = [("settings file", file)]

        def source(text: str) -> str:
            # The first line names the file; every value from it says so briefly.
            return "settings file" if text == f"settings file {self.file}" else text

        if self.catalog is not None:
            rows.append(
                ("catalogue", f"{self.catalog}  ({source(self.catalog_source)})")
            )
            rows.append(("catalogue version", self.catalog_version or "not recorded"))
        else:
            rows.append(
                ("catalogue", "not set: a collections file's pin, else the public one")
            )
        for label, path, origin in (
            ("public cache", roots.public, roots.public_source),
            ("restricted cache", roots.restricted, roots.restricted_source),
            ("staging cache", roots.staging, roots.staging_source),
        ):
            rows.append((label, f"{path}  ({source(origin)})" if path else "not set"))
        if self.publication_url is not None:
            rows.append(
                (
                    "publication URL",
                    f"{self.publication_url}  ({source(self.publication_url_source)})",
                )
            )
        for name, where in sorted(roots.datasets.items()):
            rows.append(("dataset root", f"{name} -> {where}"))
        for what, path in self.ignored:
            rows.append(("ignored", f"{path}  ({what}; no longer read)"))
        for setting, why in self.retired:
            rows.append(("ignored", f"{setting}  (no longer read: {why})"))
        return rows

    def __str__(self) -> str:
        rows = self.rows()
        width = max(len(label) for label, _ in rows)
        return "\n".join(f"{label:<{width}}  {value}" for label, value in rows)


def read_settings(
    *, root: str | Path | None = None, catalog: str | None = None
) -> Settings:
    """Every setting at once, from one read of the settings file.

    ``root`` and ``catalog`` are explicit arguments, and win as they do one at a
    time. A file ``$ETHOS_DATA_CONFIG`` names that does not exist stops here,
    naming it.
    """
    settings, origin = load_config()
    path = config_path()
    catalog_found = _catalog(catalog, settings, origin)
    url = _publication_url(settings, origin)
    return Settings(
        file=path,
        file_source=_config_source(),
        file_exists=path.is_file(),
        roots=_roots(root, settings, origin),
        catalog=catalog_found[0] if catalog_found else None,
        catalog_source=catalog_found[1] if catalog_found else "",
        publication_url=url[0] if url else None,
        publication_url_source=url[1] if url else "",
        ignored=tuple(ignored_config_files()),
        retired=tuple(
            [(key, why) for key, why in RETIRED_KEYS.items() if key in settings]
            + [
                (f"${variable}", why)
                for variable, why in RETIRED_ENV_VARS.items()
                if variable in os.environ
            ]
        ),
    )


#: Reads the catalogue route instead of a package's bundles, for one job.
DOWNLOAD_ENV_VAR = "ETHOS_DATA_DOWNLOAD"


def download_requested(explicit: bool | None = None) -> bool:
    """Whether the catalogue route is asked for instead of the bundles.

    ``explicit``, a handle's ``download=``, when given; else
    ``$ETHOS_DATA_DOWNLOAD`` set to ``1``, ``true``, ``yes`` or ``on``.
    """
    if explicit is not None:
        return explicit
    return os.environ.get(DOWNLOAD_ENV_VAR, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

