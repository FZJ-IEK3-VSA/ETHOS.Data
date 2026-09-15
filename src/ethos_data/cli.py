"""Find, fetch, and manage data for ETHOS tools and workflows.

Use collections shipped by a package (-p) or a local collections file (-c).
Local configuration, staging, cache management, and test bundles are available
at the top level. Catalogue maintenance and dCache uploads use 'catalog'.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import (
    ENV_VAR,
    SKIP_UNAVAILABLE_KEY,
    LEGACY_CACHE_KEY,
    PUBLIC_CACHE_KEY,
    RESTRICTED_CACHE_KEY,
    RESTRICTED_ENV_VAR,
    SCOPES,
    STAGING_CACHE_KEY,
    STAGING_ENV_VAR,
    config_sources,
    dataset_roots,
    resolve_catalog,
    resolve_collections,
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
from .bundles import BundleError, export_bundle, load_bundle
from .access import AccessError, cache_entries
from .catalog import UnknownDataset, load_catalog
from .maintain.cli import add_catalog_parser, dispatch as _catalog_dispatch
from .config import DEFAULT_CATALOG
from .retrieval import download, plan
from .selection import CollectionsNotFound, load_collections, package_collections, registered_packages


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
    zentrum Jülich, turned ``ethos-data list > datasets.txt`` into a
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
    """Entry point.  Turns a refusal into a message, not a traceback.

    An AccessError is the catalogue working as designed -- restricted bytes, or
    a local root that is not set up -- and it already carries the sentence the
    user needs plus the command that fixes it. Wrapped in a stack trace, that
    reads like a crash and the advice gets lost in the noise.
    """
    _use_utf8_output()
    try:
        return _main(argv)
    except (AccessError, UnknownDataset, BundleError, CollectionsNotFound) as error:
        # UnknownDataset stringifies like a KeyError (quoted), which reads badly
        # on a terminal line that already says "error:".
        message = error.args[0] if error.args else error
        print(f"error: {message}", file=sys.stderr)
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ethos-data", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Put global options before the subcommand. Examples:\n"
               "  ethos-data config show\n"
               "  ethos-data -p reskit plan onshore_wind\n"
               "  ethos-data --skip-unavailable -p reskit fetch onshore_wind\n"
               "  ethos-data catalog --catalog-root /path/to/source build --check\n"
               "Use 'ethos-data COMMAND --help' for command options.",
    )
    parser.add_argument("-c", "--collections", default=None,
                        help="path to a collections file (default: collections.yaml, "
                             "or a configured default -- see `ethos-data config show`)")
    parser.add_argument("-p", "--package", default=None,
                        help="use the collections file an installed package ships, e.g. -p reskit")
    parser.add_argument("--catalog", default=None,
                        help="datacatalog.json path or URL; overrides configuration and package pins")
    parser.add_argument("--root", default=None, help="override the public cache directory")
    parser.add_argument("--skip-unavailable", action="store_true", default=None,
                        help="carry on without data this machine has no access to "
                             "(licensed data you have no copy of), "
                             "listing what was left out instead of stopping")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list the collections this file defines")
    pather = sub.add_parser(
        "path", help="print the absolute path of a file or folder, fetching it if necessary")
    pather.add_argument("key", help="<dataset>/<file or folder>, or a dataset name")

    bundle = sub.add_parser("bundle", help="repository copies of catalogued test data")
    bundle_sub = bundle.add_subparsers(dest="bundle_command", required=True)
    exporter = bundle_sub.add_parser("export", help="copy selected official data into a new bundle")
    exporter.add_argument("target", help="new directory for the bundle")
    exporter.add_argument("bundle_collections", nargs="+", help="collections to include")
    exporter.add_argument("--source-root", action="append", default=[], metavar="DATASET=PATH",
                          help="verified existing local copy (repeat for each dataset)")
    exporter.add_argument("--source-revision",
                          help="provenance label only; select the revision with --catalog or the collections pin")
    for name in ("fetch", "verify"):
        reader = bundle_sub.add_parser(name, help="read or verify a bundle without network access")
        reader.add_argument("directory")
        reader.add_argument("collection")
        if name == "fetch":
            reader.add_argument("--allow-modified", action="store_true",
                                help="use changed fixture bytes for development, warning about divergence")

    config_parser = sub.add_parser("config", help="show or change catalogue, cache, and access settings")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="show configured values and their origins; no network access")

    for verb, key, blurb in (
        ("cache", PUBLIC_CACHE_KEY, "the public cache (alias of set-public-cache)"),
        ("public-cache", PUBLIC_CACHE_KEY, "where public and internal data is read and downloaded"),
        ("restricted-cache", RESTRICTED_CACHE_KEY, "where licensed data lives; never downloaded"),
        ("staging-cache", STAGING_CACHE_KEY, "where work in progress lives; shadows the catalogue"),
    ):
        setter = config_sub.add_parser(f"set-{verb}", help=f"set {blurb}")
        setter.add_argument("directory")
        setter.add_argument("--scope", choices=SCOPES, default="user",
                            help="project = nearest project config; user (default) = this account; environment = this conda env "
                                 "/ venv; site = whole machine")
        setter.set_defaults(option_key=key)
        unsetter = config_sub.add_parser(f"unset-{verb}", help="remove the setting again")
        unsetter.add_argument("--scope", choices=SCOPES, default="user")
        unsetter.set_defaults(option_key=key)

    skipper = config_sub.add_parser(
        "set-skip-unavailable",
        help="carry on without licensed data this machine cannot reach (for people "
             "not working on the institute cluster)")
    skipper.add_argument("value", choices=("true", "false"))
    skipper.add_argument("--scope", choices=SCOPES, default="user")
    unskipper = config_sub.add_parser("unset-skip-unavailable", help="remove the setting again")
    unskipper.add_argument("--scope", choices=SCOPES, default="user")

    rooter = config_sub.add_parser(
        "set-root", help="escape hatch: use one dataset from a local directory")
    rooter.add_argument("dataset")
    rooter.add_argument("directory")
    rooter.add_argument("--scope", choices=SCOPES, default="user")
    unrooter = config_sub.add_parser("unset-root", help="stop using a local directory for a dataset")
    unrooter.add_argument("dataset")
    unrooter.add_argument("--scope", choices=SCOPES, default="user")
    puburl = config_sub.add_parser(
        "set-publication-url",
        help="fetch bytes from a different door (e.g. the high-throughput one for CI)")
    puburl.add_argument("url")
    puburl.add_argument("--scope", choices=SCOPES, default="user")
    cataloger = config_sub.add_parser(
        "set-catalog",
        help="set the catalogue override; -c/-p still selects the collections")
    cataloger.add_argument("location", help="a datacatalog.json path or URL")
    cataloger.add_argument("--scope", choices=SCOPES, default="user")
    uncataloger = config_sub.add_parser("unset-catalog", help="remove the setting again")
    uncataloger.add_argument("--scope", choices=SCOPES, default="user")
    collectioner = config_sub.add_parser(
        "set-collections",
        help="permanently point at a collections file, so -c does not need it every time")
    collectioner.add_argument("path")
    collectioner.add_argument("--scope", choices=SCOPES, default="user")
    uncollectioner = config_sub.add_parser("unset-collections", help="remove the setting again")
    uncollectioner.add_argument("--scope", choices=SCOPES, default="user")

    for name, helptext in (
        ("info", "show what a collection contains"),
        ("plan", "preview data transfers (may retrieve catalogue metadata)"),
        ("fetch", "make a collection available, reusing cached or in-place files"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("collection")

    verifier = sub.add_parser(
        "verify", help="check file sizes, or SHA-256 hashes with --deep",
        description="Check selected files without changing them unless --repair is given. "
                    "No collection means every collection in the selected file.")
    verifier.add_argument("collection", nargs="?", help="a collection (default: --all)")
    verifier.add_argument("--all", action="store_true", help="every collection in the file")
    verifier.add_argument("--deep", action="store_true",
                          help="compare checksums, not just sizes (reads every byte)")
    verifier.add_argument("--repair", action="store_true",
                          help="re-fetch repairable data; may remove public-cache links; preview with --dry-run")
    verifier.add_argument("--dry-run", action="store_true",
                          help="with --repair: say what would be re-fetched, change nothing")
    verifier.add_argument("-q", "--quiet", action="store_true", help="only report problems")

    material = sub.add_parser(
        "materialize",
        help="copy catalogued files into the cache from a link or local source",
        description="Copy a complete dataset and verify it before replacing a cache link. "
                    "The original is kept. Explicit restricted datasets use the restricted root.")
    material.add_argument("datasets", nargs="*", help="dataset names (default: --all)")
    material.add_argument("--all", action="store_true",
                          help="every entry in the public cache that is currently a link")
    material.add_argument("--dry-run", action="store_true", help="show the cost, copy nothing")
    material.add_argument("--force", action="store_true",
                          help="compatibility option; existing real directories are still skipped")
    material.add_argument("--no-verify", action="store_true",
                          help="skip checksum verification of each copied file (not advised)")
    # `from` is a keyword, so the destination has to be named explicitly.
    material.add_argument("--from", dest="source", metavar="DIR", default=None,
                          help="copy from this directory instead of the entry's link target; "
                               "fills an entry that does not exist yet")
    material.add_argument("--catalog-root", default=None,
                          help="catalogue checkout to read source_dir from, when there is no "
                               "entry and no --from (default: search upward for catalog.yaml)")

    linker = sub.add_parser(
        "link",
        help="point cache entries at data already on this machine")
    linker.add_argument("dataset", nargs="?",
                        help="dataset name (omit with --all)")
    linker.add_argument("directory", nargs="?",
                        help="the directory to link to (default: the catalogue's source_dir)")
    linker.add_argument("--all", action="store_true",
                        help="link every dataset in the source catalogue that has a source_dir")
    linker.add_argument("--force", action="store_true",
                        help="repoint an entry that is already a link")
    linker.add_argument("--dry-run", action="store_true",
                        help="only honoured with --all; single-dataset link applies immediately")
    # Named as the maintainer commands name it, because it is the same thing: the
    # checkout holding dataset.yaml. source_dir is popped out of a descriptor when
    # it is built, so the hand-written file is the only place it exists.
    linker.add_argument("--catalog-root", default=None,
                        help="catalogue checkout to read source_dir from "
                             "(default: search upward for catalog.yaml)")
    unlinker = sub.add_parser(
        "unlink", help="remove a cache entry that is a link; never a real directory")
    unlinker.add_argument("dataset")

    add_catalog_parser(sub)

    stager = sub.add_parser("staging", help="local development data that adds to or shadows the catalogue")
    stager_sub = stager.add_subparsers(dest="staging_command", required=True)
    adder = stager_sub.add_parser("add", help="register a directory as a staged dataset")
    adder.add_argument("name")
    adder.add_argument("directory")
    adder.add_argument("--note", default="", help="what this is, for the next person")
    adder.add_argument("--copy", action="store_true",
                       help="copy the data instead of linking to it")
    lister = stager_sub.add_parser("list", help="show what is staged")
    lister.add_argument("--new-only", action="store_true",
                        help="only datasets with no entry in the public or restricted "
                             "cache -- the ones that still need describing")
    remover = stager_sub.add_parser("remove", help="unregister a staged dataset")
    remover.add_argument("name")
    remover.add_argument("--force", action="store_true",
                         help="required if the entry is a real directory, not a link")
    return parser


def _bundle_command(args) -> int:
    if args.bundle_command == "export":
        roots = {}
        for item in args.source_root:
            name, sep, directory = item.partition("=")
            if not sep or not name or not directory or name in roots:
                raise BundleError("--source-root must be a unique DATASET=PATH entry")
            roots[name] = directory
        configured = resolve_catalog(args.catalog)
        bundle = export_bundle(
            _collections_file(args),
            args.bundle_collections, args.target,
            catalog=configured[0] if configured else None,
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


def _collections_file(args) -> str:
    """The collections file to read: the one -p's package ships, else -c, a
    configured default, or ./collections.yaml."""
    if args.package and args.collections:
        raise CollectionsNotFound("give -c/--collections or -p/--package, not both")
    if args.package:
        return str(package_collections(args.package))
    resolved = resolve_collections(args.collections)
    chosen = resolved[0] if resolved else "collections.yaml"
    if not Path(chosen).is_file():
        packages = ", ".join(sorted(registered_packages())) or "none installed"
        raise CollectionsNotFound(
            f"no collections file at {chosen}. Name an installed package with -p "
            f"(registered: {packages}), or a file with -c."
        )
    return chosen


def _load(args, roots):
    """The collections file, with the catalogue it pins and staging applied."""
    resolved_catalog = resolve_catalog(args.catalog)
    catalog = resolved_catalog[0] if resolved_catalog else None
    return load_collections(_collections_file(args), catalog=catalog, roots=roots)


def _main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "bundle":
        return _bundle_command(args)
    if args.command == "config":
        return _config_command(args)
    if args.command == "staging":
        return _staging_command(args)
    # Before the cache roots are resolved: a maintainer command works on a
    # catalogue checkout, and has no use for the consumer's cache directories.
    if args.command == "catalog":
        return _catalog_dispatch(args)

    roots = resolve_roots(args.root)

    if args.command == "path":
        from . import path as fetch_path

        try:
            print(fetch_path(args.key, package=args.package, catalog=args.catalog, root=roots))
        except KeyError as error:
            # A key naming no file or folder: a message, like UnknownDataset.
            print(f"error: {error.args[0] if error.args else error}", file=sys.stderr)
            return 2
        return 0

    if args.command == "materialize":
        return _materialize_command(args, roots)

    if args.command in ("link", "unlink"):
        return _link_command(args, roots)

    loaded = _load(args, roots)

    if args.command == "list":
        print(f"catalogue: {loaded.catalog.location}")
        print(f"cache:     {roots.public}\n")
        unresolved = 0
        for name in loaded.names():
            definition = loaded.describe(name)
            try:
                resources = loaded.resolve(name)
            except UnknownDataset as error:
                # One collection naming a dataset this catalogue lacks -- a
                # withdrawn dataset, or one that only exists in somebody's
                # staging root -- must not hide every other collection in the
                # file from everybody else.
                unresolved += 1
                # UnknownDataset subclasses KeyError, whose str() is a repr --
                # quoted, with newlines escaped. args[0] is the real sentence.
                message = (error.args[0] if error.args else str(error)).splitlines()[0]
                print(f"  {name:<28} {'[unresolvable]':>17}   {message}")
                continue
            total = sum(r.bytes for r in resources)
            print(f"  {name:<28} {len(resources):>4} files  {_human(total):>10}   "
                  f"{definition.get('title','')}")
        return 1 if unresolved else 0

    if args.command == "verify":
        return _verify_command(args, loaded, roots)

    resources = loaded.resolve(args.collection)

    if args.command == "info":
        print(f"{args.collection}: {len(resources)} files, "
              f"{_human(sum(r.bytes for r in resources))}\n")
        for resource in resources:
            print(f"  {resource.key:<64} {_human(resource.bytes):>10}")
        return 0

    report = plan(loaded.catalog, resources, roots, args.skip_unavailable)
    if args.command == "plan":
        print(f"public cache:    {report['root']}")
        for origin, items in sorted(report["in_place_by_origin"].items()):
            print(f"used in place:   {len(items):>4} files  "
                  f"{_human(sum(r.bytes for r in items)):>10}  ({origin}, never copied)")
        print(f"already cached:  {len(report['present']):>4} files  "
              f"{_human(sum(r.bytes for r in report['present'])):>10}")
        print(f"to download:     {len(report['missing']):>4} files  "
              f"{_human(report['bytes_to_download']):>10}")
        for resource in report["missing"]:
            print(f"    + {resource.key}")
        if report["unavailable"]:
            names = sorted({r.dataset for r in report["unavailable"]})
            print(f"not available here: {len(report['unavailable']):>4} files            "
                  f"      ({', '.join(names)} -- left out)")
        if report["unreadable"]:
            print(f"\nMISSING from where they were expected ({len(report['unreadable'])}):")
            for location in report["unreadable"][:10]:
                print(f"    ! {location.path}   [{location.origin}]")
        return 0

    omitted = len(report["unavailable"])
    if omitted:
        names = sorted({r.dataset for r in report["unavailable"]})
        print(f"{args.collection}: leaving out {omitted} file(s) from "
              f"{', '.join(names)} -- not available on this machine.", file=sys.stderr)
    if not report["missing"]:
        note = f" ({len(report['in_place'])} used in place)" if report["in_place"] else ""
        print(f"{args.collection}: all {len(resources) - omitted} available files "
              f"already present{note}")
        download(loaded.catalog, resources, root=roots, progressbar=False,
                 skip_unavailable=args.skip_unavailable)
        return 0
    print(f"{args.collection}: fetching {len(report['missing'])} of {len(resources)} files "
          f"({_human(report['bytes_to_download'])}) into {report['root']}")
    download(loaded.catalog, resources, root=roots, skip_unavailable=args.skip_unavailable)
    print("done.")
    return 0


def _verify_command(args, loaded, roots) -> int:
    from .verify import OK, UNAVAILABLE, UNVERIFIABLE, repair, summarise, verify

    if not args.collection and not args.all:
        args.all = True
    names = loaded.names() if args.all else [args.collection]
    resources = {}
    for name in names:
        for resource in loaded.resolve(name):
            resources[resource.key] = resource
    ordered = sorted(resources.values(), key=lambda r: r.key)

    what = "every collection" if args.all else args.collection
    how = "checksums" if args.deep else "sizes"
    print(f"verifying {len(ordered):,} files from {what} ({how})\n")

    findings = verify(loaded.catalog, ordered, roots, deep=args.deep,
                      skip_unavailable=args.skip_unavailable)
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
            print(f"{len(absent):,} file(s) were NOT checked -- no access to "
                  f"{', '.join(names)} from this machine.")
        if unverifiable:
            # Never call these "matching": nothing was compared. Staged data
            # carries no checksums, which is the point of staging and also the
            # reason a result built on it is not reproducible.
            print(f"{len(unverifiable):,} file(s) could NOT be checked -- no checksum in "
                  f"the manifest (staged data). Describe and publish them to get one.")
        return 0

    if not args.repair:
        print(f"\n{len(broken)} file(s) do not match. Re-fetch them with:")
        print("    ethos-data verify --repair" + (" --deep" if args.deep else ""))
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
        print(f"\nwould re-fetch {len(outcome['resources']):,} file(s). Nothing was changed.")
        return 1
    print(f"\nre-fetched {outcome['downloaded']:,} file(s).")
    return 0 if not outcome["skipped"] else 1


def _cache_catalog(args, roots):
    """The catalogue for a command that works on cache entries by name.

    These commands take a dataset name rather than a collection, so an explicit
    --catalog wins; a collections file is consulted only because it pins the
    catalogue version a project is working against.
    """
    resolved_catalog = resolve_catalog(args.catalog)
    if resolved_catalog:
        return load_catalog(resolved_catalog[0])
    if (args.package or args.collections or resolve_collections()
            or Path("collections.yaml").is_file()):
        return _load(args, roots).catalog
    return load_catalog(DEFAULT_CATALOG)


def _link_all_command(args, roots) -> int:
    """Every dataset in the checkout with a source_dir, into the configured cache.

    This is `catalog link-cache` pointed at the cache this machine already reads,
    rather than a root typed out by hand -- the same planner, so the two can never
    disagree about what a namespace should look like, and restricted datasets are
    skipped here exactly as they are there.
    """
    import argparse

    from .maintain import resolve_catalog_root
    from .maintain import namespace as namespace_module

    try:
        catalog_root = resolve_catalog_root(args.catalog_root)
    except SystemExit as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return namespace_module.run(catalog_root, argparse.Namespace(
        root=str(roots.public), dry_run=args.dry_run, prune=False))


def _link_command(args, roots) -> int:
    from .linking import LinkError, link, unlink

    if args.command == "link":
        if args.all:
            if args.dataset or args.directory:
                print("--all links every dataset with a source_dir; it takes no names.",
                      file=sys.stderr)
                return 2
            return _link_all_command(args, roots)
        if not args.dataset:
            print("name a dataset, or use --all:\n"
                  "    ethos-data link <dataset> [directory]\n"
                  "    ethos-data link --all", file=sys.stderr)
            return 2

    catalog = _cache_catalog(args, roots)
    try:
        if args.command == "link":
            report = link(catalog, args.dataset, args.directory, roots,
                          force=args.force, catalog_root=args.catalog_root)
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
        print(f"\nwarning: the catalogue lists {report.missing!r}, which is not under "
              f"{report.target}.\n         Check this is the dataset's own directory, then "
              f"run `ethos-data verify --deep`.", file=sys.stderr)
    return 0


def _materialize_command(args, roots) -> int:
    from .materialize import materialize

    catalog = _cache_catalog(args, roots)

    names = list(args.datasets)
    if args.source is not None:
        # One directory holds one dataset's files, so spreading it over several
        # names -- or over whatever --all happens to find -- could only ever mean
        # copying the same bytes into the wrong entries.
        if args.all or len(names) != 1:
            print("--from copies one named dataset:\n"
                  "    ethos-data materialize <dataset> --from <directory>", file=sys.stderr)
            return 2
    elif args.all or not names:
        if not roots.public.is_dir():
            print(f"no public cache at {roots.public}")
            return 1
        names = sorted(name for name, path in cache_entries(roots.public) if path.is_symlink())
        if not names:
            print(f"no symbolic-link entries in {roots.public}; nothing to materialise.")
            return 0

    reports = materialize(
        catalog, names, roots,
        force=args.force, verify_hashes=not args.no_verify, dry_run=args.dry_run,
        source=args.source, catalog_root=args.catalog_root,
    )
    for report in reports:
        print(f"  {report}")
        for failure in report.failures[:10]:
            print(f"      ! {failure}")

    total = sum(r.bytes for r in reports if r.action in ("would copy", "materialized"))
    destinations = sorted({str(r.entry.parent) for r in reports
                           if r.entry is not None and r.action in ("would copy", "materialized")})
    destination = ", ".join(destinations) or "the configured caches"
    if args.dry_run:
        print(f"\nwould copy {_human(total)} into {destination}. Nothing was written.")
        return 1 if any(r.action in ("unknown", "cannot", "dangling") for r in reports) else 0
    failed = [r for r in reports if r.action in ("failed", "unknown", "cannot", "dangling")]
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
        print("\nThis shadows the catalogue for that dataset. It is not checksummed and "
              "not reproducible;\nremove it once the data is described and published:")
        print(f"    ethos-data staging remove {staged.name}")
        return 0

    if args.staging_command == "remove":
        entry = staging.remove(args.name, force=args.force)
        print(f"unstaged {args.name!r} ({entry}). The data it pointed at was not touched.")
        return 0

    root = staging.staging_root()
    if root is None:
        print("no staging root configured.")
        print("    ethos-data config set-staging-cache /path/to/ethos_data_staging")
        return 0

    roots = resolve_roots()
    entries = staging.classify_staged(roots)
    if args.new_only:
        entries = [e for e in entries if e.is_new]

    print(f"staging root:     {root}")
    print(f"official caches:  {roots.public}")
    print(f"                  {roots.restricted or '(no restricted cache on this machine)'}\n")
    if not entries:
        print("  (nothing staged)" if not args.new_only
              else "  every staged dataset also exists in an official cache.")
        return 0

    for staged in entries:
        flag = "  [BROKEN]" if staged.broken else ""
        kind = "link" if staged.is_link else "copy"
        mark = "NOT IN CATALOGUE" if staged.is_new else "shadows official"
        print(f"  {staged.name:<28} {staged.files:>6,} files  "
              f"{_human(staged.bytes):>10}  {kind}  [{mark}]{flag}")
        print(f"  {'':<28} -> {staged.target}")
        if staged.official is not None:
            print(f"  {'':<28}    official copy: {staged.official}")
        if staged.note:
            print(f"  {'':<28}    {staged.note}")
        if staged.added:
            print(f"  {'':<28}    added {staged.added} by {staged.added_by or 'unknown'}")

    new = [e for e in entries if e.is_new]
    if new:
        print(f"\n{len(new)} dataset(s) exist ONLY here. Nothing outside this machine can "
              f"resolve them:")
        print(f"    {', '.join(e.name for e in new)}")
        print("Describe them in the catalogue and publish them before anything they "
              "depend on is deleted.")
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
        removed = f"removed from {path}" if path else f"nothing set in the {args.scope} config"
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
            print("Licensed datasets this machine cannot reach will now be left out of "
                  "results and listed,\nrather than stopping the command.")
        else:
            print("Commands will now stop when licensed data cannot be reached.")
        return 0

    if command == "unset-skip-unavailable":
        path = unset_option(SKIP_UNAVAILABLE_KEY, scope=args.scope)
        print(f"removed from {path}" if path else f"nothing set in the {args.scope} config")
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
        print("-c/--collections still selects which collections file to read; this "
              "overrides the catalogue it pins for itself, the same way --catalog does.")
        return 0

    if command == "unset-catalog":
        path = unset_option("catalog", scope=args.scope)
        print(f"removed from {path}" if path else f"nothing set in the {args.scope} config")
        return 0

    if command == "set-collections":
        candidate = Path(args.path).expanduser()
        if not candidate.is_file():
            raise SystemExit(f"no such file: {candidate}")
        path = set_option("collections", str(candidate), scope=args.scope)
        print(f"collections written to {path}")
        print(f"resolved now: {resolve_collections()[0]}")
        print("-c/--collections still overrides this for a single run.")
        return 0

    if command == "unset-collections":
        path = unset_option("collections", scope=args.scope)
        print(f"removed from {path}" if path else f"nothing set in the {args.scope} config")
        return 0

    if command == "set-root":
        path = set_dataset_root(args.dataset, args.directory, scope=args.scope)
        print(f"dataset_roots[{args.dataset}] written to {path}")
        print(f"{args.dataset!r} will now be read from "
              f"{Path(args.directory).expanduser()} and never downloaded")
        return 0

    if command == "unset-root":
        path = unset_dataset_root(args.dataset, scope=args.scope)
        print(f"removed from {path}" if path
              else f"no root set for {args.dataset!r} in the {args.scope} config")
        return 0

    return _config_show()


def _config_show() -> int:
    public = resolve_public_cache()
    restricted = resolve_restricted_cache()
    staging = resolve_staging_cache()

    print("the two settings that matter:\n")
    print(f"  public cache      {public.value}")
    print(f"                    from {public.source}")
    if restricted:
        print(f"  restricted cache  {restricted.value}")
        print(f"                    from {restricted.source}")
    else:
        skipping = resolve_skip_unavailable()[0]
        consequence = ("licensed datasets are left out of results and listed"
                       if skipping else "licensed datasets will refuse to resolve")
        print(f"  restricted cache  (not set -- {consequence})")
        print("                    ethos-data config set-restricted-cache /path --scope environment")
    if staging:
        print(f"\n  staging cache     {staging.value}   [ACTIVE -- shadows the catalogue]")
        print(f"                    from {staging.source}")

    skip, skip_source = resolve_skip_unavailable()
    if skip:
        print("\n  unreachable data      left out and listed, not an error")
        print(f"                        from {skip_source}")
    elif not restricted:
        print("\n  unreachable data      stops the command (the default)")
        print("                        ethos-data config set-skip-unavailable true"
              "    # if you are not on the cluster")

    print("\nprecedence for each, first match wins:")
    print("  1. explicit --root / root=      (public cache only)")
    for label, variable in (("public", ENV_VAR), ("restricted", RESTRICTED_ENV_VAR),
                            ("staging", STAGING_ENV_VAR)):
        value = os.environ.get(variable)
        print(f"  2. ${variable:<22} {value or '(unset)'}   [{label}]")
    for index, (scope, path, exists) in enumerate(config_sources(), start=3):
        marker = "exists" if exists else "not present"
        print(f"  {index}. {scope + ' config':<24} {path}  [{marker}]")
    print(f"  {len(SCOPES) + 3}. built-in default          "
          f"per-user OS cache directory (public only)")

    roots = dataset_roots()
    if roots:
        print("\nescape hatch -- datasets read from a per-dataset root (never downloaded):")
        for name, where in sorted(roots.items()):
            exists = "" if Path(where).is_dir() else "   [MISSING]"
            print(f"  {name:<28} {where}{exists}")

    if public.value.is_dir():
        entries = cache_entries(public.value)
        links = sorted((n, p) for n, p in entries if p.is_symlink())
        real = sorted((n, p) for n, p in entries if not p.is_symlink())
        print(f"\npublic cache holds {len(links)} link(s) and {len(real)} real director(ies):")
        for name, link in links[:10]:
            broken = "   [BROKEN]" if not link.exists() else ""
            print(f"  {name:<28} -> {link.readlink()}{broken}")
        if len(links) > 10:
            print(f"  ... and {len(links) - 10} more")

    catalog = resolve_catalog()
    if catalog:
        print(f"\ncatalogue: {catalog[0]}  (from {catalog[1]})")
        print("  used instead of whatever -c/-p pins for itself; --catalog overrides it")
    else:
        print("\ncatalogue: the version -c/-p pins, else the built-in public catalogue")
        print(f"  {DEFAULT_CATALOG}")
    collections = resolve_collections()
    if collections:
        exists = "" if Path(collections[0]).is_file() else "   [MISSING]"
        print(f"\ndefault collections file: {collections[0]}{exists}  (from {collections[1]})")
        print("  used when -c/--collections is not given")

    print("\nSet them with:")
    print("  ethos-data config set-public-cache     /path --scope site")
    print("  ethos-data config set-restricted-cache /path --scope site")
    print("  ethos-data config set-staging-cache    /path            # only while developing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
