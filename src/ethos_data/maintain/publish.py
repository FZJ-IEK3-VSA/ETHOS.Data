"""Generate the public catalogue from an internal one.

The internal repository describes every dataset, including ones that are hidden
(embargoed) or whose bytes are restricted. The public catalogue must contain only
what may be listed publicly, so it is generated rather than hand-maintained:

    internal repo  --(filter visibility: public)-->  public repo

Fields that only make sense to a maintainer are stripped on the way out --
crucially the embargo block, which would otherwise announce the existence and
release date of data nobody outside is supposed to know about.

    ethos-data catalog publish ../ETHOS.Data-Catalogue --dry-run
    ethos-data catalog publish ../ETHOS.Data-Catalogue
    ethos-data catalog publish ../ETHOS.Data-Catalogue --check   # CI: is it current?

It runs as a pipeline (see :mod:`.pipeline`), and ``--dry-run`` prints its plan:

``render``  the public tree, in memory
``check``   the leak check: no unpublished key, and no withheld dataset named
``write``   the generated files that differ, and the removal of every file the
            target holds that is not generated, ``.git`` left alone

Publishing an embargoed dataset is then two edits in dataset.yaml
(visibility: public, access: public), a rebuild, an upload, and a re-run of this.
Dataset names, resource names and checksums never change, so every collection
that already referenced it keeps resolving.

Note that this rewrites a *worktree*, not a history.  A public checkout must
never have been a clone of the internal repository, or the embargo blocks are
still one ``git log`` away -- see docs/how-to/catalogue-maintainers/bootstrap-a-catalogue.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import report
from ..errors import PublishError
from ..formats import dataset as dataset_format
from ..formats import keys as k
from ..formats.derived import index_row
from ..formats.registry import unpublished_keys
from . import (
    dataset_name_for,
    datasets_dir,
    inventory_of,
    iter_dataset_dirs,
    read_catalog_meta,
)
from .pipeline import Action, Pipeline

#: Maintainer-only, never in the public catalogue: the keys the dataset.yaml
#: specification marks unpublished. ``ethos:embargo`` would leak that unpublished
#: data exists and when it lands, ``ethos:license_note`` is an internal review
#: note, and a draft's ``source_dir`` a path on one machine.
STRIP_FROM_PACKAGE = dataset_format.STRIPPED

#: What the leak check looks for as a JSON key: every key any format's
#: specification marks unpublished, not only the descriptor's.
UNPUBLISHED_KEYS = unpublished_keys()

# Written into the public tree so that a stray local artefact -- an oidc-agent
# socket symlink, a __pycache__ -- cannot be committed by a careless `git add -A`.
# It is generated rather than hand-kept because the publish step erases anything
# it did not produce.
GENERATED_GITIGNORE = """__pycache__/
*.pyc
oidc-agent.sock
"""

GENERATED_README = """# ETHOS.Data-Catalogue

Public catalogue of datasets published by Forschungszentrum Jülich, Institute of
Climate and Energy Systems (ICE-2).

> **Generated — do not edit.**
> Produced from the internal catalogue by `ethos-data catalog publish`.
> Changes made here will be overwritten. Open an issue instead.

The data itself lives on [DESY dCache InfiniteSpace][dcache] and is served over
anonymous HTTPS — no Helmholtz account is needed to download it.

```bash
pip install ethos_data
ethos-data ls
ethos-data fetch <dataset-or-key>
```

## Datasets

{table}

Datasets marked **listed only** are described here but cannot be downloaded
publicly: their bytes are licensed or institute-internal. The entry exists so a
workflow that needs them fails with a useful message rather than a mystery.

[dcache]: https://hifis.net/doc/cloud-services/Storage_DESY/
"""


def public_datasets(catalog_root: Path) -> list[tuple[Path, dict]]:
    """Every dataset whose catalogue entry may be published, with its descriptor.

    A withdrawn dataset is not one of them, though its descriptor stays on
    disk until its bytes are gone.
    """
    from .manifest import left_out

    selected = []
    root = datasets_dir(catalog_root)
    for dataset_dir in iter_dataset_dirs(root):
        descriptor_path = dataset_dir / "datapackage.json"
        if not descriptor_path.is_file() or left_out(dataset_dir):
            continue
        package = json.loads(descriptor_path.read_text(encoding="utf-8"))
        if package.get(k.VISIBILITY, k.PUBLIC) != k.PUBLIC:
            continue
        # A namespace is published only if it still has a published member. A
        # family whose members are all hidden must not leave a name behind in the
        # public catalogue pointing at nothing.
        if package.get(k.NAMESPACE) and not _has_public_member(dataset_dir):
            continue
        selected.append((dataset_dir, package))
    return selected


def _has_public_member(namespace_dir: Path) -> bool:
    from .status import withdrawn

    for member in iter_dataset_dirs(namespace_dir):
        if member == namespace_dir or withdrawn(member):
            continue
        descriptor = member / "datapackage.json"
        if not descriptor.is_file():
            continue
        package = json.loads(descriptor.read_text(encoding="utf-8"))
        if package.get(k.NAMESPACE):
            continue
        if package.get(k.VISIBILITY, k.PUBLIC) == k.PUBLIC:
            return True
    return False


def strip(package: dict) -> dict:
    return {
        key: value for key, value in package.items() if key not in STRIP_FROM_PACKAGE
    }


def render(catalog_root: Path, earlier: list[str] | None = None) -> dict[Path, str]:
    """Build the complete public tree in memory: {relative path -> str | bytes}.

    ``earlier`` are the releases the public catalogue had, which its index
    keeps listing beside the one being published: a package that bounds its
    catalogue version finds the newest public release within its bounds there.
    """
    catalog_meta = read_catalog_meta(catalog_root)
    for key in STRIP_FROM_PACKAGE:
        catalog_meta.pop(key, None)
    # Overwritten, not inherited: this copy is generated whatever the source says.
    # It is the only durable marker of that -- the public tree has no catalog.yaml,
    # so without it every tool has to guess from which files happen to be present.
    catalog_meta[k.CATALOG_ROLE] = k.ROLE_PUBLISHED
    if catalog_meta.get(k.VERSION):
        catalog_meta[k.RELEASES] = _releases(
            [*(earlier or []), str(catalog_meta[k.VERSION])]
        )

    files: dict[Path, str] = {}
    entries, rows = [], []

    for dataset_dir, package in public_datasets(catalog_root):
        public_package = strip(package)
        here = Path("datasets") / dataset_dir.relative_to(datasets_dir(catalog_root))
        files[here / "datapackage.json"] = (
            json.dumps(public_package, indent=2, ensure_ascii=False) + "\n"
        )

        # Archived licence documents travel with the descriptor. A licence that
        # exists only as a URL is a licence that can disappear -- the URL printed
        # inside this catalogue's own ESA CCI delivery readme is already dead --
        # and a public consumer who cannot read the terms cannot honour them.
        for entry in public_package.get("licenses", []):
            doc = entry.get("ethos:document")
            if not doc:
                continue
            source = dataset_dir / doc
            if not source.is_file():
                raise PublishError(
                    f"{public_package['name']}: licences entry names "
                    f"ethos:document {doc}, which is not a file at {source}."
                )
            files[here / doc] = source.read_bytes()

        # A sharded dataset is useless without its shards: the index names them
        # by relative path, so they have to travel with it or every resolve
        # 404s on a file the public catalogue swears exists. The inventory
        # lists them, and a missing one says which build is due.
        inventory = inventory_of(
            dataset_name_for(datasets_dir(catalog_root), dataset_dir), dataset_dir
        )
        for shard in inventory.shard_files():
            files[here / shard] = inventory.read_part(shard).decode("utf-8")

        # The row the source index carries, built by the same function, so a
        # reader of the public catalogue finds what a reader of the internal one
        # finds: a family row says it is a family, and remote prefix and licence
        # status cost no descriptor read.
        relative = dataset_dir.relative_to(datasets_dir(catalog_root)).as_posix()
        entries.append(
            index_row(public_package, f"datasets/{relative}/datapackage.json")
        )
        access = public_package.get(k.ACCESS, k.PUBLIC)
        size = public_package["ethos:total_bytes"] / 1e6
        note = "downloadable" if access == "public" else "**listed only**"
        rows.append(
            f"| `{public_package['name']}` | {public_package.get('title', '')} "
            f"| {public_package['ethos:file_count']} | {size:,.1f} MB | {note} |"
        )

    files[Path("datacatalog.json")] = (
        json.dumps(
            {
                k.SCHEMA: k.DATACATALOG_PROFILE,
                **catalog_meta,
                k.DATASETS: entries,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    table = "\n".join(
        [
            "| Dataset | Title | Files | Size | Availability |",
            "|:--|:--|--:|--:|:--|",
            *rows,
        ]
    )
    files[Path("README.md")] = GENERATED_README.format(table=table)
    files[Path(".gitignore")] = GENERATED_GITIGNORE
    # The source catalogue's line-ending rules travel with the tree. A public
    # checkout is used from Windows too, and without them core.autocrlf=true
    # would rewrite the licence documents whose sha256 the descriptors record.
    attributes = catalog_root / ".gitattributes"
    if attributes.is_file():
        files[Path(".gitattributes")] = attributes.read_text(encoding="utf-8")
    return files


#: Characters that continue a dataset name or path. A withheld name counts as
#: mentioned where it stands on its own: ``family/era5``, ``era5-land`` and
#: ``era5.1`` do not mention a withheld ``era5``, but ``built on secret-plan.``
#: and the escaped quotes of ``\"secret-plan\"`` in a JSON string do mention
#: ``secret-plan``. A dot continues a name only when more of it follows.
_NAME_CHARACTER = r"[A-Za-z0-9_/-]"


def leaks(files: dict[Path, str | bytes], withheld: list[str]) -> list[str]:
    """Where a generated public tree says something it must not.

    The two things a release's leak check looks for: a key any format's
    specification marks unpublished, written as a JSON key, and a withheld
    dataset mentioned anywhere, in a descriptor, the index or the README, by
    its name or by its path under ``datasets/``. Licence documents are the
    publisher's own text, carried verbatim, and are not searched.
    """
    mentions = {
        name: re.compile(
            rf"(?<!{_NAME_CHARACTER})(?<!\.){re.escape(name)}"
            rf"(?!{_NAME_CHARACTER}|\.\w)"
            rf"|datasets/{re.escape(name)}/"
        )
        for name in withheld
    }
    found = []
    for relative, content in sorted(files.items(), key=lambda item: str(item[0])):
        if isinstance(content, bytes):
            continue
        where = Path(relative).as_posix()
        for key in UNPUBLISHED_KEYS:
            if re.search(rf'"{re.escape(key)}"\s*:', content):
                found.append(f"{where} carries {key}")
        for name, mention in mentions.items():
            if mention.search(content):
                found.append(f"{where} names the withheld dataset {name}")
    return found


def _differs(path: Path, content: str | bytes) -> bool:
    """Whether the file at ``path`` is not ``content``; documents compare as bytes."""
    if not path.is_file():
        return True
    if isinstance(content, bytes):
        return path.read_bytes() != content
    return path.read_text(encoding="utf-8") != content


@dataclass
class PublishResult:
    """What ``catalog publish`` wrote, or with ``check`` what is out of date."""

    files: list[str] = field(default_factory=list)
    withheld: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    leaks: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.stale or self.orphans or self.leaks)


def _releases(names: list[str]) -> list[str]:
    """Distinct releases, oldest first; anything not of the form vMAJOR.MINOR.PATCH dropped."""
    from ..model.versions import releases

    return [str(release) for release in releases(names)]


def _published_releases(destination_root: Path) -> list[str]:
    """The releases the public catalogue in ``destination_root`` lists, if any."""
    index = destination_root / "datacatalog.json"
    if not index.is_file():
        return []
    try:
        published = json.loads(index.read_text(encoding="utf-8"))
    except ValueError:
        return []
    names = list(published.get(k.RELEASES) or [])
    if published.get(k.VERSION):
        names.append(str(published[k.VERSION]))
    return names


@dataclass
class Publication:
    """What ``catalog publish`` was asked for, and what its stages found."""

    catalog_root: Path
    target: Path
    #: Compare only, as ``--check`` does: a leak is reported, not refused.
    comparing: bool = False
    #: The public tree, by path relative to the target: set by ``render``.
    files: dict[Path, str | bytes] = field(default_factory=dict)
    withheld: list[str] = field(default_factory=list)
    #: What the leak check found: set by ``check``.
    leaked: list[str] = field(default_factory=list)
    #: Generated files that differ or are missing, and files the target holds
    #: that are not generated: set by ``write``.
    stale: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)


class Render:
    """Render the public tree in memory."""

    name = "render"

    def plan(self, publication: Publication) -> list[Action]:
        target = publication.target
        # Publishing removes every file in its target but .git, so a source
        # checkout, which holds catalog.yaml, is never one.
        if (target / "catalog.yaml").is_file():
            raise PublishError(
                f"{target} holds a catalog.yaml, so it is a source catalogue, not the "
                "public one; nothing was written. Point publish at the public "
                "catalogue's checkout."
            )
        files = render(publication.catalog_root, _published_releases(target))
        publication.files = files

        root = datasets_dir(publication.catalog_root)
        published = {
            Path(*p.parts[1:-1]).as_posix()
            for p in files
            if len(p.parts) > 2 and p.parts[0] == "datasets"
        }
        publication.withheld = [
            dataset_name_for(root, directory)
            for directory in iter_dataset_dirs(root)
            if (directory / k.PACKAGE_FILE).is_file()
            and dataset_name_for(root, directory) not in published
        ]
        return []


class Check:
    """Refuse a tree that would leak, before anything is compared or written."""

    name = "check"

    def plan(self, publication: Publication) -> list[Action]:
        # In both modes, so CI's --check fails on exactly what would stop a
        # publish.
        publication.leaked = leaks(publication.files, publication.withheld)
        if publication.comparing:
            return []
        if publication.leaked:
            raise PublishError(
                "the public catalogue would leak, so nothing was written:\n"
                + "".join(f"  {problem}\n" for problem in publication.leaked)
                + "Fix the source descriptor or its visibility, rebuild, and publish "
                "again."
            )
        if not publication.target.exists():
            raise PublishError(
                f"target does not exist: {publication.target}\n"
                "Clone the public repo there first."
            )
        return []


class Write:
    """Write the generated files that differ, and remove the ones not generated."""

    name = "write"

    def plan(self, publication: Publication) -> list[Action]:
        target = publication.target
        generated = {str(relative) for relative in publication.files}
        # Anything in the target that is not generated goes: a dataset withdrawn
        # from publication must actually disappear. Symbolic links are removed
        # without following them, so a dangling one does not survive.
        orphans = sorted(
            path
            for path in (target.rglob("*") if target.is_dir() else [])
            if (path.is_file() or path.is_symlink())
            and ".git" not in path.relative_to(target).parts
            and str(path.relative_to(target)) not in generated
        )
        publication.orphans = [str(path.relative_to(target)) for path in orphans]
        changed = sorted(
            (
                relative
                for relative, content in publication.files.items()
                if _differs(target / relative, content)
            ),
            key=str,
        )
        publication.stale = [str(relative) for relative in changed]
        actions = [
            Action(f"remove {path.relative_to(target)}", self._remove(target, path))
            for path in orphans
        ]
        actions += [
            Action(
                f"write {relative}",
                self._write(target / relative, publication.files[relative]),
            )
            for relative in changed
        ]
        return actions

    @staticmethod
    def _remove(target: Path, path: Path):
        def remove() -> None:
            path.unlink()
            parent = path.parent
            while parent != target and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent

        return remove

    @staticmethod
    def _write(destination: Path, content: str | bytes):
        def write() -> None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Licence documents are carried verbatim and may be PDFs, so the
            # rendered tree is not text-only. Everything else is generated text,
            # and both arguments below are load-bearing: the README says
            # "Jülich", which write_text left to its defaults would encode with
            # the locale codec and line-end as CRLF on Windows, so the public
            # catalogue would differ byte for byte depending on who published it.
            if isinstance(content, bytes):
                destination.write_bytes(content)
            else:
                destination.write_text(content, encoding="utf-8", newline="\n")

        return write


PIPELINE: Pipeline[Publication] = Pipeline("publish", [Render(), Check(), Write()])


@report.reported
def run(
    catalog_root: Path, target: str, check: bool = False, *, dry_run: bool = False
) -> PublishResult:
    """Write the public catalogue into ``target``, or with ``check`` compare it.

    ``dry_run`` prints the plan: the files publish would write and remove.
    """
    publication = Publication(
        catalog_root, Path(target).expanduser().resolve(), comparing=check
    )
    if check:
        PIPELINE.plan(publication)
        for problem in publication.leaked:
            report.warning(f"  LEAK: {problem}")
        if publication.stale or publication.orphans:
            report.warning("Public catalogue is out of date:")
            for relative in publication.stale:
                report.warning(f"  changed/missing: {relative}")
            for relative in publication.orphans:
                report.warning(f"  should be removed: {relative}")
        if not (publication.leaked or publication.stale or publication.orphans):
            report.info(
                f"Public catalogue is current ({len(publication.files)} files)."
            )
        return PublishResult(
            withheld=publication.withheld,
            stale=publication.stale,
            orphans=publication.orphans,
            leaks=publication.leaked,
        )

    outcome = PIPELINE.run(publication, dry_run=dry_run)
    if publication.withheld:
        report.info(
            f"\nWithheld (visibility: hidden): {', '.join(publication.withheld)}"
        )
    if outcome.planned and not dry_run:
        report.info(
            f"\nPublished to {publication.target}. Review and commit in the public "
            "repo, then push."
        )
    return PublishResult(
        files=sorted(str(relative) for relative in publication.files),
        withheld=publication.withheld,
    )
