"""Fetch catalogued data and manage ETHOS configuration, caches and catalogues.

Use 'ls' to inspect the catalogue and 'fetch' to get a dataset, folder or file
by its catalogue key. Catalogue maintenance and dCache uploads use 'catalog'.
Collections, test bundles and staging belong to a package's own data command,
such as reskit-data, built with ethos_data.tool_main.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

import yaml

from .access import AccessError, cache_entries
from .bundles import BundleError, export_bundle, load_bundle
from .catalogs import (
    Catalog,
    CatalogUnavailable,
    IncompleteCatalog,
    UnknownDataset,
    load_catalog,
)
from .config import (
    DEFAULT_CATALOG,
    ENV_VAR,
    LEGACY_CACHE_KEY,
    PUBLIC_CACHE_KEY,
    RESTRICTED_CACHE_KEY,
    RESTRICTED_ENV_VAR,
    SCOPES,
    SKIP_UNAVAILABLE_KEY,
    STAGING_CACHE_KEY,
    STAGING_ENV_VAR,
    config_sources,
    dataset_roots,
    resolve_catalog,
    resolve_public_cache,
    resolve_restricted_cache,
    resolve_roots,
    resolve_skip_unavailable,
    resolve_staging_cache,
    set_dataset_root,
    set_option,
    unset_dataset_root,
    unset_option,
)
from .maintain.cli import add_catalog_parser
from .maintain.cli import dispatch as _catalog_dispatch
from .retrieval import plan
from .selection import (
    CollectionError,
    Collections,
    CollectionsNotFound,
    UnknownCollection,
    load_collections,
    variant_name,
)


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
) -> int:
    """A tool's own command: the collection commands bound to the file it ships.

    What :func:`ethos_data.tool_main` and :meth:`ethos_data.Collections.main`
    run. The parser offers ``list``, ``info``, ``plan``, ``fetch``, ``paths``
    and ``verify`` for the file's collections, ``path`` and ``ls`` against the
    catalogue it pins, and the ``bundle``, ``staging`` and ``config`` groups.
    Shared cache and catalogue maintenance belong to ``ethos-data``.

    The handle -- and with it the catalogue -- is built only when a command
    needs it, so ``--help`` and ``config show`` work offline and a pin nobody
    can reach can still be overridden with ``--catalog`` for one run.
    ``catalog`` is the tool's own override (``$RESKIT_DATA_CATALOG``), applied
    below ``--catalog`` and above the environment; ``loaded`` is a handle that
    already exists, reused when nothing overrides its catalogue.
    """
    prog = prog or (f"{tool}-data" if tool else "ethos-data")
    source = _ToolSource(file, tool, catalog, loaded)
    return _run(
        lambda: _dispatch(_build_tool_parser(prog, source).parse_args(argv), source)
    )


def _run(command) -> int:
    """Run a parsed command, turning a refusal into a message, not a traceback.

    An AccessError is the catalogue working as designed -- restricted bytes, or
    a local root that is not set up -- and it already carries the sentence the
    user needs plus the command that fixes it. Wrapped in a stack trace, that
    reads like a crash and the advice gets lost in the noise.
    """
    _use_utf8_output()
    try:
        return command()
    except (
        AccessError,
        UnknownDataset,
        IncompleteCatalog,
        CatalogUnavailable,
        BundleError,
        CollectionsNotFound,
        UnknownCollection,
        CollectionError,
    ) as error:
        # UnknownDataset stringifies like a KeyError (quoted), which reads badly
        # on a terminal line that already says "error:".
        message = error.args[0] if error.args else error
        print(f"error: {message}", file=sys.stderr)
        return 2


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
    _add_key_commands(sub, fetch_command="fetch")
    _add_config_commands(sub)
    _add_cache_commands(sub)
    add_catalog_parser(sub)
    return parser


def _build_tool_parser(prog: str, source: _ToolSource) -> argparse.ArgumentParser:
    """A tool's collection, key, bundle, staging and config commands, no ``-c``.

    The file is fixed -- it is the one the tool ships -- so there is nothing to
    name, and the cache-maintenance commands (materialize, link, unlink, the
    maintainer's catalog group) stay with ``ethos-data``: they concern the
    shared cache, not any one tool's data. Built from the file alone: the
    catalogue is not loaded for ``--help``.
    """
    tool = source.tool or prog
    example = (source.names() or ["<collection>"])[0]
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"Find, fetch and check the data {tool} needs.\n\n"
        f"Its collections are defined in {source.file_path}. `list` shows them, "
        f"`paths` fetches one and prints the inputs it names. Data lands in "
        f"the cache every ETHOS tool shares (`{prog} config show`).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Put global options before the subcommand. Examples:\n"
        f"  {prog} list\n"
        f"  {prog} plan {example} --test\n"
        f"  {prog} paths {example} --test\n"
        f"  {prog} ls <dataset>\n"
        f"  {prog} config show\n"
        f"Use '{prog} COMMAND --help' for command options.",
    )
    _add_common_options(parser, tool_commands=True)
    sub = parser.add_subparsers(dest="command", required=True)
    _add_collection_commands(sub)
    _add_key_commands(sub)
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
    parser.add_argument(
        "--skip-unavailable",
        action="store_true",
        default=None,
        help="carry on without data this machine has no access to "
        "(licensed data you have no copy of), "
        "listing what was left out instead of stopping",
    )
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
    """The commands that name a collection, plus ``list``."""
    sub.add_parser("list", help="list the collections this file defines")
    #: The same switch on every command that names a collection, so that
    #: `plan --test` previews exactly what `fetch --test` will do.
    test_flag = {
        "action": "store_true",
        "help": "the collection's small test variant instead of the full data",
    }
    for name, helptext in (
        ("info", "show what a collection contains"),
        ("plan", "preview data transfers (may retrieve catalogue metadata)"),
        ("fetch", "make a collection available, reusing cached or in-place files"),
        (
            "paths",
            "fetch a collection and print the inputs it names, as handle and path",
        ),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("collection")
        p.add_argument("--test", **test_flag)

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


def _add_key_commands(sub, *, fetch_command: str = "path") -> None:
    """The commands that name a dataset, folder or file in the catalogue."""
    pather = sub.add_parser(
        fetch_command,
        help="fetch a dataset, folder or file and print its absolute local path",
    )
    pather.add_argument("key", help="<dataset>/<file or folder>, or a dataset name")
    lister = sub.add_parser(
        "ls",
        help="list datasets, or files under a catalogue key; fetches no data",
        description="What is in a dataset, and what to put after the slash to get one file "
        f"with `{fetch_command}`. Reads catalogue metadata only.",
    )
    lister.add_argument(
        "key",
        nargs="?",
        help="a dataset, family, folder or file (default: list datasets)",
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
    for name in ("fetch", "verify"):
        reader = bundle_sub.add_parser(
            name, help="read or verify a bundle without network access"
        )
        reader.add_argument("directory")
        reader.add_argument("collection")
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
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser(
        "show", help="show configured values and their origins; no network access"
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
        setter.add_argument(
            "--scope",
            choices=SCOPES,
            default="user",
            help="project = nearest project config; user (default) = this account; environment = this conda env "
            "/ venv; site = whole machine",
        )
        setter.set_defaults(option_key=key)
        unsetter = config_sub.add_parser(
            f"unset-{verb}", help="remove the setting again"
        )
        unsetter.add_argument("--scope", choices=SCOPES, default="user")
        unsetter.set_defaults(option_key=key)

    skipper = config_sub.add_parser(
        "set-skip-unavailable",
        help="carry on without licensed data this machine cannot reach (for people "
        "not working on the institute cluster)",
    )
    skipper.add_argument("value", choices=("true", "false"))
    skipper.add_argument("--scope", choices=SCOPES, default="user")
    unskipper = config_sub.add_parser(
        "unset-skip-unavailable", help="remove the setting again"
    )
    unskipper.add_argument("--scope", choices=SCOPES, default="user")

    rooter = config_sub.add_parser(
        "set-root", help="escape hatch: use one dataset from a local directory"
    )
    rooter.add_argument("dataset")
    rooter.add_argument("directory")
    rooter.add_argument("--scope", choices=SCOPES, default="user")
    unrooter = config_sub.add_parser(
        "unset-root", help="stop using a local directory for a dataset"
    )
    unrooter.add_argument("dataset")
    unrooter.add_argument("--scope", choices=SCOPES, default="user")
    puburl = config_sub.add_parser(
        "set-publication-url",
        help="fetch bytes from a different door (e.g. the high-throughput one for CI)",
    )
    puburl.add_argument("url")
    puburl.add_argument("--scope", choices=SCOPES, default="user")
    cataloger = config_sub.add_parser(
        "set-catalog",
        help="set the shared catalogue override, including for package data commands",
    )
    cataloger.add_argument("location", help="a datacatalog.json path or URL")
    cataloger.add_argument("--scope", choices=SCOPES, default="user")
    uncataloger = config_sub.add_parser(
        "unset-catalog", help="remove the setting again"
    )
    uncataloger.add_argument("--scope", choices=SCOPES, default="user")


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
        "entry and no --from (default: search upward for catalog.yaml)",
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
        help="catalogue checkout to read source_dir from "
        "(default: search upward for catalog.yaml)",
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
    ):
        self.file_path = Path(file)
        self.tool = tool
        self.catalog = catalog
        self._loaded = loaded

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
                self.file_path, catalog=args.catalog, roots=roots, tool=self.tool
            )
        if self._loaded is None:
            from . import collections

            self._loaded = collections(
                self.file_path, tool=self.tool, catalog=self.catalog
            )
        return self._loaded

    def catalog_override(self, args) -> str:
        return args.catalog or self.catalog or self.load(args, None).catalog.location

    def key_catalog(self, args, roots) -> Catalog:
        return self.load(args, roots).catalog


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


def _main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "config":
        return _config_command(args)
    if args.command == "catalog":
        return _catalog_dispatch(args)

    roots = resolve_roots(args.root)
    if args.command == "materialize":
        return _materialize_command(args, roots)
    if args.command in ("link", "unlink"):
        return _link_command(args, roots)

    catalog = _cache_catalog(args).overlaid(roots)
    if args.command == "ls":
        return _ls_command(args, catalog)
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
    # (list, ls, path, config, ...) simply ignore it.
    args.test = bool(getattr(args, "test", False) or args.test_global)

    if args.command == "path":
        return _path_command(args, source.key_catalog(args, roots), roots)

    if args.command == "ls":
        return _ls_command(args, source.key_catalog(args, roots))

    loaded = source.load(args, roots)

    if args.command == "list":
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
                    resources = loaded.resolve(name, test=variant == "test")
                    # The same handle check a fetch runs, so `list` flags a
                    # `paths` mistake before anybody tries to fetch it.
                    loaded._named_targets(name, variant == "test", resources)
                except (UnknownDataset, IncompleteCatalog, CollectionError) as error:
                    unresolved += 1
                    print(
                        f"  {label:<28} {'[unresolvable]':>17}   {_first_line(error)}"
                    )
                    continue
                total = sum(r.bytes for r in resources)
                title = (
                    definition.get("title", "")
                    if variant in (None, variants[0])
                    else ""
                )
                print(
                    f"  {label:<28} {len(resources):>4} files  {_human(total):>10}   {title}"
                )
        return 1 if unresolved else 0

    if args.command == "verify":
        return _verify_command(args, loaded, roots)

    if args.command == "paths":
        return _paths_command(args, loaded, roots)

    resources = loaded.resolve(args.collection, test=args.test)
    # Before plan or fetch report anything: a `paths` handle the collection
    # cannot honour is a mistake in collections.yaml, and the command line
    # must refuse it exactly where the Python API does.
    loaded._named_targets(args.collection, args.test, resources)
    label = args.collection
    if loaded.variants(args.collection):
        label = f"{args.collection} [{variant_name(args.test)}]"

    if args.command == "info":
        print(
            f"{label}: {len(resources)} files, {_human(sum(r.bytes for r in resources))}\n"
        )
        for resource in resources:
            print(f"  {resource.key:<64} {_human(resource.bytes):>10}")
        named = loaded.named_keys(args.collection, test=args.test)
        if named:
            print("\nnamed paths (the `paths` command resolves them to this machine):")
            width = max(len(handle) for handle in named)
            for handle, key in named.items():
                print(f"  {handle:<{width}}  ->  {key}")
        return 0

    report = plan(loaded.catalog, resources, roots, args.skip_unavailable)
    if args.command == "plan":
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
                f"      ({', '.join(names)} -- left out)"
            )
        if report["unreadable"]:
            print(
                f"\nMISSING from where they were expected ({len(report['unreadable'])}):"
            )
            for location in report["unreadable"][:10]:
                print(f"    ! {location.path}   [{location.origin}]")
        return 0

    omitted = len(report["unavailable"])
    if omitted:
        names = sorted({r.dataset for r in report["unavailable"]})
        print(
            f"{label}: leaving out {omitted} file(s) from "
            f"{', '.join(names)} -- not available on this machine.",
            file=sys.stderr,
        )
    if not report["missing"]:
        if omitted and omitted == len(resources):
            print(
                f"{label}: nothing to fetch -- none of its {omitted} file(s) is available "
                f"on this machine."
            )
            return 0
        note = (
            f" ({len(report['in_place'])} used in place)" if report["in_place"] else ""
        )
        print(
            f"{label}: all {len(resources) - omitted} available files "
            f"already present{note}"
        )
        loaded.fetch(
            args.collection,
            test=args.test,
            root=roots,
            progressbar=False,
            skip_unavailable=args.skip_unavailable,
        )
        return 0
    print(
        f"{label}: fetching {len(report['missing'])} of {len(resources)} files "
        f"({_human(report['bytes_to_download'])}) into {report['root']}"
    )
    loaded.fetch(
        args.collection,
        test=args.test,
        root=roots,
        progressbar=True,
        skip_unavailable=args.skip_unavailable,
    )
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
    on the collections file already loaded, so the catalogue is read once and
    --skip-unavailable means what it means for `fetch`.
    """
    files = loaded.fetch(
        args.collection,
        test=args.test,
        root=roots,
        progressbar=True,
        skip_unavailable=args.skip_unavailable,
    )
    if not files.named and not files.named.omitted:
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
            print(f"  {name:<40} {dataset.access:<12} {dataset.title}")
        return 0
    try:
        resources = catalog.resources(args.key)
    except KeyError as error:
        print(f"error: {error.args[0] if error.args else error}", file=sys.stderr)
        return 2
    print(
        f"{args.key}: {len(resources)} files, {_human(sum(r.bytes for r in resources))}\n"
    )
    for resource in resources:
        print(f"  {resource.key:<64} {_human(resource.bytes):>10}")
    return 0


def _verify_command(args, loaded, roots) -> int:
    from .verify import OK, UNAVAILABLE, UNVERIFIABLE, repair, summarise, verify

    if not args.collection and not args.all:
        args.all = True
    resources = {}
    skipped = 0
    if args.all:
        # Every collection in every variant: what is on disk is one cache, and
        # a file the test variant selects is as much a file to check as one the
        # full variant does. A variant that cannot be resolved -- a dataset not
        # in this catalogue, say -- is reported and skipped, as `list` does,
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
    how = "checksums" if args.deep else "sizes"
    print(f"verifying {len(ordered):,} files from {what} ({how})\n")

    findings = verify(
        loaded.catalog,
        ordered,
        roots,
        deep=args.deep,
        skip_unavailable=args.skip_unavailable,
    )
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
        print(
            f"    {args.prog} verify {args.collection or '--all'} --repair"
            + (" --deep" if args.deep else "")
            + (" --test" if args.test else "")
        )
        return 1

    outcome = repair(loaded.catalog, findings, roots, dry_run=args.dry_run)
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


def _cache_catalog(args):
    """The explicit or configured catalogue, with the public default as fallback."""
    resolved_catalog = resolve_catalog(args.catalog)
    if resolved_catalog:
        return load_catalog(resolved_catalog[0])
    return load_catalog(DEFAULT_CATALOG)


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
    except SystemExit as error:
        print(f"error: {error}", file=sys.stderr)
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
    )
    for report in reports:
        print(f"  {report}")
        for failure in report.failures[:10]:
            print(f"      ! {failure}")

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


def _resolve_catalog_location(location: str) -> str:
    """Validate a --set-catalog argument, so a typo fails now, not on the next
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
        raise SystemExit(
            f"{candidate} is a directory with no datacatalog.json in it.\n"
            "Point at the generated index file itself, e.g.:\n"
            f"    ethos-data config set-catalog {auto}"
        )
    if not candidate.is_file():
        raise SystemExit(
            f"no such file: {candidate}\n"
            "Expected the generated datacatalog.json inside a catalogue checkout "
            "-- not catalog.yaml (that's hand-written metadata, not the loadable index)."
        )
    return str(candidate)


#: How each cache setting is described when it is written or shown.
CACHE_KEYS = {
    PUBLIC_CACHE_KEY: ("public cache", resolve_public_cache),
    RESTRICTED_CACHE_KEY: ("restricted cache", resolve_restricted_cache),
    STAGING_CACHE_KEY: ("staging cache", resolve_staging_cache),
}


def _config_command(args) -> int:
    command = args.config_command

    if command.startswith("set-") and getattr(args, "option_key", None) in CACHE_KEYS:
        key = args.option_key
        label, resolver = CACHE_KEYS[key]
        path = set_option(key, str(Path(args.directory).expanduser()), scope=args.scope)
        print(f"{key} written to {path}")
        print(f"resolved now: {resolver()}")
        return 0

    if command.startswith("unset-") and getattr(args, "option_key", None) in CACHE_KEYS:
        key = args.option_key
        label, resolver = CACHE_KEYS[key]
        path = unset_option(key, scope=args.scope)
        removed = (
            f"removed from {path}"
            if path
            else f"nothing set in the {args.scope} config"
        )
        print(removed)
        if key == PUBLIC_CACHE_KEY:
            # The legacy name lives in the same files and would still win.
            legacy = unset_option(LEGACY_CACHE_KEY, scope=args.scope)
            if legacy:
                print(f"also removed the older {LEGACY_CACHE_KEY} key from {legacy}")
        print(f"resolved now: {resolver() or '(not set)'}")
        return 0

    if command == "set-skip-unavailable":
        path = set_option(SKIP_UNAVAILABLE_KEY, args.value == "true", scope=args.scope)
        wanted, _ = resolve_skip_unavailable()
        print(f"{SKIP_UNAVAILABLE_KEY} written to {path}")
        if wanted:
            print(
                "Licensed datasets this machine cannot reach will now be left out of "
                "results and listed,\nrather than stopping the command."
            )
        else:
            print("Commands will now stop when licensed data cannot be reached.")
        return 0

    if command == "unset-skip-unavailable":
        path = unset_option(SKIP_UNAVAILABLE_KEY, scope=args.scope)
        print(
            f"removed from {path}"
            if path
            else f"nothing set in the {args.scope} config"
        )
        return 0

    if command == "set-publication-url":
        path = set_option("publication_url", args.url, scope=args.scope)
        print(f"publication_url written to {path}")
        print(f"bytes will now be fetched from {args.url}")
        return 0

    if command == "set-catalog":
        location = _resolve_catalog_location(args.location)
        path = set_option("catalog", location, scope=args.scope)
        print(f"catalog written to {path}")
        print(f"resolved now: {resolve_catalog()[0]}")
        print(
            "Package data commands keep their own collections and use this catalogue "
            "instead of their pin, unless a package-specific override is set."
        )
        return 0

    if command == "unset-catalog":
        path = unset_option("catalog", scope=args.scope)
        print(
            f"removed from {path}"
            if path
            else f"nothing set in the {args.scope} config"
        )
        return 0

    if command == "set-root":
        path = set_dataset_root(args.dataset, args.directory, scope=args.scope)
        print(f"dataset_roots[{args.dataset}] written to {path}")
        print(
            f"{args.dataset!r} will now be read from "
            f"{Path(args.directory).expanduser()} and never downloaded"
        )
        return 0

    if command == "unset-root":
        path = unset_dataset_root(args.dataset, scope=args.scope)
        print(
            f"removed from {path}"
            if path
            else f"no root set for {args.dataset!r} in the {args.scope} config"
        )
        return 0

    return _config_show()


def _unreachable(path: Path) -> str | None:
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


def _reachability(resolved, *, created_on_demand: bool = False) -> str:
    """The ``[...]`` marker printed after a cache path; empty when all is well."""
    reason = _unreachable(resolved.value)
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
    public = resolve_public_cache()
    restricted = resolve_restricted_cache()
    staging = resolve_staging_cache()

    print("the two settings that matter:\n")
    print(
        f"  public cache      {public.value}{_reachability(public, created_on_demand=True)}"
    )
    print(f"                    from {public.source}")
    if restricted:
        print(f"  restricted cache  {restricted.value}{_reachability(restricted)}")
        print(f"                    from {restricted.source}")
    else:
        skipping = resolve_skip_unavailable()[0]
        consequence = (
            "licensed datasets are left out of results and listed"
            if skipping
            else "licensed datasets will refuse to resolve"
        )
        print(f"  restricted cache  (not set -- {consequence})")
        print(
            "                    ethos-data config set-restricted-cache /path --scope environment"
        )
    if staging:
        print(
            f"\n  staging cache     {staging.value}   [ACTIVE -- shadows the catalogue]"
            f"{_reachability(staging)}"
        )
        print(f"                    from {staging.source}")

    skip, skip_source = resolve_skip_unavailable()
    if skip:
        print("\n  unreachable data      left out and listed, not an error")
        print(f"                        from {skip_source}")
    elif not restricted:
        print("\n  unreachable data      stops the command (the default)")
        print(
            "                        ethos-data config set-skip-unavailable true"
            "    # if you are not on the cluster"
        )

    print("\nprecedence for each, first match wins:")
    print("  1. explicit --root / root=      (public cache only)")
    for label, variable in (
        ("public", ENV_VAR),
        ("restricted", RESTRICTED_ENV_VAR),
        ("staging", STAGING_ENV_VAR),
    ):
        value = os.environ.get(variable)
        print(f"  2. ${variable:<22} {value or '(unset)'}   [{label}]")
    for index, (scope, path, exists) in enumerate(config_sources(), start=3):
        marker = "exists" if exists else "not present"
        print(f"  {index}. {scope + ' config':<24} {path}  [{marker}]")
    print(
        f"  {len(SCOPES) + 3}. built-in default          "
        f"per-user OS cache directory (public only)"
    )

    roots = dataset_roots()
    if roots:
        print(
            "\nescape hatch -- datasets read from a per-dataset root (never downloaded):"
        )
        for name, where in sorted(roots.items()):
            reason = _unreachable(Path(where))
            marker = f"   [MISSING -- {reason}]" if reason else ""
            print(f"  {name:<28} {where}{marker}")

    catalog = resolve_catalog()
    if catalog:
        print(f"\ncatalogue: {catalog[0]}  (from {catalog[1]})")
        print(
            "  used instead of whatever the collections file pins for itself; "
            "--catalog overrides it"
        )
    else:
        print(
            "\ncatalogue: the built-in public catalogue for ethos-data; "
            "package data commands use their collections file's pin"
        )
        print(f"  {DEFAULT_CATALOG}")

    # Last, because it is the one section that reads the cache itself. On a slow
    # or half-connected network share this is the part that takes time, and
    # everything above must already be on screen when it does.
    reason = _unreachable(public.value)
    if reason is None:
        _print_cache_top_level(public.value)
    elif reason != "does not exist":
        print(f"\npublic cache contents: not listed -- {reason}")

    print("\nSet them with:")
    print("  ethos-data config set-public-cache     /path --scope site")
    print("  ethos-data config set-restricted-cache /path --scope site")
    print(
        "  ethos-data config set-staging-cache    /path            # only while developing"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
