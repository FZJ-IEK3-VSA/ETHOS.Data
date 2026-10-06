"""``catalog.yaml``: a catalogue's name, contact and publication root, written once."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..errors import DescriptorError
from ..model.versions import RELEASE_PATTERN, Version
from . import keys as k
from .fields import field, keys_with

__all__ = ["STRIPPED", "CatalogMeta", "StoreSettings", "check", "store_of"]

#: The DESY dCache REST interface the store settings name by default.
DCACHE_FRONTEND = "https://hifis-storage-web.desy.de/api/v1"


class StoreSettings(BaseModel):
    """How the maintainer commands reach the publication store; the institute's dCache by default."""

    model_config = ConfigDict(extra="forbid")

    remote: str = Field(
        "HIFIS", description="The rclone remote that reaches the store."
    )
    vo_path: str = Field(
        "Helmholtz/FZJ-ICE2", description="The VO's path in the store's namespace."
    )
    oidc_profile: str = Field(
        "HIFIS", description="The oidc-agent profile that issues the store's tokens."
    )
    frontend: str = Field(
        DCACHE_FRONTEND,
        description="The store's REST interface, for permissions and locality.",
    )


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
    version: str | None = field(
        k.VERSION,
        description="The release this is, vMAJOR.MINOR.PATCH; the build writes it into the index.",
        schema={"pattern": RELEASE_PATTERN},
    )
    catalog_role: str = field(
        k.CATALOG_ROLE,
        k.ROLE_SOURCE,
        description="Always source in a hand-written file; publish stamps published.",
        schema={"enum": list(k.CATALOG_ROLES)},
    )
    store: StoreSettings | None = field(
        k.STORE,
        description="How upload, release and purge reach the store; the institute's "
        "dCache by default.",
        published=False,
    )


#: Never in an index: how the maintainers reach the store is theirs to know.
STRIPPED = keys_with(CatalogMeta, "published", False)


def store_of(meta: Mapping) -> StoreSettings:
    """The store settings ``catalog.yaml`` gives, with the defaults for any it leaves out."""
    try:
        return StoreSettings.model_validate(meta.get(k.STORE) or {})
    except ValidationError as error:
        from .dataset import describe

        raise DescriptorError(
            f"catalog.yaml: {k.STORE}: {'; '.join(describe(error))}"
        ) from None


def check(meta: dict) -> None:
    """The rules ``build`` enforces on ``catalog.yaml`` before it touches any dataset.

    A catalogue you can build in is a source catalogue by definition. The role
    defaults rather than being demanded, so an existing file keeps working, but
    a wrong value is refused outright: a catalogue mislabelled ``published``
    would make every tool refuse to touch it.
    """
    store_of(meta)
    if meta.get(k.VERSION) is not None:
        try:
            Version.parse(meta[k.VERSION])
        except ValueError as error:
            raise DescriptorError(f"catalog.yaml: {k.VERSION}: {error}") from None
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
