"""``catalog add-bundle``: take a bundle's ahead datasets into the catalogue.

    ethos-data catalog add-bundle /checkout/your_tool/test_data --dry-run
    ethos-data catalog add-bundle /checkout/your_tool/test_data

A package's bundle is ahead of the catalogue when it holds changes ``bundle
update`` recorded, or datasets the catalogue does not describe (see
:mod:`ethos_data.bundles`). ``add-bundle`` takes those datasets, or the ones
named, into the maintainer's clone, one step each:

=============  =================================================================
``add``        a dataset the catalogue does not describe: placed and built, as
               ``catalog add`` does, from the bundle's description
``revise``     a published dataset whose files changed: its next revision, as
               ``catalog build --revision`` makes it, while the catalogue is at
               the revision the bundle is aligned with
``rebuild``    a dataset not published yet whose files changed: built again
``describe``   a dataset whose description or licence documents changed
=============  =================================================================

The files are copied first into a build input the catalogue maintainers own,
``<into>/<dataset>`` or ``<into>/<dataset>@<revision>``, checked against
``bundle.json`` as they are copied, so the catalogue never reads a package
checkout. ``<into>`` is the clone's ``build-inputs/`` unless named: a folder
that ignores itself in git, and whose build input ``catalog record`` deletes
once the upload is the authoritative copy. A bundle is authoritative for its bytes and descriptions, not for
access or visibility: a change of either that comes from a bundle is refused.
Every step is recorded in the dataset's status file, and the families above
the datasets are built again last.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .. import report
from ..bundles import Bundle, load_bundle
from ..errors import MaintenanceError
from ..formats import keys as k
from ..formats.edit import without_keys
from ..model import digest, lifecycle, names
from . import (
    DESCRIPTOR,
    build_inputs_dir,
    datasets_dir,
    in_build_inputs,
    make_build_inputs,
    read_descriptor,
)
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "BundleIntake", "IntakeResult", "run"]


@dataclass
class BundleIntake:
    """The bundle ``add-bundle`` takes in, which of its datasets, and where to."""

    catalog_root: Path
    directory: Path
    into: Path
    names: list[str] = field(default_factory=list)
    remove_missing: bool = False
    bundle: Bundle | None = None
    #: The datasets taken in: set by the plan.
    taken: list[str] = field(default_factory=list)


def _published(status) -> bool:
    return status.state in (lifecycle.AVAILABLE, lifecycle.FROZEN) and any(
        copy.kind in (k.COPY_UPLOADED, k.COPY_MATERIALIZED) for copy in status.copies
    )


def _make_parent(intake: BundleIntake, target: Path) -> None:
    """Make the directory ``target`` is copied into, the default build inputs ignored in git."""
    if in_build_inputs(intake.catalog_root, target):
        make_build_inputs(intake.catalog_root)
    target.parent.mkdir(parents=True, exist_ok=True)


def _copy_files(bundle: Bundle, name: str, target: Path) -> None:
    """The bundled files of ``name`` into ``target``, each checked as it is copied."""
    if target.exists():
        raise MaintenanceError(
            f"{target} exists; a build input is written once. Remove it, or name "
            "another --into"
        )
    temporary = Path(tempfile.mkdtemp(prefix=".ethos-intake-", dir=target.parent))
    try:
        for key, resource in sorted(bundle.resources.items()):
            if resource.dataset != name:
                continue
            destination = temporary / resource.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle.file(key), destination)
            if destination.stat().st_size != resource.bytes or not digest.matches(
                resource.hash, digest.of_file(destination)
            ):
                raise MaintenanceError(
                    f"{key} differs from what the bundle records; record the change "
                    "with `bundle update` first"
                )
        temporary.rename(target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _description_text(bundle: Bundle, name: str) -> str:
    """The bundle's ``dataset.yaml`` of ``name``, as the catalogue keeps it."""
    path = bundle.path / k.BUNDLE_DESCRIPTIONS_DIR / name / DESCRIPTOR
    try:
        return without_keys(path.read_bytes().decode("utf-8"), [k.SOURCE_DIR])
    except ValueError:
        raise MaintenanceError(
            f"{path}: source_dir could not be left out line by line; write it as one "
            "key per line"
        ) from None


def _documents(bundle: Bundle, name: str) -> list[str]:
    from ..bundles import _license_documents

    return _license_documents(bundle.descriptions[name])


class Update:
    name = "update"

    def plan(self, intake: BundleIntake) -> list[Action]:
        bundle = load_bundle(intake.directory)
        intake.bundle = bundle
        ahead = bundle.ahead()
        wanted = intake.names or sorted(ahead)
        unknown = sorted(set(wanted) - set(bundle.datasets))
        if unknown:
            raise MaintenanceError(
                f"{', '.join(unknown)} is not a dataset of the bundle at {bundle.path}"
            )
        if not wanted:
            report.info(f"  {self.name:<12} the bundle at {bundle.path} is aligned")
            return []
        actions: list[Action] = []
        families: set[str] = set()
        for name in wanted:
            actions += self._dataset(intake, name)
            families.update(names.ancestors(name))
            intake.taken.append(name)
        actions = self._families(intake, sorted(families)) + actions
        if families:
            from . import manifest

            def rebuild() -> None:
                manifest.run(intake.catalog_root, sorted(families))

            actions.append(Action(f"build {', '.join(sorted(families))}", rebuild))
        return actions

    @staticmethod
    def _families(intake: BundleIntake, families: list[str]) -> list[Action]:
        actions = []
        bundle = intake.bundle
        for family in families:
            if family not in bundle.manifest.families:
                continue
            text = (
                bundle.path / k.BUNDLE_DESCRIPTIONS_DIR / family / DESCRIPTOR
            ).read_bytes()
            target = datasets_dir(intake.catalog_root) / family / DESCRIPTOR
            if target.is_file() and target.read_bytes() == text:
                continue

            def write(target=target, text=text) -> None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(text)

            verb = "describe" if target.is_file() else "add"
            actions.append(Action(f"{verb} the family {family}", write))
        return actions

    def _dataset(self, intake: BundleIntake, name: str) -> list[Action]:
        bundle = intake.bundle
        entry = bundle.datasets[name]
        directory = datasets_dir(intake.catalog_root) / name
        if not (directory / DESCRIPTOR).is_file():
            return [self._add(intake, name)]
        status = dataset_status.checked_status(directory, name, "build")
        meta = read_descriptor(directory)
        mine = bundle.descriptions[name]
        for key in (k.ACCESS, k.VISIBILITY):
            if mine.get(key, k.PUBLIC) != meta.get(key, k.PUBLIC):
                raise MaintenanceError(
                    f"{name}: the bundle says {key}: {mine.get(key, k.PUBLIC)}, the "
                    f"catalogue {meta.get(key, k.PUBLIC)}. A bundle is authoritative "
                    "for bytes and descriptions, not for access or visibility; change "
                    "them in the catalogue."
                )
        files = [change for change in entry.changes if not change.document]
        actions = []
        if any(change.document for change in entry.changes):
            actions.append(self._describe(intake, name, directory))
        if not files:
            if actions:
                from . import manifest

                actions.append(
                    Action(
                        f"build {name}",
                        lambda: manifest.run(intake.catalog_root, [name]),
                    )
                )
            return actions
        if entry.alignment is None or entry.alignment.revision != status.revision:
            raise MaintenanceError(
                f"{name}: the catalogue holds revision {status.revision}, and the "
                "bundle is aligned with "
                + (
                    f"revision {entry.alignment.revision}"
                    if entry.alignment
                    else "none"
                )
                + ". Realign the bundle first: <tool>-data bundle update DIR "
                f"--from-catalog {name}"
            )
        if entry.selection != "all":
            raise MaintenanceError(
                f"{name}: the bundle holds a selection of its files, and a revision "
                "is built from every file. Propose the change with the whole dataset."
            )
        removed = [c.path for c in files if c.change == "removed"]
        if removed and not intake.remove_missing:
            raise MaintenanceError(
                f"{', '.join(removed[:5])} of {name} are gone from the bundle. Each "
                "takes its key with it, and every collection that names one breaks: "
                "propose a successor instead, or pass --remove-missing if they are "
                "meant to go."
            )
        if _published(status):
            return actions + [self._revise(intake, name, status.revision + 1)]
        return actions + [self._rebuild(intake, name, directory)]

    @staticmethod
    def _add(intake: BundleIntake, name: str) -> Action:
        from . import accept

        bundle = intake.bundle
        target = intake.into / name

        def add() -> None:
            _make_parent(intake, target)
            _copy_files(bundle, name, target)
            with tempfile.TemporaryDirectory(prefix=".ethos-draft-") as draft:
                draft_dir = Path(draft)
                meta = yaml.safe_load(_description_text(bundle, name)) or {}
                meta[k.SOURCE_DIR] = str(target)
                (draft_dir / DESCRIPTOR).write_text(
                    yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
                    encoding="utf-8",
                    newline="\n",
                )
                for document in _documents(bundle, name):
                    source = bundle.path / k.BUNDLE_DESCRIPTIONS_DIR / name / document
                    destination = draft_dir / document
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                accept.run(intake.catalog_root, draft_dir / DESCRIPTOR, name=name)

        files = sum(1 for r in bundle.resources.values() if r.dataset == name)
        return Action(f"add {name}, {files} file(s), built from {target}", add)

    @staticmethod
    def _describe(intake: BundleIntake, name: str, directory: Path) -> Action:
        bundle = intake.bundle

        def describe() -> None:
            (directory / DESCRIPTOR).write_bytes(
                _description_text(bundle, name).encode("utf-8")
            )
            for document in _documents(bundle, name):
                source = bundle.path / k.BUNDLE_DESCRIPTIONS_DIR / name / document
                destination = directory / document
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)

        return Action(f"describe {name}: its description from the bundle", describe)

    @staticmethod
    def _revise(intake: BundleIntake, name: str, number: int) -> Action:
        from . import revision

        bundle = intake.bundle
        target = intake.into / names.entry(name, number)

        def revise() -> None:
            _make_parent(intake, target)
            if not target.exists():
                _copy_files(bundle, name, target)
            revision.run(
                intake.catalog_root,
                name,
                source=target,
                remove_missing=intake.remove_missing,
            )

        return Action(f"revise {name}: revision {number}, built from {target}", revise)

    @staticmethod
    def _rebuild(intake: BundleIntake, name: str, directory: Path) -> Action:
        from . import manifest

        bundle = intake.bundle
        status = dataset_status.read(directory)
        target = intake.into / names.entry(name, status.revision)

        def rebuild() -> None:
            _make_parent(intake, target)
            stale = target.with_name(target.name + ".before")
            if target.exists():
                target.rename(stale)
            try:
                _copy_files(bundle, name, target)
            except BaseException:
                if stale.exists():
                    stale.rename(target)
                raise
            shutil.rmtree(stale, ignore_errors=True)
            current = dataset_status.read(directory)
            if current.source_dir != str(target):
                dataset_status.write(
                    directory, current.model_copy(update={"source_dir": str(target)})
                )
            manifest.run(intake.catalog_root, [name])

        return Action(f"rebuild {name} from {target}", rebuild)


PIPELINE: Pipeline[BundleIntake] = Pipeline("add-bundle", [Update()])


@dataclass(frozen=True)
class IntakeResult:
    """The datasets ``add-bundle`` took in, or would take in."""

    datasets: list[str]
    made: bool

    @property
    def ok(self) -> bool:
        return True


@report.reported
def run(
    catalog_root: Path,
    directory: str | Path,
    datasets: list[str] | None = None,
    *,
    into: str | Path | None = None,
    remove_missing: bool = False,
    dry_run: bool = False,
) -> IntakeResult:
    """Take the ahead datasets of the bundle at ``directory``, or ``datasets``, in.

    ``into`` is the directory of build inputs the catalogue maintainers own,
    the clone's ``build-inputs/`` by default.
    """
    intake = BundleIntake(
        catalog_root,
        Path(directory).expanduser().absolute(),
        Path(into).expanduser().absolute()
        if into is not None
        else build_inputs_dir(catalog_root),
        list(datasets or []),
        remove_missing,
    )
    outcome = PIPELINE.run(intake, dry_run=dry_run)
    if outcome.planned and not dry_run:
        report.info(
            f"\n{', '.join(intake.taken)} taken in. Make what is new available, "
            "merge it and release it; `ethos-data catalog status` says how. The "
            "package maintainer then runs `bundle update` with the catalogue "
            "readable, which records the alignment."
        )
    return IntakeResult(intake.taken, not dry_run)
