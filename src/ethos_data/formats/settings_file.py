"""The settings file: where data lies for one person on one machine."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SettingsFile"]


class SettingsFile(BaseModel):
    """The keys ``ethos-data config set-*`` writes and every ETHOS tool reads."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    catalog: str | None = Field(
        None, description="The catalogue to read; replaces the public one and any pin."
    )
    public_cache: str | None = Field(
        None, description="Where public and internal data is read and downloaded."
    )
    restricted_cache: str | None = Field(
        None, description="Where licensed data lives; read in place, never written."
    )
    staging_cache: str | None = Field(
        None, description="Where work in progress lives; shadows the catalogue."
    )
    publication_url: str | None = Field(
        None, description="Fetch bytes from another door of the published store."
    )
