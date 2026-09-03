"""Access classes, and where a dataset's bytes actually come from.

Three classes, declared per dataset in the catalogue:

    public      on dCache with o+rx -- anyone downloads it
    internal    held by ICE-2, not published (yet) -- VO credentials or a local root
    restricted  licensed; may never be copied -- resolved in place, never downloaded

Independently of the class, any dataset may have a **local root** configured for
this machine (``dataset_roots`` in the config). When it does, files are used
where they lie and nothing is downloaded. That one mechanism covers three
situations that would otherwise each need their own:

  * licensed data that must not be duplicated into per-user caches
  * data already staged centrally on the HPC, which 50 users should not each re-fetch
  * data that simply has not been uploaded yet -- the case before dCache is live

The rule that matters: restricted data is never written into the shared cache,
and never silently downloaded. If no root is configured, asking for it fails
with an explanation instead of doing something surprising.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .catalog import Catalog, Dataset, Resource

__all__ = ["AccessError", "Location", "locate", "requires_local_root"]

PUBLIC = "public"
INTERNAL = "internal"
RESTRICTED = "restricted"


class AccessError(RuntimeError):
    """Raised when a dataset cannot be reached under the current configuration."""


@dataclass(frozen=True)
class Location:
    """Where one resource lives on this machine, and how it got there."""

    resource: Resource
    path: Path
    #: "download" -- fetch into the shared cache; "in-place" -- already on disk, never copied
    mode: str

    @property
    def in_place(self) -> bool:
        return self.mode == "in-place"


def access_class(dataset: Dataset) -> str:
    # From the catalogue index, not the descriptor: deciding *where* a dataset
    # comes from must never be the thing that pulls its file inventory in.
    return dataset.access


def requires_local_root(dataset: Dataset) -> bool:
    """Restricted data can only ever be used from a configured local root."""
    return access_class(dataset) == RESTRICTED


def locate(
    catalog: Catalog,
    resources: list[Resource],
    cache_root: Path,
    dataset_roots: dict[str, str | Path] | None = None,
) -> list[Location]:
    """Work out where every resource should be read from.

    Raises AccessError -- naming the dataset and what to configure -- rather than
    falling back to the cache or to a download when neither is permitted.
    """
    roots = {name: Path(path).expanduser() for name, path in (dataset_roots or {}).items()}
    located: list[Location] = []

    for resource in resources:
        dataset = catalog.dataset(resource.dataset)
        root = roots.get(dataset.name)

        if root is not None:
            located.append(Location(resource, root / resource.path, "in-place"))
            continue

        if requires_local_root(dataset):
            note = dataset.descriptor.get("ice2:restriction", "")
            lines = [f"dataset {dataset.name!r} is restricted and is never downloaded."]
            if note:
                lines.append(f"  {note}")
            lines.append("Point ice2-data at the copy on this machine:")
            lines.append(
                f"    ice2-data config set-root {dataset.name} /path/to/{dataset.name} --scope environment"
            )
            raise AccessError("\n".join(lines))

        if not catalog.publication_url:
            raise AccessError(
                f"dataset {dataset.name!r} has no local root configured and the catalogue "
                f"declares no publication URL, so there is nowhere to fetch it from.\n"
                f"Either set ice2:publication_url in catalog.yaml, or, while the data is not "
                f"yet uploaded, use the local copy:\n"
                f"    ice2-data config set-root {dataset.name} /path/to/{dataset.name} --scope environment"
            )

        located.append(Location(resource, cache_root / dataset.name / resource.path, "download"))

    return located


def check_missing(locations: list[Location]) -> list[Location]:
    """In-place files that are not actually there.

    A misconfigured root is a common and confusing failure, so it is reported as
    a list of concrete missing paths rather than one generic error.
    """
    return [loc for loc in locations if loc.in_place and not loc.path.is_file()]
