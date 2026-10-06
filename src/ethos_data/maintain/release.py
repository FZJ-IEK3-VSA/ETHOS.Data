"""``catalog release``: make a release of the checked source catalogue.

    ethos-data catalog release v1.3.0 --public ../ETHOS.Data-Catalogue --dry-run
    ethos-data catalog release v1.3.0 --public ../ETHOS.Data-Catalogue
    ethos-data catalog release v1.3.0 --public ../ETHOS.Data-Catalogue --push --upload

One release names the internal catalogue and the public one alike. The
stages:

``check``   the version is admissible (see below); both checkouts are clean and
            the public one is not a source catalogue; every manifest is current;
            every public dataset the public catalogue lists has an upload
            verified after its last inventory change; the public tree does not
            leak
``stamp``   write the version into ``catalog.yaml`` and the index, and add a
            release step to the history of every dataset with steps since its
            last release; a major release adds one to every withdrawn dataset
``commit``  commit the source checkout and tag it with the version
``public``  generate the public catalogue in its checkout, commit and tag it
``push``    with ``--push``: push both checkouts and the tag
``store``   with ``--upload``: put the public catalogue beside the data on the
            store, under ``<publication root>/catalogue/``, replacing the
            one before; the store keeps the latest release only

The version is the next patch, minor or major of the last release, at or above
the smallest level the changes since need (see :func:`changes_since`), and the
first release is ``v1.0.0``. A patch or minor release that changes nothing is
refused; a major release is a retention epoch, which needs no change.

Run again with the same version, it does only what is left: a stamp, a
release step or a tag that is there is not made again. A release made without
``--push`` and ``--upload`` is pushed and uploaded by running it again with
them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import report
from ..adapters import Git, Store
from ..adapters.dcache import MODE_0755
from ..errors import MaintenanceError, UploadError
from ..formats import keys as k
from ..formats.catalogue import store_of
from ..model import lifecycle
from ..model.versions import FIRST, LEVELS, MAJOR, MINOR, PATCH, Version, admissible
from . import CATALOG_MARKER, read_catalog_meta
from . import status as dataset_status
from .pipeline import Action, Pipeline

__all__ = [
    "PIPELINE",
    "Changes",
    "Release",
    "ReleaseResult",
    "changes_since",
    "next_release",
    "run",
    "stamped",
]

#: The steps that change a dataset's data, which needs at least a minor release.
DATA_STEPS = frozenset({"add", "build", "change", "revise", "remove"})
#: The keys of an index row that say where and how a dataset's bytes are read.
DATA_KEYS = (k.ACCESS, k.VISIBILITY, k.TOTAL_BYTES, k.FILE_COUNT, k.REMOTE_PREFIX)


@dataclass(frozen=True)
class Changes:
    """What changed since the last release, and the smallest level that needs."""

    #: ``patch``, ``minor``, or None when nothing changed.
    level: str | None
    #: One line per change, in the order found.
    reasons: tuple[str, ...] = ()


def _rows(before: str | None, after: str | None, which: str) -> list[tuple[str, str]]:
    """How the index rows of one catalogue changed, as ``(level, reason)``."""
    if before is None or after is None:
        return []
    old = {row[k.NAME]: row for row in json.loads(before).get(k.DATASETS, [])}
    new = {row[k.NAME]: row for row in json.loads(after).get(k.DATASETS, [])}
    found = []
    for name in sorted(old.keys() | new.keys()):
        if name not in old:
            found.append((MINOR, f"{name} enters the {which} catalogue"))
        elif name not in new:
            found.append((MINOR, f"{name} leaves the {which} catalogue"))
        else:
            data = [
                key for key in DATA_KEYS if old[name].get(key) != new[name].get(key)
            ]
            if data:
                found.append(
                    (MINOR, f"{name}: {', '.join(data)} in the {which} catalogue")
                )
            elif old[name] != new[name]:
                found.append((PATCH, f"{name}: its row in the {which} catalogue"))
    return found


def changes_since(
    catalog_root: Path,
    git: Git,
    last: Version | None,
    *,
    public: Path | None = None,
    public_git: Git | None = None,
) -> Changes:
    """What changed in the clone at ``catalog_root`` since the release ``last``.

    From the steps recorded in the status files since each dataset's last
    release: adding, building, changing, revising or withdrawing a dataset
    changes data.
    From the index rows of both catalogues compared with ``last``, read from
    the tags through ``git`` and ``public_git``: a dataset that enters or leaves
    a catalogue, or whose access, visibility or bytes differ, changes data; any
    other difference, metadata. And from the files of the clone that differ
    from ``last``, the status files aside: metadata.
    """
    found: list[tuple[str, str]] = []
    for name, directory in dataset_status.datasets(catalog_root, [], tombstones=True):
        status = dataset_status.read(directory)
        if status is None:
            continue
        steps = sorted(
            {entry.step for entry in dataset_status.since_release(status)} & DATA_STEPS
        )
        if steps:
            found.append((MINOR, f"{name}: {', '.join(steps)}"))
    if last is not None:
        tag = str(last)
        index = catalog_root / k.INDEX_FILE
        found += _rows(
            git.show(tag, k.INDEX_FILE),
            index.read_text(encoding="utf-8") if index.is_file() else None,
            "internal",
        )
        if public is not None and public_git is not None:
            from .publish import plan

            files, _, _ = plan(catalog_root, public)
            rendered = files.get(Path(k.INDEX_FILE))
            found += _rows(public_git.show(tag, k.INDEX_FILE), rendered, "public")
        differ = [
            path
            for path in git.changed(tag)
            if path.rsplit("/", 1)[-1] != dataset_status.STATUS
        ]
        if differ:
            shown = ", ".join(differ[:3]) + (
                f" and {len(differ) - 3} more" if len(differ) > 3 else ""
            )
            found.append((PATCH, f"files differ from {tag}: {shown}"))
    if not found:
        return Changes(None)
    level = max((each for each, _ in found), key=LEVELS.index)
    return Changes(level, tuple(reason for _, reason in found))


def next_release(catalog_root: Path, git: Git) -> tuple[Version | None, Changes]:
    """The smallest admissible next release of the clone, and the changes it needs.

    The release is None when nothing changed since the last one.
    """
    current = read_catalog_meta(catalog_root).get(k.VERSION)
    last = Version.parse(current) if current else None
    changes = changes_since(catalog_root, git, last)
    if last is not None and changes.level is None:
        return None, changes
    return admissible(last, changes.level or PATCH)[0], changes


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
            self._admissible(release, version, current)
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

    def _admissible(
        self, release: Release, version: Version, current: str | None
    ) -> None:
        last = Version.parse(current) if current else None
        if last is not None and version <= last:
            raise MaintenanceError(
                f"{release.version} does not follow the catalogue's release {last}"
            )
        if release.version in release.source_git.tag_names():
            raise MaintenanceError(
                f"the source checkout has a tag {release.version} already; "
                "a released tag never moves"
            )
        changes = changes_since(
            release.catalog_root,
            release.source_git,
            last,
            public=release.public,
            public_git=release.public_git,
        )
        if last is not None and changes.level is None and not version.is_major:
            raise MaintenanceError(
                f"nothing changed since {last}, so there is nothing to release; a "
                f"major release, {last.next(MAJOR)}, needs no change"
            )
        allowed = admissible(last, changes.level or PATCH)
        if last is not None and changes.level is not None:
            report.info(
                f"  {self.name:<12} the changes since {last} need a {changes.level} "
                f"release, at least {allowed[0]}:"
            )
            for reason in changes.reasons[:10]:
                report.info(f"  {'':<12}   {reason}")
        if version not in allowed:
            if last is None:
                raise MaintenanceError(
                    f"{release.version} cannot be the catalogue's first release, "
                    f"which is {FIRST}"
                )
            raise MaintenanceError(
                f"{release.version} is not admissible after {last}: the changes "
                f"since need a {changes.level} release, so the next is one of "
                f"{', '.join(str(each) for each in allowed)}"
            )

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

        if not manifest.run(
            release.catalog_root, [], check=True, reporter=report.NullReporter()
        ).ok:
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
            if status is None or not _upload_verified(status):
                missing.append(package[k.NAME])
        if missing:
            raise MaintenanceError(
                "the public catalogue would offer downloads with no upload verified "
                f"after their last inventory change: {', '.join(missing)}. Upload "
                "them with `ethos-data catalog upload`, or keep them hidden."
            )


def _upload_verified(status) -> bool:
    """Whether an upload was verified after the last step that changed the inventory."""
    if status.state not in (lifecycle.AVAILABLE, lifecycle.FROZEN):
        return False
    changed = max(
        (
            entry.at
            for entry in status.history
            if entry.step in ("build", "change", "revise")
        ),
        default="",
    )
    return any(
        copy.kind == k.COPY_UPLOADED
        and copy.verified is not None
        and copy.verified >= changed
        for copy in status.copies
    )


class Stamp:
    name = "stamp"

    def plan(self, release: Release) -> list[Action]:
        if release.version in release.source_git.tag_names():
            return []
        actions = []
        if not release.stamped:
            actions.append(
                Action(
                    f"write {k.VERSION}: {release.version} into catalog.yaml and the "
                    "index",
                    self._stamp(release),
                )
            )
        major = Version.parse(release.version).is_major
        for name, directory in dataset_status.datasets(
            release.catalog_root, [], tombstones=True
        ):
            status = dataset_status.read(directory)
            if status is None:
                continue
            last, after = dataset_status.releases(status)
            if last == release.version:
                continue
            if after or (major and status.state == lifecycle.WITHDRAWN):
                actions.append(
                    Action(
                        f"{name}: record the release {release.version}",
                        self._record(release, name, directory),
                    )
                )
        return actions

    @staticmethod
    def _stamp(release: Release):
        def stamp() -> None:
            from . import manifest

            path = release.catalog_root / CATALOG_MARKER
            text = stamped(path.read_bytes().decode("utf-8"), release.version)
            if (yaml.safe_load(text) or {}).get(k.VERSION) != release.version:
                raise MaintenanceError(f"could not write the version into {path}")
            path.write_bytes(text.encode("utf-8"))
            manifest.write_index(release.catalog_root)

        return stamp

    @staticmethod
    def _record(release: Release, name: str, directory: Path):
        def record() -> None:
            dataset_status.take(
                directory,
                dataset_status.read(directory),
                "release",
                dataset=name,
                release=release.version,
            )

        return record


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
        store = release.store
        destination = f"{publication_url.rsplit('/', 1)[-1]}/catalogue"
        index_url = f"{publication_url}/catalogue/{k.INDEX_FILE}"

        def upload() -> None:
            store.sync(release.public, destination)
            folder = f"{settings.vo_path}/{destination}"
            try:
                store.chmod(folder, MODE_0755, store.token(settings.oidc_profile))
            except UploadError as error:
                report.warning(f"{error.message}; anonymous reads fail without it")

        def readable() -> str:
            try:
                store.served(index_url)
            except UploadError as error:
                return error.message
            return ""

        return [
            Action(
                f"put the public catalogue on the store at {destination}, replacing "
                "the previous one",
                upload,
                readable,
            )
        ]


PIPELINE: Pipeline[Release] = Pipeline(
    "release", [Check(), Stamp(), Commit(), Public(), Push(), Upload()]
)


@dataclass(frozen=True)
class ReleaseResult:
    """The release ``catalog release`` made, or with a dry run would make."""

    version: str
    #: Whether it was made: not for a dry run.
    made: bool

    @property
    def ok(self) -> bool:
        return True


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
    source_git: Git | None = None,
    public_git: Git | None = None,
    store: Store | None = None,
) -> ReleaseResult:
    """Release ``catalog_root`` as ``version``, its public catalogue in ``public``.

    The checkouts are reached through ``source_git`` and ``public_git``, git
    by default, and the store through ``store``, the one ``catalog.yaml``
    names by default. Raises what refuses the release.
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
    return ReleaseResult(version, not dry_run)
