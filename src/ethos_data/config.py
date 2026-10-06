"""Where the caches and the catalogue are, for one person on one machine.

There are three kinds of root:

    public_cache       public data -- a namespace of symbolic links to data
                       already on this machine, plus real directories for
                       anything downloaded from dCache; one per account, and
                       on the cluster one shared directory
    restricted_caches  restricted data, read in place and never downloaded:
                       an ordered list of directories, each admitting one
                       access combination; none by default
    staging_cache      optional: work in progress that is not in the catalogue
                       yet, shadowing it during development

Deliberately *not* one setting per dataset. A cache shared by a whole institute
has to be configurable in one line, or people will not configure it at all.
Which root a dataset comes from follows from its access class, and whether it is
read in place follows from whether its entry in the root is a symbolic link --
both facts already available without anybody writing them down. A local copy of
one dataset is linked into a cache with ``ethos-data link NAME DIR``.

Each setting is resolved from the first of:

    1. an explicit argument        fetch(..., root=...) / --root, catalog= / --catalog
    2. an environment variable     $ETHOS_DATA_DIR, $ETHOS_RESTRICTED_DIRS, ...
    3. the settings file           the file $ETHOS_DATA_CONFIG names, else the
                                   one in the account
    4. the built-in default        the per-user cache directory (public cache only)

One file, in the account, because a script has to find the same settings however
it is started: from its own folder or another, from an editor, a notebook or a
batch job, in whichever Python environment. ``$ETHOS_DATA_CONFIG`` replaces the
account's file rather than merging with it, so a CI job or a test run is
isolated from the account it runs under.

The restricted caches are a list with no explicit argument:
``$ETHOS_RESTRICTED_DIRS`` holds paths separated by :data:`os.pathsep` and
replaces the file's list; nothing is merged.

Nothing has to be configured for public data: layer 4 works on Linux, macOS and
Windows alike. The restricted caches and the staging root have *no* built-in
default on purpose -- where restricted bytes are read is a decision somebody has
to make out loud, and staging is opt-in by nature. An account that lists no
restricted cache reads public data only, which is a valid set-up everywhere.
No root contains another: :func:`set_cache` and :func:`add_restricted_cache`
refuse a directory that is, contains or lies inside another root.

:func:`read_settings` reads every setting at once and records *where* each value
came from, because "why is my data going there?" is the question people actually
ask. The :class:`Settings` it returns is what a handle or a command keeps, and
every later read of a setting goes through it.
"""

from __future__ import annotations

import getpass
import os
import stat
from dataclasses import dataclass, replace
from pathlib import Path

import platformdirs
import yaml

from .errors import CatalogVersionError, ConfigurationError
from .formats import keys as k
from .model.versions import Bounds

__all__ = [
    "CATALOG_ENV_VAR",
    "CONFIG_ENV_VAR",
    "DEFAULT_CATALOG",
    "ENV_VAR",
    "PUBLICATION_URL_ENV_VAR",
    "RESTRICTED_ENV_VAR",
    "STAGING_ENV_VAR",
    "Roots",
    "Settings",
    "account_config_path",
    "add_restricted_cache",
    "catalog_index",
    "config_path",
    "current_user",
    "load_config",
    "read_settings",
    "remove_restricted_cache",
    "set_cache",
    "set_option",
    "unset_option",
    "unreachable",
    "PUBLIC_RELEASE_URL",
]

#: The public catalogue, used whenever nothing else names one -- so that public
#: data needs no configuration at all. It follows a moving branch, and lists
#: every release; a collections file's release bounds choose one of them.
DEFAULT_CATALOG = "https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/main/datacatalog.json"
#: Where the public catalogue keeps one release: the tag of that release.
PUBLIC_RELEASE_URL = "https://raw.githubusercontent.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/{version}/datacatalog.json"
#: Point every tool in one shell or job at another catalogue -- the internal one,
#: say -- without editing a file. Wins over the settings file and over the
#: public release a collections file's bounds select; an explicit ``catalog=`` /
#: ``--catalog`` wins over it. One variable for every package.
CATALOG_ENV_VAR = "ETHOS_DATA_CATALOG"
#: A settings file to read instead of the one in the account -- for a CI job, a
#: container, a lesson, or a team's file on a shared machine. Replaces the
#: account's file; nothing is merged.
CONFIG_ENV_VAR = "ETHOS_DATA_CONFIG"

#: The public cache.
ENV_VAR = "ETHOS_DATA_DIR"
#: The restricted caches, separated by :data:`os.pathsep`; replaces the file's list.
RESTRICTED_ENV_VAR = "ETHOS_RESTRICTED_DIRS"
STAGING_ENV_VAR = "ETHOS_STAGING_DIR"
PUBLICATION_URL_ENV_VAR = "ETHOS_PUBLICATION_URL"


APP = "ethos-data"

#: Where the account's settings file is, the source a value read from it names.
ACCOUNT = "your account"


@dataclass(frozen=True)
class Roots:
    """The cache roots, resolved together with their provenance.

    Passed around as one object so that adding a root later does not mean
    changing every signature between the command line and ``locate()``.
    ``restricted`` are the restricted caches in the order they are read; the
    list has one source.
    """

    public: Path
    restricted: tuple[Path, ...] = ()
    staging: Path | None = None
    public_source: str = ""
    restricted_source: str = ""
    staging_source: str = ""

    def with_public(self, value: str | Path) -> Roots:
        """These roots with the public cache named explicitly, for one call or handle."""
        return replace(
            self, public=Path(value).expanduser(), public_source="explicit argument"
        )

    def restricted_cache(self, directory: str | Path) -> Path | None:
        """The listed restricted cache ``directory`` names, or None if it is not one."""
        wanted = _same(directory)
        return next(
            (cache for cache in self.restricted if _same(cache) == wanted), None
        )


def _same(directory: str | Path) -> str:
    """A directory's spelling for comparison: absolute, normalised, case-folded where the system is."""
    return os.path.normcase(os.path.abspath(Path(directory).expanduser()))


# -- the settings file ---------------------------------------------------------


def account_config_path() -> Path:
    """The settings file in the account: one per person and machine.

    ``~/.config/ethos-data/config.yaml`` on Linux (``$XDG_CONFIG_HOME``
    respected), ``%LOCALAPPDATA%\\ethos-data\\config.yaml`` on Windows and
    ``~/Library/Application Support/ethos-data/config.yaml`` on macOS.
    """
    return Path(platformdirs.user_config_dir(APP, appauthor=False)) / k.SETTINGS_FILE


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
    and then nothing is set.
    """
    path = config_path()
    if path.is_file():
        return path
    if os.environ.get(CONFIG_ENV_VAR):
        raise _missing_named_file(path)
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


def _check(path: Path, document: dict) -> None:
    """Raise naming every way ``document`` breaks the settings file's specification."""
    from pydantic import ValidationError

    from .formats.fields import describe
    from .formats.settings_file import SettingsFile

    try:
        SettingsFile.model_validate(document)
    except ValidationError as error:
        problems = "".join(f"\n  {line}" for line in describe(error))
        raise ConfigurationError(
            f"{path} is not a valid settings file:{problems}"
        ) from None


def load_config() -> tuple[dict, dict[str, str]]:
    """The settings file's values, and where each came from.

    The file is checked against its specification,
    :class:`~ethos_data.formats.SettingsFile`, and every problem is reported at
    once. One file, so the provenance of every key is the same file; it is kept
    per key because the snapshot reports it per value.
    """
    path = _file_to_read()
    if path is None:
        return {}, {}
    document = _read_document(path)
    _check(path, document)
    where = f"settings file {path}"
    return document, {key: where for key in document}


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
    how such a file comes to exist.
    """
    path = config_path()
    return path, _read_document(path) if path.is_file() else {}


def _existing() -> tuple[Path, dict] | None:
    """The settings file to remove a value from, or None if there is none.

    Removing needs no file to exist, except that a file ``$ETHOS_DATA_CONFIG``
    names must: only a setter creates one.
    """
    path = config_path()
    if not path.is_file():
        if os.environ.get(CONFIG_ENV_VAR):
            raise _missing_named_file(path)
        return None
    document = _read_document(path)
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


def _overlapping(directory: Path, others: dict[str, Path]) -> None:
    """Refuse ``directory`` if it is, contains or lies inside one of ``others``."""
    mine = Path(_same(directory))
    for label, other in others.items():
        theirs = Path(_same(other))
        if mine == theirs or mine in theirs.parents or theirs in mine.parents:
            raise ConfigurationError(
                f"{directory} is, contains or lies inside the {label}, {other}. The "
                "public cache, the staging root and each restricted cache are separate "
                "directories; choose another."
            )


def _other_roots(roots: Roots, *, keep: str) -> dict[str, Path]:
    """Every root of ``roots`` but the one the setting ``keep`` names."""
    others: dict[str, Path] = {}
    if keep != k.SETTING_PUBLIC_CACHE:
        others["public cache"] = roots.public
    if keep != k.SETTING_STAGING_CACHE and roots.staging is not None:
        others["staging root"] = roots.staging
    for number, cache in enumerate(roots.restricted, start=1):
        others[f"restricted cache {number}"] = cache
    return others


def _current_roots() -> Roots:
    """The roots in effect, as a setter sees them.

    A setter may create the file ``$ETHOS_DATA_CONFIG`` names, so a missing one
    holds no roots here rather than stopping the command, and a value the
    specification would refuse can still be replaced.
    """
    path = config_path()
    document = _read_document(path) if path.is_file() else {}
    return _roots(None, document, {key: f"settings file {path}" for key in document})


def set_cache(key: str, directory: str | Path) -> Path:
    """Set the public cache or the staging root, refusing a directory that overlaps another root."""
    if key not in (k.SETTING_PUBLIC_CACHE, k.SETTING_STAGING_CACHE):
        raise ValueError(f"{key!r} is not the public cache or the staging root")
    target = Path(directory).expanduser()
    _overlapping(target, _other_roots(_current_roots(), keep=key))
    return set_option(key, str(target))


def add_restricted_cache(directory: str | Path) -> Path:
    """Append a restricted cache to the settings file's list.

    Refuses a directory the list already holds, and one that is, contains or
    lies inside another root.
    """
    target = Path(directory).expanduser()
    path, document = _editable()
    listed = [str(item) for item in document.get(k.SETTING_RESTRICTED_CACHES) or []]
    if any(_same(item) == _same(target) for item in listed):
        raise ConfigurationError(f"{target} is already a restricted cache in {path}.")
    others = _other_roots(replace(_current_roots(), restricted=()), keep="")
    for number, item in enumerate(listed, start=1):
        others[f"restricted cache {number}"] = Path(item)
    _overlapping(target, others)
    document[k.SETTING_RESTRICTED_CACHES] = [*listed, str(target)]
    _write(path, document)
    return path


def remove_restricted_cache(directory: str | Path) -> Path:
    """Remove a restricted cache from the settings file's list."""
    found = _existing()
    listed = [
        str(item)
        for item in (found[1] if found else {}).get(k.SETTING_RESTRICTED_CACHES) or []
    ]
    kept = [item for item in listed if _same(item) != _same(directory)]
    if found is None or len(kept) == len(listed):
        where = found[0] if found else config_path()
        shown = ", ".join(listed) or "none"
        raise ConfigurationError(
            f"{directory} is not a restricted cache in {where}; it lists {shown}."
        )
    path, document = found
    if kept:
        document[k.SETTING_RESTRICTED_CACHES] = kept
    else:
        del document[k.SETTING_RESTRICTED_CACHES]
    _write(path, document)
    return path


# -- resolving each setting --------------------------------------------------------


def _from_file(
    key: str, settings: dict, origin: dict[str, str]
) -> tuple[Path, str] | None:
    """The path the settings file sets for ``key``, with its provenance."""
    if settings.get(key):
        return Path(str(settings[key])).expanduser(), origin[key]
    return None


def _public(explicit, settings: dict, origin: dict[str, str]) -> tuple[Path, str]:
    if explicit is not None:
        return Path(explicit).expanduser(), "explicit argument"
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Path(from_env).expanduser(), f"${ENV_VAR}"
    return _from_file(k.SETTING_PUBLIC_CACHE, settings, origin) or (
        Path(platformdirs.user_cache_dir(APP, appauthor=False)),
        "built-in default, the per-user cache directory",
    )


def _optional_root(
    variable: str, key: str, settings: dict, origin: dict[str, str]
) -> tuple[Path, str] | None:
    from_env = os.environ.get(variable)
    if from_env:
        return Path(from_env).expanduser(), f"${variable}"
    return _from_file(key, settings, origin)


def _restricted(settings: dict, origin: dict[str, str]) -> tuple[tuple[Path, ...], str]:
    """The restricted caches in order, and where the list came from.

    ``$ETHOS_RESTRICTED_DIRS`` replaces the file's list; nothing is merged.
    """
    from_env = os.environ.get(RESTRICTED_ENV_VAR)
    if from_env:
        listed = [item for item in from_env.split(os.pathsep) if item.strip()]
        source = f"${RESTRICTED_ENV_VAR}"
    else:
        listed = [str(item) for item in settings.get(k.SETTING_RESTRICTED_CACHES) or []]
        source = origin.get(k.SETTING_RESTRICTED_CACHES, "")
    if not listed:
        return (), ""
    return tuple(Path(item).expanduser() for item in listed), source


def _roots(public, settings: dict, origin: dict[str, str]) -> Roots:
    public_path, public_source = _public(public, settings, origin)
    restricted, restricted_source = _restricted(settings, origin)
    staging = _optional_root(STAGING_ENV_VAR, k.SETTING_STAGING_CACHE, settings, origin)
    return Roots(
        public=public_path,
        restricted=restricted,
        staging=staging[0] if staging else None,
        public_source=public_source,
        restricted_source=restricted_source,
        staging_source=staging[1] if staging else "",
    )


def _catalog(
    explicit: str | None, settings: dict, origin: dict[str, str]
) -> tuple[str, str] | None:
    # A string, not a Path: pathlib collapses the "//" in "https://host".
    if explicit:
        return explicit, "explicit argument"
    from_env = os.environ.get(CATALOG_ENV_VAR)
    if from_env:
        if not from_env.startswith(("http://", "https://")):
            from_env = str(Path(from_env).expanduser())
        return from_env, f"${CATALOG_ENV_VAR}"
    catalog = settings.get(k.SETTING_CATALOG)
    if not catalog:
        return None
    catalog = str(catalog)
    if not catalog.startswith(("http://", "https://")):
        catalog = str(Path(catalog).expanduser())
    return catalog, origin[k.SETTING_CATALOG]


def _publication_url(settings: dict, origin: dict[str, str]) -> tuple[str, str] | None:
    # Deliberately NOT a Path: pathlib collapses the "//" in "https://host".
    from_env = os.environ.get(PUBLICATION_URL_ENV_VAR)
    if from_env:
        return from_env, f"${PUBLICATION_URL_ENV_VAR}"
    if settings.get(k.SETTING_PUBLICATION_URL):
        return (
            str(settings[k.SETTING_PUBLICATION_URL]),
            origin[k.SETTING_PUBLICATION_URL],
        )
    return None


def current_user() -> str:
    """Who is running this, for the provenance records that say so.

    ``$USER`` is a POSIX convention; Windows sets ``$USERNAME`` instead.
    ``getpass.getuser`` knows both, and falls back to the password database. An
    unattended account may have neither, and a provenance record with no name
    is still worth writing -- so this reports "" rather than raising.
    """
    try:
        return getpass.getuser()
    except (OSError, KeyError, ImportError):
        return ""


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

    What a handle or a command keeps, so a script that changes directory or
    environment half-way keeps the catalogue and caches it began with.
    ``print(settings)`` names the settings file, the catalogue and its version,
    the caches and the source of each, ready to be recorded next to results;
    :meth:`as_dict` gives the same as plain values.

    ``catalog`` is the catalogue override from the settings alone until a
    handle fills in the catalogue it actually uses: the public release a
    collections file's bounds select, or the built-in default.
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

    def choose_catalog(
        self, *, explicit: str | None = None, bounds: Bounds | None = None
    ) -> tuple[str, str]:
        """The catalogue to read, and why: one order for every handle and command.

        An explicit location; then ``$ETHOS_DATA_CATALOG`` or the settings
        file, as these settings read them; then the public catalogue, so that
        public data needs nothing configured. A collections file's ``bounds``
        choose the public release: a full ``exact_version`` reads that
        release's tag, any other bounds the newest release they admit among
        those the public ``main`` index lists. A catalogue chosen any other way
        is checked against the bounds once it is loaded.
        """
        if explicit:
            return explicit, "explicit argument"
        if self.catalog is not None:
            return self.catalog, self.catalog_source
        if bounds is None:
            return DEFAULT_CATALOG, "built-in public catalogue"
        release = bounds.release()
        if release is not None:
            return (
                PUBLIC_RELEASE_URL.format(version=release),
                f"the public release {release}",
            )
        from .catalogs import public_releases

        published = public_releases(self)
        newest = bounds.newest(published)
        if newest is None:
            listed = ", ".join(map(str, published)) or "none"
            raise CatalogVersionError(
                f"no public catalogue release is within {bounds}; the public "
                f"releases are: {listed}."
            )
        return (
            PUBLIC_RELEASE_URL.format(version=newest),
            f"the public release {newest}, the newest within {bounds}",
        )

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
            "restricted_caches": [
                cache(path, roots.restricted_source) for path in roots.restricted
            ],
            "staging_cache": cache(roots.staging, roots.staging_source),
            "publication_url": None
            if self.publication_url is None
            else {"url": self.publication_url, "source": self.publication_url_source},
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
                ("catalogue", "not set: the public one, at a package's release bounds")
            )
        rows.append(
            ("public cache", f"{roots.public}  ({source(roots.public_source)})")
        )
        if not roots.restricted:
            rows.append(("restricted caches", "none listed: public data only"))
        for number, path in enumerate(roots.restricted, start=1):
            rows.append(
                (
                    f"restricted cache {number}",
                    f"{path}  ({source(roots.restricted_source)})",
                )
            )
        staging = roots.staging
        rows.append(
            (
                "staging cache",
                f"{staging}  ({source(roots.staging_source)})"
                if staging
                else "not set",
            )
        )
        if self.publication_url is not None:
            rows.append(
                (
                    "publication URL",
                    f"{self.publication_url}  ({source(self.publication_url_source)})",
                )
            )
        return rows

    def __str__(self) -> str:
        rows = self.rows()
        width = max(len(label) for label, _ in rows)
        return "\n".join(f"{label:<{width}}  {value}" for label, value in rows)


def read_settings(
    *, root: str | Path | None = None, catalog: str | None = None
) -> Settings:
    """Every setting at once, from one read of the settings file.

    ``root`` and ``catalog`` are explicit arguments, and win over every other
    source. A file ``$ETHOS_DATA_CONFIG`` names that does not exist stops here,
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
    )
