"""Upload a dataset to DESY dCache InfiniteSpace, then prove it is readable.

    ethos-data catalog upload reskit-test-data --dry-run
    ethos-data catalog upload reskit-test-data
    ethos-data catalog upload reskit-test-data --verify-only

One dataset, or a subset of the catalogue -- naming them by name or by path:

    ethos-data catalog upload global-wind-atlas-v4 global-solar-atlas
    ethos-data catalog upload datasets/global-wind-atlas-v4

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
  * every dataset named is loaded and checked before any of them is uploaded,
    so a subset upload cannot publish two datasets and then refuse the third
  * only files in the manifest are uploaded.  A source_dir narrowed by
    ``ethos:include`` / ``ethos:exclude`` is usually a shared download directory
    holding things that are not the dataset, so "copy the directory" is not the
    same instruction as "publish the dataset"
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from .. import report
from ..errors import UploadError
from ..formats import keys as k
from ..formats.derived import license_settled, remote_prefix_of, resource_url
from ..formats.keys import ROLE_PUBLISHED
from . import (
    catalogue_role,
    dataset_name_for,
    datasets_dir,
    is_namespace,
    iter_dataset_dirs,
    read_catalog_meta,
    read_descriptor,
    resources_of,
    source_dir_of,
)


@dataclass(frozen=True)
class UploadOptions:
    """The flags of ``ethos-data catalog upload``, with the command's defaults."""

    remote: str = "HIFIS"
    oidc_profile: str = "HIFIS"
    vo_path: str = "Helmholtz/FZJ-ICE2"
    #: The publication root under the VO; None means the catalogue's own.
    root: str | None = None
    dry_run: bool = False
    verify_only: bool = False
    allow_internal: bool = False
    no_chmod: bool = False
    transfers: int = 8


FRONTEND = "https://hifis-storage-web.desy.de/api/v1"
MODE_0755 = 493  # dCache wants the mode as a decimal integer, not octal


def _capture(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, **kwargs)


def token(profile: str) -> str:
    result = _capture(["oidc-token", profile])
    if result.returncode != 0 or not result.stdout.strip():
        raise UploadError(
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
        known = sorted(
            dataset_name_for(datasets_dir(catalog_root), d)
            for d in iter_dataset_dirs(datasets_dir(catalog_root))
        )
        listing = "\n".join(f"    {name}" for name in known) or "    (none)"
        raise UploadError(
            f"no dataset called {dataset_name!r} in {datasets_dir(catalog_root)}.\n"
            f"Datasets in this catalogue:\n{listing}\n"
            "To add one, see docs/how-to/catalogue-maintainers/add-a-dataset.md."
        )
    if not package_file.is_file():
        raise UploadError(
            f"{dataset_name!r} has no datapackage.json yet. Run:\n"
            f"    ethos-data catalog build {dataset_name}"
        )
    meta = read_descriptor(dataset_dir)
    package = json.loads(package_file.read_text(encoding="utf-8"))
    # None for a dataset marked ethos:uploaded: true -- dCache is already the
    # source of truth, and there is nothing local left to read bytes from.
    return meta, package, source_dir_of(dataset_dir, meta), dataset_dir


def preflight(
    name: str,
    package: dict,
    source_dir: Path | None,
    allow_internal: bool,
    verify_only: bool,
) -> str:
    access = package.get(k.ACCESS, k.PUBLIC)
    # The documented default, and the folder the reader downloads from: the
    # dataset's own name unless it declares a prefix.
    prefix = remote_prefix_of(package)

    if access == k.RESTRICTED:
        raise UploadError(
            f"{name} is restricted and must never be uploaded.\n"
            "Restricted data stays where it is; register it in a restricted cache:\n"
            f"    ethos-data link {name} /path/to/{name}"
        )
    if access == "internal" and not allow_internal:
        raise UploadError(
            f"{name} is internal (not published). Upload it only if the VO-only "
            "prefix is really where you want it, and pass --allow-internal.\n"
            "It will NOT be made world-readable."
        )

    # Ahead of the mechanical checks below, and no longer a warning. Publishing
    # is the irreversible half of this: once the bytes are on dCache under terms
    # nobody has read, "we were not sure" stops being a position anybody can
    # take. It comes first because it is the reason that does not depend on how
    # the dataset is configured -- being told about a missing prefix instead
    # sends somebody off to fix the wrong thing. --verify-only is still allowed:
    # rechecking what is already published copies nothing.
    if not verify_only and not license_settled(package):
        note = package.get(k.LICENSE_NOTE, "")
        raise UploadError(
            f"{name} has unresolved licensing and is not uploaded. {note}\n".rstrip()
            + "\n"
            "Record the terms in its dataset.yaml -- a `licenses:` entry, or "
            "`ethos:license_status: resolved` once somebody has read them -- and rebuild.\n"
            "Development against it does not need an upload; stage it instead:\n"
            f"    staging add {name} <directory>  (with your package's data command)"
        )

    if source_dir is None:
        if not verify_only:
            raise UploadError(
                f"{name} has no source_dir (ethos:uploaded: true) -- there is nothing left "
                "to upload. Pass --verify-only to recheck what is already on dCache, or "
                "unset ethos:uploaded and restore source_dir to publish a fresh copy."
            )
    elif not source_dir.is_dir():
        raise UploadError(f"source_dir does not exist: {source_dir}")
    return prefix


def remote_manifest_check(
    resources: list[dict], base_url: str
) -> tuple[list, list, list]:
    """HEAD every resource anonymously. Returns (ok, missing, wrong_size).

    ``base_url`` is the dataset's folder on the published store.
    """
    ok, missing, wrong = [], [], []
    for resource in resources:
        url = f"{base_url.rstrip('/')}/{resource[k.PATH]}"
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
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def resolve_name(catalog_root: Path, argument: str) -> str:
    """Turn one command-line argument -- a name, or a path -- into a dataset name.

    Paths are accepted because they are what shell completion produces: someone
    looking at ``datasets/global-wind-atlas-v4`` will type that, and answering
    "no dataset called 'datasets/global-wind-atlas-v4'" teaches them nothing.
    """
    datasets = datasets_dir(catalog_root)

    # A nested dataset's name contains a slash -- `reskit-test-data/era5` -- so a
    # slash does not mean "this is a path". Try it as a name first: if it names
    # a described dataset, that is what it is.
    if (
        not Path(argument).is_absolute()
        and (datasets / argument / "dataset.yaml").is_file()
    ):
        return argument
    # Anything still holding a separator is a path. Both of them, not just "/":
    # on Windows shell completion produces `datasets\global-wind-atlas-v4`, the
    # one form of the argument a Windows user is most likely to type.
    if not any(sep and sep in argument for sep in (os.sep, os.altsep, "/")):
        return argument

    path = Path(argument).expanduser().resolve()
    # Resolve BOTH sides before asking whether one contains the other, so the
    # two are written the same way: `resolve()` expands a Windows 8.3 short
    # name, and %TEMP% is one for any account whose name holds a dot, so
    # `C:\Users\JA60A~1.BEL\...` and `C:\Users\j.belina\...` name the same
    # directory and compare unequal unless both are resolved. A symlinked home
    # or /tmp does the same thing on Linux.
    resolved_datasets = datasets.expanduser().resolve()
    if path.is_relative_to(resolved_datasets) and (path / "dataset.yaml").is_file():
        return dataset_name_for(resolved_datasets, path)

    # Naming a directory in the *published* catalogue is the easy mistake to
    # make: it has the same datasets/<name> layout, so the path looks right, but
    # it carries no dataset.yaml and no source_dir -- there are no local bytes
    # there to upload, and never were.
    if catalogue_role(path.parent.parent) == ROLE_PUBLISHED:
        raise UploadError(
            f"{path}\nis in a {ROLE_PUBLISHED} catalogue, which carries descriptors only "
            "-- no dataset.yaml, no source_dir, so nothing to upload from.\n"
            f"Name it in the source catalogue instead:\n"
            f"    ethos-data catalog upload {path.name}"
        )
    raise UploadError(
        f"{path}\nis not a dataset of the catalogue being uploaded from.\n"
        f"  catalogue  {catalog_root}\n"
        f"  datasets   {datasets}\n"
        "Pass a bare dataset name, or a path inside that datasets directory."
    )


def expand_families(catalog_root: Path, names: list[str]) -> list[str]:
    """Replace a family name by its member datasets, in name order.

    A namespace -- ``reskit-test-data`` -- describes no files and carries no
    licence of its own, so as an upload it is nothing, and checking it as one
    dataset only produces a puzzling "unresolved licensing". What somebody
    naming it means is "every member under it". Expanded here, before any
    check, so the members are vetted and uploaded exactly as if listed.
    """
    root = datasets_dir(catalog_root)
    expanded: list[str] = []
    for name in names:
        dataset_dir = root / name
        if not (dataset_dir / "dataset.yaml").is_file() or not is_namespace(
            dataset_dir
        ):
            expanded.append(name)
            continue
        members = [
            dataset_name_for(root, member)
            for member in iter_dataset_dirs(dataset_dir)
            if member != dataset_dir and not is_namespace(member)
        ]
        if not members:
            raise UploadError(
                f"{name} is a family with no member dataset beneath it; nothing to upload."
            )
        report.info(
            f"{name} is a family: its {len(members)} members are uploaded in its place"
        )
        expanded.extend(members)
    return expanded


class Plan(NamedTuple):
    """One dataset, loaded and cleared for upload."""

    name: str
    package: dict
    source_dir: Path | None
    dataset_dir: Path
    prefix: str


def upload_one(
    options: UploadOptions, plan: Plan, base_url: str, root: str, bearer
) -> int:
    """Upload and verify a single dataset. Returns a process-style exit code."""
    namespace_path = f"{options.vo_path}/{root}/{plan.prefix}"
    destination = f"{options.remote}:{root}/{plan.prefix}"
    dataset_url = resource_url(base_url, plan.prefix)

    report.info(
        f"dataset      {plan.name}  ({plan.package['ethos:file_count']} files, "
        f"{plan.package['ethos:total_bytes'] / 1e6:,.1f} MB)"
    )
    report.info(
        f"from         {plan.source_dir or '(already uploaded -- no local source_dir)'}"
    )
    report.info(f"to           {destination}")
    report.info(f"public URL   {dataset_url}\n")

    resources = resources_of(plan.package, plan.dataset_dir)

    if not options.verify_only:
        # Upload the manifest, not the directory. They are the same thing only
        # when nothing else lives under source_dir; with ethos:include or
        # ethos:exclude in play they are not, and `rclone copy <dir>` would
        # publish the strays the manifest deliberately leaves out -- silently,
        # since verification only ever looks for files it knows about.

        # A nested dataset's name is `reskit-test-data/era5`, and a slash is a
        # directory separator in a filename on every platform -- on Windows not
        # a legal character in one at all. Flatten it, or naming such a dataset
        # fails in mkstemp before a single byte is uploaded.
        stem = plan.name.replace("/", "-").replace(os.sep, "-")
        handle, listing_path = tempfile.mkstemp(
            prefix=f"ethos-data-upload-{stem}-", suffix=".txt"
        )
        # rclone reads --files-from as UTF-8, one path per line. Written as bytes
        # because a text-mode write on Windows would end every line CRLF, and
        # rclone would then look for files whose names end in a carriage return.
        with open(handle, "wb") as listing_file:
            listing_file.writelines(
                f"{resource['path']}\n".encode() for resource in resources
            )
        listing = Path(listing_path)
        command = [
            "rclone",
            "copy",
            str(plan.source_dir),
            destination,
            "--files-from",
            str(listing),
            "--transfers",
            str(options.transfers),
            "--checksum",
            # dCache cannot modify a file in place -- a changed file is delete +
            # rewrite. --immutable makes rclone fail loudly if a published file
            # differs, instead of silently republishing under the same path.
            "--immutable",
            "--progress" if not options.dry_run else "--dry-run",
        ]
        report.info(f"  ({len(resources)} files listed in {listing})")
        report.info("  $ " + " ".join(command) + "\n")
        try:
            result = subprocess.run(command)
        finally:
            listing.unlink(missing_ok=True)
        if result.returncode != 0:
            report.warning("\nrclone failed. Common causes:")
            report.warning(
                "  * no rclone remote called "
                f"{options.remote!r} -- check ~/.config/rclone/rclone.conf"
            )
            report.warning(
                "  * oidc-agent not running, so bearer_token_command returned nothing"
            )
            report.warning(
                "  * --immutable tripped: a published file changed. Publish it at a "
                "NEW path rather than overwriting."
            )
            return result.returncode
        if options.dry_run:
            report.info("\nDry run only; nothing was uploaded.")
            return 0

    if not options.no_chmod and plan.package.get(k.ACCESS, k.PUBLIC) == k.PUBLIC:
        status = chmod(namespace_path, MODE_0755, bearer())
        report.info(f"\nchmod 0755 {namespace_path} -> HTTP {status}")
        if status not in (200, 204):
            report.info("  chmod failed; anonymous reads will 401 until it succeeds.")

    report.info(
        "\nverifying anonymous access (no credentials, exactly what a public user gets)"
    )
    ok, missing, wrong = remote_manifest_check(resources, dataset_url)
    report.info(f"  readable       {len(ok)}/{plan.package['ethos:file_count']}")
    if wrong:
        report.info(f"  WRONG SIZE     {len(wrong)}")
        for resource, length in wrong[:5]:
            report.info(
                f"    {resource['path']}: {length} on server, {resource['bytes']} in manifest"
            )
    if missing:
        report.info(f"  NOT READABLE   {len(missing)}")
        for resource, why in missing[:5]:
            report.info(f"    {resource['path']}: {why}")
        report.info("\n  A 401 here means the directory is not world-readable yet.")
        report.info(
            f'    curl -H "Authorization: Bearer $(oidc-token {options.oidc_profile})" \\'
        )
        report.info("      -H 'Content-Type: application/json' -X POST \\")
        report.info(
            f'      \'{FRONTEND}/namespace/{namespace_path}\' -d \'{{"action":"chmod","mode":493}}\''
        )

    sample = resources[0]["path"]
    where = locality(f"{namespace_path}/{sample}", bearer())
    report.info(f"\n  storage locality of {sample}: {where}")
    if where == "NEARLINE":
        report.info(
            "    NEARLINE means tape only -- the first read will block on staging."
        )
    elif where == "ONLINE":
        report.info(
            "    ONLINE means disk. Large files may also gain a tape copy after ~1 week."
        )

    return 1 if (missing or wrong) else 0


@dataclass
class UploadResult:
    """The datasets an upload handled, and those that failed with rclone's status."""

    datasets: list[str] = field(default_factory=list)
    failed: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed


@report.reported
def run(
    catalog_root: Path, datasets: list[str], options: UploadOptions | None = None
) -> UploadResult:
    """Upload ``datasets`` -- names, paths or families -- and verify each anonymously.

    Every dataset is loaded and checked before any of them is uploaded.
    ``options`` are the command's flags; ``reporter=`` takes the progress.
    """
    options = options or UploadOptions()
    catalog_meta = read_catalog_meta(catalog_root)
    base_url = catalog_meta[k.PUBLICATION_URL].rstrip("/")

    # The upload destination and the URL we verify afterwards have to name the
    # same folder, so derive the default from the catalogue rather than repeating
    # it. Were they to differ, the bytes would go to one folder and every
    # verification HEAD would 404 against the other, which reads like a
    # permissions problem and is not one.
    published_root = base_url.rstrip("/").rsplit("/", 1)[-1]
    root = options.root or published_root
    if options.root and options.root != published_root:
        raise UploadError(
            f"--root {options.root!r} does not match the catalogue's publication root "
            f"{published_root!r} (from ethos:publication_url in catalog.yaml).\n"
            f"Uploading to {options.root!r} would publish bytes that {base_url}/... never serves.\n"
            "Fix ethos:publication_url, or drop --root to use the catalogue's own value."
        )

    # Deduplicated, because naming a dataset twice should cost one upload, and
    # ordered, so the run reads in the order it was asked for.
    names = dict.fromkeys(
        expand_families(
            catalog_root,
            [resolve_name(catalog_root, argument) for argument in datasets],
        )
    )

    # Load and check EVERY dataset before uploading ANY of them. The checks that
    # matter here -- restricted data, an unbuilt manifest, a vanished source_dir
    # -- are exactly the ones you want to hear about before bytes start moving,
    # and a subset upload that dies on its fourth dataset has already published
    # three. Nothing below this loop can raise UploadError for a reason that was
    # knowable up here.
    plans = []
    for name in names:
        _meta, package, source_dir, dataset_dir = load(catalog_root, name)
        prefix = preflight(
            name, package, source_dir, options.allow_internal, options.verify_only
        )
        plans.append(Plan(name, package, source_dir, dataset_dir, prefix))

    # One token for the whole run, fetched only if something actually needs it:
    # a --dry-run never talks to dCache, and asking oidc-agent for a token it
    # will not use turns a rehearsal into a login prompt.
    cached: list[str] = []

    def bearer() -> str:
        if not cached:
            cached.append(token(options.oidc_profile))
        return cached[0]

    if len(plans) > 1:
        files = sum(plan.package["ethos:file_count"] for plan in plans)
        size = sum(plan.package["ethos:total_bytes"] for plan in plans)
        report.info(f"{len(plans)} datasets, {files:,} files, {size / 1e9:,.2f} GB")
        report.info(f"  {', '.join(plan.name for plan in plans)}\n")

    failed: dict[str, int] = {}
    for index, plan in enumerate(plans, start=1):
        if len(plans) > 1:
            report.info(
                f"---- [{index}/{len(plans)}] {plan.name} "
                + "-" * max(0, 50 - len(plan.name))
            )
        status = upload_one(options, plan, base_url, root, bearer)
        if status:
            failed[plan.name] = status
        if len(plans) > 1:
            report.info()

    result = UploadResult([plan.name for plan in plans], failed)
    if len(plans) == 1:
        return result

    report.info("=" * 72)
    report.info(f"{len(plans) - len(failed)}/{len(plans)} datasets ok")
    for name, status in failed.items():
        report.info(f"  FAILED   {name} (exit {status})")
    return result
