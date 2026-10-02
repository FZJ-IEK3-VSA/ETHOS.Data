"""The ``ethos-data catalog ...`` subcommands.

``build``, ``publish``, ``upload`` and ``check-store``; the maintainer
pipelines ``add``, ``record``, ``remove``, ``check-source``, ``release`` and
``update-checkout``, which plan every stage before any of them acts; and
``status`` and ``migrate``, which show and write each dataset's
``status.yaml``.

The maintainer group owns source metadata and publication operations. Local
configuration, staging, and cache management also write files, but remain at the
top level because consumers and package developers use them independently. That
includes building a shared cache as links: ``ethos-data link --all`` reads a
checkout the way the commands here do, but the person filling a whole cache from
one and the person pointing a single dataset at a directory are doing the same
thing at different scale, and splitting them across two command groups made the
smaller job look like the unrelated one.

Every one of them but ``check-store`` needs a catalogue checkout, found by
searching upward from the current directory for ``catalog.yaml``, so they work
from anywhere inside one. ``check-store`` probes dCache and has nothing to do
with any particular catalogue.

This module owns the argument definitions rather than exporting a ``main``:
:mod:`ethos_data.cli` calls :func:`add_catalog_parser` to graft them on, and
:func:`dispatch` to run them.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from .. import report
from ..errors import MaintenanceError
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
            report.warning(
                "check-store needs bash, which is not on PATH.\n"
                "It is a shell script on purpose -- it prints the very curl and rclone\n"
                "commands it ran, so that a failure can be retried by hand.\n"
                "Install Git for Windows (which ships one) or run it from WSL:\n"
                f"    bash {script} {vo}"
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
        description="Build source metadata, generate its public view, or upload "
        "bytes. Uses a source checkout containing catalog.yaml; --catalog at the "
        "top level selects reader metadata.",
        epilog="Folder operations use rclone mkdir/moveto/deletefile/rmdir/purge. "
        "Run a command with --help for its options.",
    )
    # NOT a top-level option: `ethos-data --catalog` already exists and means
    # something else entirely -- which catalogue to *read*. Keeping this one
    # inside the group is what stops the two from being confusable.
    parser.add_argument(
        "--catalog-root",
        default=None,
        help="catalogue checkout to act on (default: search upward for catalog.yaml)",
    )

    catalog_sub = parser.add_subparsers(dest="catalog_command", required=True)

    adder = catalog_sub.add_parser(
        "add",
        help="take a reviewed draft dataset.yaml into the catalogue and build it",
        description="Check the draft as the build would, write datasets/<name>/ "
        "with its description, licence documents and status.yaml, and build it. "
        "source_dir goes into status.yaml; a relative one is relative to the draft.",
    )
    adder.add_argument(
        "source", help="the draft dataset.yaml, or the directory that holds it"
    )
    adder.add_argument(
        "--name",
        default=None,
        help="the dataset's name, for a draft that states none",
    )
    adder.add_argument(
        "--dry-run", action="store_true", help="check and plan; write nothing"
    )

    builder = catalog_sub.add_parser(
        "build",
        help="regenerate datapackage.json and datacatalog.json from dataset.yaml",
    )
    builder.add_argument(
        "datasets", nargs="*", help="dataset directory names (default: all)"
    )
    builder.add_argument(
        "--check",
        action="store_true",
        help="fail if any manifest is out of date; write nothing",
    )

    publisher = catalog_sub.add_parser(
        "publish", help="generate the public catalogue from this source one"
    )
    publisher.add_argument(
        "target",
        help="dedicated generated public checkout; replaces everything except .git",
    )
    publisher.add_argument(
        "--check",
        action="store_true",
        help="fail if the target is out of date; write nothing",
    )

    uploader = catalog_sub.add_parser(
        "upload",
        help="upload dataset bytes and check anonymous readability and sizes",
        description="Upload built, licensed, non-restricted datasets. Checks use anonymous "
        "HTTP HEAD, not remote SHA-256. A verified upload is recorded in the dataset's "
        "status.yaml; `catalog record` then freezes the dataset.",
    )
    # A list, like `build`, so that publishing a subset of the catalogue is one
    # command rather than a shell loop. A loop is not equivalent: it re-checks
    # nothing up front, so it can upload half the subset and then stop on a
    # dataset that was never eligible.
    uploader.add_argument(
        "datasets",
        nargs="+",
        help="dataset directory names, or paths to them (e.g. datasets/global-wind-atlas-v4); "
        "a family name such as reskit-test-data uploads every member beneath it",
    )
    uploader.add_argument(
        "--remote",
        default=None,
        help="rclone remote name (default: catalog.yaml's ethos:store, else HIFIS)",
    )
    uploader.add_argument(
        "--oidc-profile",
        default=None,
        help="oidc-agent profile (default: catalog.yaml's ethos:store, else HIFIS)",
    )
    uploader.add_argument(
        "--vo-path",
        default=None,
        help="namespace path of the VO (default: catalog.yaml's ethos:store, "
        "else Helmholtz/FZJ-ICE2)",
    )
    uploader.add_argument(
        "--root",
        default=None,
        help="publication root under the VO (default: the last path segment of "
        "catalog.yaml's ethos:publication_url)",
    )
    uploader.add_argument(
        "--dry-run",
        action="store_true",
        help="preview rclone transfers; may contact storage; do not combine with --verify-only",
    )
    uploader.add_argument(
        "--verify-only",
        action="store_true",
        help="skip transfer; public chmod still runs unless --no-chmod is also given",
    )
    uploader.add_argument(
        "--allow-internal",
        action="store_true",
        help="permit internal data without public chmod; verification is still anonymous",
    )
    uploader.add_argument(
        "--no-chmod", action="store_true", help="do not set 0755 on the dataset prefix"
    )
    uploader.add_argument(
        "--transfers",
        type=int,
        default=8,
        help="parallel rclone transfers (default: 8)",
    )

    stater = catalog_sub.add_parser(
        "status",
        help="each dataset's state and next step, from its status.yaml",
        description="List every dataset with its state -- draft, built, available, "
        "frozen, withdrawn or purged -- its access class and what it needs next. "
        "A dataset without a status.yaml shows '-'.",
    )
    stater.add_argument(
        "datasets",
        nargs="*",
        help="dataset names; a family lists its members (default: all)",
    )
    stater.add_argument(
        "--check",
        action="store_true",
        help="also compare each record with the evidence -- the inventory, the "
        "source_dir and every recorded copy, file by file; exit 1 if one does not hold",
    )

    recorder = catalog_sub.add_parser(
        "record",
        help="freeze a dataset whose bytes are available, naming its authoritative copy",
        description="Check a recorded copy file by file, make it the dataset's "
        "authoritative copy and retire its source_dir; a rebuild then keeps the "
        "inventory as it is.",
    )
    recorder.add_argument("dataset", help="dataset name, or the path to it")
    recorder.add_argument(
        "--copy",
        default=None,
        metavar="LOCATION",
        help="the recorded copy to make authoritative (default: the upload, else the "
        "copy a cache owns, else for restricted data its registered installation)",
    )
    recorder.add_argument(
        "--dry-run", action="store_true", help="check the copy; write nothing"
    )

    remover = catalog_sub.add_parser(
        "remove",
        help="withdraw datasets: out of the index and the public catalogue",
        description="Record each dataset as withdrawn -- a family stands for its "
        "members -- and rebuild the index without them. Their description, status "
        "file, cache entries and bytes stay until a release without them is out.",
    )
    remover.add_argument("datasets", nargs="+", help="dataset or family names")
    remover.add_argument(
        "--reason", default="", help="why, for the record in status.yaml"
    )
    remover.add_argument(
        "--purge",
        action="store_true",
        help="once a release without them is recorded: delete their cache entries, "
        "their bytes on the store and their directories but status.yaml",
    )
    remover.add_argument(
        "--dry-run", action="store_true", help="check and plan; write nothing"
    )

    checker = catalog_sub.add_parser(
        "check-source",
        help="compare a fresh download from the source with the recorded inventory",
        description="Hash every file under DIR the inventory lists, compare size and "
        "SHA-256 with the recorded ones, and record the result in status.yaml. "
        "Exit 1 if a file differs.",
    )
    checker.add_argument("dataset", help="a downloaded dataset")
    checker.add_argument(
        "directory", help="the folder holding the fresh download, laid out as recorded"
    )
    checker.add_argument(
        "--note",
        default="",
        help="what was compared against, such as the source's release, for the record",
    )
    checker.add_argument(
        "--dry-run", action="store_true", help="compare; record nothing"
    )

    releaser = catalog_sub.add_parser(
        "release",
        help="release the catalogue: stamp, commit, tag, generate the public one",
        description="Check the catalogue, write the version into catalog.yaml and "
        "the index, record the release in the status files, commit and tag the "
        "source checkout, and generate, commit and tag the public catalogue. "
        "--push and --upload reach past this machine; run it again with them to "
        "finish a release made without.",
    )
    releaser.add_argument("version", help="the release, vYYYY.MM.N")
    releaser.add_argument(
        "--public",
        required=True,
        metavar="DIR",
        help="the checkout of the public catalogue repository",
    )
    releaser.add_argument(
        "--push", action="store_true", help="push both checkouts and the tag"
    )
    releaser.add_argument(
        "--upload",
        action="store_true",
        help="put the public catalogue on the store, under <publication root>/catalogue/",
    )
    releaser.add_argument(
        "--remote", default="origin", help="the git remote to push to (default: origin)"
    )
    releaser.add_argument(
        "--dry-run", action="store_true", help="check and plan; write nothing"
    )

    updater = catalog_sub.add_parser(
        "update-checkout",
        help="move the checkout readers are served to a release, by fast-forward",
        description="In the served checkout: fetch, fast-forward to the release, "
        "and check every manifest against its files. Run it on the machine that "
        "serves it, when no jobs read it.",
    )
    updater.add_argument(
        "--to",
        default=None,
        metavar="VERSION",
        help="the release (default: the latest)",
    )
    updater.add_argument(
        "--remote", default="origin", help="the git remote to fetch (default: origin)"
    )
    updater.add_argument(
        "--dry-run", action="store_true", help="plan; fetch and move nothing"
    )

    migrator = catalog_sub.add_parser(
        "migrate",
        help="move source_dir, ethos:uploaded and ethos:frozen into status.yaml",
        description="Write each dataset's status.yaml from the keys its dataset.yaml "
        "held before status files, and remove them line by line, keeping every "
        "other line and comment.",
    )
    migrator.add_argument("datasets", nargs="*", help="dataset names (default: all)")
    migrator.add_argument(
        "--dry-run", action="store_true", help="show what would change; write nothing"
    )

    # Was `check-access`, which did not say access to *what*. It probes the
    # publication store, and is the one subcommand here that needs no catalogue.
    prober = catalog_sub.add_parser(
        "check-store",
        help="probe dCache permissions using temporary remote objects",
        description="Creates and cleans up temporary remote files/directories to test access "
        "and permission inheritance. Needs storage credentials, no catalogue checkout.",
    )
    prober.add_argument(
        "vo", nargs="?", default="FZJ-ICE2", help="VO name (default: FZJ-ICE2)"
    )

    return parser


def dispatch(args) -> int:
    """Run one ``ethos-data catalog`` subcommand.

    The heavy modules are imported here rather than at module scope: a plain
    ``ethos-data ls`` builds this parser too, and should not pay to import the
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

    if args.catalog_command == "upload":
        from . import upload

        return upload.run(root, args.datasets, upload.UploadOptions.from_args(args))

    if args.catalog_command == "status":
        from . import status

        return status.run(root, args.datasets, check=args.check)

    if args.catalog_command == "record":
        from . import freeze

        return freeze.run(root, args.dataset, copy=args.copy, dry_run=args.dry_run)

    if args.catalog_command == "migrate":
        from . import migrate

        return migrate.run(root, args.datasets, dry_run=args.dry_run)

    if args.catalog_command == "add":
        from . import accept

        return accept.run(root, args.source, name=args.name, dry_run=args.dry_run)

    if args.catalog_command == "remove":
        from . import remove

        return remove.run(
            root,
            args.datasets,
            reason=args.reason,
            purge=args.purge,
            dry_run=args.dry_run,
        )

    if args.catalog_command == "release":
        from . import release

        return release.run(
            root,
            args.version,
            args.public,
            push=args.push,
            upload=args.upload,
            remote=args.remote,
            dry_run=args.dry_run,
        )

    if args.catalog_command == "update-checkout":
        from . import checkout

        return checkout.run(root, to=args.to, remote=args.remote, dry_run=args.dry_run)

    if args.catalog_command == "check-source":
        from . import provenance

        return provenance.run(
            root, args.dataset, args.directory, note=args.note, dry_run=args.dry_run
        )

    raise MaintenanceError(f"unknown catalog command: {args.catalog_command}")
