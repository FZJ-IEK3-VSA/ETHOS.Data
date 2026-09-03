"""Command line interface: ``ice2-data list|info|plan|fetch``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import (
    ENV_VAR,
    SCOPES,
    config_path,
    config_sources,
    dataset_roots,
    resolve_cache_dir,
    resolve_catalog,
    resolve_collections,
    set_dataset_root,
    set_option,
    unset_dataset_root,
    unset_option,
)
from .access import AccessError
from .catalog import UnknownDataset
from .fetch import cache_dir, download, plan
from .selection import load_collections


def _human(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def main(argv: list[str] | None = None) -> int:
    """Entry point.  Turns a refusal into a message, not a traceback.

    An AccessError is the catalogue working as designed -- restricted bytes, or
    a local root that is not set up -- and it already carries the sentence the
    user needs plus the command that fixes it. Wrapped in a stack trace, that
    reads like a crash and the advice gets lost in the noise.
    """
    try:
        return _main(argv)
    except (AccessError, UnknownDataset) as error:
        # UnknownDataset stringifies like a KeyError (quoted), which reads badly
        # on a terminal line that already says "error:".
        message = error.args[0] if error.args else error
        print(f"error: {message}", file=sys.stderr)
        return 2


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ice2-data", description=__doc__)
    parser.add_argument("-c", "--collections", default=None,
                        help="path to a collections file (default: collections.yaml, "
                             "or a configured default -- see `ice2-data config show`)")
    parser.add_argument("--catalog", default=None, help="override the catalogue location")
    parser.add_argument("--root", default=None, help="override the cache directory")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list the collections this file defines")

    config_parser = sub.add_parser("config", help="show or change where the cache lives")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="show the resolved cache directory and why")
    setter = config_sub.add_parser("set-cache", help="set the cache directory persistently")
    setter.add_argument("directory")
    setter.add_argument("--scope", choices=SCOPES, default="user",
                        help="user (default) = this account; environment = this conda env / venv; site = whole machine")
    unsetter = config_sub.add_parser("unset-cache", help="remove the setting again")
    unsetter.add_argument("--scope", choices=SCOPES, default="user")
    rooter = config_sub.add_parser(
        "set-root", help="use a dataset from a local directory instead of downloading it")
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
        help="permanently point at a catalogue, so -c/--catalog do not need it every time")
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

    for name, helptext in (("info", "show what a collection contains"), ("plan", "show what a fetch would download"), ("fetch", "download a collection")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("collection")
    args = parser.parse_args(argv)

    if args.command == "config":
        return _config_command(args)

    resolved_catalog = resolve_catalog(args.catalog)
    catalog = resolved_catalog[0] if resolved_catalog else None
    resolved_collections = resolve_collections(args.collections)
    collections_file = resolved_collections[0] if resolved_collections else "collections.yaml"
    loaded = load_collections(collections_file, catalog=catalog)
    root = Path(args.root).expanduser() if args.root else cache_dir()

    if args.command == "list":
        print(f"catalogue: {loaded.catalog.location}")
        print(f"cache:     {root}\n")
        for name in loaded.names():
            definition = loaded.describe(name)
            resources = loaded.resolve(name)
            total = sum(r.bytes for r in resources)
            print(f"  {name:<28} {len(resources):>4} files  {_human(total):>10}   {definition.get('title','')}")
        return 0

    resources = loaded.resolve(args.collection)

    if args.command == "info":
        print(f"{args.collection}: {len(resources)} files, {_human(sum(r.bytes for r in resources))}\n")
        for resource in resources:
            print(f"  {resource.key:<64} {_human(resource.bytes):>10}")
        return 0

    report = plan(loaded.catalog, resources, root)
    if args.command == "plan":
        print(f"cache root:      {report['root']}")
        if report["in_place"]:
            print(f"used in place:   {len(report['in_place']):>4} files  "
                  f"{_human(sum(r.bytes for r in report['in_place'])):>10}  (local root, never copied)")
        print(f"already cached:  {len(report['present']):>4} files  "
              f"{_human(sum(r.bytes for r in report['present'])):>10}")
        print(f"to download:     {len(report['missing']):>4} files  {_human(report['bytes_to_download']):>10}")
        for resource in report["missing"]:
            print(f"    + {resource.key}")
        if report["unreadable"]:
            print(f"\nMISSING from their local root ({len(report['unreadable'])}):")
            for location in report["unreadable"][:10]:
                print(f"    ! {location.path}")
        return 0

    if not report["missing"]:
        note = f" ({len(report['in_place'])} used in place)" if report["in_place"] else ""
        print(f"{args.collection}: all {len(resources)} files already available{note}")
        download(loaded.catalog, resources, root=root, progressbar=False)
        return 0
    print(f"{args.collection}: fetching {len(report['missing'])} of {len(resources)} files "
          f"({_human(report['bytes_to_download'])}) into {report['root']}")
    download(loaded.catalog, resources, root=root)
    print("done.")
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
            f"    ice2-data config set-catalog {auto}"
        )
    if not candidate.is_file():
        raise SystemExit(
            f"no such file: {candidate}\n"
            "Expected the generated datacatalog.json inside a catalogue checkout "
            "-- not catalog.yaml (that's hand-written metadata, not the loadable index)."
        )
    return str(candidate)


def _config_command(args) -> int:
    if args.config_command == "set-cache":
        path = set_option("cache_dir", str(Path(args.directory).expanduser()), scope=args.scope)
        print(f"cache_dir written to {path}")
        print(f"resolved now: {resolve_cache_dir()}")
        return 0

    if args.config_command == "set-publication-url":
        path = set_option("publication_url", args.url, scope=args.scope)
        print(f"publication_url written to {path}")
        print(f"bytes will now be fetched from {args.url}")
        return 0

    if args.config_command == "set-catalog":
        location = _resolve_catalog_location(args.location)
        path = set_option("catalog", location, scope=args.scope)
        print(f"catalog written to {path}")
        print(f"resolved now: {resolve_catalog()[0]}")
        print("-c/--collections still selects which collections file to read; this "
              "overrides the catalogue it pins for itself, the same way --catalog does.")
        return 0

    if args.config_command == "unset-catalog":
        path = unset_option("catalog", scope=args.scope)
        print(f"removed from {path}" if path else f"nothing set in the {args.scope} config")
        return 0

    if args.config_command == "set-collections":
        candidate = Path(args.path).expanduser()
        if not candidate.is_file():
            raise SystemExit(f"no such file: {candidate}")
        path = set_option("collections", str(candidate), scope=args.scope)
        print(f"collections written to {path}")
        print(f"resolved now: {resolve_collections()[0]}")
        print("-c/--collections still overrides this for a single run.")
        return 0

    if args.config_command == "unset-collections":
        path = unset_option("collections", scope=args.scope)
        print(f"removed from {path}" if path else f"nothing set in the {args.scope} config")
        return 0

    if args.config_command == "set-root":
        path = set_dataset_root(args.dataset, args.directory, scope=args.scope)
        print(f"dataset_roots[{args.dataset}] written to {path}")
        print(f"{args.dataset!r} will now be read from {Path(args.directory).expanduser()} and never downloaded")
        return 0

    if args.config_command == "unset-root":
        path = unset_dataset_root(args.dataset, scope=args.scope)
        print(f"removed from {path}" if path else f"no root set for {args.dataset!r} in the {args.scope} config")
        return 0

    if args.config_command == "unset-cache":
        path = unset_option("cache_dir", scope=args.scope)
        print(f"removed from {path}" if path else f"nothing set in the {args.scope} config")
        print(f"resolved now: {resolve_cache_dir()}")
        return 0

    resolved = resolve_cache_dir()
    print(f"cache directory: {resolved.value}")
    print(f"          from: {resolved.source}\n")
    print("precedence (first match wins):")
    env_value = os.environ.get(ENV_VAR)
    print(f"  1. explicit --root / root=      {'(not given)'}")
    print(f"  2. ${ENV_VAR:<22} {env_value or '(unset)'}")
    for index, (scope, path, exists) in enumerate(config_sources(), start=3):
        marker = "exists" if exists else "not present"
        print(f"  {index}. {scope + ' config':<24} {path}  [{marker}]")
    print(f"  {len(SCOPES) + 3}. built-in default          per-user OS cache directory")
    roots = dataset_roots()
    if roots:
        print("\ndatasets read from a local root (never downloaded):")
        for name, where in sorted(roots.items()):
            exists = "" if Path(where).is_dir() else "   [MISSING]"
            print(f"  {name:<28} {where}{exists}")
    catalog = resolve_catalog()
    if catalog:
        print(f"\ndefault catalog: {catalog[0]}  (from {catalog[1]})")
        print("  used instead of whatever -c/--collections pins for itself; --catalog overrides both")
    collections = resolve_collections()
    if collections:
        exists = "" if Path(collections[0]).is_file() else "   [MISSING]"
        print(f"\ndefault collections file: {collections[0]}{exists}  (from {collections[1]})")
        print("  used when -c/--collections is not given")
    print("\nSet it with one of:")
    print("  ice2-data config set-cache /path/to/data --scope project      # a visible file here")
    print("  ice2-data config set-cache /path/to/data                      # just for you")
    print("  ice2-data config set-cache /path/to/data --scope site         # everyone on this machine")
    print("  ice2-data config set-catalog /path/or/url --scope project     # default catalogue")
    print("  ice2-data config set-collections /path/to/collections.yaml --scope project")
    return 0


if __name__ == "__main__":
    sys.exit(main())
