"""What one role hands another, drafted from what the tools know.

A proposal, the answer to it, a problem report, and the notices of a release
and of a removal: each has a template among the formats,
``ethos_data/formats/templates/handoffs/``, which the format registry fills
in, and the command that knows the facts drafts it.

========================  ==================================================
``proposal``              :func:`propose`, ``<tool>-data propose DIR``
``report``                :func:`report`, ``ethos-data report`` and
                          ``<tool>-data report``
``answer``                the ``notices`` stage of ``catalog release``, one
                          per dataset the release adds
``release-notice``        the ``notices`` stage of ``catalog release``
``removal-notice``        the ``notices`` stage of ``catalog remove``
========================  ==================================================

The proposal and the report are also the public catalogue's issue templates,
which ``catalog publish`` writes: :func:`issue_template` fills each
placeholder with what to write there. People post the drafts; nothing here
writes to a tracker.
"""

from __future__ import annotations

import dataclasses
import getpass
import os
import platform
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .errors import BundleError, DescriptorError, EthosDataError, UnknownDataset
from .formats import keys as k
from .formats.registry import handoff

if TYPE_CHECKING:
    from .bundles import Bundle
    from .catalogs import Catalog
    from .config import Roots, Settings
    from .model.resource import Resource
    from .selection import Collections

__all__ = [
    "INTERNAL_TRACKER",
    "PUBLIC_TRACKER",
    "Proposal",
    "answer",
    "issue_template",
    "propose",
    "release_notice",
    "removal_notice",
    "report",
    "scrub",
    "tracker",
]

#: Where proposals and reports about restricted data, and reports from a
#: cluster installation, go.
INTERNAL_TRACKER = (
    "https://jugit.fz-juelich.de/iek-3/shared-code/ethos-data-catalog-internal"
)
#: Where proposals and reports about public data go.
PUBLIC_TRACKER = "https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/issues"


def tracker(access: str) -> str:
    """Where a proposal or a report about data of ``access`` is posted."""
    if access == k.RESTRICTED:
        return f"{INTERNAL_TRACKER}: the data is restricted"
    return f"{PUBLIC_TRACKER}, or {INTERNAL_TRACKER} from a cluster installation"


#: What an issue template says in place of each placeholder.
_HINTS = {
    "name": "<dataset name>",
    "identity": "name, version, title, the workflows that use it, new dataset or revision",
    "description": "the draft `dataset.yaml`, or the bundle directory that holds it",
    "bytes": "the readable directory, archive or link, and how long it stays",
    "collection": "the entry",
    "findings": "",
    "tracker": "this tracker",
    "versions": "ETHOS.Data, the package, Python, operating system",
    "selftest": "the output of `ethos-data selftest`",
    "settings": "the output of `ethos-data config show`",
    "package": "the output of `<your-tool>-data show`",
    "plan": "the output of `fetch --plan`",
    "verify": "the output of `verify`",
}

#: Issue templates: the handoff, its title, and what it is for.
ISSUES = {
    "propose-a-dataset": ("proposal", "Propose a dataset", "Hand a new or changed dataset to the catalogue maintainers"),
    "report-a-problem": ("report", "Report a problem", "A dataset, its catalogue entry or its download does not work"),
}  # fmt: skip


def issue_template(issue: str) -> str:
    """A catalogue repository's issue template, from the handoff it is made of."""
    handoff_name, title, about = ISSUES[issue]
    body = handoff(handoff_name, **_HINTS)
    return f"---\nname: {title}\nabout: {about}\n---\n\n{body}"


_CREDENTIALS = (
    (re.compile(r"(https?://)[^/@\s:]+:[^/@\s]+@"), r"\1<redacted>@"),
    (re.compile(r"(?i)(bearer\s+)\S+"), r"\1<redacted>"),
    (re.compile(r"(?i)((?:token|password|secret)[=:]\s*)\S+"), r"\1<redacted>"),
)


def scrub(text: str) -> str:
    """``text`` without tokens, credentials in URLs, the home directory or the account name.

    For a report someone posts in a tracker: what is left says what went
    wrong without saying whose machine it was.
    """
    for pattern, replacement in _CREDENTIALS:
        text = pattern.sub(replacement, text)
    home = str(Path.home())
    for spelling in {home, home.replace("\\", "/")}:
        if spelling and len(spelling) > 1:
            text = text.replace(spelling, "~")
    try:
        user = getpass.getuser()
    except (OSError, KeyError, ImportError):
        user = ""
    if len(user) > 2:
        text = re.sub(rf"\b{re.escape(user)}\b", "<user>", text)
    return text


def _human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size} B"  # pragma: no cover


# -- a proposal ------------------------------------------------------------------------


@dataclass
class Proposal:
    """The text of a proposal and what checking the candidate found."""

    name: str
    text: str
    findings: list[str] = field(default_factory=list)


def propose(directory: str | Path, collections: Collections | None = None) -> Proposal:
    """Check a candidate, a draft ``dataset.yaml`` or a bundle, and draft its proposal.

    ``directory`` holds the draft, or is a bundle; ``collections`` is the
    package's handle, which names the collections that read the candidate and
    whether its catalogue has it already.

    A draft is checked as the build checks it, its bytes, under its
    ``source_dir`` and after ``ethos:include`` and ``ethos:exclude``, are
    inventoried, and every file still writable is named. A bundle's proposal
    covers its datasets that are ahead of the catalogue. Raises
    :class:`~ethos_data.errors.DescriptorError` for a draft the build would
    refuse or one without ``source_dir``, and
    :class:`~ethos_data.errors.BundleError` for a bundle that holds data it
    may not hold, a file that differs from ``bundle.json``, or nothing ahead.
    """
    path = Path(directory).expanduser()
    if path.name == k.BUNDLE_FILE or (path / k.BUNDLE_FILE).is_file():
        return _propose_bundle(path, collections)
    draft = path / k.DESCRIPTION_FILE if path.is_dir() else path
    if not draft.is_file():
        raise DescriptorError(
            f"no draft at {draft}: name its {k.DESCRIPTION_FILE} or its directory"
        )
    return _propose_draft(draft.resolve(), collections)


def _catalogue(collections: Collections | None) -> tuple[Catalog | None, list[str]]:
    """The catalogue the handle reads, without its bundles and staging, or why there is none."""
    if collections is None:
        return None, []
    try:
        return collections.base_catalog(), []
    except EthosDataError as error:
        why = (
            "the catalogue cannot be read, so the proposal does not say whether it "
            f"has the dataset: {error.message}"
        )
        return None, [why]


def _with_candidates(catalog: Catalog | None, candidates: Iterable[str]) -> Catalog:
    """``catalog`` with the candidates in it, and the families above them, to match names."""
    from .catalogs import Catalog, Dataset
    from .model import names
    from .model.inventory import Inventory

    base = catalog or Catalog(location="candidates", descriptor={}, datasets={})
    datasets = dict(base.datasets)
    for name in candidates:
        for family in names.ancestors(name):
            datasets.setdefault(
                family,
                Dataset(
                    family,
                    family,
                    {k.NAME: family, k.NAMESPACE: True},
                    Inventory.from_records(family, {k.NAME: family, k.NAMESPACE: True}),
                ),
            )
        datasets[name] = Dataset(
            name,
            name,
            {k.NAME: name},
            Inventory.from_records(name, {k.NAME: name, k.RESOURCES: []}),
        )
    return dataclasses.replace(base, datasets=datasets)


def _collections_naming(
    collections: Collections | None, view: Catalog, wanted: set[str]
) -> list[str]:
    """The collections whose rules select one of ``wanted`` in ``view``, or extend one that does."""
    if collections is None:
        return []

    def patterns(name: str, seen: frozenset[str]) -> set[str]:
        try:
            collection = collections.describe(name)
        except EthosDataError:
            return set()
        selections = [
            getattr(collection, variant) for variant in collection.variants()
        ] or [collection]
        found = set()
        for selection in selections:
            found |= {rule.dataset for rule in selection.include}
            for other in selection.extends:
                if other not in seen:
                    found |= patterns(other, seen | {name})
        return found

    def selects(pattern: str) -> bool:
        try:
            return any(d.name in wanted for d in view.matching_datasets(pattern))
        except UnknownDataset:
            return False

    return [
        name
        for name in collections.names()
        if any(selects(pattern) for pattern in patterns(name, frozenset({name})))
    ]


def _collection(naming: list[str], names: list[str]) -> str:
    if naming:
        return f"{', '.join(naming)} already name it"
    rules = ", ".join(f"{{dataset: {name}}}" for name in names)
    return f"`include: [{rules}]`"


def _propose_draft(draft: Path, collections: Collections | None) -> Proposal:
    from .files import iter_data_files, select
    from .formats import dataset as dataset_format

    meta = yaml.safe_load(draft.read_text(encoding="utf-8")) or {}
    if not isinstance(meta, dict):
        raise DescriptorError(f"{draft} is not a mapping of keys to values")
    name = meta.get(k.NAME)
    if not name:
        raise DescriptorError(f"{draft} names no dataset; add `name:`")
    if not meta.get(k.SOURCE_DIR):
        raise DescriptorError(
            f"{name}: the draft names no {k.SOURCE_DIR}; add `{k.SOURCE_DIR}:`, the "
            f"directory that holds its bytes, relative to {draft.parent}"
        )
    findings = dataset_format.check_draft(meta)
    source = Path(str(meta[k.SOURCE_DIR])).expanduser()
    if not source.is_absolute():
        source = Path(os.path.abspath(draft.parent / source))
    if not source.is_dir():
        raise DescriptorError(f"{name}: its {k.SOURCE_DIR} {source} is not a directory")
    files = select(name, source, list(iter_data_files(source)), meta)
    size = sum(path.stat().st_size for path in files)
    writable = [path for path in files if path.stat().st_mode & 0o222]
    if writable:
        findings.append(
            f"{name}: {len(writable)} of {len(files)} files are still writable; stop "
            f"changing them and make the directory read-only: chmod -R a-w {source}"
        )
    catalog, unread = _catalogue(collections)
    findings += unread
    supersedes = meta.get(k.SUPERSEDES)
    if supersedes:
        kind = f"a successor of {supersedes}"
    elif catalog is None and collections is not None:
        kind = "a new dataset or a revision: the catalogue was not read"
    elif catalog is not None and name in catalog.datasets:
        kind = f"a revision of the catalogued {name}"
    else:
        kind = "a new dataset"
    version = meta.get(k.VERSION)
    identity = "; ".join(
        part
        for part in (
            f"`{name}`",
            str(meta.get(k.TITLE) or ""),
            f"version {version}" if version else "",
            kind,
        )
        if part
    )
    naming = _collections_naming(collections, _with_candidates(catalog, [name]), {name})
    text = handoff(
        "proposal",
        name=name,
        identity=identity,
        description=f"`{draft}`",
        bytes=f"`{source}`: {len(files)} files, {_human(size)}",
        collection=_collection(naming, [name]),
        findings="".join(f"- {finding}\n" for finding in findings),
        tracker=tracker(meta.get(k.ACCESS, k.PUBLIC)),
    )
    return Proposal(str(name), text, findings)


def _bundled_kind(bundle: Bundle, name: str, why: str) -> str:
    supersedes = bundle.descriptions[name].get(k.SUPERSEDES)
    alignment = bundle.datasets[name].alignment
    if supersedes:
        return f"a successor of {supersedes}"
    if alignment is None:
        return "a new dataset"
    return f"{why} since revision {alignment.revision}"


def _propose_bundle(path: Path, collections: Collections | None) -> Proposal:
    from .bundles import load_bundle, refuse_what_the_catalogue_withholds, with_bundles
    from .formats import dataset as dataset_format

    bundle = load_bundle(path)
    catalog, findings = _catalogue(collections)
    if catalog is not None:
        refuse_what_the_catalogue_withholds(bundle, catalog)
    differ = [finding for finding in bundle.verify() if not finding.ok]
    if differ:
        raise BundleError(
            f"{len(differ)} file(s) of the bundle at {bundle.path} differ from "
            f"{k.BUNDLE_FILE}, the first {differ[0].key} ({differ[0].status}): record "
            "the changes with `bundle update` first"
        )
    ahead = bundle.ahead()
    if not ahead:
        raise BundleError(
            f"no dataset of the bundle at {bundle.path} is ahead of the catalogue: "
            "there is nothing to propose"
        )
    names = sorted(ahead)
    for name in names:
        findings += dataset_format.check_draft(bundle.descriptions[name])
    identity = "; ".join(
        f"`{name}`"
        + (f", {bundle.descriptions[name][k.TITLE]}" if bundle.descriptions[name].get(k.TITLE) else "")
        + f": {_bundled_kind(bundle, name, ahead[name])}"
        for name in names
    )  # fmt: skip
    resources = [
        resource for resource in bundle.resources.values() if resource.dataset in ahead
    ]
    descriptions = ", ".join(f"`{name}/{k.DESCRIPTION_FILE}`" for name in names)
    naming = _collections_naming(
        collections, with_bundles(catalog, [bundle]), set(names)
    )
    text = handoff(
        "proposal",
        name=", ".join(names),
        identity=identity,
        description=f"under `{bundle.path / k.BUNDLE_DESCRIPTIONS_DIR}`: {descriptions}",
        bytes=(
            f"`{bundle.path / k.BUNDLE_DATA_DIR}`: {len(resources)} files, "
            f"{_human(sum(resource.bytes for resource in resources))}, in the "
            "package's repository"
        ),
        collection=_collection(naming, names),
        findings="".join(f"- {finding}\n" for finding in findings),
        tracker=tracker(k.PUBLIC),
    )
    return Proposal(", ".join(names), text, findings)


# -- a problem report ------------------------------------------------------------------


def _section(produce: Callable[[], str]) -> str:
    """What ``produce`` says, or the error it raised: a report is drafted when things fail."""
    try:
        return produce().rstrip() or "(nothing)"
    except EthosDataError as error:
        return f"error: {error.message}"


def _selftest(catalog: str | None, root: str | Path | None) -> str:
    from .selftest import run_selftest

    result = run_selftest(catalog=catalog, root=root)
    lines = []
    if result.catalog:
        lines.append(
            f"catalogue {result.catalog} ({result.catalog_source}), "
            f"version {result.version or 'not recorded'}"
        )
    for outcome in result.files:
        check = "" if outcome.ok else f"  [{outcome.status}: {outcome.detail}]"
        lines.append(f"{outcome.how:<15}  {outcome.key}  {outcome.path}{check}")
    lines.append(
        f"selftest FAILED at {result.failed}: {result.error}"
        if result.failed
        else "selftest passed"
    )
    return "\n".join(lines)


def _settings(settings: Settings) -> str:
    """The settings, and the state of every cache they list."""
    from .config import unreachable

    roots = settings.roots
    rows = settings.rows()
    width = max(len(label) for label, _ in rows)
    lines = []
    for label, value in rows:
        path = None
        if label == "public cache":
            path = roots.public
        elif label.startswith("restricted cache "):
            path = roots.restricted[int(label.rsplit(" ", 1)[1]) - 1]
        elif label == "staging cache":
            path = roots.staging
        reason = unreachable(path) if path is not None else None
        if reason == "does not exist" and path == roots.public:
            reason = "not created yet: the first download creates it"
        state = f"  [{reason}]" if reason else ""
        lines.append(f"{label:<{width}}  {value}{state}")
    return "\n".join(lines)


def _package(collections: Collections) -> str:
    """What ``<tool>-data show`` says: the catalogue, the bundles and every collection."""
    from .bundles import describe_bundle

    lines = [f"catalogue: {collections.catalog.location}"]
    for bundle in collections.bundles:
        lines.append(f"bundle {bundle.path}")
        lines += [f"  {line}" for line in describe_bundle(bundle)]
    for name in collections.names():
        try:
            variants = collections.variants(name) or (None,)
        except EthosDataError as error:
            lines.append(f"{name}: unresolvable: {error.message.splitlines()[0]}")
            continue
        for variant in variants:
            label = name if variant is None else f"{name} [{variant}]"
            try:
                resources = collections.select(name, test=variant == "test")
            except EthosDataError as error:
                lines.append(f"{label}: unresolvable: {error.message.splitlines()[0]}")
                continue
            size = _human(sum(resource.bytes for resource in resources))
            lines.append(f"{label}: {len(resources)} files, {size}")
    return "\n".join(lines)


def _plan(view: Catalog, resources: list[Resource], roots: Roots) -> str:
    """What a fetch would do, and the state of every restricted cache for its restricted data."""
    from .access import entry_states
    from .retrieval import plan

    found = plan(view, resources, roots)
    lines = [f"public cache: {found['root']}"]
    for origin, items in sorted(found["in_place_by_origin"].items()):
        size = _human(sum(resource.bytes for resource in items))
        lines.append(f"used in place: {len(items)} files, {size} ({origin})")
    present = _human(sum(resource.bytes for resource in found["present"]))
    lines.append(f"already cached: {len(found['present'])} files, {present}")
    lines.append(
        f"to download: {len(found['missing'])} files, "
        f"{_human(found['bytes_to_download'])}"
    )
    for name, reason in sorted(found["unavailable_reasons"].items()):
        lines.append(f"not available here: {name}: {reason}")
    for location in found["unreadable"][:10]:
        lines.append(f"missing where expected: {location.path} [{location.origin}]")
    for name in sorted({resource.dataset for resource in resources}):
        dataset = view.dataset(name)
        if dataset.access != k.RESTRICTED:
            continue
        states = entry_states(roots.restricted, dataset.entry_name)
        lines.append(
            f"restricted caches for {name}: "
            + ("; ".join(f"{cache}: {state}" for cache, state in states) or "none listed")
        )  # fmt: skip
    return "\n".join(lines)


def _verify(view: Catalog, resources: list[Resource], roots: Roots) -> str:
    """A ``verify`` by size: one ``stat`` per file, no file read."""
    from .verify import NOTE, OK, summarise, verify

    findings = verify(view, resources, roots, deep=False)
    counts = ", ".join(
        f"{len(found)} {status}" for status, found in summarise(findings).items()
    )
    files = [finding for finding in findings if finding.status != NOTE]
    shown = [finding for finding in findings if finding.status != OK]
    lines = [f"{len(files)} files: {counts or 'none'}"]
    lines += [str(finding) for finding in shown[:20]]
    if len(shown) > 20:
        lines.append(f"... and {len(shown) - 20} more")
    return "\n".join(lines)


def _resolved(
    target: str,
    collections: Collections | None,
    settings: Settings,
    test: bool,
) -> tuple[Catalog, list[Resource]]:
    """The catalogue view that answers for ``target``, and its files."""
    if collections is not None:
        resources = collections.resolve(target, test=test)
        return collections.view_for(resources), resources
    from .catalogs import catalog_for

    view = catalog_for(settings).overlaid(settings.roots)
    return view, view.resources(target)


def report(
    target: str | None = None,
    *,
    collections: Collections | None = None,
    catalog: str | None = None,
    root: str | Path | None = None,
    test: bool = False,
    selftest: bool = True,
    version: str = "",
) -> str:
    """Draft a problem report about ``target``, ready to post.

    ``target`` is a collection of ``collections``, the package's handle, or,
    without one, a catalogue key; ``catalog`` and ``root`` are the catalogue
    and the public cache the commands were given; ``version`` is the
    ETHOS.Data version the command line reports. The report holds the
    versions, the self-test (left out without ``selftest``), the settings
    with the state of every cache they list, the package's collections, what
    a fetch of ``target`` would do, the state of every restricted cache for
    its restricted data, and a ``verify`` by size, which reads no file. A
    part that fails says why in its place. Tokens, credentials in URLs, the
    home directory and the account name are removed.
    """
    from .config import read_settings

    try:
        settings = (
            collections.settings
            if collections is not None
            else read_settings(root=root, catalog=catalog)
        )
        settings_text = _settings(settings)
    except EthosDataError as error:
        settings, settings_text = None, f"error: {error.message}"
    view, resources = None, []
    if target is None:
        plan_text = verify_text = "(no collection or key named)"
    elif settings is None:
        plan_text = verify_text = "(the settings cannot be read)"
    else:
        try:
            view, resources = _resolved(target, collections, settings, test)
        except EthosDataError as error:
            plan_text, verify_text = f"error: {error.message}", "(nothing to verify)"
        else:
            plan_text = _section(lambda: _plan(view, resources, settings.roots))
            verify_text = _section(lambda: _verify(view, resources, settings.roots))
    restricted = view is not None and any(
        view.dataset(name).access == k.RESTRICTED
        for name in {resource.dataset for resource in resources}
    )
    text = handoff(
        "report",
        versions=", ".join(
            part
            for part in (
                f"ETHOS.Data {version}" if version else "",
                f"Python {platform.python_version()}",
                platform.platform(),
            )
            if part
        ),
        selftest=(
            _section(lambda: _selftest(catalog, root)) if selftest else "(left out)"
        ),
        settings=settings_text,
        package=(
            _section(lambda: _package(collections))
            if collections is not None
            else "(no package)"
        ),
        plan=plan_text,
        verify=verify_text,
        tracker=tracker(k.RESTRICTED if restricted else k.PUBLIC),
    )
    return scrub(text)


# -- notices -------------------------------------------------------------------------------


def release_notice(release: str, changes: dict[str, list[str]]) -> str:
    """The notice of ``release``: its new datasets, revisions, successors and removals."""
    titles = {
        "added": "New datasets",
        "revised": "New revisions, under the same keys",
        "successors": "Successors, under new keys",
        "withdrawn": "Withdrawn",
    }
    sections = [
        f"{titles[kind]}:\n\n" + "".join(f"- {line}\n" for line in lines)
        for kind, lines in changes.items()
        if lines
    ]
    return handoff(
        "release-notice",
        release=release,
        changes="\n".join(sections).rstrip() or "No dataset changed.",
    )


def answer(name: str, release: str) -> str:
    """The answer to the proposal of ``name``, which ``release`` adds."""
    return handoff("answer", name=name, release=release)


def removal_notice(
    name: str, reason: str, last_release: str | None, replacement: list[str]
) -> str:
    """The notice that ``name`` was withdrawn, for the packages that read it."""
    return handoff(
        "removal-notice",
        name=name,
        reason=reason or "no reason was given.",
        described=(
            f"The last release that describes it is {last_release}."
            if last_release
            else "No release describes it."
        ),
        replacement=(
            f"Read {', '.join(replacement)} instead, under its own keys."
            if replacement
            else "Nothing replaces it."
        ),
    )
