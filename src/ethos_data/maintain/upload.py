"""Upload a dataset to DESY dCache InfiniteSpace, then prove it is readable.

    ethos-data catalog upload reskit-test-data --dry-run
    ethos-data catalog upload reskit-test-data
    ethos-data catalog upload reskit-test-data --verify-only

One dataset, or a subset of the catalogue -- naming them by name or by path:

    ethos-data catalog upload global-wind-atlas-v4 global-solar-atlas
    ethos-data catalog upload datasets/global-wind-atlas-v4

The verify stage is the point of this tool. Uploading is one rclone call;
knowing that an anonymous user on the other side of the internet can actually
read what you uploaded is the part that goes wrong, and it goes wrong quietly.

It runs as a pipeline (see :mod:`.pipeline`), and a dry run is its plan:

``check``        load and check every dataset named, before any byte moves
``transfer``     copy each dataset's inventory to dCache
``permissions``  make each dataset's folder world-readable
``verify``       read every file back anonymously, as any reader does
``record``       record each verified upload in the dataset's ``status.yaml``

Requires:
  * oidc-agent with a profile (default "HIFIS") -- `oidc-token HIFIS` must work
  * an rclone remote (default "HIFIS") pointing at /Helmholtz/<VO>

Guard rails:
  * only public data is uploaded: a restricted dataset is refused, and its
    installation is registered by name in a restricted cache instead
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
``status.yaml`` as a copy on dCache, and makes a built dataset available. A
dataset whose upload of its current inventory is verified and recorded is
not uploaded again, so a run interrupted half-way is finished by running it
again; a failed dataset does not stop the others.
"""

from __future__ import annotations

import dataclasses
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
from ..formats.catalogue import store_of
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
)
from . import status as dataset_status
from .pipeline import Action, Pipeline


@dataclass(frozen=True)
class UploadOptions:
    """The flags of ``ethos-data catalog upload``, with the command's defaults.

    ``remote``, ``oidc_profile`` and ``vo_path`` left None are taken from
    ``catalog.yaml``'s ``ethos:store``, whose own defaults are the institute's dCache.
    """

    remote: str | None = None
    oidc_profile: str | None = None
    vo_path: str | None = None
    #: The publication root under the VO; None means the catalogue's own.
    root: str | None = None
    dry_run: bool = False
    verify_only: bool = False
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
    name: str, package: dict, source_dir: Path | None, verify_only: bool
) -> str:
    """The dataset's folder on the store, after the checks of the step.

    Raises :class:`~ethos_data.errors.TransitionError` for data that is not
    public or whose licensing is not settled, and
    :class:`~ethos_data.errors.UploadError` when nothing is left to upload.
    """
    access = package.get(k.ACCESS, k.PUBLIC)
    # The documented default, and the folder the reader downloads from: the
    # dataset's own name unless it declares a prefix.
    prefix = remote_prefix_of(package)

    # The guards of the step, ahead of the mechanical checks below: they do
    # not depend on how the dataset is configured, and being told about a
    # missing prefix instead would send somebody off to fix the wrong thing.
    # --verify-only rechecks what is published and hands nothing out.
    lifecycle.guard(
        "upload",
        name,
        access=access,
        settled=verify_only or license_settled(package),
        note=package.get(k.LICENSE_NOTE, ""),
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
    #: Its status file, which records the upload.
    status: StatusFile


@dataclass
class Upload:
    """What ``catalog upload`` was asked for, and what its stages found."""

    catalog_root: Path
    arguments: list[str]
    options: UploadOptions
    store: Store
    #: The store's REST interface, for the command a failed read-back prints.
    frontend: str = FRONTEND
    #: The publication URL and the folder under the VO it serves: set by ``check``.
    base_url: str = ""
    root: str = ""
    #: Each dataset cleared for upload, in the order asked for: set by ``check``.
    plans: list[Plan] = field(default_factory=list)
    _token: list[str] = field(default_factory=list)

    def bearer(self) -> str:
        """One token for the whole run, asked for when an action first needs it."""
        if not self._token:
            self._token.append(self.store.token(self.options.oidc_profile))
        return self._token[0]

    def url(self, plan: Plan) -> str:
        return resource_url(self.base_url, plan.prefix)

    def namespace_path(self, plan: Plan) -> str:
        return f"{self.options.vo_path}/{self.root}/{plan.prefix}"


def _uploaded(status: StatusFile, location: str) -> bool:
    """Whether the status file records a verified upload of the current inventory."""
    return status.state == lifecycle.AVAILABLE and any(
        copy.kind == k.COPY_UPLOADED
        and copy.location == location
        and copy.verified is not None
        for copy in status.copies
    )


class Check:
    """Load and check every dataset named before any byte moves."""

    name = "check"

    def plan(self, upload: Upload) -> list[Action]:
        options = upload.options
        catalog_meta = read_catalog_meta(upload.catalog_root)
        upload.base_url = catalog_meta[k.PUBLICATION_URL].rstrip("/")
        # The upload destination and the URL read back afterwards name the same
        # folder, so the default comes from the catalogue. Were they to differ,
        # the bytes would go to one folder and every read-back would 404
        # against the other, which reads like a permissions problem and is not
        # one.
        published_root = upload.base_url.rsplit("/", 1)[-1]
        upload.root = options.root or published_root
        if options.root and options.root != published_root:
            raise UploadError(
                f"--root {options.root!r} does not match the catalogue's publication "
                f"root {published_root!r} (from ethos:publication_url in catalog.yaml).\n"
                f"Uploading to {options.root!r} would publish bytes that "
                f"{upload.base_url}/... never serves.\n"
                "Fix ethos:publication_url, or drop --root to use the catalogue's own "
                "value."
            )

        # Deduplicated, because naming a dataset twice should cost one upload,
        # and ordered, so the run reads in the order it was asked for.
        names = dict.fromkeys(
            expand_families(
                upload.catalog_root,
                [resolve_name(upload.catalog_root, each) for each in upload.arguments],
            )
        )
        step = "verify" if options.verify_only else "upload"
        for name in names:
            meta, package, source_dir, dataset_dir = load(upload.catalog_root, name)
            prefix = preflight(name, package, source_dir, options.verify_only)
            status = dataset_status.build_input(dataset_dir, meta, name).status
            plan = Plan(name, package, source_dir, dataset_dir, prefix, status)
            if not options.verify_only and _uploaded(status, upload.url(plan)):
                report.info(
                    f"  {self.name:<12} {name}: its upload is verified and recorded "
                    "already; --verify-only rechecks it"
                )
                continue
            lifecycle.step(step, status.state, name)
            upload.plans.append(plan)

        if len(upload.plans) > 1:
            files = sum(plan.package[k.FILE_COUNT] for plan in upload.plans)
            size = sum(plan.package[k.TOTAL_BYTES] for plan in upload.plans)
            report.info(
                f"{len(upload.plans)} datasets, {files:,} files, {size / 1e9:,.2f} GB"
            )
        return []


class Transfer:
    """Copy each dataset's inventory, and nothing else, to the store."""

    name = "transfer"

    def plan(self, upload: Upload) -> list[Action]:
        if upload.options.verify_only:
            return []
        return [
            Action(
                f"copy {plan.package[k.FILE_COUNT]:,} files "
                f"({plan.package[k.TOTAL_BYTES] / 1e6:,.1f} MB) of {plan.name} from "
                f"{plan.source_dir} to {upload.options.remote}:{upload.root}/"
                f"{plan.prefix}",
                self._copy(upload, plan),
                subject=plan.name,
            )
            for plan in upload.plans
        ]

    @staticmethod
    def _copy(upload: Upload, plan: Plan):
        def copy() -> None:
            records = inventory_of(plan.name, plan.dataset_dir).records()
            upload.store.copy(
                plan.source_dir,
                f"{upload.root}/{plan.prefix}",
                [record[k.PATH] for record in records],
                transfers=upload.options.transfers,
            )

        return copy


class Permissions:
    """Make each dataset's folder world-readable."""

    name = "permissions"

    def plan(self, upload: Upload) -> list[Action]:
        if upload.options.no_chmod:
            return []
        return [
            Action(
                f"chmod 0755 {upload.namespace_path(plan)}",
                self._chmod(upload, plan),
                subject=plan.name,
            )
            for plan in upload.plans
        ]

    @staticmethod
    def _chmod(upload: Upload, plan: Plan):
        def chmod() -> None:
            try:
                upload.store.chmod(
                    upload.namespace_path(plan), MODE_0755, upload.bearer()
                )
            except UploadError as error:
                # The read-back that follows says whether it mattered.
                report.warning(f"{error.message}; anonymous reads fail without it.")

        return chmod


class Verify:
    """Read every file back anonymously, as a reader on the internet does."""

    name = "verify"

    def plan(self, upload: Upload) -> list[Action]:
        return [
            Action(
                f"read the {plan.package[k.FILE_COUNT]:,} files of {plan.name} back "
                f"anonymously from {upload.url(plan)}",
                self._verify(upload, plan),
                subject=plan.name,
            )
            for plan in upload.plans
        ]

    @staticmethod
    def _verify(upload: Upload, plan: Plan):
        def verify() -> None:
            resources = inventory_of(plan.name, plan.dataset_dir).records()
            dataset_url = upload.url(plan)
            namespace_path = upload.namespace_path(plan)
            ok, missing, wrong = read_back(upload.store, resources, dataset_url)
            report.info(f"\n{plan.name}, read back anonymously from {dataset_url}")
            report.info(f"  readable       {len(ok)}/{plan.package[k.FILE_COUNT]}")
            if wrong:
                report.info(f"  WRONG SIZE     {len(wrong)}")
                for resource, length in wrong[:5]:
                    report.info(
                        f"    {resource[k.PATH]}: {length} on server, "
                        f"{resource[k.BYTES]} in manifest"
                    )
            if missing:
                report.info(f"  NOT READABLE   {len(missing)}")
                for _resource, why in missing[:5]:
                    report.info(f"    {why}")
                report.info("\n  A 401 here means the directory is not world-readable.")
                report.info(
                    f'    curl -H "Authorization: Bearer $(oidc-token '
                    f'{upload.options.oidc_profile})" \\'
                )
                report.info("      -H 'Content-Type: application/json' -X POST \\")
                report.info(
                    f"      '{upload.frontend}/namespace/{namespace_path}' "
                    """-d '{"action":"chmod","mode":493}'"""
                )

            sample = resources[0][k.PATH]
            try:
                where = upload.store.locality(
                    f"{namespace_path}/{sample}", upload.bearer()
                )
            except UploadError as error:
                where = f"unknown ({error.message})"
            report.info(f"  storage locality of {sample}: {where}")
            if where == "NEARLINE":
                report.info(
                    "    NEARLINE means tape only -- the first read will block on staging."
                )
            elif where == "ONLINE":
                report.info(
                    "    ONLINE means disk. Large files may also gain a tape copy after "
                    "~1 week."
                )

            if missing or wrong:
                raise UploadError(
                    f"{len(missing)} file(s) of {plan.name} are not readable and "
                    f"{len(wrong)} have the wrong size at {dataset_url}"
                )

        return verify


class Record:
    """Record each verified upload as a copy on dCache in the status file."""

    name = "record"

    def plan(self, upload: Upload) -> list[Action]:
        step = "verify" if upload.options.verify_only else "upload"
        return [
            Action(
                f"{plan.name} becomes {lifecycle.step(step, plan.status.state)}, its "
                "copy on dCache verified",
                self._record(upload, plan, step),
                subject=plan.name,
            )
            for plan in upload.plans
        ]

    @staticmethod
    def _record(upload: Upload, plan: Plan, step: str):
        def record() -> None:
            dataset_status.take(
                plan.dataset_dir,
                dataset_status.read(plan.dataset_dir),
                step,
                dataset=plan.name,
                copy=Copy(
                    kind=k.COPY_UPLOADED,
                    location=upload.url(plan),
                    verified=dataset_status.now(),
                ),
                files=plan.package[k.FILE_COUNT],
                bytes=plan.package[k.TOTAL_BYTES],
            )

        return record


PIPELINE: Pipeline[Upload] = Pipeline(
    "upload", [Check(), Transfer(), Permissions(), Verify(), Record()]
)


@dataclass
class UploadResult:
    """The datasets an upload handled, and why each one that failed did."""

    datasets: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed


@report.reported
def run(
    catalog_root: Path,
    datasets: list[str],
    options: UploadOptions | None = None,
    *,
    store: Store | None = None,
) -> UploadResult:
    """Upload ``datasets`` -- names, paths or families -- and verify each anonymously.

    Every dataset is loaded and checked before any of them is uploaded, and a
    dry run is the plan: it contacts no store. ``options`` are the command's
    flags, over the store settings of ``catalog.yaml``; ``store`` is the
    publication store, dCache through the remote they name by default;
    ``reporter=`` takes the progress.
    """
    settings = store_of(read_catalog_meta(catalog_root))
    options = dataclasses.replace(
        options or UploadOptions(),
        remote=(options and options.remote) or settings.remote,
        oidc_profile=(options and options.oidc_profile) or settings.oidc_profile,
        vo_path=(options and options.vo_path) or settings.vo_path,
    )
    if store is None:
        store = DcacheStore(options.remote, settings.frontend)
    upload = Upload(catalog_root, list(datasets), options, store, settings.frontend)
    outcome = PIPELINE.run(upload, dry_run=options.dry_run)
    result = UploadResult([plan.name for plan in upload.plans], outcome.failed)
    if len(upload.plans) > 1 and not options.dry_run:
        report.info("\n" + "=" * 72)
        report.info(
            f"{len(upload.plans) - len(result.failed)}/{len(upload.plans)} datasets ok"
        )
        for name, why in result.failed.items():
            report.info(f"  FAILED   {name}: {why.splitlines()[0]}")
    return result
