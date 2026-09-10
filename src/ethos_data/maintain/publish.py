"""Generate the public catalogue from an internal one.

The internal repository describes every dataset, including ones that are hidden
(embargoed) or whose bytes are restricted. The public catalogue must contain only
what may be listed publicly, so it is generated rather than hand-maintained:

    internal repo  --(filter visibility: public)-->  public repo

Fields that only make sense to a maintainer are stripped on the way out --
crucially the embargo block, which would otherwise announce the existence and
release date of data nobody outside is supposed to know about.

    ethos-data catalog publish ../ethos-data-catalog
    ethos-data catalog publish ../ethos-data-catalog --check   # CI: is it current?

Publishing an embargoed dataset is then two edits in dataset.yaml
(visibility: public, access: public), a rebuild, an upload, and a re-run of this.
Dataset names, resource names and checksums never change, so every collection
that already referenced it keeps resolving.

Note that this rewrites a *worktree*, not a history.  A public checkout must
never have been a clone of the internal repository, or the embargo blocks are
still one ``git log`` away -- see docs/how-to/bootstrap-a-catalogue.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from ..catalog import ROLE_KEY, ROLE_PUBLISHED
from . import NAMESPACE_KEY, dataset_name_for, datasets_dir, iter_dataset_dirs

# Maintainer-only. Never appears in the public catalogue.
#   ethos:embargo        -- would leak that unpublished data exists, and when it lands
#   ethos:license_note   -- internal review notes, not a public statement
#   source_dir          -- a path on someone's workstation
#   ethos:uploaded       -- workflow bookkeeping about where the manifest came from
STRIP_FROM_PACKAGE = ("ethos:embargo", "ethos:license_note", "source_dir", "ethos:uploaded")

# Written into the public tree so that a stray local artefact -- an oidc-agent
# socket symlink, a __pycache__ -- cannot be committed by a careless `git add -A`.
# It is generated rather than hand-kept because the publish step erases anything
# it did not produce.
GENERATED_GITIGNORE = """__pycache__/
*.pyc
oidc-agent.sock
"""

GENERATED_README = """# ethos-data-catalog

Public catalogue of datasets published by Forschungszentrum Jülich, Institute of
Climate and Energy Systems (ICE-2).

> **Generated — do not edit.**
> Produced from the internal catalogue by `ethos-data catalog publish`.
> Changes made here will be overwritten. Open an issue instead.

The data itself lives on [DESY dCache InfiniteSpace][dcache] and is served over
anonymous HTTPS — no Helmholtz account is needed to download it.

```bash
pip install ethos_data
ethos-data -c collections.yaml fetch test_suite
```

## Datasets

{table}

Datasets marked **listed only** are described here but cannot be downloaded
publicly: their bytes are licensed or institute-internal. The entry exists so a
workflow that needs them fails with a useful message rather than a mystery.

[dcache]: https://hifis.net/doc/cloud-services/Storage_DESY/
"""


def public_datasets(catalog_root: Path) -> list[tuple[Path, dict]]:
    """Every dataset whose catalogue entry may be published, with its descriptor."""
    selected = []
    root = datasets_dir(catalog_root)
    for dataset_dir in iter_dataset_dirs(root):
        descriptor_path = dataset_dir / "datapackage.json"
        if not descriptor_path.is_file():
            continue
        package = json.loads(descriptor_path.read_text())
        if package.get("ethos:visibility", "public") != "public":
            continue
        # A namespace is published only if it still has a published member. A
        # family whose members are all hidden must not leave a name behind in the
        # public catalogue pointing at nothing.
        if package.get(NAMESPACE_KEY) and not _has_public_member(dataset_dir):
            continue
        selected.append((dataset_dir, package))
    return selected


def _has_public_member(namespace_dir: Path) -> bool:
    for member in iter_dataset_dirs(namespace_dir):
        if member == namespace_dir:
            continue
        descriptor = member / "datapackage.json"
        if not descriptor.is_file():
            continue
        package = json.loads(descriptor.read_text())
        if package.get(NAMESPACE_KEY):
            continue
        if package.get("ethos:visibility", "public") == "public":
            return True
    return False


def strip(package: dict) -> dict:
    return {key: value for key, value in package.items() if key not in STRIP_FROM_PACKAGE}


def render(catalog_root: Path) -> dict[Path, str]:
    """Build the complete public tree in memory: {relative path -> str | bytes}."""
    catalog_meta = yaml.safe_load((catalog_root / "catalog.yaml").read_text())
    for key in STRIP_FROM_PACKAGE:
        catalog_meta.pop(key, None)
    # Overwritten, not inherited: this copy is generated whatever the source says.
    # It is the only durable marker of that -- the public tree has no catalog.yaml,
    # so without it every tool has to guess from which files happen to be present.
    catalog_meta[ROLE_KEY] = ROLE_PUBLISHED

    files: dict[Path, str] = {}
    entries, rows = [], []

    for dataset_dir, package in public_datasets(catalog_root):
        public_package = strip(package)
        here = Path("datasets") / dataset_dir.relative_to(datasets_dir(catalog_root))
        files[here / "datapackage.json"] = json.dumps(public_package, indent=2, ensure_ascii=False) + "\n"

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
                raise SystemExit(
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
                raise SystemExit(
                    f"{public_package['name']}: shard {shard['path']} is missing. Run:\n"
                    f"    ethos-data catalog build {dataset_name_for(datasets_dir(catalog_root), dataset_dir)}"
                )
            files[here / shard["path"]] = source.read_text()

        entries.append(
            {
                "name": public_package["name"],
                "path": f"datasets/{dataset_dir.relative_to(datasets_dir(catalog_root)).as_posix()}/datapackage.json",
                "title": public_package.get("title", ""),
                "ethos:access": public_package.get("ethos:access", "public"),
                "ethos:total_bytes": public_package["ethos:total_bytes"],
                "ethos:file_count": public_package["ethos:file_count"],
            }
        )
        access = public_package.get("ethos:access", "public")
        size = public_package["ethos:total_bytes"] / 1e6
        note = "downloadable" if access == "public" else "**listed only**"
        rows.append(
            f"| `{public_package['name']}` | {public_package.get('title','')} "
            f"| {public_package['ethos:file_count']} | {size:,.1f} MB | {note} |"
        )

    files[Path("datacatalog.json")] = (
        json.dumps(
            {
                "$schema": "https://datapackage.org/profiles/2.0/datacatalog.json",
                **catalog_meta,
                "datasets": entries,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    table = "\n".join(
        ["| Dataset | Title | Files | Size | Availability |", "|:--|:--|--:|--:|:--|", *rows]
    )
    files[Path("README.md")] = GENERATED_README.format(table=table)
    files[Path(".gitignore")] = GENERATED_GITIGNORE
    return files


def run(catalog_root: Path, target: str, check: bool = False) -> int:
    destination_root = Path(target).expanduser().resolve()
    files = render(catalog_root)

    root = datasets_dir(catalog_root)
    all_datasets = [d for d in iter_dataset_dirs(root) if (d / "datapackage.json").is_file()]
    published = {
        Path(*p.parts[1:-1]).as_posix() for p in files if len(p.parts) > 2 and p.parts[0] == "datasets"
    }
    withheld = [
        dataset_name_for(root, d) for d in all_datasets
        if dataset_name_for(root, d) not in published
    ]

    if check:
        stale = [
            rel for rel, text in files.items()
            if not (destination_root / rel).is_file() or (destination_root / rel).read_text() != text
        ]
        # Anything in the target that we no longer generate is also staleness --
        # a dataset withdrawn from publication must actually disappear.
        generated = {str(rel) for rel in files}
        orphans = [
            str(p.relative_to(destination_root))
            for p in destination_root.rglob("*")
            if p.is_file() and ".git" not in p.parts and str(p.relative_to(destination_root)) not in generated
        ]
        if stale or orphans:
            print("Public catalogue is out of date:", file=sys.stderr)
            for rel in stale:
                print(f"  changed/missing: {rel}", file=sys.stderr)
            for rel in orphans:
                print(f"  should be removed: {rel}", file=sys.stderr)
            return 1
        print(f"Public catalogue is current ({len(files)} files).")
        return 0

    if not destination_root.exists():
        raise SystemExit(f"target does not exist: {destination_root}\nClone the public repo there first.")

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
        # tree is not text-only. Everything else is generated text.
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content)

    print(f"Published to {destination_root}")
    for rel in sorted(files, key=str):
        print(f"  + {rel}")
    if withheld:
        print(f"\nWithheld (visibility: hidden): {', '.join(withheld)}")
    print("\nReview and commit in the public repo, then push.")
    return 0
