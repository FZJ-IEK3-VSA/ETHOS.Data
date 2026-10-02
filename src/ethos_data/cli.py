"""Fetch catalogued data and manage ETHOS configuration, caches and catalogues.

Use 'ls' to inspect the catalogue and 'fetch' to get a dataset, folder or file
by its catalogue key. Catalogue maintenance and dCache uploads use 'catalog'.
Collections, test bundles and staging belong to a package's own data command,
such as <tool>-data, built with ethos_data.tool_main.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from .access import cache_entries, chain_for, locate
from .bundles import create_bundle, export_bundle, load_bundle, update_bundle
from .catalogs import Catalog, catalog_for
from .config import (
    CATALOG_ENV_VAR,
    CATALOG_KEY,
    CONFIG_ENV_VAR,
    DEFAULT_CATALOG,
    ENV_VAR,
    LEGACY_CACHE_KEY,
    PUBLIC_CACHE_KEY,
    PUBLICATION_URL_KEY,
    RESTRICTED_CACHE_KEY,
    RESTRICTED_ENV_VAR,
    STAGING_CACHE_KEY,
    STAGING_ENV_VAR,
    Resolved,
    catalog_index,
    config_path,
    read_settings,
    resolve_catalog,
    resolve_public_cache,
    resolve_restricted_cache,
    resolve_roots,
    resolve_staging_cache,
    set_dataset_root,
    set_option,
    unreachable,
    unset_dataset_root,
    unset_option,
)
from .errors import (
    BundleError,
    CatalogueRootError,
    CollectionError,
    EthosDataError,
    IncompleteCatalog,
    UnknownDataset,
)
from .formats.derived import reader_description
from .maintain.cli import add_catalog_parser
from .maintain.cli import dispatch as _catalog_dispatch
from .retrieval import plan
from .selection import Collections, load_collections, variant_name


def _human(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def _use_utf8_output() -> None:
    """Let this command's output survive being redirected on Windows.

    Attached to a console, Python already writes Windows' own UTF-16 console
    API. Redirect or pipe the same command and ``sys.stdout`` falls back to the
    *locale* encoding instead -- cp1252 on a German machine -- so a catalogue
    holding a dataset titled in Chinese, or an attribution naming Forschungs-
    zentrum Jülich, turned ``ethos-data ls > datasets.txt`` into a
    UnicodeEncodeError traceback while the same command printed fine on screen.

    Done here rather than in the library: a command line tool owns its own
    streams, an imported module does not.
    """
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        # Absent when the stream has been replaced by something that is not a
        # TextIOWrapper -- a test harness capturing output, most often.
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):  # pragma: no cover - stream already closed
            pass


def main(argv: list[str] | None = None) -> int:
    """The ``ethos-data`` command: catalogue access and shared maintenance."""
    return _run(lambda: _main(argv))


def run_tool(
    file: str | Path,
    *,
    tool: str | None = None,
    prog: str | None = None,
    catalog: str | None = None,
    argv: list[str] | None = None,
    loaded: Collections | None = None,
    bundles: tuple | list = (),
) -> int:
    """A tool's own command: the collection commands bound to the file it ships.

    What :func:`ethos_data.tool_main` and :meth:`ethos_data.Collections.main`
    run, and all a tool needs to offer its users a data command -- geokit's is
    a tool's, with its file and its name. The parser offers ``show``,
    ``fetch`` and ``verify`` for the file's collections and the ``bundle``,
    ``staging`` and ``config`` groups. Access by catalogue key and shared cache
    and catalogue maintenance belong to ``ethos-data``.

    The handle -- and with it the catalogue -- is built only when a command
    needs it, so ``--help`` and ``config show`` work offline and a pin nobody
    can reach can still be overridden with ``--catalog`` for one run.
    ``catalog`` is the tool's own override (``$<TOOL>_DATA_CATALOG``), applied
    below ``--catalog`` and above the environment; ``loaded`` is a handle that
    already exists, reused when nothing overrides its catalogue.
    """
    prog = prog or (f"{tool}-data" if tool else "ethos-data")
    retired = _retired_command(prog, argv)
    if retired is not None:
        return retired
    source = _ToolSource(file, tool, catalog, loaded, tuple(bundles))
    return _run(
        lambda: _dispatch(_build_tool_parser(prog, source).parse_args(argv), source)
    )


#: Commands a tool's data command used to have, and what replaces each.
#: They are gone, not aliased: the whole point of the shorter command list is
#: that there is one way to ask each question, and an alias that keeps working
#: keeps the old shape alive in every script nobody got round to updating. But
#: argparse's "invalid choice" would leave somebody staring at a command that
#: worked last week, so each retired name gets one line saying what to type.
_RETIRED_COMMANDS = {
    "list": "{prog} show",
    "info": "{prog} show <collection>",
    "plan": "{prog} fetch <collection> --plan",
    "paths": "{prog} fetch <collection> --paths",
    "path": "ethos-data fetch <key>",
    "ls": "ethos-data ls [<key>]",
}

#: Global options that take a value, so their value is not mistaken for the
#: subcommand when looking for a retired name.
_VALUED_GLOBALS = ("--catalog", "--root")


def _retired_command(prog: str, argv: list[str] | None) -> int | None:
    """Two lines pointing at the replacement, or None to parse as usual."""
    skip = False
    for word in sys.argv[1:] if argv is None else argv:
        if skip:
            skip = False
            continue
        if word.startswith("-"):
            skip = word in _VALUED_GLOBALS
            continue
        replacement = _RETIRED_COMMANDS.get(word)
        if replacement is None:
            return None
        print(
            f"error: `{prog} {word}` is gone -- "
            f"use `{replacement.format(prog=prog)}`.\n"
            f"Run `{prog} --help` for the commands this version has.",
            file=sys.stderr,
        )
        return 2
    return None


def _run(command) -> int:
    """Run a parsed command, turning a refusal into a message, not a traceback.

    Every refusal the library raises on purpose is an
    :class:`~ethos_data.errors.EthosDataError`, and it already carries the
    sentence the user needs plus the command that fixes it. Wrapped in a stack
    trace, that reads like a crash and the advice gets lost in the noise. The
    error says which status to exit with: ``2`` when the request could not be
    served, ``1`` when a maintenance command refused its input. Anything else
    is a bug and keeps its traceback.
    """
    _use_utf8_output()
    try:
        return command()
    except EthosDataError as error:
        # ``message`` rather than str(): the KeyError subclasses stringify
        # quoted, which reads badly on a line that already says "error:".
        print(f"error: {error.message}", file=sys.stderr)
        return error.exit_code


def _build_parser() -> argparse.ArgumentParser:
    """Catalogue access, configuration and maintenance, without collections."""
    parser = argparse.ArgumentParser(
        prog="ethos-data",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Put global options before the subcommand. Examples:\n"
        "  ethos-data config show\n"
        "  ethos-data ls\n"
        "  ethos-data ls global-wind-atlas-v4\n"
        "  ethos-data fetch global-wind-atlas-v4\n"
        "  ethos-data link --all --root /shared/ethos/public\n"
        "  ethos-data catalog --catalog-root /path/to/source build --check\n"
        "Use 'ethos-data COMMAND --help' for command options.",
    )
    _add_common_options(parser)
    sub = parser.add_subparsers(dest="command", required=True)
    _add_key_commands(sub)
    _add_config_commands(sub)
    _add_cache_commands(sub)
    add_catalog_parser(sub)
    return parser


def _build_tool_parser(prog: str, source: _ToolSource) -> argparse.ArgumentParser:
    """A tool's collection, bundle, staging and config commands, no ``-c``.

    Six commands, and the two that carry the work are ``show`` and ``fetch``:
    whatever a tool's user wants out of the catalogue, they ask for it through
    one of the collections the tool ships. Access by catalogue key
    (``ethos-data ls``, ``ethos-data fetch``) and cache maintenance
    (materialize, link, unlink, the maintainer's catalog group) stay with
    ``ethos-data``; they are about the shared catalogue and cache, not about
    any one tool's data.

    The file is fixed -- it is the one the tool ships -- so there is nothing to
    name. Built from the file alone: the catalogue is not loaded for ``--help``.
    """
    tool = source.tool or prog
    example = (source.names() or ["<collection>"])[0]
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"Find, fetch and check the data {tool} needs.\n\n"
        f"Its collections are defined in {source.file_path}. `show` lists them "
        f"and describes one; `fetch` makes one available and, with --paths, "
        f"prints the inputs it names. Data lands in the cache every ETHOS tool "
        f"shares (`{prog} config show`). This command works in collections: a "
        f"single catalogue key is `ethos-data ls` and `ethos-data fetch`.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Put global options before the subcommand. Examples:\n"
        f"  {prog} show\n"
        f"  {prog} show {example} --test\n"
        f"  {prog} fetch {example} --test --plan\n"
        f"  {prog} fetch {example} --test --paths\n"
        f"  {prog} config show\n"
        f"Use '{prog} COMMAND --help' for command options.",
    )
    _add_common_options(parser, tool_commands=True)
    sub = parser.add_subparsers(dest="command", required=True)
    _add_collection_commands(sub)
    _add_bundle_commands(sub)
    _add_config_commands(sub)
    _add_staging_commands(sub)
    parser.set_defaults(prog=prog)
    return parser


def _add_common_options(
    parser: argparse.ArgumentParser, *, tool_commands: bool = False
) -> None:
    """Shared options, plus collection-specific switches for package commands."""
    parser.add_argument(
        "--catalog",
        default=None,
        help="datacatalog.json path or URL; overrides configuration"
        + (" and the collections file's pin" if tool_commands else ""),
    )
    parser.add_argument(
        "--root", default=None, help="override the public cache directory"
    )
    if not tool_commands:
        return
    # Accepted here as well as after the subcommand: `--test fetch onshore_wind`
    # is what people type after reading "put global options first", and a bare
    # "unrecognized arguments: --test" would send them looking for a typo.
    # Merged into args.test in _dispatch.
    parser.add_argument(
        "--test",
        dest="test_global",
        action="store_true",
        help="the collection's small test variant instead of the full data "
        "(same as --test after the subcommand)",
    )


def _add_collection_commands(sub) -> None:
    """``show``, ``fetch`` and ``verify``: everything that names a collection.

    Two verbs, split by what they do to the machine rather than by what they
    print. ``show`` answers questions from the catalogue and never transfers a
    byte, so it is safe to run anywhere, on any collection, without wondering
    what it will cost; ``fetch`` is the one that moves data, and its options
    choose what to report about the transfer -- ``--plan`` to describe it
    instead of running it, ``--paths`` to name the result. That is why the
    preview is an option of ``fetch`` and not a command of its own: a preview
    that could drift from the fetch it previews is worth nothing, and sharing
    one parser makes the drift impossible.
    """
    #: The same switch on every command that names a collection, so that
    #: `fetch --plan --test` previews exactly what `fetch --test` will do.
    test_flag = {
        "action": "store_true",
        "help": "the collection's small test variant instead of the full data",
    }

    shower = sub.add_parser(
        "show",
        help="list the collections, or describe one; fetches no data",
        description="Without a collection, every collection in the file with its file "
        "count and size -- one row per variant where a collection defines "
        "them. With one, that collection's size and the inputs it names for a "
        "workflow. Reads catalogue metadata only; nothing is downloaded.",
    )
    shower.add_argument(
        "collection", nargs="?", help="a collection (default: list them all)"
    )
    shower.add_argument("--test", **test_flag)
    shower.add_argument(
        "--files",
        action="store_true",
        help="with a collection: list every file it selects, with its size",
    )
    shower.add_argument(
        "--meta",
        action="store_true",
        help="with a collection: print the description of every dataset it selects",
    )

    fetcher = sub.add_parser(
        "fetch",
        help="make a collection available, reusing cached or in-place files",
        description="Download whatever the collection selects and is not already on this "
        "machine. --plan says what that would be and stops; --paths prints the "
        "inputs the collection names, one `handle<TAB>path` line each, for a "
        "script to read back.",
    )
    fetcher.add_argument("collection")
    fetcher.add_argument("--test", **test_flag)
    report = fetcher.add_mutually_exclusive_group()
    report.add_argument(
        "--plan",
        action="store_true",
        help="preview the transfer and stop (may retrieve catalogue metadata)",
    )
    report.add_argument(
        "--paths",
        action="store_true",
        help="print the inputs the collection names, as handle and path",
    )

    verifier = sub.add_parser(
        "verify",
        help="check file sizes, or SHA-256 hashes with --deep",
        description="Check selected files without changing them unless --repair is given. "
        "No collection means every collection in the selected file, in every "
        "variant.",
    )
    verifier.add_argument("collection", nargs="?", help="a collection (default: --all)")
    verifier.add_argument(
        "--all", action="store_true", help="every collection in the file"
    )
    verifier.add_argument("--test", **test_flag)
    verifier.add_argument(
        "--deep",
        action="store_true",
        help="compare checksums, not just sizes (reads every byte)",
    )
    verifier.add_argument(
        "--repair",
        action="store_true",
        help="re-fetch repairable data; may remove public-cache links; preview with --dry-run",
    )
    verifier.add_argument(
        "--dry-run",
        action="store_true",
        help="with --repair: say what would be re-fetched, change nothing",
    )
    verifier.add_argument(
        "-q", "--quiet", action="store_true", help="only report problems"
    )


def _add_key_commands(sub) -> None:
    """The commands that name a dataset, folder or file in the catalogue.

    ``ethos-data`` only: a tool's own command works in the collections that
    tool ships, and reaching past them into the catalogue is this command's job.
    """
    pather = sub.add_parser(
        "fetch",
        help="fetch a dataset, folder or file and print its absolute local path",
    )
    pather.add_argument("key", help="<dataset>/<file or folder>, or a dataset name")
    lister = sub.add_parser(
        "ls",
        help="list datasets, or files under a catalogue key; fetches no data",
        description="What is in a dataset, and what to put after the slash to get one file "
        "with `fetch`. Reads catalogue metadata only.",
    )
    lister.add_argument(
        "key",
        nargs="?",
        help="a dataset, family, folder or file (default: list datasets)",
    )
    lister.add_argument(
        "--meta",
        action="store_true",
        help="with a key: print the description of the dataset(s) under it",
    )
    checker = sub.add_parser(
        "verify",
        help="check the files under a key: sizes, or SHA-256 hashes with --deep",
        description="Check a dataset, folder or file against the catalogue, without "
        "changing anything unless --repair is given.",
    )
    checker.add_argument("key", help="<dataset>/<file or folder>, or a dataset name")
    checker.add_argument(
        "--deep",
        action="store_true",
        help="compare checksums, not just sizes (reads every byte)",
    )
    checker.add_argument(
        "--repair",
        action="store_true",
        help="re-fetch repairable data; may remove public-cache links; preview with --dry-run",
    )
    checker.add_argument(
        "--dry-run",
        action="store_true",
        help="with --repair: say what would be re-fetched, change nothing",
    )
    checker.add_argument(
        "-q", "--quiet", action="store_true", help="only report problems"
    )
    sub.add_parser(
        "selftest",
        help="check that this machine can obtain data: settings, catalogue, a small download",
        description="Fetch the small public collections ETHOS.Data ships, under 200 KB, "
        "and check every file against the catalogue. Give an empty --root to force a "
        "download where the files are already cached.",
    )


def _add_bundle_commands(sub) -> None:
    bundle = sub.add_parser("bundle", help="repository copies of catalogued test data")
    bundle_sub = bundle.add_subparsers(dest="bundle_command", required=True)
    exporter = bundle_sub.add_parser(
        "export", help="copy selected official data into a new bundle"
    )
    exporter.add_argument("target", help="new directory for the bundle")
    exporter.add_argument(
        "bundle_collections", nargs="+", help="collections to include"
    )
    exporter.add_argument(
        "--source-root",
        action="append",
        default=[],
        metavar="DATASET=PATH",
        help="verified existing local copy (repeat for each dataset)",
    )
    exporter.add_argument(
        "--source-revision",
        help="provenance label only; select the revision with --catalog or the collections pin",
    )
    creator = bundle_sub.add_parser(
        "create",
        help="start a bundle from files under DIR/data/<family>/<member>/",
        description="Hash every file, write bundle.json as version 1, not yet "
        "published, and draft a dataset.yaml for the family and each member.",
    )
    creator.add_argument("directory", help="the bundle directory in the repository")
    creator.add_argument(
        "--family", required=True, help="the family its datasets belong to"
    )
    updater = bundle_sub.add_parser(
        "update",
        help="record the changes to a bundle's files; its next version once published",
        description="Re-inventory the files and record what changed, appeared, "
        "moved or disappeared. A version a catalogue release holds is never "
        "changed: the first change after it starts the next version. With nothing "
        "changed, record the release that holds the current version, if there is one.",
    )
    updater.add_argument("directory", help="the bundle directory")
    for name in ("fetch", "verify"):
        reader = bundle_sub.add_parser(
            name, help="read or verify a bundle without network access"
        )
        reader.add_argument("directory")
        reader.add_argument(
            "collection",
            nargs="?",
            default=None,
            help="an exported bundle's collection (default: every file)",
        )
        if name == "fetch":
            reader.add_argument(
                "--allow-modified",
                action="store_true",
                help="use changed fixture bytes for development, warning about divergence",
            )


def _add_config_commands(sub) -> None:
    config_parser = sub.add_parser(
        "config", help="show or change catalogue, cache, and access settings"
    )
    config_parser.description = (
        "Every setting lives in one file: the one $ETHOS_DATA_CONFIG names, else the "
        "one in your account. The setters write to it, creating it if need be."
    )
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser(
        "show", help="show the settings in effect and their origins; no network access"
    )

    for verb, key, blurb in (
        ("cache", PUBLIC_CACHE_KEY, "the public cache (alias of set-public-cache)"),
        (
            "public-cache",
            PUBLIC_CACHE_KEY,
            "where public and internal data is read and downloaded",
        ),
        (
            "restricted-cache",
            RESTRICTED_CACHE_KEY,
            "where licensed data lives; never downloaded",
        ),
        (
            "staging-cache",
            STAGING_CACHE_KEY,
            "where work in progress lives; shadows the catalogue",
        ),
    ):
        setter = config_sub.add_parser(f"set-{verb}", help=f"set {blurb}")
        setter.add_argument("directory")
        setter.set_defaults(option_key=key)
        unsetter = config_sub.add_parser(
            f"unset-{verb}", help="remove the setting again"
        )
        unsetter.set_defaults(option_key=key)

    rooter = config_sub.add_parser(
        "set-root", help="escape hatch: use one dataset from a local directory"
    )
    rooter.add_argument("dataset")
    rooter.add_argument("directory")
    unrooter = config_sub.add_parser(
        "unset-root", help="stop using a local directory for a dataset"
    )
    unrooter.add_argument("dataset")
    puburl = config_sub.add_parser(
        "set-publication-url",
        help="fetch bytes from a different door (e.g. the high-throughput one for CI)",
    )
    puburl.add_argument("url")
    config_sub.add_parser(
        "unset-publication-url",
        help="fetch bytes from the door the catalogue names again",
    )
    cataloger = config_sub.add_parser(
        "set-catalog",
        help="set the shared catalogue override, including for package data commands",
    )
    cataloger.add_argument("location", help="a datacatalog.json path or URL")
    config_sub.add_parser("unset-catalog", help="remove the setting again")


def _add_cache_commands(sub) -> None:
    """Commands on the shared cache itself; ``ethos-data`` only."""
    material = sub.add_parser(
        "materialize",
        help="copy catalogued files into the cache from a link or local source",
        description="Copy a complete dataset and verify it before replacing a cache link. "
        "The original is kept. Explicit restricted datasets use the restricted root.",
    )
    material.add_argument("datasets", nargs="*", help="dataset names (default: --all)")
    material.add_argument(
        "--all",
        action="store_true",
        help="every entry in the public cache that is currently a link",
    )
    material.add_argument(
        "--dry-run", action="store_true", help="show the cost, copy nothing"
    )
    material.add_argument(
        "--force",
        action="store_true",
        help="compatibility option; existing real directories are still skipped",
    )
    material.add_argument(
        "--no-verify",
        action="store_true",
        help="skip checksum verification of each copied file (not advised)",
    )
    # `from` is a keyword, so the destination has to be named explicitly.
    material.add_argument(
        "--from",
        dest="source",
        metavar="DIR",
        default=None,
        help="copy from this directory instead of the entry's link target; "
        "fills an entry that does not exist yet",
    )
    material.add_argument(
        "--catalog-root",
        default=None,
        help="catalogue checkout to read source_dir from, when there is no "
        "entry and no --from (default: search upward for catalog.yaml); given, "
        "each copy is also recorded in the dataset's status.yaml there",
    )

    linker = sub.add_parser(
        "link",
        help="point cache entries at data already on this machine",
        description="Two modes, one command. Naming a dataset registers one "
        "directory as that dataset's entry, in whichever cache its access class "
        "belongs to -- so a restricted dataset deliberately named here lands in "
        "the restricted cache, which is how an authorised installation is meant "
        "to be recorded. --all instead builds the whole public namespace from a "
        "source checkout, and never links a restricted or unlicensed dataset "
        "into it, because a cache several people read must not hold licensed "
        "bytes nobody reviewed. Neither mode ever replaces a real directory "
        "with a link.",
    )
    linker.add_argument("dataset", nargs="?", help="dataset name (omit with --all)")
    linker.add_argument(
        "directory",
        nargs="?",
        help="the directory to link to (default: the catalogue's source_dir)",
    )
    linker.add_argument(
        "--all",
        action="store_true",
        help="link every dataset in the source catalogue that has a source_dir",
    )
    # dest is spelled out because argparse copies a subparser's whole namespace
    # -- defaults included -- over the main one. A second argument literally
    # called `root` would therefore reset `ethos-data --root DIR link ...` to
    # None whenever --root was not repeated after the subcommand, and the links
    # would quietly be built in a directory nobody named.
    linker.add_argument(
        "--root",
        dest="cache_root",
        metavar="DIR",
        default=None,
        help="with --all: the public cache directory to build "
        "(default: the cache this machine is configured to read)",
    )
    linker.add_argument(
        "--prune",
        action="store_true",
        help="with --all: remove links for names the catalogue no longer describes",
    )
    linker.add_argument(
        "--force",
        action="store_true",
        help="one named dataset; repoint an entry that is already a link "
        "(not valid with --all)",
    )
    linker.add_argument(
        "--dry-run",
        action="store_true",
        help="only honoured with --all, where it also previews what --prune "
        "would remove; single-dataset link applies immediately",
    )
    # Named as the maintainer commands name it, because it is the same thing: the
    # checkout holding dataset.yaml. source_dir is popped out of a descriptor when
    # it is built, so the hand-written file is the only place it exists.
    linker.add_argument(
        "--catalog-root",
        default=None,
        help="catalogue checkout to read source_dir from (default: search upward "
        "for catalog.yaml); given, each link is also recorded in the dataset's "
        "status.yaml there",
    )
    unlinker = sub.add_parser(
        "unlink", help="remove a cache entry that is a link; never a real directory"
    )
    unlinker.add_argument("dataset")


def _add_staging_commands(sub) -> None:
    stager = sub.add_parser(
        "staging", help="local development data that adds to or shadows the catalogue"
    )
    stager_sub = stager.add_subparsers(dest="staging_command", required=True)
    adder = stager_sub.add_parser(
        "add", help="register a directory as a staged dataset"
    )
    adder.add_argument("name")
    adder.add_argument("directory")
    adder.add_argument("--note", default="", help="what this is, for the next person")
    adder.add_argument(
        "--copy", action="store_true", help="copy the data instead of linking to it"
    )
    lister = stager_sub.add_parser("list", help="show what is staged")
    lister.add_argument(
        "--new-only",
        action="store_true",
        help="only datasets with no entry in the public or restricted "
        "cache -- the ones that still need describing",
    )
    remover = stager_sub.add_parser("remove", help="unregister a staged dataset")
    remover.add_argument("name")
    remover.add_argument(
        "--force",
        action="store_true",
        help="required if the entry is a real directory, not a link",
    )


class _ToolSource:
    """A tool's command: the file the tool ships, and a handle on it built the
    first time a command needs one.

    The catalogue is chosen as :func:`ethos_data.collections` chooses it --
    the tool's own override, then the environment and configuration, then the
    pin -- and only an explicit ``--catalog`` changes that, for one run. A
    handle the caller already has is reused when nothing overrides its choice.
    """

    def __init__(
        self,
        file: str | Path,
        tool: str | None,
        catalog: str | None,
        loaded: Collections | None = None,
        bundles: tuple = (),
    ):
        self.file_path = Path(file)
        self.tool = tool
        self.catalog = catalog
        self._loaded = loaded
        self.bundles = bundles

    def names(self) -> list[str]:
        """The collection names, read from the file alone -- for help text."""
        try:
            document = yaml.safe_load(self.file_path.read_text(encoding="utf-8")) or {}
            return sorted(document.get("collections", {}) or {})
        except (OSError, yaml.YAMLError, AttributeError):
            return []

    def file(self, args) -> str:
        return str(self.file_path)

    def load(self, args, roots) -> Collections:
        if args.catalog:
            return load_collections(
                self.file_path,
                catalog=args.catalog,
                roots=roots,
                tool=self.tool,
                bundles=self.bundles,
            )
        if self._loaded is None:
            from . import collections

            self._loaded = collections(
                self.file_path,
                tool=self.tool,
                catalog=self.catalog,
                bundles=self.bundles,
            )
        return self._loaded

    def catalog_override(self, args) -> str:
        return args.catalog or self.catalog or self.load(args, None).catalog.location


def _bundle_command(args, source) -> int:
    if args.bundle_command == "export":
        roots = {}
        for item in args.source_root:
            name, sep, directory = item.partition("=")
            if not sep or not name or not directory or name in roots:
                raise BundleError("--source-root must be a unique DATASET=PATH entry")
            roots[name] = directory
        bundle = export_bundle(
            source.file(args),
            args.bundle_collections,
            args.target,
            catalog=source.catalog_override(args),
            dataset_roots=roots,
            source_revision=args.source_revision,
        )
        print(f"Bundle created at {args.target}: {', '.join(bundle.names())}")
        return 0
    if args.bundle_command == "create":
        bundle = create_bundle(args.directory, args.family)
        files = len(bundle.resources)
        print(
            f"Bundle {bundle.family} version 1 created at {bundle.path}: "
            f"{len(bundle.datasets)} dataset(s), {files} file(s).\n"
            f"Fill in the drafts under {bundle.path / 'datasets'}, then commit."
        )
        return 0
    if args.bundle_command == "update":
        return _bundle_update(args, source)
    bundle = load_bundle(args.directory)
    if args.bundle_command == "verify":
        findings = bundle.verify(args.collection)
        for finding in findings:
            print(f"{finding.status}: {finding.key}")
        return 1 if any(f.status != "ok" for f in findings) else 0
    files = bundle.fetch(args.collection, allow_modified=args.allow_modified)
    for key, path in files.items():
        print(f"{key}: {path}")
    return 0


def _bundle_update(args, source) -> int:
    """``bundle update``: what changed, and the version or release it recorded."""
    try:
        catalog = source.load(args, None).base_catalog
    except EthosDataError as error:
        catalog = None
        print(f"note: the catalogue could not be read, so no release is recorded: "
              f"{_first_line(error)}")  # fmt: skip
    update = update_bundle(args.directory, catalog)
    bundle = update.bundle
    for label, found in (
        ("changed", update.changed),
        ("new", update.added),
        ("gone", update.removed),
    ):
        for name, paths in found.items():
            for path in paths:
                print(f"  {label:<10} {name}/{path}")
    for name, pairs in update.moved.items():
        for old, new in pairs:
            print(f"  {'moved':<10} {name}/{old} -> {new}")
    for name in update.new_members:
        print(
            f"  {'new':<10} {name}, drafted {bundle.path / 'datasets' / name / 'dataset.yaml'}"
        )
    for name in update.gone_members:
        print(f"  {'gone':<10} {name}")
    if update.removed or update.gone_members:
        print(
            "\nA file that goes takes its key with it, and every collection that "
            "names it breaks. If the layout changed, propose a successor: a new "
            "dataset whose dataset.yaml says ethos:supersedes."
        )
    if update.changes:
        started = bundle.version != update.previous_version
        print(
            f"\n{bundle.family} is version {bundle.version}"
            + (", the next after the published one" if started else "")
            + "; it is not in the catalogue yet."
        )
    elif update.released:
        print(
            f"{bundle.family} version {bundle.version} is in release {update.released}."
        )
    else:
        print(f"{bundle.family} version {bundle.version}: nothing changed.")
    return 0


def _main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "config":
        return _config_command(args)
    if args.command == "catalog":
        return _catalog_dispatch(args)
    if args.command == "selftest":
        return _selftest_command(args)

    roots = resolve_roots(args.root)
    if args.command == "materialize":
        return _materialize_command(args, roots)
    if args.command in ("link", "unlink"):
        return _link_command(args, roots)

    catalog = _cache_catalog(args).overlaid(roots)
    if args.command == "ls":
        return _ls_command(args, catalog)
    if args.command == "verify":
        return _key_verify_command(args, catalog, roots)
    return _path_command(args, catalog, roots)


def _dispatch(args, source) -> int:
    """Run a package command against its shipped collections file."""
    if args.command == "bundle":
        return _bundle_command(args, source)
    if args.command == "config":
        return _config_command(args)
    if args.command == "staging":
        return _staging_command(args)

    roots = resolve_roots(args.root)
    # --test may sit before or after the subcommand; commands without the flag
    # (config, staging, ...) simply ignore it.
    args.test = bool(getattr(args, "test", False) or args.test_global)

    loaded = source.load(args, roots)
    if args.command == "show":
        return _show_command(args, loaded, roots)
    if args.command == "verify":
        return _verify_command(args, loaded, roots)
    return _collection_fetch_command(args, loaded, roots)


def _show_command(args, loaded, roots) -> int:
    """What the file defines, or what one collection of it holds.

    Reads catalogue metadata and nothing else: no byte moves, whichever form
    is used, so this is the command to reach for when the question is "what is
    there" rather than "give it to me".
    """
    if args.collection is None:
        return _show_the_collections(loaded, roots)
    return _show_one_collection(args, loaded)


def _show_the_collections(loaded, roots) -> int:
    """One row per collection -- per variant, where a collection defines them."""
    print(f"catalogue: {loaded.catalog.location}")
    print(f"cache:     {roots.public}\n")
    unresolved = 0
    for name in loaded.names():
        # One collection naming a dataset this catalogue lacks -- a
        # withdrawn dataset, one that only exists in somebody's staging
        # root, or a mistake in its own definition, down to not being a
        # mapping at all -- must not hide every other collection in the
        # file from everybody else. So even describing it is inside the try.
        try:
            definition = loaded.describe(name)
            # A collection with variants gets one row per variant: the two
            # differ by orders of magnitude, and a single total would
            # describe neither.
            variants = loaded.variants(name) or (None,)
        except CollectionError as error:
            unresolved += 1
            print(f"  {name:<28} {'[unresolvable]':>17}   {_first_line(error)}")
            continue
        for variant in variants:
            label = name if variant is None else f"{name} [{variant}]"
            try:
                # The same handle check a fetch runs, so `show` flags a
                # `paths:` mistake before anybody tries to fetch it.
                resources = loaded.select(name, test=variant == "test")
            except (UnknownDataset, IncompleteCatalog, CollectionError) as error:
                unresolved += 1
                print(f"  {label:<28} {'[unresolvable]':>17}   {_first_line(error)}")
                continue
            total = sum(r.bytes for r in resources)
            title = (
                definition.get("title", "") if variant in (None, variants[0]) else ""
            )
            print(
                f"  {label:<28} {len(resources):>4} files  {_human(total):>10}   {title}"
            )
    return 1 if unresolved else 0


def _show_one_collection(args, loaded) -> int:
    """A collection's size and the inputs it names; every file under --files.

    The named inputs come first and the file list is opt-in: a workflow is
    wired up from the handles, and a collection big enough to be worth asking
    about is big enough that its file list buries them.
    """
    resources, label = _selection(args, loaded)
    print(f"{label}: {len(resources)} files, {_human(sum(r.bytes for r in resources))}")
    if args.meta:
        print()
        _print_meta(loaded.catalog, sorted({r.dataset for r in resources}))
        return 0
    title = loaded.describe(args.collection).get("title", "")
    if title:
        print(f"  {title}")
    named = loaded.named_keys(args.collection, test=args.test)
    if named:
        variant = " --test" if args.test and loaded.variants(args.collection) else ""
        print(
            f"\nnamed paths (`{args.prog} fetch {args.collection}{variant} --paths` "
            f"resolves them to this machine):"
        )
        width = max(len(handle) for handle in named)
        for handle, key in named.items():
            print(f"  {handle:<{width}}  ->  {key}")
    if args.files:
        print()
        for resource in resources:
            print(f"  {resource.key:<64} {_human(resource.bytes):>10}")
    elif resources:
        print(f"\n({len(resources)} files; --files lists them)")
    return 0


def _selection(args, loaded):
    """The resources a collection selects, and the label to print them under.

    Resolving is also the check: a ``paths:`` handle the collection cannot
    honour is a mistake in the collections file, and every command must refuse
    it exactly where the Python API does -- before reporting anything, and
    before moving any data.
    """
    resources = loaded.select(args.collection, test=args.test)
    label = args.collection
    if loaded.variants(args.collection):
        label = f"{args.collection} [{variant_name(args.test)}]"
    return resources, label


def _collection_fetch_command(args, loaded, roots) -> int:
    """Make a collection available; --plan describes the transfer instead.

    One parser, one resolution, one report shape for both: what ``--plan``
    prints is what the very next line of code would download.
    """
    resources, label = _selection(args, loaded)
    if args.paths:
        return _paths_command(args, loaded, roots)

    report = plan(loaded.catalog, resources, roots)
    if args.plan:
        print(f"public cache:    {report['root']}")
        for origin, items in sorted(report["in_place_by_origin"].items()):
            print(
                f"used in place:   {len(items):>4} files  "
                f"{_human(sum(r.bytes for r in items)):>10}  ({origin}, never copied)"
            )
        print(
            f"already cached:  {len(report['present']):>4} files  "
            f"{_human(sum(r.bytes for r in report['present'])):>10}"
        )
        print(
            f"to download:     {len(report['missing']):>4} files  "
            f"{_human(report['bytes_to_download']):>10}"
        )
        for resource in report["missing"]:
            print(f"    + {resource.key}")
        if report["unavailable"]:
            names = sorted({r.dataset for r in report["unavailable"]})
            print(
                f"not available here: {len(report['unavailable']):>4} files            "
                f"      ({', '.join(names)} -- a fetch stops here)"
            )
        if report["unreadable"]:
            print(
                f"\nMISSING from where they were expected ({len(report['unreadable'])}):"
            )
            for location in report["unreadable"][:10]:
                print(f"    ! {location.path}   [{location.origin}]")
        return 0

    if report["unavailable"]:
        # Every input is required: stop before anything is printed or fetched,
        # with the refusal that says what the dataset is and how to get it.
        locate(loaded.catalog, resources, roots)
    if not report["missing"]:
        note = (
            f" ({len(report['in_place'])} used in place)" if report["in_place"] else ""
        )
        print(f"{label}: all {len(resources)} files already present{note}")
        loaded.fetch(args.collection, test=args.test, root=roots, progressbar=False)
        return 0
    print(
        f"{label}: fetching {len(report['missing'])} of {len(resources)} files "
        f"({_human(report['bytes_to_download'])}) into {report['root']}"
    )
    loaded.fetch(args.collection, test=args.test, root=roots, progressbar=True)
    print("done.")
    return 0


def _first_line(error: BaseException) -> str:
    """The sentence in an error, for a one-line report.

    UnknownDataset subclasses KeyError, whose str() is a repr -- quoted, with
    newlines escaped -- so args[0] is the real sentence.
    """
    return (error.args[0] if error.args else str(error)).splitlines()[0]


def _paths_command(args, loaded, roots) -> int:
    """Fetch a collection and print its named inputs, one `handle<TAB>path` per line.

    Tab-separated so a shell can read it back -- `while IFS=$'\\t' read handle
    path` -- which is the whole point of naming inputs rather than files. Runs
    on the collections file already loaded, so the catalogue is read once.
    """
    files = loaded.fetch(args.collection, test=args.test, root=roots, progressbar=True)
    if not files.named:
        raise CollectionError(
            f"collection {args.collection!r} declares no named paths -- nothing under 'paths:' "
            f"in its definition. `fetch {args.collection}` gets its files; ask the "
            f"{loaded.tool or 'collections file'} maintainer to name the workflow's inputs."
        )
    for handle, local in files.named.items():
        print(f"{handle}\t{local}")
    return 0


def _path_command(args, catalog: Catalog, roots) -> int:
    """Fetch a catalogue key and print a path suitable for shell use."""
    try:
        print(catalog.path(args.key, root=roots))
    except KeyError as error:
        print(f"error: {error.args[0] if error.args else error}", file=sys.stderr)
        return 2
    return 0


def _ls_command(args, catalog: Catalog) -> int:
    """List what the catalogue holds under a key, fetching nothing."""
    if args.key is None:
        print(f"catalogue: {catalog.location}\n")
        for name, dataset in sorted(catalog.datasets.items()):
            line = f"  {name:<40} {dataset.access:<12} {dataset.title}"
            if dataset.superseded_by:
                line += f"  (superseded by {', '.join(dataset.superseded_by)})"
            print(line)
        return 0
    try:
        resources = catalog.resources(args.key)
    except KeyError as error:
        print(f"error: {error.args[0] if error.args else error}", file=sys.stderr)
        return 2
    if args.meta:
        _print_meta(catalog, sorted({r.dataset for r in resources}))
        return 0
    print(
        f"{args.key}: {len(resources)} files, {_human(sum(r.bytes for r in resources))}\n"
    )
    for resource in resources:
        print(f"  {resource.key:<64} {_human(resource.bytes):>10}")
    return 0


def _verify_command(args, loaded, roots) -> int:
    if not args.collection and not args.all:
        args.all = True
    resources = {}
    skipped = 0
    if args.all:
        # Every collection in every variant: what is on disk is one cache, and
        # a file the test variant selects is as much a file to check as one the
        # full variant does. A variant that cannot be resolved -- a dataset not
        # in this catalogue, say -- is reported and skipped, as `show` does,
        # rather than stopping the check of everything else.
        for name in loaded.names():
            try:
                variants = loaded.variants(name) or (None,)
            except CollectionError as error:
                skipped += 1
                print(f"skipped {name}: {_first_line(error)}")
                continue
            for variant in variants:
                label = name if variant is None else f"{name} [{variant}]"
                try:
                    selected = loaded.resolve(name, test=variant == "test")
                except (UnknownDataset, IncompleteCatalog, CollectionError) as error:
                    skipped += 1
                    print(f"skipped {label}: {_first_line(error)}")
                    continue
                for resource in selected:
                    resources[resource.key] = resource
        if skipped:
            print()
    else:
        for resource in loaded.resolve(args.collection, test=args.test):
            resources[resource.key] = resource
    ordered = sorted(resources.values(), key=lambda r: r.key)

    what = "every collection" if args.all else args.collection
    retry = (
        f"{args.prog} verify {args.collection or '--all'} --repair"
        + (" --deep" if args.deep else "")
        + (" --test" if args.test else "")
    )
    return _report_findings(
        args, loaded.catalog, ordered, roots, what=what, retry=retry, skipped=skipped
    )


def _key_verify_command(args, catalog: Catalog, roots) -> int:
    """Check the files under one catalogue key, as a package's verify checks a collection."""
    resources = catalog.resources(args.key)
    retry = f"ethos-data verify {args.key} --repair" + (" --deep" if args.deep else "")
    return _report_findings(args, catalog, resources, roots, what=args.key, retry=retry)


def _report_findings(
    args, catalog: Catalog, ordered, roots, *, what: str, retry: str, skipped: int = 0
) -> int:
    """Verify ``ordered``, print what was found, and repair it if asked."""
    from .verify import OK, UNAVAILABLE, UNVERIFIABLE, repair, summarise, verify

    how = "checksums" if args.deep else "sizes"
    print(f"verifying {len(ordered):,} files from {what} ({how})\n")

    findings = verify(catalog, ordered, roots, deep=args.deep)
    grouped = summarise(findings)

    for status, group in grouped.items():
        if status == OK and args.quiet:
            continue
        print(f"{status}: {len(group)}")
        if status == OK:
            continue
        for finding in group[:20]:
            print(f"    {finding}")
        if len(group) > 20:
            print(f"    ... and {len(group) - 20} more")

    broken = [f for f in findings if not f.ok]
    unverifiable = [f for f in findings if f.status == UNVERIFIABLE]
    absent = [f for f in findings if f.status == UNAVAILABLE]
    if not broken:
        checked = len(findings) - len(unverifiable) - len(absent)
        print(f"\n{checked:,} file(s) match the catalogue.")
        if absent:
            names = sorted({f.resource.dataset for f in absent})
            print(
                f"{len(absent):,} file(s) were NOT checked -- no access to "
                f"{', '.join(names)} from this machine."
            )
        if unverifiable:
            # Never call these "matching": nothing was compared. Staged data
            # carries no checksums, which is the point of staging and also the
            # reason a result built on it is not reproducible.
            print(
                f"{len(unverifiable):,} file(s) could NOT be checked -- no checksum in "
                f"the manifest (staged data). Describe and publish them to get one."
            )
        if skipped:
            # The files checked are fine, but the check was not complete, and
            # an exit status of 0 would let a CI job believe it was.
            print(
                f"{skipped} collection variant(s) could not be resolved and were skipped "
                f"(see above)."
            )
            return 1
        return 0

    if not args.repair:
        print(f"\n{len(broken)} file(s) do not match. Re-fetch them with:")
        print(f"    {retry}")
        return 1

    outcome = repair(catalog, findings, roots, dry_run=args.dry_run)
    if outcome["links_to_remove"]:
        print("\nthese links will be removed so a download has somewhere to land")
        print("(other people share this cache -- they will be re-fetching too):")
        for link in outcome["links_to_remove"]:
            print(f"    {link} -> {link.readlink()}")
    for key, why in sorted(outcome["skipped"].items()):
        print(f"  not repairable: {key}  ({why})")
    if args.dry_run:
        print(
            f"\nwould re-fetch {len(outcome['resources']):,} file(s). Nothing was changed."
        )
        return 1
    print(f"\nre-fetched {outcome['downloaded']:,} file(s).")
    return 0 if not outcome["skipped"] else 1


def _print_meta(catalog: Catalog, names: list[str]) -> None:
    """Each dataset's description, from its descriptor: nothing is fetched."""
    for index, name in enumerate(names):
        if index:
            print()
        print(name)
        for line in reader_description(catalog.dataset(name).descriptor, classes=True):
            print(f"  {line}")


def _selftest_command(args) -> int:
    """Settings, catalogue, then every file: the first failing step is named."""
    from .selftest import run_selftest

    result = run_selftest(catalog=args.catalog, root=args.root)
    print("1. settings")
    if result.settings is not None:
        roots = result.settings.roots
        for label, value in result.settings.rows():
            marker = ""
            if label == "public cache":
                marker = _reachability(
                    Resolved(roots.public, ""), created_on_demand=True
                )
            elif label == "restricted cache" and roots.restricted:
                marker = _reachability(Resolved(roots.restricted, ""))
            if label not in ("catalogue", "catalogue version"):
                print(f"   {label:<17}  {value}{marker}")
    if result.failed == "settings":
        return _selftest_failed(result)
    print("\n2. catalogue")
    if result.catalog:
        print(f"   {result.catalog}  ({result.catalog_source})")
        print(f"   version {result.version or 'not recorded'}")
    if result.failed == "catalogue":
        return _selftest_failed(result)
    print("\n3. files")
    width = max((len(o.key) for o in result.files), default=0)
    for outcome in result.files:
        check = "" if outcome.ok else f"   [{outcome.status}: {outcome.detail}]"
        print(f"   {outcome.how:<15}  {outcome.key:<{width}}  {outcome.path}{check}")
    if result.failed:
        return _selftest_failed(result)
    print("\nselftest passed")
    return 0


def _selftest_failed(result) -> int:
    print(f"\nselftest FAILED at {result.failed}: {result.error}", file=sys.stderr)
    return 1


def _cache_catalog(args):
    """The catalogue for access by key, chosen as every handle chooses one."""
    return catalog_for(read_settings(root=args.root, catalog=args.catalog))


def _link_all_command(args, roots) -> int:
    """Every dataset in the checkout with a source_dir, into one named cache.

    Which cache that is gets decided here and nowhere else. A top-level
    ``--root``, ``$ETHOS_DATA_DIR`` and the configuration files are read once,
    into ``roots``, and the planner is handed the answer rather than asked to
    work it out again: two lookups in one process can disagree -- the
    environment read at a different moment, or an override the second lookup
    never sees -- and the failure that produces is a complete link tree built in
    a directory nobody asked for, reported as a success. ``--root`` after
    ``link`` overrules that, and is the only thing that does.
    """
    from .maintain import namespace as namespace_module
    from .maintain import resolve_catalog_root

    try:
        catalog_root = resolve_catalog_root(args.catalog_root)
    except CatalogueRootError as error:
        print(f"error: {error.message}", file=sys.stderr)
        return 2

    # Decided only once there is a checkout to link from. A run that ends in
    # "no catalogue here" has chosen nothing, and a line above that error
    # naming a cache reads as a step that did succeed -- so the next thing
    # anyone does is go looking in that directory for links this run never made.
    if args.cache_root is None:
        root = roots.public
        # Names where this answer came from, not whether a flag was typed: a
        # top-level ``ethos-data --root DIR link --all`` reaches here too, with
        # that directory already resolved into ``roots``, and "no --root given"
        # read as a denial of the flag the person had just used.
        print(
            f"no --root after `link`; using the public cache from {roots.public_source}"
        )
    else:
        root = Path(args.cache_root).expanduser()

    return namespace_module.run(
        catalog_root,
        root,
        dry_run=args.dry_run,
        prune=args.prune,
        record=args.catalog_root is not None,
    )


def _link_command(args, roots) -> int:
    from .linking import LinkError, link, unlink

    if args.command == "link":
        if args.all:
            if args.dataset or args.directory:
                print(
                    "--all links every dataset with a source_dir; it takes no names.",
                    file=sys.stderr,
                )
                return 2
            if args.force:
                print(
                    "--force belongs to `ethos-data link <dataset>`. --all already "
                    "repoints a link whose source_dir has moved, and it never "
                    "replaces a real directory -- so there is nothing here for "
                    "--force to overrule.",
                    file=sys.stderr,
                )
                return 2
            return _link_all_command(args, roots)
        if not args.dataset:
            print(
                "name a dataset, or use --all:\n"
                "    ethos-data link <dataset> [directory]\n"
                "    ethos-data link --all\n"
                "    ethos-data link --all --root DIR [--prune]",
                file=sys.stderr,
            )
            return 2
        if args.cache_root is not None or args.prune:
            print(
                "--root and --prune describe a whole cache, not one entry, so "
                "they go with --all:\n"
                "    ethos-data link --all --root DIR --prune\n"
                f"    ethos-data link {args.dataset} [directory]",
                file=sys.stderr,
            )
            return 2

    catalog = _cache_catalog(args)
    try:
        if args.command == "link":
            report = link(
                catalog,
                args.dataset,
                args.directory,
                roots,
                force=args.force,
                catalog_root=args.catalog_root,
                record=args.catalog_root is not None,
            )
        else:
            report = unlink(catalog, args.dataset, roots)
    except (LinkError, UnknownDataset) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    # Flushed, because the warning below goes to stderr: unflushed, the two
    # streams arrive in the opposite order and the warning reads as being about
    # whatever came before it.
    print(f"  {report}", flush=True)
    if args.command == "link":
        _print_recorded([report])
    if report.missing:
        # Not a failure: the link is made, and the person who typed the path is
        # the only one who can say whether it is the right level.
        print(
            f"\nwarning: the catalogue lists {report.missing!r}, which is not under "
            f"{report.target}.\n         Check this is the dataset's own directory, then "
            f"run your package's data command with `verify --deep`.",
            file=sys.stderr,
        )
    return 0


def _print_recorded(reports) -> None:
    """Say what a link or a copy recorded in the checkout's status files."""
    for report in reports:
        if report.recorded:
            print(
                f"  recorded    {report.dataset} is {report.recorded}, in its status.yaml"
            )
    unrecorded = [report.dataset for report in reports if report.unrecorded]
    if unrecorded:
        from .maintain.status import unrecorded as unrecorded_warning

        print(f"warning: {unrecorded_warning(unrecorded)}", file=sys.stderr, flush=True)


def _materialize_command(args, roots) -> int:
    from .materialize import materialize

    catalog = _cache_catalog(args)

    names = list(args.datasets)
    if args.source is not None:
        # One directory holds one dataset's files, so spreading it over several
        # names -- or over whatever --all happens to find -- could only ever mean
        # copying the same bytes into the wrong entries.
        if args.all or len(names) != 1:
            print(
                "--from copies one named dataset:\n"
                "    ethos-data materialize <dataset> --from <directory>",
                file=sys.stderr,
            )
            return 2
    elif args.all or not names:
        if not roots.public.is_dir():
            print(f"no public cache at {roots.public}")
            return 1
        names = sorted(
            name for name, path in cache_entries(roots.public) if path.is_symlink()
        )
        if not names:
            print(
                f"no symbolic-link entries in {roots.public}; nothing to materialise."
            )
            return 0

    reports = materialize(
        catalog,
        names,
        roots,
        force=args.force,
        verify_hashes=not args.no_verify,
        dry_run=args.dry_run,
        source=args.source,
        catalog_root=args.catalog_root,
        record=args.catalog_root is not None,
    )
    for report in reports:
        print(f"  {report}")
        for failure in report.failures[:10]:
            print(f"      ! {failure}")
    _print_recorded(reports)

    total = sum(r.bytes for r in reports if r.action in ("would copy", "materialized"))
    destinations = sorted(
        {
            str(r.entry.parent)
            for r in reports
            if r.entry is not None and r.action in ("would copy", "materialized")
        }
    )
    destination = ", ".join(destinations) or "the configured caches"
    if args.dry_run:
        print(f"\nwould copy {_human(total)} into {destination}. Nothing was written.")
        return (
            1
            if any(r.action in ("unknown", "cannot", "dangling") for r in reports)
            else 0
        )
    failed = [
        r for r in reports if r.action in ("failed", "unknown", "cannot", "dangling")
    ]
    print(f"\ncopied {_human(total)} into {destination}.")
    return 1 if failed else 0


def _staging_command(args) -> int:
    from . import staging

    if args.staging_command == "add":
        staged = staging.add(args.name, args.directory, note=args.note, copy=args.copy)
        # For a copy the entry *is* the data, so staged.target resolves to the
        # entry itself; the source is only interesting as provenance.
        source = Path(args.directory).expanduser().resolve()
        verb = "copied from" if args.copy else "linked to"
        print(f"staged {staged.name!r}: {staged.entry} {verb} {source}")
        print(f"  {staged.files:,} files, {_human(staged.bytes)}")
        if staged.descriptor is not None:
            print(
                f"  wrote {staged.descriptor}: the start of the dataset's description; "
                "fill it in as you learn more"
            )
        print(
            "\nThis shadows the catalogue for that dataset. It is not checksummed and "
            "not reproducible;\nremove it once the data is described and published:"
        )
        print(f"    {args.prog} staging remove {staged.name}")
        return 0

    if args.staging_command == "remove":
        entry = staging.remove(args.name, force=args.force)
        print(f"unstaged {args.name!r} ({entry}).")
        return 0

    root = staging.staging_root()
    if root is None:
        print("no staging root configured.")
        print(f"    {args.prog} config set-staging-cache /path/to/ethos_data_staging")
        return 0

    roots = resolve_roots()
    entries = staging.classify_staged(roots)
    if args.new_only:
        entries = [e for e in entries if e.is_new]

    print(f"staging root:     {root}")
    print(f"official caches:  {roots.public}")
    print(
        f"                  {roots.restricted or '(no restricted cache on this machine)'}\n"
    )
    if not entries:
        print(
            "  (nothing staged)"
            if not args.new_only
            else "  every staged dataset also exists in an official cache."
        )
        return 0

    for staged in entries:
        flag = "  [BROKEN]" if staged.broken else ""
        kind = "link" if staged.is_link else "copy"
        mark = "NOT IN CATALOGUE" if staged.is_new else "shadows official"
        print(
            f"  {staged.name:<28} {staged.files:>6,} files  "
            f"{_human(staged.bytes):>10}  {kind}  [{mark}]{flag}"
        )
        print(f"  {'':<28} -> {staged.target}")
        if staged.official is not None:
            print(f"  {'':<28}    official copy: {staged.official}")
        if staged.note:
            print(f"  {'':<28}    {staged.note}")
        if staged.added:
            print(
                f"  {'':<28}    added {staged.added} by {staged.added_by or 'unknown'}"
            )

    new = [e for e in entries if e.is_new]
    if new:
        print(
            f"\n{len(new)} dataset(s) exist ONLY here. Nothing outside this machine can "
            f"resolve them:"
        )
        print(f"    {', '.join(e.name for e in new)}")
        print(
            "Describe them in the catalogue and publish them before anything they "
            "depend on is deleted."
        )
    return 0


#: How each cache setting is described when it is written or shown.
CACHE_KEYS = {
    PUBLIC_CACHE_KEY: ("public cache", resolve_public_cache),
    RESTRICTED_CACHE_KEY: ("restricted cache", resolve_restricted_cache),
    STAGING_CACHE_KEY: ("staging cache", resolve_staging_cache),
}


def _nothing_set() -> str:
    return f"nothing set in {config_path()}"


def _config_command(args) -> int:
    command = args.config_command

    if command.startswith("set-") and getattr(args, "option_key", None) in CACHE_KEYS:
        key = args.option_key
        label, resolver = CACHE_KEYS[key]
        path = set_option(key, str(Path(args.directory).expanduser()))
        print(f"{key} written to {path}")
        print(f"resolved now: {resolver()}")
        return 0

    if command.startswith("unset-") and getattr(args, "option_key", None) in CACHE_KEYS:
        key = args.option_key
        label, resolver = CACHE_KEYS[key]
        path = unset_option(key)
        print(f"removed from {path}" if path else _nothing_set())
        if key == PUBLIC_CACHE_KEY:
            # The older name lives in the same file and would still win.
            legacy = unset_option(LEGACY_CACHE_KEY)
            if legacy:
                print(f"also removed the older {LEGACY_CACHE_KEY} key from {legacy}")
        print(f"resolved now: {resolver() or '(not set)'}")
        return 0

    if command == "set-publication-url":
        path = set_option(PUBLICATION_URL_KEY, args.url)
        print(f"{PUBLICATION_URL_KEY} written to {path}")
        print(f"bytes will now be fetched from {args.url}")
        return 0

    if command == "unset-publication-url":
        path = unset_option(PUBLICATION_URL_KEY)
        print(f"removed from {path}" if path else _nothing_set())
        return 0

    if command == "set-catalog":
        location = catalog_index(args.location)
        path = set_option(CATALOG_KEY, location)
        print(f"catalog written to {path}")
        print(f"resolved now: {resolve_catalog()[0]}")
        print(
            "Package data commands keep their own collections and use this catalogue "
            "instead of their pin, unless a package-specific override is set."
        )
        return 0

    if command == "unset-catalog":
        path = unset_option(CATALOG_KEY)
        print(f"removed from {path}" if path else _nothing_set())
        return 0

    if command == "set-root":
        path = set_dataset_root(args.dataset, args.directory)
        print(f"dataset_roots[{args.dataset}] written to {path}")
        print(
            f"{args.dataset!r} will now be read from "
            f"{Path(args.directory).expanduser()} and never downloaded"
        )
        return 0

    if command == "unset-root":
        path = unset_dataset_root(args.dataset)
        print(
            f"removed from {path}"
            if path
            else f"no root set for {args.dataset!r} in {config_path()}"
        )
        return 0

    return _config_show()


def _reachability(resolved, *, created_on_demand: bool = False) -> str:
    """The ``[...]`` marker printed after a cache path; empty when all is well."""
    reason = unreachable(resolved.value)
    if reason is None:
        return ""
    if created_on_demand and reason == "does not exist":
        return "   [not created yet -- the first download creates it]"
    return f"   [NOT REACHABLE -- {reason}]"


def _print_cache_top_level(root: Path) -> None:
    """One directory listing of the public cache, never a walk.

    A cache on a network share can hold hundreds of thousands of files, and
    ``config show`` is what people run when something is already wrong, so it
    looks only at the entries directly under the root and finishes in the time
    one listing takes. A family of nested datasets therefore counts once, as its
    directory. On Windows, links served by a Samba share look like plain
    directories, so a count of zero links there says nothing about the Linux
    side.
    """
    try:
        entries = sorted(root.iterdir())
    except OSError as error:
        print(
            f"\npublic cache contents: could not be listed ({error.strerror or error})"
        )
        return
    links = [entry for entry in entries if entry.is_symlink()]
    real = [entry for entry in entries if not entry.is_symlink() and entry.is_dir()]
    print(
        f"\npublic cache holds {len(links)} link(s) and {len(real)} director(ies) "
        "at the top level:"
    )
    for link in links[:10]:
        broken = "   [BROKEN]" if not link.exists() else ""
        print(f"  {link.name:<28} -> {link.readlink()}{broken}")
    if len(links) > 10:
        print(f"  ... and {len(links) - 10} more link(s)")
    for directory in real[:10]:
        print(f"  {directory.name:<28} (directory)")
    if len(real) > 10:
        print(f"  ... and {len(real) - 10} more director(ies)")
    if os.name == "nt" and real and not links:
        print(
            "  (on Windows, links served by a Samba/SMB share appear as plain directories)"
        )


def _config_show() -> int:
    """The settings in effect, where each came from, and whether each cache is there.

    The snapshot every handle takes, printed as a handle would print it, with
    what only a person looking needs on top: whether each cache can be reached,
    the dataset roots that are gone, the precedence, and one listing of the
    public cache.
    """
    settings = read_settings()
    roots = settings.roots
    rows = [row for row in settings.rows() if row[0] != "dataset root"]
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        marker = ""
        if label == "public cache":
            marker = _reachability(Resolved(roots.public, ""), created_on_demand=True)
        elif label == "restricted cache" and roots.restricted:
            marker = _reachability(Resolved(roots.restricted, ""))
        elif label == "restricted cache":
            marker = " -- a workflow that needs licensed data stops and describes it"
        elif label == "staging cache" and roots.staging:
            marker = "   [ACTIVE -- shadows the catalogue]" + _reachability(
                Resolved(roots.staging, "")
            )
        print(f"{label:<{width}}  {value}{marker}")
        if label == "catalogue" and settings.catalog is None:
            print(f"{'':<{width}}  public catalogue: {DEFAULT_CATALOG}")

    if roots.datasets:
        print(
            "\nescape hatch -- datasets read from a per-dataset root (never downloaded):"
        )
        for name, where in sorted(roots.datasets.items()):
            reason = unreachable(Path(where))
            marker = f"   [MISSING -- {reason}]" if reason else ""
            print(f"  {name:<28} {where}{marker}")

    print("\nprecedence for each setting, first match wins:")
    print("  1. an explicit argument   --root / root=, --catalog / catalog=")
    for variable in (
        ENV_VAR,
        RESTRICTED_ENV_VAR,
        STAGING_ENV_VAR,
        CATALOG_ENV_VAR,
    ):
        value = os.environ.get(variable)
        print(f"  2. ${variable:<22} {value or '(unset)'}")
    print(
        f"  3. the settings file      {settings.file}"
        f"  ({'from $' + CONFIG_ENV_VAR if os.environ.get(CONFIG_ENV_VAR) else 'your account'})"
    )
    print(
        "  4. the built-in default   the per-user cache directory (public cache only)"
    )

    print("\nwhere a file is read, first match wins:")
    print(chain_for(roots))

    # Last, because it is the one section that reads the cache itself. On a slow
    # or half-connected network share this is the part that takes time, and
    # everything above must already be on screen when it does.
    reason = unreachable(roots.public)
    if reason is None:
        _print_cache_top_level(roots.public)
    elif reason != "does not exist":
        print(f"\npublic cache contents: not listed -- {reason}")

    print("\nSet them with:")
    print("  ethos-data config set-public-cache     /path")
    print("  ethos-data config set-restricted-cache /path")
    print(
        "  ethos-data config set-staging-cache    /path            # only while developing"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
