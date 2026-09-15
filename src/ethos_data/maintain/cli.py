"""The ``ethos-data catalog ...`` subcommands: build, publish, upload, link-cache, check-store.

The maintainer group owns source metadata and publication operations. Local
configuration, staging, and cache management also write files, but remain at the
top level because consumers and package developers use them independently.

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
import shutil
import subprocess
import sys
from pathlib import Path

from . import resolve_catalog_root

SCRIPTS = Path(__file__).resolve().parent / "scripts"


def check_store(vo: str) -> int:
    """Run the dCache access probe, which is a shell script by necessity.

    It reproduces exactly what a maintainer types by hand against curl and
    rclone; rewriting it in Python would make it a worse diagnostic, because the
    commands it prints on failure would no longer be the ones it ran.

    Invoked through ``bash`` rather than executed directly. Windows has no
    concept of an executable bit and cannot run a ``.sh`` from CreateProcess at
    all -- ``os.access(..., X_OK)`` answers yes for any readable file there, so
    the direct call sailed past the guard and died in the kernel instead. Git
    for Windows and the WSL distributions both put a usable bash on PATH.
    """
    script = SCRIPTS / "check_dcache_access.sh"
    if os.name == "nt":
        bash = shutil.which("bash")
        if bash is None:
            print(
                "check-store needs bash, which is not on PATH.\n"
                "It is a shell script on purpose -- it prints the very curl and rclone\n"
                "commands it ran, so that a failure can be retried by hand.\n"
                "Install Git for Windows (which ships one) or run it from WSL:\n"
                f"    bash {script} {vo}",
                file=sys.stderr,
            )
            return 1
        return subprocess.run([bash, str(script), vo]).returncode
    if not os.access(script, os.X_OK):
        script.chmod(0o755)
    return subprocess.run([str(script), vo]).returncode


def add_catalog_parser(sub: "argparse._SubParsersAction") -> argparse.ArgumentParser:
    """Graft ``catalog`` and its subcommands onto the ``ethos-data`` parser."""
    parser = sub.add_parser(
        "catalog",
        help="maintainer commands: describe, publish and upload datasets",
        description="Build source metadata, generate its public view, upload bytes, "
                    "or register existing data in a cache. Uses a source checkout "
                    "containing catalog.yaml; --catalog at the top level selects reader metadata.",
        epilog="Folder operations use rclone mkdir/moveto/deletefile/rmdir/purge. "
               "Run a command with --help for its options.",
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
    publisher.add_argument("target",
                           help="dedicated generated public checkout; replaces everything except .git")
    publisher.add_argument("--check", action="store_true",
                           help="fail if the target is out of date; write nothing")

    uploader = catalog_sub.add_parser(
        "upload", help="upload dataset bytes and check anonymous readability and sizes",
        description="Upload built, licensed, non-restricted datasets. Checks use anonymous "
                    "HTTP HEAD, not remote SHA-256. Does not set ethos:uploaded automatically.")
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
    uploader.add_argument("--dry-run", action="store_true",
                          help="preview rclone transfers; may contact storage; do not combine with --verify-only")
    uploader.add_argument("--verify-only", action="store_true",
                          help="skip transfer; public chmod still runs unless --no-chmod is also given")
    uploader.add_argument("--allow-internal", action="store_true",
                          help="permit internal data without public chmod; verification is still anonymous")
    uploader.add_argument("--no-chmod", action="store_true",
                          help="do not set 0755 on the dataset prefix")
    uploader.add_argument("--transfers", type=int, default=8,
                          help="parallel rclone transfers (default: 8)")

    # Named for what it produces, not for the internal idea behind it. It was
    # `namespace`, which named the concept ("a namespace of links") and left the
    # reader of `--root /projects5/...` with no way to guess that the thing being
    # built is the shared cache.
    linker = catalog_sub.add_parser(
        "link-cache",
        help="build the shared cache as links to data already on this machine")
    # Not required, but still worth naming: this command usually builds a cache
    # for a whole machine, which is rarely the one the maintainer's own account
    # reads. The default is there so that filling your own cache from a checkout
    # is one word, not a path you have to look up.
    linker.add_argument("--root", default=None,
                        help="the public cache directory to build "
                             "(default: the configured public cache)")
    linker.add_argument("--dry-run", action="store_true",
                        help="show what would change, write nothing")
    linker.add_argument("--prune", action="store_true",
                        help="also remove links for datasets no longer in the catalogue")

    # Was `check-access`, which did not say access to *what*. It probes the
    # publication store, and is the one subcommand here that needs no catalogue.
    prober = catalog_sub.add_parser(
        "check-store", help="probe dCache permissions using temporary remote objects",
        description="Creates and cleans up temporary remote files/directories to test access "
                    "and permission inheritance. Needs storage credentials, no catalogue checkout.")
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
