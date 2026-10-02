"""What one role hands another, drafted from what the tools know.

A proposal, the answer to it, a problem report, and the notices of a release
and of a removal: each has a template among the formats,
``ethos_data/formats/templates/handoffs/``, and a command fills it in.

========================  ==================================================
``proposal``              ``<tool>-data propose DIR``, a package maintainer
``report``                ``ethos-data report``, ``<tool>-data report``, a user
``answer``                ``catalog release``, for every proposal it accepted
``release-notice``        ``catalog release``
``removal-notice``        ``catalog remove``
========================  ==================================================

The same templates serve as issue templates in the catalogue repositories:
:func:`issue_template` fills each placeholder with what to write there.
"""

from __future__ import annotations

import getpass
import os
import re
import string
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from .errors import DescriptorError
from .formats import keys as k

__all__ = [
    "INTERNAL_TRACKER",
    "PUBLIC_TRACKER",
    "Proposal",
    "handoff",
    "issue_template",
    "names",
    "propose",
    "scrub",
]

#: Where proposals and reports about internal or restricted data go.
INTERNAL_TRACKER = (
    "https://jugit.fz-juelich.de/iek-3/shared-code/ethos-data-catalog-internal"
)
#: Where proposals and reports about public data go.
PUBLIC_TRACKER = "https://github.com/FZJ-IEK3-VSA/ETHOS.Data-Catalogue/issues"


class _Template(string.Template):
    """Only ``${braced}`` names are placeholders, as in the formats' templates."""

    pattern = r"""
    \$(?:
      (?P<escaped>(?!))                      |
      (?P<named>(?!))                        |
      {(?P<braced>[_a-z][_a-z0-9]*)}         |
      (?P<invalid>(?!))
    )
    """


def _text(name: str) -> str:
    folder = resources.files("ethos_data.formats") / "templates" / "handoffs"
    return (folder / f"{name}.md").read_text(encoding="utf-8")


def names() -> list[str]:
    """The handoffs there are templates for."""
    folder = resources.files("ethos_data.formats") / "templates" / "handoffs"
    return sorted(
        entry.name.removesuffix(".md")
        for entry in folder.iterdir()
        if entry.name.endswith(".md")
    )


def handoff(name: str, /, **values: str) -> str:
    """The handoff ``name`` with its placeholders filled in; every one must be given."""
    return _Template(_text(name)).substitute(values)


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
    "plan": "the output of `fetch --plan` and `verify`",
}

#: Issue templates: the handoff, its title, and what it is for.
ISSUES = {
    "propose-a-dataset": ("proposal", "Propose a dataset", "Hand a new or changed dataset to the catalogue maintainers"),
    "report-a-problem": ("report", "Report a problem", "A dataset, its catalogue entry or its download does not work"),
}  # fmt: skip


def issue_template(issue: str) -> str:
    """A catalogue repository's issue template, from the handoff it is made of."""
    handoff_name, title, about = ISSUES[issue]
    body = _Template(_text(handoff_name)).substitute(_HINTS)
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


# -- a proposal ------------------------------------------------------------------------


@dataclass
class Proposal:
    """The text of a proposal and what checking the candidate found."""

    name: str
    text: str
    findings: list[str] = field(default_factory=list)


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size} B"  # pragma: no cover


def _writable(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.stat().st_mode & 0o222]


def _collections_naming(collections, name: str) -> list[str]:
    """The collections of ``collections`` whose rules name ``name`` or its family."""
    if collections is None:
        return []
    found = []
    for collection, definition in collections.definitions.items():
        text = yaml.safe_dump(definition) if isinstance(definition, dict) else ""
        if f"dataset: {name}\n" in text or f"dataset: {name.split('/')[0]}\n" in text:
            found.append(collection)
    return found


def _tracker(access: str) -> str:
    if access in (k.INTERNAL, k.RESTRICTED):
        return f"{INTERNAL_TRACKER}, from a cluster installation: the data is {access}"
    return f"{PUBLIC_TRACKER} from a public installation, or {INTERNAL_TRACKER} from a cluster installation"


def propose(directory: str | Path, collections=None) -> Proposal:
    """Check a candidate, a draft ``dataset.yaml`` or a bundle, and draft its proposal.

    ``directory`` holds the draft, or is a repository bundle; ``collections``
    is the package's handle, to name the collections that read the dataset
    and whether its catalogue has it already. Raises
    :class:`~ethos_data.errors.DescriptorError` for a draft the build would
    refuse.
    """
    path = Path(directory).expanduser()
    if (path / "bundle.json").is_file():
        return _propose_bundle(path, collections)
    draft = path / "dataset.yaml" if path.is_dir() else path
    if not draft.is_file():
        raise DescriptorError(
            f"no draft at {draft}: name its dataset.yaml or its directory"
        )
    return _propose_draft(draft.resolve(), collections)


def _propose_draft(draft: Path, collections) -> Proposal:
    from .formats import dataset as dataset_format
    from .maintain.manifest import iter_data_files, select

    meta = yaml.safe_load(draft.read_text(encoding="utf-8")) or {}
    name = meta.get(k.NAME)
    if not name:
        raise DescriptorError(f"{draft} names no dataset; add `name:`")
    checked = {key: value for key, value in meta.items() if key != k.SOURCE_DIR}
    try:
        dataset_format.check(checked)
        dataset_format.check_legacy_state(meta)
    except DescriptorError as error:
        raise DescriptorError(f"{name}: {error.message}") from None
    findings = [f"{name}: {warning}" for warning in dataset_format.lint(meta)]
    source = Path(str(meta[k.SOURCE_DIR])).expanduser()
    if not source.is_absolute():
        source = Path(os.path.abspath(draft.parent / source))
    if not source.is_dir():
        raise DescriptorError(f"{name}: its source_dir {source} is not a directory")
    files = select(name, source, list(iter_data_files(source)), meta)
    size = sum(path.stat().st_size for path in files)
    writable = _writable(files)
    if writable:
        findings.append(
            f"{len(writable)} of {len(files)} files are still writable; stop changing "
            f"them and make the directory read-only: chmod -R a-w {source}"
        )
    catalogued = collections is not None and name in collections.catalog.datasets
    supersedes = meta.get(k.SUPERSEDES)
    kind = (
        f"a successor of {supersedes}"
        if supersedes
        else f"a revision of the catalogued {name}"
        if catalogued
        else "a new dataset"
    )
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
    naming = _collections_naming(collections, name)
    collection = (
        f"{', '.join(naming)} already name it"
        if naming
        else f"`include: [{{dataset: {name}}}]`"
    )
    text = handoff(
        "proposal",
        name=name,
        identity=identity,
        description=f"`{draft}`",
        bytes=f"`{source}`: {len(files)} files, {_human(size)}",
        collection=collection,
        findings="".join(f"- {finding}\n" for finding in findings),
        tracker=_tracker(meta.get(k.ACCESS, k.PUBLIC)),
    )
    return Proposal(str(name), text, findings)


def _propose_bundle(path: Path, collections) -> Proposal:
    from .bundles import load_bundle

    bundle = load_bundle(path)
    if not bundle.repository:
        raise DescriptorError(
            f"{bundle.path} is a copy exported from the catalogue; there is nothing "
            "in it to propose"
        )
    if bundle.published:
        raise DescriptorError(
            f"{bundle.family} version {bundle.version} is in release {bundle.release} "
            "already; change it and run `bundle update` for the next version"
        )
    bad = [finding for finding in bundle.verify() if not finding.ok]
    if bad:
        raise DescriptorError(
            f"{len(bad)} bundled file(s) differ from bundle.json, the first "
            f"{bad[0].key}: record the change with `bundle update` first"
        )
    from .formats import dataset as dataset_format

    findings = []
    for name, package in bundle.datasets.items():
        meta = {key: value for key, value in package.items() if key != k.RESOURCES}
        meta[k.NAME] = name
        try:
            dataset_format.check(meta)
        except DescriptorError as error:
            raise DescriptorError(f"{name}: {error.message}") from None
        findings += [f"{name}: {warning}" for warning in dataset_format.lint(meta)]
    files = len(bundle.resources)
    size = sum(resource.bytes for resource in bundle.resources.values())
    members = ", ".join(f"`{name}`" for name in sorted(bundle.datasets))
    text = handoff(
        "proposal",
        name=f"{bundle.family}, version {bundle.version}",
        identity=f"the bundle of `{bundle.family}`, version {bundle.version}: {members}",
        description=f"`{bundle.path}`, its `datasets/` holding the descriptions",
        bytes=f"`{bundle.path / 'data'}`: {files} files, {_human(size)}, in the package repository",
        collection=", ".join(
            sorted(
                {
                    c
                    for n in bundle.datasets
                    for c in _collections_naming(collections, n)
                }
            )
        )
        or f"`include: [{{dataset: {bundle.family}}}]`",
        findings="".join(f"- {finding}\n" for finding in findings),
        tracker=_tracker(k.PUBLIC),
    )
    return Proposal(bundle.family, text, findings)


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
    """The answer to the proposal ``release`` accepted as ``name``."""
    return handoff("answer", name=name, release=release)


def removal_notice(
    name: str, reason: str, last_release: str | None, replacement: list[str]
) -> str:
    """The notice that ``name`` was withdrawn, for the packages that read it."""
    return handoff(
        "removal-notice",
        name=name,
        reason=reason or "no reason was given.",
        last_release=last_release or "none yet",
        replacement=(
            f"read {', '.join(replacement)} instead, under its own keys."
            if replacement
            else "nothing replaces it."
        ),
    )
