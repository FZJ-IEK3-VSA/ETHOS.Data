"""``bundle.json``: a repository copy of catalogue data, as :mod:`ethos_data.bundles` writes it.

Two kinds. A repository bundle, which ``bundle create`` starts, is the source
of truth for a family of test datasets: its files change by commit, and its
version counts the changes the catalogue has to publish. An exported bundle
is a copy of what the catalogue already publishes, with the collections it
was exported for.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .package import ResourceRecord

__all__ = [
    "BUNDLE_FORMAT",
    "REPOSITORY_FORMAT",
    "BundleManifest",
    "BundleSource",
    "RepositoryBundle",
    "RepositoryDataset",
]

BUNDLE_FORMAT = "ethos-data-bundle-v1"
REPOSITORY_FORMAT = "ethos-data-bundle-v2"


class BundleSource(BaseModel):
    """Where the bundled data came from."""

    model_config = ConfigDict(extra="allow")

    catalog: str = Field(
        description="The catalogue location the bundle was exported from."
    )
    revision: str | None = Field(None, description="The pinned revision, as given.")
    catalog_version: str | None = Field(
        None, description="The release of that catalogue."
    )
    catalog_descriptor_sha256: str | None = Field(
        None, description="The digest of the index the bundle was exported from."
    )


class BundleManifest(BaseModel):
    """The manifest of a bundle: its source, the datasets and the bundled collections."""

    model_config = ConfigDict(extra="allow")

    format: Literal["ethos-data-bundle-v1"] = Field(
        BUNDLE_FORMAT, description="An exported bundle."
    )
    source: BundleSource = Field(description="Where the bundled data came from.")
    datasets: dict[str, dict] = Field(
        description="Dataset name to its descriptor, resources included."
    )
    collections: dict[str, list[str]] = Field(
        description="Collection name to the resource keys it bundles, sidecars included."
    )


class RepositoryDataset(BaseModel):
    """One member of a repository bundle: its files, as a catalogue inventory."""

    model_config = ConfigDict(extra="allow")

    resources: list[ResourceRecord] = Field(
        description="Every file under `data/<dataset>/`, with its size and SHA-256."
    )


class RepositoryBundle(BaseModel):
    """The manifest of a repository bundle: one family of datasets, versioned."""

    model_config = ConfigDict(extra="allow")

    format: Literal["ethos-data-bundle-v2"] = Field(
        REPOSITORY_FORMAT, description="A repository bundle."
    )
    family: str = Field(description="The family the bundle's datasets belong to.")
    version: int = Field(
        1, ge=1, description="Counts the changes the catalogue publishes."
    )
    release: str | None = Field(
        None,
        description="The catalogue release that publishes this version; null until one does.",
    )
    datasets: dict[str, RepositoryDataset] = Field(
        description="Each member by its name, `<family>/<member>`."
    )
