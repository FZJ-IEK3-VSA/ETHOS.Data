"""The ``ethos-data catalog ...`` subcommands.

The pipelines ``add``, ``build``, ``upload``, ``record``, ``remove``,
``check-source``, ``publish``, ``release`` and ``update-checkout``, which plan
every stage before any of them acts, so ``--dry-run`` prints the plan;
``status`` and ``migrate``, which show and write each dataset's
``status.yaml``; and ``check-store``.

The maintainer group owns source metadata and publication operations. Local
configuration, staging, and cache management also write files, but remain at the
top level because consumers and package developers use them independently. That
includes building the public cache as links: ``ethos-data link --all`` reads a
checkout the way the commands here do, but the person filling a whole cache from
one and the person pointing a single dataset at a directory are doing the same
thing at different scale, and splitting them across two command groups made the
smaller job look like the unrelated one.

Every one of them but ``check-store`` needs a catalogue checkout, found by
searching upward from the current directory for ``catalog.yaml``, so they work
from anywhere inside one. ``check-store`` probes dCache; run inside a
checkout, it probes the store ``catalog.yaml`` names under ``ethos:store``.

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


def check_store(vo: str | None, start: Path | None = None) -> int:
    """Run the dCache access probe, which is a shell script by necessity.

    Inside a catalogue checkout, the probe reaches the store ``catalog.yaml``
    names under ``ethos:store``; ``vo`` names another VO.

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
    env = {**os.environ, **_store_environment(vo, start)}
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
        return subprocess.run([bash, str(script)], env=env, check=False).returncode
    if not os.access(script, os.X_OK):
        script.chmod(0o755)
    return subprocess.run([str(script)], env=env, check=False).returncode


def _store_environment(vo: str | None, start: Path | None) -> dict[str, str]:
    """The store the probe reaches: ``ethos:store`` of the enclosing checkout, if any."""
    from ..formats.catalogue import StoreSettings, store_of
    from . import find_catalog_root, read_catalog_meta

    try:
        settings = store_of(read_catalog_meta(find_catalog_root(start)))
    except MaintenanceError:
        settings = StoreSettings()
    return {
        "ETHOS_STORE_VO_PATH": f"Helmholtz/{vo}" if vo else settings.vo_path,
        "ETHOS_STORE_FRONTEND": settings.frontend,
        "ETHOS_STORE_OIDC_PROFILE": settings.oidc_profile,
    }


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
    builder.add_argument("datasets", nargs="*", help="dataset names (default: all)")
    builder.add_argument(
        "--check",
        action="store_true",
        help="fail if any manifest is out of date; write nothing",
    )
    builder.add_argument(
        "--dry-run",
        action="store_true",
        help="show what the build would write and record; write nothing",
    )

    publisher = catalog_sub.add_parser(
        "publish", help="generate the public catalogue from this source one"
    )
    publisher.add_argument(
        "target",
        help="dedicated generated public checkout; every file but .git is generated",
    )
    publisher.add_argument(
        "--check",
        action="store_true",
        help="fail if the target is out of date; write nothing",
    )
    publisher.add_argument(
        "--dry-run",
        action="store_true",
        help="show what publish would write and remove; write nothing",
    )

    uploader = catalog_sub.add_parser(
        "upload",
        help="upload dataset bytes and check anonymous readability and sizes",
        description="Upload built, licensed, public datasets. Checks use anonymous "
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
        help="check and print the plan; contact no store",
    )
    uploader.add_argument(
        "--verify-only",
        action="store_true",
        help="skip the transfer; the chmod runs unless --no-chmod is given too",
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
        "A dataset without a status.yaml is named with `catalog migrate`, and fails "
        "the command.",
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
        "file, cache entries and bytes stay until a major release is recorded after "
        "the removal.",
    )
    remover.add_argument("datasets", nargs="+", help="dataset or family names")
    remover.add_argument(
        "--reason", default="", help="why, for the record in status.yaml"
    )
    remover.add_argument(
        "--purge",
        action="store_true",
        help="once a major release is recorded after their removal: delete their "
        "cache entries, their bytes on the store and their directories but "
        "status.yaml",
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
        description="Check the catalogue and that the version is the next patch, "
        "minor or major of the last release at or above the level the changes "
        "need, write the version into catalog.yaml and the index, record the "
        "release in the status files, commit and tag the source checkout, and "
        "generate, commit and tag the public catalogue. --push and --upload reach "
        "past this machine; run it again with them to finish a release made "
        "without.",
    )
    releaser.add_argument(
        "version", help="the release, vMAJOR.MINOR.PATCH; the first is v1.0.0"
    )
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
        help="convert source_dir, ethos:uploaded and ethos:frozen into status.yaml",
        description="Write each dataset's status.yaml from source_dir, ethos:uploaded "
        "and ethos:frozen in its dataset.yaml, remove those keys line by line, keeping "
        "every other line and comment, and move manifests/ to shards/.",
    )
    migrator.add_argument("datasets", nargs="*", help="dataset names (default: all)")
    migrator.add_argument(
        "--dry-run", action="store_true", help="show what would change; write nothing"
    )

    # It probes the publication store, and is the one subcommand here that
    # needs no catalogue.
    prober = catalog_sub.add_parser(
        "check-store",
        help="probe dCache permissions using temporary remote objects",
        description="Creates and cleans up temporary remote files/directories to test access "
        "and permission inheritance. Needs storage credentials; inside a catalogue "
        "checkout it probes the store catalog.yaml names under ethos:store.",
    )
    prober.add_argument(
        "vo",
        nargs="?",
        default=None,
        help="VO name (default: from catalog.yaml's ethos:store, else FZJ-ICE2)",
    )

    return parser


def _status(result) -> int:
    """The exit status of a maintenance command: 0 when its result is ok."""
    return 0 if result.ok else 1


def _upload_options(args):
    """The upload flags a parsed command line carries, as the upload takes them."""
    from .upload import UploadOptions

    return UploadOptions(
        **{name: getattr(args, name) for name in UploadOptions.__dataclass_fields__}
    )


def dispatch(args) -> int:
    """Run one ``ethos-data catalog`` subcommand.

    The heavy modules are imported here rather than at module scope: a plain
    ``ethos-data ls`` builds this parser too, and should not pay to import the
    manifest builder to do it.
    """
    if args.catalog_command == "check-store":
        start = Path(args.catalog_root) if args.catalog_root else None
        return check_store(args.vo, start)

    root = resolve_catalog_root(args.catalog_root)

    if args.catalog_command == "build":
        from . import manifest

        return _status(
            manifest.run(root, args.datasets, check=args.check, dry_run=args.dry_run)
        )

    if args.catalog_command == "publish":
        from . import publish

        return _status(
            publish.run(root, args.target, check=args.check, dry_run=args.dry_run)
        )

    if args.catalog_command == "upload":
        from . import upload

        return _status(upload.run(root, args.datasets, _upload_options(args)))

    if args.catalog_command == "status":
        from . import status

        return _status(status.run(root, args.datasets, check=args.check))

    if args.catalog_command == "record":
        from . import freeze

        return _status(
            freeze.run(root, args.dataset, copy=args.copy, dry_run=args.dry_run)
        )

    if args.catalog_command == "migrate":
        from . import migrate

        return _status(migrate.run(root, args.datasets, dry_run=args.dry_run))

    if args.catalog_command == "add":
        from . import accept

        return _status(
            accept.run(root, args.source, name=args.name, dry_run=args.dry_run)
        )

    if args.catalog_command == "remove":
        from . import remove

        return _status(
            remove.run(
                root,
                args.datasets,
                reason=args.reason,
                purge=args.purge,
                dry_run=args.dry_run,
            )
        )

    if args.catalog_command == "release":
        from . import release

        return _status(
            release.run(
                root,
                args.version,
                args.public,
                push=args.push,
                upload=args.upload,
                remote=args.remote,
                dry_run=args.dry_run,
            )
        )

    if args.catalog_command == "update-checkout":
        from . import checkout

        return _status(
            checkout.run(root, to=args.to, remote=args.remote, dry_run=args.dry_run)
        )

    if args.catalog_command == "check-source":
        from . import provenance

        return _status(
            provenance.run(
                root, args.dataset, args.directory, note=args.note, dry_run=args.dry_run
            )
        )

    raise MaintenanceError(f"unknown catalog command: {args.catalog_command}")
