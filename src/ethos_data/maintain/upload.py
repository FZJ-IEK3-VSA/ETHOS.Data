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
  * the dataset's state must allow the step: a built dataset is uploaded, a
    frozen one only rechecked with ``--verify-only``

A verified upload, or a recheck that passes, is recorded in the dataset's
``status.yaml`` as a copy on dCache, and makes a built dataset available.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from .. import report
from ..adapters import Store
from ..adapters.dcache import FRONTEND, MODE_0755, DcacheStore
from ..errors import UploadError
from ..formats import keys as k
from ..formats.derived import license_settled, remote_prefix_of, resource_url
from ..formats.keys import ROLE_PUBLISHED
from ..formats.status_file import Copy, StatusFile
from ..model import lifecycle
from . import (
    catalogue_role,
    dataset_name_for,
    datasets_dir,
    inventory_of,
    is_namespace,
    iter_dataset_dirs,
    read_catalog_meta,
    read_descriptor,
    source_dir_of,
)
from . import status as dataset_status


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
    # None for a frozen dataset -- its authoritative copy is elsewhere, and
    # there is nothing local left to read bytes from.
    source = dataset_status.build_input(dataset_dir, meta, dataset_name).source_dir
    return meta, package, source, dataset_dir


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
                f"{name} has no source_dir: its inventory is final, so there is nothing "
                "left to upload. Pass --verify-only to recheck what is already on dCache."
            )
    elif not source_dir.is_dir():
        raise UploadError(f"source_dir does not exist: {source_dir}")
    return prefix


def read_back(
    store: Store, resources: list[dict], base_url: str
) -> tuple[list, list, list]:
    """Read every resource back anonymously: ``(ok, unreadable, wrong_size)``.

    ``base_url`` is the dataset's folder on the published store. ``ok`` and
    ``wrong_size`` hold ``(resource, size the server reports)``,
    ``unreadable`` holds ``(resource, why)``.
    """
    ok, unreadable, wrong = [], [], []
    for resource in resources:
        url = f"{base_url.rstrip('/')}/{resource[k.PATH]}"
        try:
            size = store.served(url)
        except UploadError as error:
            unreadable.append((resource, error.message))
            continue
        (ok if size == resource[k.BYTES] else wrong).append((resource, size))
    return ok, unreadable, wrong


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
    #: Its status file; None for a dataset without one, whose upload is not recorded.
    status: StatusFile | None = None


def upload_one(
    options: UploadOptions,
    plan: Plan,
    base_url: str,
    root: str,
    bearer,
    store: Store,
) -> None:
    """Upload and verify a single dataset; raises UploadError saying what failed."""
    namespace_path = f"{options.vo_path}/{root}/{plan.prefix}"
    destination = f"{options.remote}:{root}/{plan.prefix}"
    dataset_url = resource_url(base_url, plan.prefix)

    report.info(
        f"dataset      {plan.name}  ({plan.package['ethos:file_count']} files, "
        f"{plan.package['ethos:total_bytes'] / 1e6:,.1f} MB)"
    )
    report.info(
        f"from         {plan.source_dir or '(no source_dir: the inventory is final)'}"
    )
    report.info(f"to           {destination}")
    report.info(f"public URL   {dataset_url}\n")

    resources = inventory_of(plan.name, plan.dataset_dir).records()

    if not options.verify_only:
        store.copy(
            plan.source_dir,
            f"{root}/{plan.prefix}",
            [resource["path"] for resource in resources],
            transfers=options.transfers,
            dry_run=options.dry_run,
        )
        if options.dry_run:
            report.info("\nDry run only; nothing was uploaded.")
            return

    if not options.no_chmod and plan.package.get(k.ACCESS, k.PUBLIC) == k.PUBLIC:
        try:
            store.chmod(namespace_path, MODE_0755, bearer())
            report.info(f"\nchmod 0755 {namespace_path}")
        except UploadError as error:
            report.warning(
                f"{error.message}; anonymous reads fail without it."
            )

    report.info(
        "\nverifying anonymous access (no credentials, exactly what a public user gets)"
    )
    ok, missing, wrong = read_back(store, resources, dataset_url)
    report.info(f"  readable       {len(ok)}/{plan.package['ethos:file_count']}")
    if wrong:
        report.info(f"  WRONG SIZE     {len(wrong)}")
        for resource, length in wrong[:5]:
            report.info(
                f"    {resource['path']}: {length} on server, {resource['bytes']} in manifest"
            )
    if missing:
        report.info(f"  NOT READABLE   {len(missing)}")
        for _resource, why in missing[:5]:
            report.info(f"    {why}")
        report.info("\n  A 401 here means the directory is not world-readable yet.")
        report.info(
            f'    curl -H "Authorization: Bearer $(oidc-token {options.oidc_profile})" \\'
        )
        report.info("      -H 'Content-Type: application/json' -X POST \\")
        report.info(
            f'      \'{FRONTEND}/namespace/{namespace_path}\' -d \'{{"action":"chmod","mode":493}}\''
        )

    sample = resources[0]["path"]
    try:
        where = store.locality(f"{namespace_path}/{sample}", bearer())
    except UploadError as error:
        where = f"unknown ({error.message})"
    report.info(f"\n  storage locality of {sample}: {where}")
    if where == "NEARLINE":
        report.info(
            "    NEARLINE means tape only -- the first read will block on staging."
        )
    elif where == "ONLINE":
        report.info(
            "    ONLINE means disk. Large files may also gain a tape copy after ~1 week."
        )

    if missing or wrong:
        raise UploadError(
            f"{len(missing)} file(s) of {plan.name} are not readable and "
            f"{len(wrong)} have the wrong size at {dataset_url}"
        )


@dataclass
class UploadResult:
    """The datasets an upload handled, and why each one that failed did."""

    datasets: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed


def _record(plan: Plan, options: UploadOptions, base_url: str) -> bool:
    """Record a verified upload, or a recheck that passed; False without a status file."""
    status = dataset_status.read(plan.dataset_dir)
    if status is None:
        return False
    taken = dataset_status.take(
        plan.dataset_dir,
        status,
        "verify" if options.verify_only else "upload",
        dataset=plan.name,
        copy=Copy(
            kind=k.COPY_UPLOADED,
            location=resource_url(base_url, plan.prefix),
            verified=dataset_status.now(),
        ),
        files=plan.package[k.FILE_COUNT],
        bytes=plan.package[k.TOTAL_BYTES],
    )
    report.info(
        f"\nrecorded     {plan.name} is {taken.state}, its copy on dCache verified"
    )
    return True


@report.reported
def run(
    catalog_root: Path,
    datasets: list[str],
    options: UploadOptions | None = None,
    *,
    store: Store | None = None,
) -> UploadResult:
    """Upload ``datasets`` -- names, paths or families -- and verify each anonymously.

    Every dataset is loaded and checked before any of them is uploaded.
    ``options`` are the command's flags; ``store`` is the publication store,
    dCache through ``options.remote`` by default; ``reporter=`` takes the
    progress.
    """
    options = options or UploadOptions()
    store = store if store is not None else DcacheStore(options.remote)
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
        status = dataset_status.read(dataset_dir)
        if status is not None:
            lifecycle.step(
                "verify" if options.verify_only else "upload", status.state, name
            )
        plans.append(Plan(name, package, source_dir, dataset_dir, prefix, status))

    # One token for the whole run, fetched only if something actually needs it:
    # a --dry-run never talks to dCache, and asking oidc-agent for a token it
    # will not use turns a rehearsal into a login prompt.
    cached: list[str] = []

    def bearer() -> str:
        if not cached:
            cached.append(store.token(options.oidc_profile))
        return cached[0]

    if len(plans) > 1:
        files = sum(plan.package["ethos:file_count"] for plan in plans)
        size = sum(plan.package["ethos:total_bytes"] for plan in plans)
        report.info(f"{len(plans)} datasets, {files:,} files, {size / 1e9:,.2f} GB")
        report.info(f"  {', '.join(plan.name for plan in plans)}\n")

    failed: dict[str, str] = {}
    unrecorded: list[str] = []
    for index, plan in enumerate(plans, start=1):
        if len(plans) > 1:
            report.info(
                f"---- [{index}/{len(plans)}] {plan.name} "
                + "-" * max(0, 50 - len(plan.name))
            )
        # One dataset that fails does not stop the others: each was checked
        # before any byte moved, so what fails here is the transfer or the
        # read-back, and the summary names it.
        try:
            upload_one(options, plan, base_url, root, bearer, store)
        except UploadError as error:
            failed[plan.name] = error.message
            report.warning(error.message)
        else:
            if not options.dry_run and not _record(plan, options, base_url):
                unrecorded.append(plan.name)
        if len(plans) > 1:
            report.info()
    if unrecorded:
        report.warning(dataset_status.unrecorded(unrecorded))

    result = UploadResult([plan.name for plan in plans], failed)
    if len(plans) == 1:
        return result

    report.info("=" * 72)
    report.info(f"{len(plans) - len(failed)}/{len(plans)} datasets ok")
    for name, why in failed.items():
        report.info(f"  FAILED   {name}: {why.splitlines()[0]}")
    return result
