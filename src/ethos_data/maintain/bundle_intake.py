"""``catalog add-bundle``: take a package's repository bundle into the catalogue.

    ethos-data catalog add-bundle /checkout/your_tool/data/test_data --dry-run
    ethos-data catalog add-bundle /checkout/your_tool/data/test_data

The repository is the source of truth for a bundle and the catalogue holds
its published versions, so the catalogue is updated from the bundle, never
the other way round. ``add-bundle`` compares the bundle with what the
catalogue holds of its family and plans one step for each difference:

=============  =================================================================
``family``     the family's description, where the catalogue lacks it or it changed
``add``        a member the catalogue lacks: placed and built, as ``catalog add``
               does, from the bundle's draft and files
``describe``   a member whose description changed: its ``dataset.yaml`` replaced
``rebuild``    a member not published yet whose files changed: rebuilt from them
``revise``     a member whose published files changed: its next revision, as
               ``catalog build --revision`` makes it, its unchanged files kept
=============  =================================================================

The bundle's files are the build input: each member's ``source_dir`` is its
folder under the bundle's ``data/``. A file the bundle no longer has is
refused for a published member unless ``--remove-missing`` says it is meant.
A member of the family that the bundle lacks is left as it is; ``catalog
remove`` takes it out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .. import report
from ..bundles import DATA_DIR, METADATA_DIR, Bundle, load_bundle
from ..errors import MaintenanceError
from ..formats import keys as k
from ..model import digest, lifecycle
from . import DESCRIPTOR, datasets_dir, iter_dataset_dirs, resources_of
from . import status as dataset_status
from .migrate import edited_text
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "BundleIntake", "run"]


@dataclass
class BundleIntake:
    """The bundle ``add-bundle`` takes in, and where to."""

    catalog_root: Path
    directory: Path
    remove_missing: bool = False
    bundle: Bundle | None = None


def _hashes(records: list[dict]) -> dict[str, str | None]:
    return {record[k.PATH]: digest.expected(record[k.HASH]) for record in records}


def _published(status) -> bool:
    return status.state in (lifecycle.AVAILABLE, lifecycle.FROZEN) and any(
        copy.kind in (k.COPY_UPLOADED, k.COPY_MATERIALIZED) for copy in status.copies
    )


class Update:
    name = "update"

    def plan(self, intake: BundleIntake) -> list[Action]:
        bundle = load_bundle(intake.directory)
        if not bundle.repository:
            raise MaintenanceError(
                f"{bundle.path} is a copy exported from the catalogue; there is "
                "nothing in it the catalogue does not hold"
            )
        intake.bundle = bundle
        actions = self._family(intake)
        for name in sorted(bundle.datasets):
            actions += self._member(intake, name)
        if actions:
            from . import manifest

            # The family's own entry sums its members: built after them.
            actions.append(
                Action(
                    f"rebuild the family {bundle.family}",
                    lambda: manifest.run(intake.catalog_root, [bundle.family]),
                )
            )
        root = datasets_dir(intake.catalog_root)
        family = root / bundle.family
        if family.is_dir():
            for directory in iter_dataset_dirs(family):
                name = directory.relative_to(root).as_posix()
                if directory != family and name not in bundle.datasets:
                    report.info(
                        f"  {name} is not in the bundle; left as it is, "
                        "`ethos-data catalog remove` takes it out"
                    )
        return actions

    @staticmethod
    def _family(intake: BundleIntake) -> list[Action]:
        bundle = intake.bundle
        draft = bundle.path / METADATA_DIR / bundle.family / DESCRIPTOR
        if not draft.is_file():
            return []
        target = datasets_dir(intake.catalog_root) / bundle.family / DESCRIPTOR
        text = draft.read_bytes()
        if target.is_file() and target.read_bytes() == text:
            return []

        def write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text)

        verb = "describe" if target.is_file() else "add"
        return [Action(f"{verb} the family {bundle.family}", write)]

    @staticmethod
    def _member(intake: BundleIntake, name: str) -> list[Action]:
        from . import accept, manifest, revision

        bundle = intake.bundle
        draft = bundle.path / METADATA_DIR / name / DESCRIPTOR
        source = bundle.path / DATA_DIR / name
        directory = datasets_dir(intake.catalog_root) / name
        if not (directory / DESCRIPTOR).is_file():
            # Checked now, so a draft the build would refuse stops the plan.
            accept.Intake().plan(accept.Draft(intake.catalog_root, draft, name))
            return [
                Action(
                    f"add {name}, {len(bundle.datasets[name][k.RESOURCES])} file(s)",
                    lambda: accept.run(intake.catalog_root, draft, name=name),
                )
            ]
        status = dataset_status.read(directory)
        if status is None:
            raise MaintenanceError(
                f"{name} has no {dataset_status.STATUS} yet; write one with\n"
                f"    ethos-data catalog migrate {name}"
            )
        actions = []
        described = edited_text(draft.read_bytes().decode("utf-8"), [k.SOURCE_DIR])
        if described is None:
            raise MaintenanceError(
                f"{draft}: source_dir could not be left out line by line; write it "
                "as one key per line"
            )
        if (directory / DESCRIPTOR).read_bytes().decode("utf-8") != described:
            actions.append(
                Action(
                    f"describe {name}: its {DESCRIPTOR} from the bundle",
                    lambda: (directory / DESCRIPTOR).write_bytes(
                        described.encode("utf-8")
                    ),
                )
            )
        package = json.loads((directory / "datapackage.json").read_text("utf-8"))
        held = _hashes(resources_of(package, directory))
        bundled = _hashes(bundle.datasets[name][k.RESOURCES])
        if held == bundled:
            if actions:
                actions.append(
                    Action(
                        f"rebuild {name}'s descriptor",
                        lambda: manifest.run(intake.catalog_root, [name]),
                    )
                )
            return actions
        gone = sorted(set(held) - set(bundled))
        if _published(status):
            if gone and not intake.remove_missing:
                raise MaintenanceError(
                    f"the bundle no longer has {', '.join(gone[:5])} of {name}, whose "
                    "files are published. Each takes its key with it, and every "
                    "collection that names one breaks: propose a successor instead, "
                    "or pass --remove-missing if they are meant to go."
                )
            revision.Compare().plan(
                revision.Revision(
                    intake.catalog_root, name, source, intake.remove_missing
                )
            )
            actions.append(
                Action(
                    f"revise {name}: revision {status.revision + 1} from the bundle",
                    lambda: revision.run(
                        intake.catalog_root,
                        name,
                        source=source,
                        remove_missing=intake.remove_missing,
                    ),
                )
            )
            return actions

        def rebuild() -> None:
            current = dataset_status.read(directory)
            if current.source_dir != str(source):
                dataset_status.write(
                    directory, current.model_copy(update={"source_dir": str(source)})
                )
            if manifest.run(intake.catalog_root, [name]):
                raise MaintenanceError(f"{name}: the build failed")

        actions.append(Action(f"rebuild {name} from the bundle", rebuild))
        return actions


PIPELINE: Pipeline[BundleIntake] = Pipeline("add-bundle", [Update()])


@report.reported
def run(
    catalog_root: Path,
    directory: str | Path,
    *,
    remove_missing: bool = False,
    dry_run: bool = False,
) -> int:
    """Bring the catalogue's family up to the bundle at ``directory``."""
    intake = BundleIntake(catalog_root, Path(directory).expanduser(), remove_missing)
    planned = PIPELINE.run(intake, dry_run=dry_run)
    if planned and not dry_run:
        report.info(
            f"\n{intake.bundle.family} is up to the bundle's version "
            f"{intake.bundle.version}. Make what is new available and release it; "
            "`ethos-data catalog status` says how."
        )
    return 0
