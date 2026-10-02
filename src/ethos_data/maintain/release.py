"""``catalog release``: make a release of the checked source catalogue.

    ethos-data catalog release v2026.10.1 --public ../ETHOS.Data-Catalogue --dry-run
    ethos-data catalog release v2026.10.1 --public ../ETHOS.Data-Catalogue
    ethos-data catalog release v2026.10.1 --public ../ETHOS.Data-Catalogue --push --upload

One release names the internal catalogue and the public one alike. The
stages:

``check``   the version follows the catalogue's last release; both checkouts
            are clean and the public one is not a source catalogue; every
            manifest is current; every public dataset the public catalogue
            lists has a verified upload recorded; the public tree does not leak
``stamp``   write the version into ``catalog.yaml`` and the index, and add a
            release step to the history of every dataset with steps since
            its last release
``commit``  commit the source checkout and tag it with the version
``public``  generate the public catalogue in its checkout, commit and tag it
``push``    with ``--push``: push both checkouts and the tag
``store``   with ``--upload``: put the public catalogue beside the data on the
            store, under ``<publication root>/catalogue/``, replacing the
            one before; the store keeps the latest release only
``notices`` draft the release notice and the answer to every proposal the
            release accepts, printed and, with ``--notices DIR``, written there

Run again with the same version, it does only what is left: a stamp or a tag
that is there is not made again. A release made without ``--push`` and
``--upload`` is pushed and uploaded by running it again with them.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import report
from ..adapters import Git, Store
from ..adapters.dcache import MODE_0755
from ..errors import MaintenanceError
from ..formats import keys as k
from ..formats.catalogue import store_of
from ..model.versions import Version
from . import CATALOG_MARKER, read_catalog_meta
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = ["PIPELINE", "Release", "run", "stamped"]


@dataclass
class Release:
    """One release: its version, the two checkouts, and what reaches past them."""

    catalog_root: Path
    version: str
    public: Path
    source_git: Git
    public_git: Git
    store: Store | None = None
    push: bool = False
    upload: bool = False
    remote: str = "origin"
    #: Where the notice and the answers are written, besides being printed.
    notices: Path | None = None
    #: Stamped by an earlier run with the same version.
    stamped: bool = False


def stamped(text: str, version: str) -> str:
    """``catalog.yaml``'s text with ``version`` in place of the one there, or added."""
    line = f"{k.VERSION}: {version}"
    pattern = re.compile(rf"^{k.VERSION}\s*:.*$", re.MULTILINE)
    if len(pattern.findall(text)) > 1:
        raise MaintenanceError("catalog.yaml states version more than once")
    if pattern.search(text):
        return pattern.sub(line, text)
    return text + ("" if text.endswith("\n") or not text else "\n") + line + "\n"


class Check:
    name = "check"

    def plan(self, release: Release) -> list[Action]:
        try:
            version = Version.parse(release.version)
        except ValueError as error:
            raise MaintenanceError(str(error)) from None
        root = release.catalog_root
        current = read_catalog_meta(root).get(k.VERSION)
        release.stamped = current == release.version
        if not release.stamped:
            if current and Version.parse(current) >= version:
                raise MaintenanceError(
                    f"{release.version} does not follow the catalogue's release "
                    f"{current}; releases are numbered vYYYY.MM.N"
                )
            if release.version in release.source_git.tag_names():
                raise MaintenanceError(
                    f"the source checkout has a tag {release.version} already; "
                    "a released tag never moves"
                )
        resuming = (
            release.stamped and release.version not in release.source_git.tag_names()
        )
        if not resuming and not release.source_git.is_clean():
            raise MaintenanceError(
                f"{root} has changes nobody committed; commit them, so the release "
                "commit holds its own stamp only"
            )
        self._public(release)
        self._manifests(release)
        self._uploads(release)
        from .publish import plan

        _, _, leaked = plan(root, release.public)
        if leaked:
            raise MaintenanceError(
                "the public catalogue would leak:\n"
                + "".join(f"  {problem}\n" for problem in leaked)
                + "Fix the source descriptor or its visibility, rebuild, and commit."
            )
        return []

    @staticmethod
    def _public(release: Release) -> None:
        public = release.public
        if not public.is_dir():
            raise MaintenanceError(
                f"no public checkout at {public}; clone the public repository there"
            )
        if (
            public / CATALOG_MARKER
        ).is_file() or public.resolve() == release.catalog_root.resolve():
            raise MaintenanceError(
                f"{public} is a source catalogue; the public catalogue is generated "
                "into a checkout of the public repository, which it replaces"
            )
        if not release.public_git.is_clean():
            raise MaintenanceError(f"{public} has changes nobody committed")

    @staticmethod
    def _manifests(release: Release) -> None:
        from . import manifest

        if manifest.run(
            release.catalog_root, [], check=True, reporter=report.NullReporter()
        ):
            raise MaintenanceError(
                "the manifests are not current: run `ethos-data catalog build`, "
                "review and commit the result, then release"
            )

    @staticmethod
    def _uploads(release: Release) -> None:
        from .publish import public_datasets

        missing = []
        for directory, package in public_datasets(release.catalog_root):
            if package.get(k.NAMESPACE) or package.get(k.ACCESS, k.PUBLIC) != k.PUBLIC:
                continue
            status = dataset_status.read(directory)
            if status is None or not any(
                copy.kind == k.COPY_UPLOADED for copy in status.copies
            ):
                missing.append(package[k.NAME])
        if missing:
            raise MaintenanceError(
                "the public catalogue would offer downloads with no verified upload "
                f"recorded: {', '.join(missing)}. Upload them with "
                "`ethos-data catalog upload`, or keep them hidden."
            )


class Stamp:
    name = "stamp"

    def plan(self, release: Release) -> list[Action]:
        if release.stamped:
            return []
        changed = []
        for name, directory in dataset_status.datasets(
            release.catalog_root, [], tombstones=True
        ):
            status = dataset_status.read(directory)
            if status is not None and dataset_status.releases(status)[1]:
                changed.append((name, directory))

        def stamp() -> None:
            from . import manifest

            path = release.catalog_root / CATALOG_MARKER
            text = stamped(path.read_bytes().decode("utf-8"), release.version)
            if (yaml.safe_load(text) or {}).get(k.VERSION) != release.version:
                raise MaintenanceError(f"could not write the version into {path}")
            path.write_bytes(text.encode("utf-8"))
            manifest.write_index(release.catalog_root)

        def record() -> None:
            for name, directory in changed:
                dataset_status.take(
                    directory,
                    dataset_status.read(directory),
                    "release",
                    dataset=name,
                    release=release.version,
                )

        actions = [
            Action(
                f"write {k.VERSION}: {release.version} into catalog.yaml and the index",
                stamp,
            )
        ]
        if changed:
            actions.append(
                Action(
                    f"record the release in {len(changed)} dataset(s): "
                    + ", ".join(name for name, _ in changed[:5])
                    + (" and more" if len(changed) > 5 else ""),
                    record,
                )
            )
        return actions


class Commit:
    name = "commit"

    def plan(self, release: Release) -> list[Action]:
        if release.version in release.source_git.tag_names():
            return []

        # A stamp made in this run changed the checkout; one an interrupted run
        # made may be committed already, which git knows.
        stamping = not release.stamped

        def commit() -> None:
            if stamping or not release.source_git.is_clean():
                release.source_git.commit(f"Release {release.version}")
            release.source_git.tag(release.version, f"Release {release.version}")

        return [
            Action(f"commit the source checkout and tag it {release.version}", commit)
        ]


class Public:
    name = "public"

    def plan(self, release: Release) -> list[Action]:
        if release.version in release.public_git.tag_names():
            return []

        def publish() -> None:
            from . import publish as publisher

            publisher.run(release.catalog_root, str(release.public))
            if not release.public_git.is_clean():
                release.public_git.commit(f"Release {release.version}")
            release.public_git.tag(release.version, f"Release {release.version}")

        return [
            Action(
                f"generate the public catalogue in {release.public}, commit and tag it",
                publish,
            )
        ]


class Push:
    name = "push"

    def plan(self, release: Release) -> list[Action]:
        if not release.push:
            return []
        return [
            Action(
                f"push the {which} checkout and {release.version} to {release.remote}",
                lambda git=git: git.push(release.remote, "HEAD", release.version),
            )
            for which, git in (
                ("source", release.source_git),
                ("public", release.public_git),
            )
        ]


class Upload:
    name = "store"

    def plan(self, release: Release) -> list[Action]:
        if not release.upload:
            return []
        meta = read_catalog_meta(release.catalog_root)
        publication_url = (meta.get(k.PUBLICATION_URL) or "").rstrip("/")
        if not publication_url:
            raise MaintenanceError(
                f"catalog.yaml names no {k.PUBLICATION_URL}, so the public catalogue "
                "has nowhere to go on the store"
            )
        settings = store_of(meta)
        if release.store is None:
            from ..adapters.dcache import DcacheStore

            release.store = DcacheStore(settings.remote, settings.frontend)
        destination = f"{publication_url.rsplit('/', 1)[-1]}/catalogue"
        index_url = f"{publication_url}/catalogue/datacatalog.json"

        def upload() -> None:
            store = release.store
            if store.sync(release.public, destination, dry_run=False):
                raise MaintenanceError(
                    f"copying the public catalogue to {destination} failed"
                )
            bearer = store.token(settings.oidc_profile)
            status = store.chmod(f"{settings.vo_path}/{destination}", MODE_0755, bearer)
            if status not in (200, 204):
                report.warning(
                    f"chmod 0755 {settings.vo_path}/{destination} answered HTTP {status}; "
                    "anonymous reads fail until it succeeds"
                )

        def readable() -> str:
            request = urllib.request.Request(index_url, method="HEAD")
            try:
                with urllib.request.urlopen(request, timeout=60):
                    return ""
            except (urllib.error.URLError, OSError) as error:
                return f"{index_url} is not readable anonymously: {error}"

        return [
            Action(
                f"put the public catalogue on the store at {destination}, replacing "
                "the previous one",
                upload,
                readable,
            )
        ]


def changes_in(
    catalog_root: Path, version: str
) -> tuple[dict[str, list[str]], list[str]]:
    """What release ``version`` changed, by kind, and the datasets it accepted.

    Read off the status files: every step between a dataset's release step for
    ``version`` and the release step before it.
    """
    from . import read_descriptor

    found: dict[str, list[str]] = {
        "added": [],
        "revised": [],
        "successors": [],
        "withdrawn": [],
    }
    accepted = []
    for name, directory in dataset_status.datasets(catalog_root, [], tombstones=True):
        status = dataset_status.read(directory)
        if status is None:
            continue
        window, collecting = [], False
        for entry in reversed(status.history):
            if entry.step == "release":
                if collecting:
                    break
                collecting = entry.release == version
                continue
            if collecting:
                window.append(entry)
        steps = {entry.step for entry in window}
        meta = (
            read_descriptor(directory) if (directory / "dataset.yaml").is_file() else {}
        )
        title = f": {meta[k.TITLE]}" if meta.get(k.TITLE) else ""
        if "add" in steps:
            accepted.append(name)
            if meta.get(k.SUPERSEDES):
                found["successors"].append(
                    f"`{name}`{title}, superseding `{meta[k.SUPERSEDES]}`"
                )
            else:
                found["added"].append(f"`{name}`{title}")
        elif "revise" in steps:
            found["revised"].append(f"`{name}`, revision {status.revision}")
        if "remove" in steps:
            reason = next((e.note for e in window if e.step == "remove" and e.note), "")
            found["withdrawn"].append(f"`{name}`" + (f": {reason}" if reason else ""))
    return found, sorted(accepted)


class Notices:
    name = "notices"

    def plan(self, release: Release) -> list[Action]:
        def draft() -> None:
            from .. import handoffs

            changes, accepted = changes_in(release.catalog_root, release.version)
            drafts = {
                f"release-{release.version}.md": handoffs.release_notice(
                    release.version, changes
                )
            }
            for name in accepted:
                drafts[f"answer-{name.replace('/', '-')}.md"] = handoffs.answer(
                    name, release.version
                )
            if release.notices is not None:
                release.notices.mkdir(parents=True, exist_ok=True)
                for file_name, text in drafts.items():
                    (release.notices / file_name).write_text(
                        text, encoding="utf-8", newline="\n"
                    )
            for text in drafts.values():
                report.info("\n" + text.rstrip())

        where = f", into {release.notices}" if release.notices is not None else ""
        return [
            Action(
                f"draft the release notice and the answers to the proposals it "
                f"accepts{where}",
                draft,
            )
        ]


PIPELINE: Pipeline[Release] = Pipeline(
    "release", [Check(), Stamp(), Commit(), Public(), Push(), Upload(), Notices()]
)


@report.reported
def run(
    catalog_root: Path,
    version: str,
    public: str | Path,
    *,
    push: bool = False,
    upload: bool = False,
    remote: str = "origin",
    dry_run: bool = False,
    notices: str | Path | None = None,
    source_git: Git | None = None,
    public_git: Git | None = None,
    store: Store | None = None,
) -> int:
    """Release ``catalog_root`` as ``version``, its public catalogue in ``public``.

    The checkouts are reached through ``source_git`` and ``public_git``, git
    by default, and the store through ``store``, the one ``catalog.yaml``
    names by default. Returns 0, or raises.
    """
    from ..adapters.git import GitRepository

    public = Path(public).expanduser()
    release = Release(
        catalog_root,
        version,
        public,
        source_git or GitRepository(catalog_root),
        public_git or GitRepository(public),
        store,
        push,
        upload,
        remote,
        Path(notices).expanduser() if notices is not None else None,
    )
    PIPELINE.run(release, dry_run=dry_run)
    if not dry_run:
        left = [
            step
            for step, wanted in (("--push", push), ("--upload", upload))
            if not wanted
        ]
        report.info(
            f"\n{version} is released"
            + (
                f"; run this again with {' and '.join(left)} to finish it."
                if left
                else "."
            )
            + " Then update the checkout cluster users read: "
            "`ethos-data catalog update-checkout` there."
        )
    return 0
