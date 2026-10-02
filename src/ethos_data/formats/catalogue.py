"""``catalog.yaml``: a catalogue's name, contact and publication root, written once."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..errors import DescriptorError
from . import keys as k
from .fields import field

__all__ = ["CatalogMeta", "check"]


class CatalogMeta(BaseModel):
    """The hand-written keys of ``catalog.yaml``; ``build`` merges them into the index."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = field(
        k.NAME, description="The catalogue's name; the public catalogue shares it."
    )
    title: str | None = field(k.TITLE, description="A short human-readable title.")
    description: str | None = field(
        k.DESCRIPTION, description="What the catalogue is for."
    )
    publication_url: str | None = field(
        k.PUBLICATION_URL,
        description="Root of the public data store; a resource is <url>/<remote_prefix>/<path>.",
    )
    contact: str | None = field(k.CONTACT, description="Team or username.")
    catalog_role: str = field(
        k.CATALOG_ROLE,
        k.ROLE_SOURCE,
        description="Always source in a hand-written file; publish stamps published.",
        schema={"enum": list(k.CATALOG_ROLES)},
    )


def check(meta: dict) -> None:
    """The rules ``build`` enforces on ``catalog.yaml`` before it touches any dataset.

    A catalogue you can build in is a source catalogue by definition. The role
    defaults rather than being demanded, so an existing file keeps working, but
    a wrong value is refused outright: a catalogue mislabelled ``published``
    would make every tool refuse to touch it.
    """
    role = meta.get(k.CATALOG_ROLE, k.ROLE_SOURCE)
    if role not in k.CATALOG_ROLES:
        raise DescriptorError(
            f"catalog.yaml: {k.CATALOG_ROLE} must be one of {k.CATALOG_ROLES}, got {role!r}"
        )
    if role != k.ROLE_SOURCE:
        raise DescriptorError(
            f"catalog.yaml declares {k.CATALOG_ROLE}: {role!r}, but this is the catalogue being built "
            f"from dataset.yaml files, which makes it {k.ROLE_SOURCE!r}. The published copy gets "
            "its role set by `ethos-data catalog publish`; do not set it by hand."
        )
