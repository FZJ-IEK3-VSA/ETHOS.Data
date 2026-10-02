"""Records the tools write beside data: the staging registry and the materialisation record."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, RootModel

__all__ = ["MaterializedRecord", "StagingEntry", "StagingRegistry"]


class StagingEntry(BaseModel):
    """Who staged a directory under a name, and why."""

    model_config = ConfigDict(extra="allow")

    target: str = Field(
        description="The directory the entry links to or was copied from."
    )
    note: str = Field("", description="What the entry is for.")
    added: str = Field(
        "", description="When it was staged, in local time with its UTC offset."
    )
    added_by: str = Field("", description="The account that staged it.")
    copied: bool = Field(
        False, description="A copy the staging root owns, rather than a link."
    )


class StagingRegistry(RootModel[dict[str, StagingEntry]]):
    """``.ice2-staging.json`` in the staging root: name to entry."""


class MaterializedRecord(BaseModel):
    """``.ethos-data-materialized.json`` in a materialised cache entry."""

    model_config = ConfigDict(extra="allow")

    dataset: str = Field(description="The dataset the entry holds.")
    materialized_from: str = Field(
        description="The directory the bytes were copied from."
    )
    was_a_link_at: str | None = Field(
        None, description="The entry that was a link, or null when the copy created it."
    )
    catalog: str = Field(description="The catalogue the copy was checked against.")
    files: int = Field(description="How many files were copied.")
    bytes: int = Field(description="Their size together.")
    verified: bool = Field(
        description="Whether every copy was checked against its hash."
    )
    when: str = Field(description="When, in local time with its UTC offset.")
    by: str = Field("", description="The account that made the copy.")
