"""Upload a dataset to DESY dCache InfiniteSpace, then prove it is readable.

    ice2-data catalog upload reskit-test-data --dry-run
    ice2-data catalog upload reskit-test-data
    ice2-data catalog upload reskit-test-data --verify-only

The verify step is the point of this tool. Uploading is one rclone call; knowing
that an anonymous user on the other side of the internet can actually read what
you uploaded is the part that goes wrong, and it goes wrong quietly.

Requires:
  * oidc-agent with a profile (default "HIFIS") -- `oidc-token HIFIS` must work
  * an rclone remote (default "HIFIS") pointing at /Helmholtz/<VO>

Guard rails:
  * restricted datasets are never uploaded -- that is what "restricted" means
  * internal datasets need --allow-internal, and are NOT made world-readable
  * paths are immutable: an upload that would overwrite an existing, differing
    file is refused, because published paths must never change under consumers
  * only files in the manifest are uploaded.  A source_dir narrowed by
    ``ice2:include`` / ``ice2:exclude`` is usually a shared download directory
    holding things that are not the dataset, so "copy the directory" is not the
    same instruction as "publish the dataset"
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import yaml

from . import datasets_dir, resources_of

FRONTEND = "https://hifis-storage-web.desy.de/api/v1"
MODE_0755 = 493  # dCache wants the mode as a decimal integer, not octal


def _capture(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, **kwargs)


def token(profile: str) -> str:
    result = _capture(["oidc-token", profile])
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit(
            f"could not get a token from `oidc-token {profile}`.\n"
            f"  {result.stderr.strip()}\n"
            "Start the agent and register the profile:\n"
            "    eval $(oidc-agent-service use)\n"
            f"    oidc-gen {profile} --flow=code --client-id=desy-public \\\n"
            "        --scope='openid profile offline_access' \\\n"
            "        --iss=https://keycloak.desy.de/auth/realms/production/ \\\n"
            "        --redirect-uri=http://localhost:4242"
        )
    return result.stdout.strip()


def load(catalog_root: Path, dataset_name: str) -> tuple[dict, dict, Path | None, Path]:
    dataset_dir = datasets_dir(catalog_root) / dataset_name
    meta_file = dataset_dir / "dataset.yaml"
    package_file = dataset_dir / "datapackage.json"
    if not meta_file.is_file():
        # Distinguish "not described yet" from "described but not built" -- they
        # need different fixes, and telling someone to build a dataset that does
        # not exist just moves the same error one command further along.
        known = sorted(d.name for d in datasets_dir(catalog_root).iterdir() if (d / "dataset.yaml").is_file())
        listing = "\n".join(f"    {name}" for name in known) or "    (none)"
        raise SystemExit(
            f"no dataset called {dataset_name!r} in {datasets_dir(catalog_root)}.\n"
            f"Datasets in this catalogue:\n{listing}\n"
            "To add a new one, describe it first -- see docs/how-to/describe-a-dataset.md."
        )
    if not package_file.is_file():
        raise SystemExit(
            f"{dataset_name!r} has no datapackage.json yet. Run:\n"
            f"    ice2-data catalog build {dataset_name}"
        )
    meta = yaml.safe_load(meta_file.read_text())
    package = json.loads(package_file.read_text())
    raw_source_dir = meta.get("source_dir")
    # A dataset marked ice2:uploaded: true has none -- dCache is already the
    # source of truth, and there is nothing local left to read bytes from.
    if raw_source_dir is None:
        return meta, package, None, dataset_dir
    source_dir = Path(raw_source_dir).expanduser()
    # Resolve exactly as the manifest builder does -- relative to the dataset
    # directory, not the current one. Otherwise a relative source_dir means two
    # different things depending on where you happened to run the tool from, and
    # the upload silently takes its bytes from somewhere the manifest never saw.
    if not source_dir.is_absolute():
        source_dir = (dataset_dir / source_dir).resolve()
    return meta, package, source_dir, dataset_dir


def preflight(name: str, package: dict, source_dir: Path | None, allow_internal: bool,
              verify_only: bool) -> str:
    access = package.get("ice2:access", "public")
    prefix = package.get("ice2:remote_prefix")

    if access == "restricted":
        raise SystemExit(
            f"{name} is restricted and must never be uploaded.\n"
            "Restricted data stays where it is; users point at it with\n"
            f"    ice2-data config set-root {name} /path/to/{name}"
        )
    if access == "internal" and not allow_internal:
        raise SystemExit(
            f"{name} is internal (not published). Upload it only if the VO-only "
            "prefix is really where you want it, and pass --allow-internal.\n"
            "It will NOT be made world-readable."
        )
    if not prefix:
        raise SystemExit(f"{name} declares no ice2:remote_prefix, so there is nowhere to put it.")

    if source_dir is None:
        if not verify_only:
            raise SystemExit(
                f"{name} has no source_dir (ice2:uploaded: true) -- there is nothing left "
                "to upload. Pass --verify-only to recheck what is already on dCache, or "
                "unset ice2:uploaded and restore source_dir to publish a fresh copy."
            )
    elif not source_dir.is_dir():
        raise SystemExit(f"source_dir does not exist: {source_dir}")

    if package.get("ice2:license_status") == "unresolved":
        print(f"  ! {name} has unresolved licensing. Publishing it may not be permitted.")
        print("    Settle the redistribution terms before making it world-readable.\n")
    return prefix


def remote_manifest_check(resources: list[dict], base_url: str) -> tuple[list, list, list]:
    """HEAD every resource anonymously. Returns (ok, missing, wrong_size)."""
    ok, missing, wrong = [], [], []
    for resource in resources:
        url = f"{base_url}/{resource['path']}"
        request = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                length = int(response.headers.get("Content-Length", -1))
            (ok if length == resource["bytes"] else wrong).append((resource, length))
        except urllib.error.HTTPError as error:
            missing.append((resource, error.code))
        except Exception as error:  # noqa: BLE001 - network shapes vary
            missing.append((resource, str(error)))
    return ok, missing, wrong


def locality(path: str, bearer: str) -> str:
    """ONLINE (disk) / NEARLINE (tape only) / ONLINE_AND_NEARLINE (both)."""
    url = f"{FRONTEND}/namespace/{path.lstrip('/')}?locality=true"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response).get("fileLocality", "unknown")
    except Exception as error:  # noqa: BLE001
        return f"unknown ({error})"


def chmod(path: str, mode: int, bearer: str) -> int:
    request = urllib.request.Request(
        f"{FRONTEND}/namespace/{path.lstrip('/')}",
        data=json.dumps({"action": "chmod", "mode": mode}).encode(),
        headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def run(catalog_root: Path, args) -> int:
    catalog_meta = yaml.safe_load((catalog_root / "catalog.yaml").read_text())
    base_url = catalog_meta["ice2:publication_url"].rstrip("/")

    meta, package, source_dir, dataset_dir = load(catalog_root, args.dataset)
    prefix = preflight(args.dataset, package, source_dir, args.allow_internal, args.verify_only)

    # The upload destination and the URL we verify afterwards have to name the
    # same folder, so derive the default from the catalogue rather than repeating
    # it. They drifted apart once already, when the publication root moved from
    # reskit-data to ice2-data-files: bytes would have gone to the old folder and
    # every verification HEAD would have 404d against the new one, which reads
    # like a permissions problem and is not one.
    published_root = base_url.rstrip("/").rsplit("/", 1)[-1]
    root = args.root or published_root
    if args.root and args.root != published_root:
        raise SystemExit(
            f"--root {args.root!r} does not match the catalogue's publication root "
            f"{published_root!r} (from ice2:publication_url in catalog.yaml).\n"
            f"Uploading to {args.root!r} would publish bytes that {base_url}/... never serves.\n"
            "Fix ice2:publication_url, or drop --root to use the catalogue's own value."
        )

    namespace_path = f"{args.vo_path}/{root}/{prefix}"
    destination = f"{args.remote}:{root}/{prefix}"
    dataset_url = f"{base_url}/{prefix}"

    print(f"dataset      {args.dataset}  ({package['ice2:file_count']} files, "
          f"{package['ice2:total_bytes'] / 1e6:,.1f} MB)")
    print(f"from         {source_dir or '(already uploaded -- no local source_dir)'}")
    print(f"to           {destination}")
    print(f"public URL   {dataset_url}\n")

    resources = resources_of(package, dataset_dir)

    if not args.verify_only:
        # Upload the manifest, not the directory. They are the same thing only
        # when nothing else lives under source_dir; with ice2:include or
        # ice2:exclude in play they are not, and `rclone copy <dir>` would
        # publish the strays the manifest deliberately leaves out -- silently,
        # since verification only ever looks for files it knows about.
        handle, listing_path = tempfile.mkstemp(
            prefix=f"ice2-upload-{args.dataset}-", suffix=".txt", text=True)
        with open(handle, "w") as listing_file:
            listing_file.writelines(f"{resource['path']}\n" for resource in resources)
        listing = Path(listing_path)
        command = [
            "rclone", "copy", str(source_dir), destination,
            "--files-from", str(listing),
            "--transfers", str(args.transfers),
            "--checksum",
            # dCache cannot modify a file in place -- a changed file is delete +
            # rewrite. --immutable makes rclone fail loudly if a published file
            # differs, instead of silently republishing under the same path.
            "--immutable",
            "--progress" if not args.dry_run else "--dry-run",
        ]
        print(f"  ({len(resources)} files listed in {listing})")
        print("  $ " + " ".join(command) + "\n")
        try:
            result = subprocess.run(command)
        finally:
            listing.unlink(missing_ok=True)
        if result.returncode != 0:
            print("\nrclone failed. Common causes:", file=sys.stderr)
            print("  * no rclone remote called "
                  f"{args.remote!r} -- check ~/.config/rclone/rclone.conf", file=sys.stderr)
            print("  * oidc-agent not running, so bearer_token_command returned nothing", file=sys.stderr)
            print("  * --immutable tripped: a published file changed. Publish it at a "
                  "NEW path rather than overwriting.", file=sys.stderr)
            return result.returncode
        if args.dry_run:
            print("\nDry run only; nothing was uploaded.")
            return 0

    bearer = token(args.oidc_profile)

    if not args.no_chmod and package.get("ice2:access") == "public":
        status = chmod(namespace_path, MODE_0755, bearer)
        print(f"\nchmod 0755 {namespace_path} -> HTTP {status}")
        if status not in (200, 204):
            print("  chmod failed; anonymous reads will 401 until it succeeds.")

    print("\nverifying anonymous access (no credentials, exactly what a public user gets)")
    ok, missing, wrong = remote_manifest_check(resources, dataset_url)
    print(f"  readable       {len(ok)}/{package['ice2:file_count']}")
    if wrong:
        print(f"  WRONG SIZE     {len(wrong)}")
        for resource, length in wrong[:5]:
            print(f"    {resource['path']}: {length} on server, {resource['bytes']} in manifest")
    if missing:
        print(f"  NOT READABLE   {len(missing)}")
        for resource, why in missing[:5]:
            print(f"    {resource['path']}: {why}")
        print("\n  A 401 here means the directory is not world-readable yet.")
        print(f"    curl -H \"Authorization: Bearer $(oidc-token {args.oidc_profile})\" \\")
        print("      -H 'Content-Type: application/json' -X POST \\")
        print(f"      '{FRONTEND}/namespace/{namespace_path}' -d '{{\"action\":\"chmod\",\"mode\":493}}'")

    sample = resources[0]["path"]
    where = locality(f"{namespace_path}/{sample}", bearer)
    print(f"\n  storage locality of {sample}: {where}")
    if where == "NEARLINE":
        print("    NEARLINE means tape only -- the first read will block on staging.")
    elif where == "ONLINE":
        print("    ONLINE means disk. Large files may also gain a tape copy after ~1 week.")

    return 1 if (missing or wrong) else 0
