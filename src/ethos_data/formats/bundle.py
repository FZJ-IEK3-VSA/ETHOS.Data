"""``bundle.json``: a repository copy of catalogue data, as :mod:`ethos_data.bundles` writes it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["BUNDLE_FORMAT", "BundleManifest", "BundleSource"]

BUNDLE_FORMAT = "ethos-data-bundle-v1"


class BundleSource(BaseModel):
    """Where the bundled data came from."""

    model_config = ConfigDict(extra="allow")

    catalog: str = Field(
        description="The catalogue location the bundle was exported from."
    )
    revision: str | None = Field(None, description="The pinned revision, as given.")
    catalog_version: str | None = None
    catalog_descriptor_sha256: str | None = None


class BundleManifest(BaseModel):
    """The manifest of a bundle: its source, the datasets and the bundled collections."""

    model_config = ConfigDict(extra="allow")

    format: Literal["ethos-data-bundle-v1"] = BUNDLE_FORMAT
    source: BundleSource
    datasets: dict[str, dict] = Field(
        description="Dataset name to its descriptor, resources included."
    )
    collections: dict[str, list[str]] = Field(
        description="Collection name to the resource keys it bundles, sidecars included."
    )
