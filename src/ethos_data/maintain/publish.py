"""Generate the public catalogue from an internal one.

The internal repository describes every dataset, including ones that are hidden
(embargoed) or whose bytes are restricted. The public catalogue must contain only
what may be listed publicly, so it is generated rather than hand-maintained:

    internal repo  --(filter visibility: public)-->  public repo

Fields that only make sense to a maintainer are stripped on the way out --
crucially the embargo block, which would otherwise announce the existence and
release date of data nobody outside is supposed to know about.

    ethos-data catalog publish ../ETHOS.Data-Catalogue
    ethos-data catalog publish ../ETHOS.Data-Catalogue --check   # CI: is it current?

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
from pathlib import Path

from .. import report
from ..errors import PublishError
from ..formats import dataset as dataset_format
from ..formats import keys as k
from ..formats.derived import index_row
from . import dataset_name_for, datasets_dir, iter_dataset_dirs, read_catalog_meta

#: Maintainer-only, never in the public catalogue: the keys the dataset.yaml
#: specification marks unpublished. ``ethos:embargo`` would leak that unpublished
#: data exists and when it lands, ``ethos:license_note`` is an internal review
#: note, ``source_dir`` a path on somebody's workstation, ``ethos:uploaded`` and
#: ``ethos:frozen`` bookkeeping about where the inventory came from.
STRIP_FROM_PACKAGE = dataset_format.STRIPPED

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
    from ..formats.catalogue import STRIPPED as STRIP_FROM_INDEX

    catalog_meta = read_catalog_meta(catalog_root)
    for key in (*STRIP_FROM_PACKAGE, *STRIP_FROM_INDEX):
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
        # 404s on a file the public catalogue swears exists.
        for shard in public_package.get("ethos:shards", []):
            source = dataset_dir / shard["path"]
            if not source.is_file():
                raise PublishError(
                    f"{public_package['name']}: shard {shard['path']} is missing. Run:\n"
                    f"    ethos-data catalog build {dataset_name_for(datasets_dir(catalog_root), dataset_dir)}"
                )
            files[here / shard["path"]] = source.read_text(encoding="utf-8")

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
    # The handoffs a public user starts, as the repository's issue templates:
    # the same templates the commands fill in, so the two never ask for
    # different things.
    from ..handoffs import ISSUES, issue_template

    for issue in ISSUES:
        files[Path(".github") / "ISSUE_TEMPLATE" / f"{issue}.md"] = issue_template(
            issue
        )
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

    The two things a release's leak check looks for: a key the dataset.yaml
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
        for key in STRIP_FROM_PACKAGE:
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


def _releases(names: list[str]) -> list[str]:
    """Distinct releases, oldest first; anything not of the form vYYYY.MM.N dropped."""
    from ..model.versions import Version

    found = set()
    for name in names:
        try:
            found.add(Version.parse(name))
        except ValueError:
            continue
    return [str(release) for release in sorted(found)]


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


def plan(
    catalog_root: Path, destination_root: Path
) -> tuple[dict[Path, str | bytes], list[str], list[str]]:
    """The public tree for ``destination_root``, the datasets it withholds, its leaks.

    Withheld are the datasets the tree leaves out, hidden ones among them; a
    withdrawn dataset is neither published nor withheld.
    """
    from .manifest import left_out

    files = render(catalog_root, _published_releases(destination_root))
    root = datasets_dir(catalog_root)
    all_datasets = [
        d
        for d in iter_dataset_dirs(root)
        if (d / "datapackage.json").is_file() and not left_out(d)
    ]
    published = {
        Path(*p.parts[1:-1]).as_posix()
        for p in files
        if len(p.parts) > 2 and p.parts[0] == "datasets"
    }
    withheld = [
        dataset_name_for(root, d)
        for d in all_datasets
        if dataset_name_for(root, d) not in published
    ]
    return files, withheld, leaks(files, withheld)


@report.reported
def run(catalog_root: Path, target: str, check: bool = False) -> int:
    destination_root = Path(target).expanduser().resolve()
    # Before anything is compared or written: a tree that would leak is refused
    # whatever the target holds, and in both modes, so CI's --check fails on
    # exactly what would stop a publish.
    files, withheld, leaked = plan(catalog_root, destination_root)

    if check:
        stale = [
            rel
            for rel, content in files.items()
            if _differs(destination_root / rel, content)
        ]
        # Anything in the target that we no longer generate is also staleness --
        # a dataset withdrawn from publication must actually disappear.
        generated = {str(rel) for rel in files}
        orphans = [
            str(p.relative_to(destination_root))
            for p in destination_root.rglob("*")
            if p.is_file()
            and ".git" not in p.parts
            and str(p.relative_to(destination_root)) not in generated
        ]
        for problem in leaked:
            report.warning(f"  LEAK: {problem}")
        if stale or orphans or leaked:
            if stale or orphans:
                report.warning("Public catalogue is out of date:")
            for rel in stale:
                report.warning(f"  changed/missing: {rel}")
            for rel in orphans:
                report.warning(f"  should be removed: {rel}")
            return 1

        report.info(f"Public catalogue is current ({len(files)} files).")
        return 0

    if leaked:
        raise PublishError(
            "the public catalogue would leak, so nothing was written:\n"
            + "".join(f"  {problem}\n" for problem in leaked)
            + "Fix the source descriptor or its visibility, rebuild, and publish again."
        )

    if not destination_root.exists():
        raise PublishError(
            f"target does not exist: {destination_root}\nClone the public repo there first."
        )

    # Remove previously generated content so withdrawn datasets really go away.
    # Symlinks are unlinked without following them: a dangling one is neither a
    # file nor a directory, and would otherwise survive every publish forever.
    for path in sorted(destination_root.rglob("*"), reverse=True):
        if ".git" in path.parts:
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()

    for rel, content in files.items():
        destination = destination_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Licence documents are carried verbatim and may be PDFs, so the rendered
        # tree is not text-only. Everything else is generated text, and both
        # arguments below are load-bearing: this README says "Jülich", which
        # write_text left to its defaults would encode with the locale codec and
        # line-end as CRLF on Windows, so the public catalogue would differ byte
        # for byte depending on who published it.
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content, encoding="utf-8", newline="\n")

    report.info(f"Published to {destination_root}")
    for rel in sorted(files, key=str):
        report.info(f"  + {rel}")
    if withheld:
        report.info(f"\nWithheld (visibility: hidden): {', '.join(withheld)}")
    report.info("\nReview and commit in the public repo, then push.")
    return 0
