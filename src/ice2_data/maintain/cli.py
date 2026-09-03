"""Command line interface: ``ice2-catalog build|publish|upload|check-access``.

The maintainer counterpart to ``ice2-data``.  Everything here writes -- to a
catalogue checkout, or to the storage behind it -- which is why it is a separate
command rather than more subcommands on the consumer tool: the two have
different audiences, and nothing a data *user* runs should be one typo away from
republishing a catalogue.

The catalogue to act on is found by searching upward from the current directory
for ``catalog.yaml``, so these commands work from anywhere inside a checkout.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import find_catalog_root

SCRIPTS = Path(__file__).resolve().parent / "scripts"


def check_access(vo: str) -> int:
    """Run the dCache access probe, which is a shell script by necessity.

    It reproduces exactly what a maintainer types by hand against curl and
    rclone; rewriting it in Python would make it a worse diagnostic, because the
    commands it prints on failure would no longer be the ones it ran.
    """
    script = SCRIPTS / "check_dcache_access.sh"
    if not os.access(script, os.X_OK):
        script.chmod(0o755)
    return subprocess.run([str(script), vo]).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ice2-catalog", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog-root", default=None,
                        help="catalogue checkout to act on (default: search upward for catalog.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)

    builder = sub.add_parser("build", help="regenerate datapackage.json and datacatalog.json")
    builder.add_argument("datasets", nargs="*", help="dataset directory names (default: all)")
    builder.add_argument("--check", action="store_true", help="fail if any manifest is out of date")

    publisher = sub.add_parser("publish", help="generate the public catalogue from this internal one")
    publisher.add_argument("target", help="path to a checkout of the public ice2-data-catalog repo")
    publisher.add_argument("--check", action="store_true", help="fail if the target is out of date")

    uploader = sub.add_parser("upload", help="put a dataset's bytes on dCache, then verify them")
    uploader.add_argument("dataset")
    uploader.add_argument("--remote", default="HIFIS", help="rclone remote name (default: HIFIS)")
    uploader.add_argument("--oidc-profile", default="HIFIS", help="oidc-agent profile (default: HIFIS)")
    uploader.add_argument("--vo-path", default="Helmholtz/FZJ-ICE2", help="namespace path of the VO")
    uploader.add_argument("--root", default="reskit-data", help="publication root under the VO")
    uploader.add_argument("--dry-run", action="store_true", help="show what rclone would transfer")
    uploader.add_argument("--verify-only", action="store_true", help="skip the upload, just check readability")
    uploader.add_argument("--allow-internal", action="store_true")
    uploader.add_argument("--no-chmod", action="store_true", help="do not set 0755 on the dataset prefix")
    uploader.add_argument("--transfers", type=int, default=8)

    prober = sub.add_parser("check-access", help="probe what we can do on dCache InfiniteSpace")
    prober.add_argument("vo", nargs="?", default="FZJ-ICE2", help="VO name (default: FZJ-ICE2)")

    args = parser.parse_args(argv)

    if args.command == "check-access":
        return check_access(args.vo)

    root = Path(args.catalog_root).expanduser().resolve() if args.catalog_root else find_catalog_root()
    if not (root / "catalog.yaml").is_file():
        raise SystemExit(f"not a catalogue checkout (no catalog.yaml): {root}")

    if args.command == "build":
        from . import manifest
        return manifest.run(root, args.datasets, check=args.check)

    if args.command == "publish":
        from . import publish
        return publish.run(root, args.target, check=args.check)

    if args.command == "upload":
        from . import upload
        return upload.run(root, args)

    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
