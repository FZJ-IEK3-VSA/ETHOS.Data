"""The ``ethos-data catalog ...`` subcommands: build, publish, upload, link-cache, check-store.

The maintainer half of one command. Everything here **writes** -- to a catalogue
checkout, or to the storage behind it -- while everything under ``ethos-data``
itself only reads. That split used to be two executables (``ice2-catalog`` and
``ethos-data``), which made the separation obvious at the cost of a second name
to install, remember and keep on PATH; people hit "command not found" and
concluded the tooling was gone.

One executable, two modes. The ``catalog`` noun does the same job the second
binary did -- nothing a data *user* types is one key away from republishing a
catalogue -- and it does it where the user is already looking. Grouping is not
decoration: ``ethos-data --help`` stays a list of things that read, and every
command that writes is one word further in.

Four of the five need a catalogue checkout, found by searching upward from the
current directory for ``catalog.yaml``, so they work from anywhere inside one.
``check-store`` is the exception: it probes dCache and has nothing to do with
any particular catalogue.

This module owns the argument definitions rather than exporting a ``main``:
:mod:`ethos_data.cli` calls :func:`add_catalog_parser` to graft them on, and
:func:`dispatch` to run them.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from . import resolve_catalog_root

SCRIPTS = Path(__file__).resolve().parent / "scripts"


def check_store(vo: str) -> int:
    """Run the dCache access probe, which is a shell script by necessity.

    It reproduces exactly what a maintainer types by hand against curl and
    rclone; rewriting it in Python would make it a worse diagnostic, because the
    commands it prints on failure would no longer be the ones it ran.
    """
    script = SCRIPTS / "check_dcache_access.sh"
    if not os.access(script, os.X_OK):
        script.chmod(0o755)
    return subprocess.run([str(script), vo]).returncode


def add_catalog_parser(sub: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    """Graft ``catalog`` and its subcommands onto the ``ethos-data`` parser."""
    parser = sub.add_parser(
        "catalog",
        help="maintainer commands: describe, publish and upload datasets",
        description="Write to a catalogue, or to the storage behind it. "
                    "Everything else in ethos-data only reads.",
    )
    # NOT a top-level option: `ethos-data --catalog` already exists and means
    # something else entirely -- which catalogue to *read*. Keeping this one
    # inside the group is what stops the two from being confusable.
    parser.add_argument(
        "--catalog-root", default=None,
        help="catalogue checkout to act on (default: search upward for catalog.yaml)")

    catalog_sub = parser.add_subparsers(dest="catalog_command", required=True)

    builder = catalog_sub.add_parser(
        "build", help="regenerate datapackage.json and datacatalog.json from dataset.yaml")
    builder.add_argument("datasets", nargs="*", help="dataset directory names (default: all)")
    builder.add_argument("--check", action="store_true",
                         help="fail if any manifest is out of date; write nothing")

    publisher = catalog_sub.add_parser(
        "publish", help="generate the public catalogue from this source one")
    publisher.add_argument("target", help="path to a checkout of the public ETHOS.Data-Catalogue repo")
    publisher.add_argument("--check", action="store_true",
                           help="fail if the target is out of date; write nothing")

    uploader = catalog_sub.add_parser(
        "upload", help="put datasets' bytes on dCache, then verify them anonymously")
    # A list, like `build`, so that publishing a subset of the catalogue is one
    # command rather than a shell loop. A loop is not equivalent: it re-checks
    # nothing up front, so it can upload half the subset and then stop on a
    # dataset that was never eligible.
    uploader.add_argument(
        "datasets", nargs="+",
        help="dataset directory names, or paths to them (e.g. datasets/global-wind-atlas-v4)")
    uploader.add_argument("--remote", default="HIFIS", help="rclone remote name (default: HIFIS)")
    uploader.add_argument("--oidc-profile", default="HIFIS",
                          help="oidc-agent profile (default: HIFIS)")
    uploader.add_argument("--vo-path", default="Helmholtz/FZJ-ICE2",
                          help="namespace path of the VO")
    uploader.add_argument("--root", default=None,
                          help="publication root under the VO (default: the last path segment of "
                               "catalog.yaml's ethos:publication_url)")
    uploader.add_argument("--dry-run", action="store_true", help="show what rclone would transfer")
    uploader.add_argument("--verify-only", action="store_true",
                          help="skip the upload, just check readability")
    uploader.add_argument("--allow-internal", action="store_true")
    uploader.add_argument("--no-chmod", action="store_true",
                          help="do not set 0755 on the dataset prefix")
    uploader.add_argument("--transfers", type=int, default=8)

    # Named for what it produces, not for the internal idea behind it. It was
    # `namespace`, which named the concept ("a namespace of links") and left the
    # reader of `--root /projects5/...` with no way to guess that the thing being
    # built is the shared cache.
    linker = catalog_sub.add_parser(
        "link-cache",
        help="build the shared cache as links to data already on this machine")
    linker.add_argument("--root", required=True,
                        help="the public cache directory to build "
                             "(e.g. /shared/ethos/public)")
    linker.add_argument("--dry-run", action="store_true",
                        help="show what would change, write nothing")
    linker.add_argument("--prune", action="store_true",
                        help="also remove links for datasets no longer in the catalogue")

    # Was `check-access`, which did not say access to *what*. It probes the
    # publication store, and is the one subcommand here that needs no catalogue.
    prober = catalog_sub.add_parser(
        "check-store", help="probe what this account can do on dCache InfiniteSpace")
    prober.add_argument("vo", nargs="?", default="FZJ-ICE2", help="VO name (default: FZJ-ICE2)")

    return parser


def dispatch(args) -> int:
    """Run one ``ethos-data catalog`` subcommand.

    The heavy modules are imported here rather than at module scope: a plain
    ``ethos-data list`` builds this parser too, and should not pay to import the
    manifest builder to do it.
    """
    if args.catalog_command == "check-store":
        return check_store(args.vo)

    root = resolve_catalog_root(args.catalog_root)

    if args.catalog_command == "build":
        from . import manifest
        return manifest.run(root, args.datasets, check=args.check)

    if args.catalog_command == "publish":
        from . import publish
        return publish.run(root, args.target, check=args.check)

    if args.catalog_command == "link-cache":
        from . import namespace
        return namespace.run(root, args)

    if args.catalog_command == "upload":
        from . import upload
        return upload.run(root, args)

    raise SystemExit(f"unknown catalog command: {args.catalog_command}")
