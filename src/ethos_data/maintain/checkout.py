"""``catalog update-checkout``: move the checkout readers are served to a release.

    ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout --dry-run
    ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout
    ethos-data catalog --catalog-root /shared/ethos/catalogue update-checkout --to v2026.10.1

Cluster users read one checkout of the source catalogue, which holds one
release, the latest. A runner elsewhere cannot reach it, so it is updated on
the machine that serves it, by this command, when no jobs are reading it:

``fetch``    fetch the remote's branches and tags
``advance``  move the checkout to the release, by fast-forward only
``check``    check every manifest against its files, writing nothing

Nothing is rebuilt in a served checkout: an index from one release paired
with inventories from another is what a reader reports as an incomplete
catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import report
from ..adapters import Git
from ..errors import MaintenanceError
from ..formats import keys as k
from ..model.versions import Version
from . import read_catalog_meta
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "Update", "latest", "run"]


@dataclass
class Update:
    """The served checkout, the release to move it to, and the remote it comes from."""

    catalog_root: Path
    git: Git
    to: str | None = None
    remote: str = "origin"
    #: The release the checkout was moved to, once it was.
    reached: str | None = None


def latest(names: list[str]) -> str | None:
    """The newest of ``names`` that is a release, vYYYY.MM.N."""
    releases = []
    for name in names:
        try:
            releases.append(Version.parse(name))
        except ValueError:
            continue
    return str(max(releases)) if releases else None


class Fetch:
    name = "fetch"

    def plan(self, update: Update) -> list[Action]:
        if update.to is not None:
            try:
                Version.parse(update.to)
            except ValueError as error:
                raise MaintenanceError(str(error)) from None
        if not update.git.is_clean():
            raise MaintenanceError(
                f"the served checkout {update.catalog_root} has changes nobody "
                "committed; it holds a release and nothing else"
            )
        return [
            Action(f"fetch {update.remote}", lambda: update.git.fetch(update.remote))
        ]


class Advance:
    name = "advance"

    def plan(self, update: Update) -> list[Action]:
        def advance() -> None:
            target = update.to or latest(update.git.tag_names())
            if target is None:
                raise MaintenanceError(f"{update.remote} has no release tag yet")
            update.git.fast_forward(target)
            update.reached = target

        def reached() -> str:
            version = read_catalog_meta(update.catalog_root).get(k.VERSION)
            if version != update.reached:
                return (
                    f"the checkout is at {update.reached}, but its catalog.yaml says "
                    f"{version}; the release was tagged before it was stamped"
                )
            return ""

        return [
            Action(
                f"move the checkout to {update.to or 'the latest release'}",
                advance,
                reached,
            )
        ]


class Check:
    name = "check"

    def plan(self, update: Update) -> list[Action]:
        def check() -> None:
            from . import manifest

            if manifest.run(update.catalog_root, [], check=True):
                raise MaintenanceError(
                    f"{update.reached} does not check clean in the served checkout: its "
                    "manifests and the files they describe disagree. Do not announce it."
                )

        return [Action("check every manifest against its files", check)]


PIPELINE: Pipeline[Update] = Pipeline("update-checkout", [Fetch(), Advance(), Check()])


@report.reported
def run(
    catalog_root: Path,
    *,
    to: str | None = None,
    remote: str = "origin",
    dry_run: bool = False,
    git: Git | None = None,
) -> int:
    """Move the served checkout at ``catalog_root`` to ``to``, or the latest release."""
    from ..adapters.git import GitRepository

    update = Update(catalog_root, git or GitRepository(catalog_root), to, remote)
    PIPELINE.run(update, dry_run=dry_run)
    if not dry_run:
        report.info(
            f"\nThe served checkout is at {update.reached}; announce the release."
        )
    return 0
