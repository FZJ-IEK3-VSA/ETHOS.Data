"""``status.yaml``: where a dataset stands in its source catalogue.

One beside each ``dataset.yaml`` that describes files, written by the
``catalog`` commands, and by ``link`` and ``materialize`` given
``--catalog-root``. Never by hand, and never published: it names directories
on the maintainers' machines.

It is not a description of the data: it holds the build input while there is
one, the copies of the bytes, which of them is authoritative once the
inventory is final, and the history of every step taken.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..errors import DescriptorError
from . import keys as k

__all__ = ["Copy", "Event", "StatusFile", "check"]

#: The file, beside the dataset's ``dataset.yaml``.
FILENAME = "status.yaml"


class _Record(BaseModel):
    """Keys a later release adds are kept, so an older one rewrites them unchanged."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Copy(_Record):
    """One place the dataset's bytes can be read from, as a command put them there."""

    kind: str = Field(
        description="uploaded to dCache, linked into a cache, or materialized there",
        json_schema_extra={"enum": list(k.COPY_KINDS)},
    )
    location: str = Field(
        description="The dataset's folder on the store for an upload; the cache entry otherwise."
    )
    target: str | None = Field(
        None, description="The directory a linked entry points at."
    )
    verified: str | None = Field(
        None, description="When a command last found every file there, in UTC."
    )


class Event(_Record):
    """One entry of the history: a step taken, by whom and when."""

    at: str = Field(description="When, in UTC.")
    by: str = Field("", description="The account that took the step.")
    step: str = Field(
        description="add, migrate, build, revise, change, upload, verify, link, "
        "materialize, record, check-source, remove, purge or release."
    )
    previous: str | None = Field(
        None, alias="from", description="The state before, when the step changed it."
    )
    state: str = Field(alias="to", description="The state after.")
    note: str | None = Field(
        None,
        description="Why, as the command was told: a removal's reason, a check's note.",
    )
    files: int | None = Field(
        None, description="The inventory's file count, for a step that read it."
    )
    bytes: int | None = Field(None, description="The inventory's size in bytes.")
    copy_: Copy | None = Field(
        None, alias="copy", description="The copy the step made or checked."
    )
    source_dir: str | None = Field(
        None, description="The build input that freezing the dataset retired."
    )
    release: str | None = Field(
        None,
        description="The catalogue release a release step made, vMAJOR.MINOR.PATCH.",
    )


class StatusFile(_Record):
    """The keys of a ``status.yaml``."""

    state: str = Field(
        alias=k.STATE,
        description="Where the dataset stands; see the lifecycle.",
        json_schema_extra={"enum": list(k.STATES)},
    )
    source_dir: str | None = Field(
        None,
        alias=k.SOURCE_DIR,
        description="The build input: the directory the build reads, relative to the dataset directory if relative.",
    )
    revision: int = Field(
        1,
        alias="revision",
        description="Which revision of the dataset the inventory describes; 1 for the first.",
        ge=1,
    )
    authority: str | None = Field(
        None,
        alias=k.AUTHORITY,
        description="The location of the authoritative copy, once the dataset is frozen.",
    )
    copies: list[Copy] = Field(
        [], alias=k.COPIES, description="Every place the bytes were made available."
    )
    history: list[Event] = Field(
        [], alias=k.HISTORY, description="Every step taken, oldest first."
    )


#: The states in which the build reads a build input.
_BUILT_FROM_SOURCE = (k.STATE_DRAFT, k.STATE_BUILT, k.STATE_AVAILABLE)


def check(status: StatusFile) -> None:
    """Raise :class:`~ethos_data.errors.DescriptorError` for the first rule ``status`` breaks.

    The rules a status file keeps on its own. Whether its record still matches
    the dataset -- the access class in ``dataset.yaml``, the files a copy holds
    -- is ``catalog status --check``'s question. The messages carry no dataset
    name; the caller, which knows it, prefixes one.
    """
    if status.state not in k.STATES:
        raise DescriptorError(
            f"state is {status.state!r}, which is not one of {', '.join(k.STATES)}"
        )
    for copy in status.copies:
        if copy.kind not in k.COPY_KINDS:
            raise DescriptorError(
                f"a copy at {copy.location} is {copy.kind!r}, which is not one of "
                f"{', '.join(k.COPY_KINDS)}"
            )
    if status.state in _BUILT_FROM_SOURCE and not status.source_dir:
        raise DescriptorError(
            f"a {status.state} dataset is built from its source_dir, and the status "
            "file names none"
        )
    if status.state == k.STATE_FROZEN and status.source_dir:
        raise DescriptorError(
            "a frozen dataset is never rebuilt from local files, yet the status file "
            f"still names source_dir: {status.source_dir!r}"
        )
    locations = {copy.location for copy in status.copies}
    if status.authority is not None and status.authority not in locations:
        raise DescriptorError(
            f"the authoritative copy {status.authority} is not one of the recorded copies"
        )
