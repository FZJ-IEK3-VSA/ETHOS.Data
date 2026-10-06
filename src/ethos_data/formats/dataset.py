"""``dataset.yaml``: the hand-written description of one dataset.

Three things live here, for the one file:

* :class:`DatasetDescriptor` and :class:`NamespaceDescriptor`, the structure
  of the file as pydantic models: the type, default and description of every
  documented key, and its four properties (see :mod:`.fields`). They give the
  code typed access and the package its JSON Schema.
* :func:`check`, the rules the build enforces, with the messages maintainers
  already know. The first broken rule raises :class:`~ethos_data.errors.DescriptorError`.
* :func:`lint`, what the structure says beyond those rules: a value of the
  wrong type, an ``ethos:`` key the format does not know, a value outside a
  closed vocabulary. Reported as warnings: the build names each one and goes
  on.

The messages carry no dataset name; the caller, which knows it, prefixes one.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ..errors import DescriptorError
from ..model.names import relative
from . import keys as k
from .fields import describe, field, keys, keys_with

__all__ = [
    "Contributor",
    "DatasetDescriptor",
    "Embargo",
    "License",
    "NamespaceDescriptor",
    "Source",
    "Upstream",
    "apply_defaults",
    "check",
    "check_namespace",
    "lint",
]


class _Part(BaseModel):
    """A mapping inside a descriptor. Unknown keys are kept, as Frictionless allows."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Source(_Part):
    """One entry of ``sources``: where the data came from, or what it was derived from."""

    title: str | None = None
    path: str | None = None


class Contributor(_Part):
    """One entry of ``contributors``; Data Package v2, so ``roles`` is a list."""

    title: str
    roles: list[str] = []
    organization: str | None = None
    path: str | None = None
    email: str | None = None


class License(_Part):
    """One entry of ``licenses``: an Open Definition ``name``, a ``path`` to the terms, or both."""

    name: str | None = None
    path: str | None = None
    title: str | None = None
    applies_to: list[str] | None = field(
        k.APPLIES_TO,
        description="Globs of the files this licence covers; omit to cover every file.",
    )
    document: str | None = field(
        k.DOCUMENT,
        description="An archived copy of the terms, relative to the dataset directory.",
    )
    document_sha256: str | None = field(
        k.DOCUMENT_SHA256,
        description="The archived document's digest; written by the build, or a pin it verifies.",
    )


class Embargo(_Part):
    """Why a hidden dataset is hidden, and until when."""

    until: str
    reason: str | None = None
    becomes: str | None = None


class Upstream(_Part):
    """Whether the original source still serves this delivery."""

    status: str = field(
        "status",
        description="Whether upstream still serves this delivery.",
        schema={"enum": list(k.UPSTREAM_STATUSES)},
    )
    checked: str | None = None
    note: str | None = None


_ACCESS_ENUM = {"enum": list(k.ACCESS_CLASSES)}
_VISIBILITY_ENUM = {"enum": list(k.VISIBILITIES)}


class DatasetDescriptor(_Part):
    """The keys of a ``dataset.yaml`` describing a dataset with files.

    Keys outside this list pass through to the generated descriptor unchanged;
    :func:`lint` names the ``ethos:`` ones, which are usually typos.
    """

    # -- identity ----------------------------------------------------------
    name: str | None = field(
        k.NAME,
        description="The dataset's name; the directory decides it, and a stated one must agree.",
        promoted=True,
    )
    title: str | None = field(
        k.TITLE,
        description="A short human-readable title.",
        promoted=True,
        user_facing=True,
    )
    description: str | None = field(
        k.DESCRIPTION, description="What it is and what it is for.", user_facing=True
    )
    homepage: str | None = field(
        k.HOMEPAGE,
        description="The product's landing page.",
        user_facing=True,
        inherited=True,
    )
    id: str | None = field(
        k.ID, description="The most persistent identifier of this release."
    )
    version: str | int | float | None = field(
        k.VERSION,
        description="The publisher's own release designation, verbatim and quoted.",
        promoted=True,
        user_facing=True,
    )
    sources: list[Source] = field(
        k.SOURCES, [], description="Where it came from.", user_facing=True
    )
    contributors: list[Contributor] = field(
        k.CONTRIBUTORS,
        [],
        description="Who made it; an author is required for derived and created data.",
    )
    licenses: list[License] = field(
        k.LICENSES,
        [],
        description="The terms; several entries for several licences.",
        user_facing=True,
    )
    retrieved: str | None = field(
        k.RETRIEVED,
        description='The date the bytes were fetched from upstream, quoted, or "unknown".',
    )
    contact: str | None = field(
        k.CONTACT,
        description="The person or team to ask about this dataset.",
        user_facing=True,
        inherited=True,
    )
    attribution: str | None = field(
        k.ATTRIBUTION,
        description="The statement anyone redistributing the data has to reproduce.",
        user_facing=True,
        inherited=True,
    )
    coverage_note: str | None = field(
        k.COVERAGE_NOTE, description="What a user would assume is here and is not."
    )
    upstream: Upstream | None = field(
        k.UPSTREAM,
        description="Present when upstream no longer serves this delivery.",
        user_facing=True,
    )

    # -- provenance --------------------------------------------------------
    origin: str = field(
        k.ORIGIN,
        k.DOWNLOADED,
        description="How the dataset came to exist.",
        schema={"enum": list(k.ORIGINS)},
    )
    derivation: str | None = field(
        k.DERIVATION, description="The method, parameters and inputs of derived data."
    )
    provenance: str | None = field(
        k.PROVENANCE,
        description="How this copy was obtained or restored, where sources and retrieval do not say it.",
    )
    verified: str | None = field(
        k.VERIFIED,
        description="The date this copy was last checked against its source, quoted.",
    )
    input_datasets: list[str] | None = field(
        k.INPUT_DATASETS,
        description="The catalogue names of the datasets derived data was computed from.",
    )
    tiling: dict | None = field(
        k.TILING, description="The tiling scheme of a dataset split into tiles."
    )
    additional_variables: dict | None = field(
        k.ADDITIONAL_VARIABLES,
        description="Variable name to description, for variables beyond the dataset's main ones.",
    )

    # -- where the bytes are -----------------------------------------------
    source_dir: str | None = field(
        k.SOURCE_DIR,
        description="Where a draft's files are; status.yaml keeps it once the dataset is in a catalogue.",
        published=False,
    )
    remote_prefix: str | None = field(
        k.REMOTE_PREFIX,
        description="Folder on the public store; defaults to the name.",
        promoted=True,
    )

    # -- classification ----------------------------------------------------
    access: str = field(
        k.ACCESS,
        k.PUBLIC,
        description="Who may read the bytes; picks the cache root.",
        promoted=True,
        user_facing=True,
        schema=_ACCESS_ENUM,
    )
    visibility: str = field(
        k.VISIBILITY,
        k.PUBLIC,
        description="Whether the dataset appears in the published catalogue.",
        promoted=True,
        schema=_VISIBILITY_ENUM,
    )
    embargo: Embargo | None = field(
        k.EMBARGO,
        description="Required when hidden: until when, why, and what it becomes.",
        published=False,
    )
    license_status: str | None = field(
        k.LICENSE_STATUS,
        description="Derived from licenses; set unresolved while nobody has read the terms.",
        promoted=True,
        schema={"enum": list(k.LICENSE_STATUSES)},
    )
    license_note: str | None = field(
        k.LICENSE_NOTE,
        description="Internal working note on the licence.",
        published=False,
    )
    restriction: str | None = field(
        k.RESTRICTION,
        description="Why restricted data is restricted and how somebody entitled to it gets a copy.",
        user_facing=True,
    )

    # -- inventory control -------------------------------------------------
    include: list[str] | None = field(
        k.INCLUDE, description="Only these files are the dataset."
    )
    exclude: list[str] | None = field(k.EXCLUDE, description="Applied after include.")
    shard_depth: int | None = field(
        k.SHARD_DEPTH,
        description="Split the inventory into shards at this directory depth.",
        ge=0,
    )


class NamespaceDescriptor(_Part):
    """The keys of a ``dataset.yaml`` naming a family of datasets rather than files."""

    name: str | None = field(
        k.NAME, description="The family's name; the directory decides it."
    )
    title: str | None = field(k.TITLE, description="A short human-readable title.")
    description: str | None = field(k.DESCRIPTION, description="What the family holds.")
    homepage: str | None = field(
        k.HOMEPAGE,
        description="Handed to members that do not set their own.",
        inherited=True,
    )
    contact: str | None = field(
        k.CONTACT,
        description="Handed to members that do not set their own.",
        inherited=True,
    )
    attribution: str | None = field(
        k.ATTRIBUTION,
        description="Handed to members that do not set their own.",
        inherited=True,
    )
    visibility: str = field(k.VISIBILITY, k.PUBLIC, schema=_VISIBILITY_ENUM)


# -- the rules the build enforces ---------------------------------------------------


def apply_defaults(meta: dict) -> dict:
    """Write the defaulted keys into ``meta``, as the generated descriptor carries them.

    Appended where absent, in the fixed key order the specification sets:
    access and visibility, then origin.
    """
    meta.setdefault(k.ACCESS, k.PUBLIC)
    meta.setdefault(k.VISIBILITY, k.PUBLIC)
    meta.setdefault(k.ORIGIN, k.DOWNLOADED)
    return meta


def check(meta: dict) -> None:
    """Raise :class:`~ethos_data.errors.DescriptorError` for the first rule ``meta`` breaks.

    ``meta`` is the parsed ``dataset.yaml`` of a dataset with files, with any
    inherited keys applied. It is not changed.
    """
    problem = (
        _classification(meta) or _provenance(meta) or _licenses(meta) or _patterns(meta)
    )
    if problem:
        raise DescriptorError(problem)


def check_namespace(meta: dict) -> None:
    """The same for a family's ``dataset.yaml``: it may not describe files or terms."""
    for forbidden in (k.SOURCE_DIR, k.SHARD_DEPTH, k.INCLUDE, k.EXCLUDE):
        if forbidden in meta:
            raise DescriptorError(
                "is a namespace -- it holds other datasets -- so it cannot also "
                f"describe files of its own, and {forbidden} says it does. Move that key "
                "into one of its members, or move the members out."
            )
    if k.ACCESS in meta:
        raise DescriptorError(
            "is a namespace and must not declare ethos:access. An access class says "
            "where bytes are read from, and a namespace has none -- its members each declare "
            "their own, which is the whole reason a family can be part public and part not."
        )
    if k.LICENSES in meta or meta.get(k.LICENSE_STATUS):
        raise DescriptorError(
            "is a namespace and must not carry licensing. Its members each state "
            "their own -- a licence inherited without being read is how a dataset ends up "
            "published under terms nobody applied to it."
        )


def _classification(meta: dict) -> str | None:
    """The access/visibility pair, both defaulting to public.

    Independent: a dataset can be listed publicly while its bytes stay closed,
    and hidden while colleagues use it daily. Public bytes may not be hidden.
    """
    access = meta.get(k.ACCESS, k.PUBLIC)
    visibility = meta.get(k.VISIBILITY, k.PUBLIC)
    if access not in k.ACCESS_CLASSES:
        return f"ethos:access must be one of {k.ACCESS_CLASSES}, got {access!r}"
    if visibility not in k.VISIBILITIES:
        return f"ethos:visibility must be one of {k.VISIBILITIES}, got {visibility!r}"
    if access == k.PUBLIC and visibility == k.HIDDEN:
        return (
            "access=public with visibility=hidden makes no sense -- "
            "if the bytes are downloadable by anyone, list the dataset."
        )
    if visibility == k.HIDDEN and k.EMBARGO not in meta:
        return (
            "visibility=hidden needs an ethos:embargo block saying when and why "
            "it becomes public, otherwise it stays hidden by accident forever. "
            'Use `until: "unspecified"` only with an explicit reason.'
        )
    if access == k.RESTRICTED and meta.get(k.REMOTE_PREFIX):
        return (
            "restricted data must not declare ethos:remote_prefix -- "
            "it is never uploaded. Each machine reads it from a restricted cache."
        )
    return None


def _provenance(meta: dict) -> str | None:
    """``ethos:origin`` and ``contributors``; an origin claiming authorship names an author."""
    origin = meta.get(k.ORIGIN, k.DOWNLOADED)
    if origin not in k.ORIGINS:
        return f"{k.ORIGIN} must be one of {k.ORIGINS}, got {origin!r}"

    contributors = meta.get(k.CONTRIBUTORS) or []
    if not isinstance(contributors, list):
        return f"{k.CONTRIBUTORS} must be a list of mappings."
    for index, person in enumerate(contributors):
        where = f"{k.CONTRIBUTORS}[{index}]"
        if not isinstance(person, dict):
            return f"{where} must be a mapping with at least a 'title'."
        if not person.get("title"):
            return f"{where} needs a 'title' -- the person or group's name."
        roles = person.get("roles", [])
        if isinstance(roles, str):
            # Data Package v1 spelled this as a scalar. Rejected rather than
            # coerced: half-following two versions of the spec is worse.
            return (
                f"{where}: 'roles' is a list in Data Package v2 -- write "
                f"roles: [{roles}], not roles: {roles}."
            )
        if not isinstance(roles, list):
            return f"{where}: 'roles' must be a list."
        for role in roles:
            if role not in k.CONTRIBUTOR_ROLES:
                return (
                    f"{where}: unknown role {role!r}. Use one of {k.CONTRIBUTOR_ROLES}."
                )

    if origin == k.DOWNLOADED:
        return None

    authors = [p for p in contributors if k.AUTHOR in (p.get("roles") or [])]
    if not authors:
        return (
            f"{k.ORIGIN} is {origin!r}, which claims this data was made here, "
            f"so it has to say by whom. Add a {k.CONTRIBUTORS} entry with "
            f"roles: [{k.AUTHOR}]:\n"
            f"    {k.CONTRIBUTORS}:\n"
            f"      - title: Some Person\n"
            f"        roles: [{k.AUTHOR}]\n"
            f"        organization: Forschungszentrum Julich, ICE-2"
        )
    if origin == k.DERIVED:
        if not meta.get(k.SOURCES):
            return (
                f"{k.ORIGIN}: derived needs 'sources' saying what it was "
                "derived FROM. Derived data inherits obligations from its inputs; a "
                "derivation with no named input cannot be checked against them."
            )
        if not meta.get(k.DERIVATION):
            return (
                f"{k.ORIGIN}: derived needs {k.DERIVATION} saying HOW -- the "
                "method, parameters and inputs, in enough detail that somebody could "
                "redo it. Without that, 'derived' says only that the numbers are not "
                "upstream's, which is the least useful half of the claim."
            )
    return None


def _licenses(meta: dict) -> str | None:
    """The ``licenses`` list, and the parts of a licence document that need no disk."""
    licenses = meta.get(k.LICENSES)
    if licenses is None:
        return None
    if not isinstance(licenses, list):
        return (
            f"{k.LICENSES} must be a list, even with one entry -- "
            "a dataset can be under several."
        )
    for index, entry in enumerate(licenses):
        where = f"{k.LICENSES}[{index}]"
        if not isinstance(entry, dict):
            return f"{where} must be a mapping with 'name' and/or 'path'."
        if not (entry.get("name") or entry.get("path")):
            return (
                f"{where} has neither 'name' nor 'path'. Give an Open Definition id "
                "(name: CC-BY-4.0) or a URL to the terms (path: https://...); a bare "
                "title names no licence. If the terms are not settled, drop the entry "
                "and set ethos:license_status: unresolved instead."
            )
        patterns = entry.get(k.APPLIES_TO)
        if patterns is not None and (
            not isinstance(patterns, list)
            or not all(isinstance(p, str) and p for p in patterns)
        ):
            return f"{where}: {k.APPLIES_TO} must be a list of glob patterns."
        problem = _document(where, entry)
        if problem:
            return problem
    return None


def _document(where: str, entry: dict) -> str | None:
    document = entry.get(k.DOCUMENT)
    if document is None:
        if k.DOCUMENT_SHA256 in entry:
            return (
                f"{where} has {k.DOCUMENT_SHA256} but no {k.DOCUMENT} to hash. "
                "Archive the terms beside dataset.yaml and name the file, or drop "
                "the hash."
            )
        return None
    # The one rule for a path inside a dataset, checked as spelled: ``./terms.txt``
    # or ``licenses//terms.txt`` would read one way here and another in a bundle.
    try:
        relative(document, k.DOCUMENT)
    except ValueError:
        return (
            f"{where}: {k.DOCUMENT} must be a relative path inside the dataset "
            f"directory, such as licenses/terms.txt; got {document!r}."
        )
    pinned = entry.get(k.DOCUMENT_SHA256)
    if pinned is not None and not isinstance(pinned, str):
        return (
            f"{where}: {k.DOCUMENT_SHA256} must be a hex digest in quotes; YAML "
            f"read {pinned!r} as a number, which loses leading zeros. Quote it, "
            f"or delete it and let the build record the digest."
        )
    return None


def _patterns(meta: dict) -> str | None:
    """``ethos:include`` / ``ethos:exclude`` / ``ethos:shard_depth`` shapes."""
    for key in (k.INCLUDE, k.EXCLUDE):
        raw = meta.get(key)
        if raw is None:
            continue
        if isinstance(raw, str) or not isinstance(raw, list):
            return f"{key} must be a list of patterns, got {type(raw).__name__}"
        if not raw:
            return (
                f"{key} is an empty list, which would select nothing. "
                f"Remove the key instead -- absent means 'no filter'."
            )
        if not all(isinstance(entry, str) for entry in raw):
            return f"every entry in {key} must be a string"
    depth = meta.get(k.SHARD_DEPTH)
    if depth is not None:
        try:
            if int(depth) < 0:
                return "ethos:shard_depth must not be negative"
        except (TypeError, ValueError):
            return f"ethos:shard_depth must be a whole number, got {depth!r}"
    return None


# -- what the structure adds -------------------------------------------------------


def lint(meta: dict, *, namespace: bool = False) -> list[str]:
    """Warnings about ``meta`` that :func:`check` does not raise.

    A value whose type the format does not allow, an ``ethos:`` key the format
    does not define, a value outside ``ethos:license_status`` or the upstream
    statuses, and a ``version`` YAML read as a number. Each is one line naming
    the key.
    """
    model = NamespaceDescriptor if namespace else DatasetDescriptor
    warnings: list[str] = []
    try:
        model.model_validate(meta)
    except ValidationError as error:
        warnings.extend(describe(error))
    known = set(keys(model))
    for key in meta:
        if key.startswith("ethos:") and key not in known and not namespace:
            warnings.append(f"{key} is not a key of the dataset.yaml format; a typo?")
    status = meta.get(k.LICENSE_STATUS)
    if status is not None and status not in k.LICENSE_STATUSES:
        warnings.append(
            f"{k.LICENSE_STATUS} is one of {k.LICENSE_STATUSES}, got {status!r}"
        )
    version = meta.get(k.VERSION)
    if version is not None and not isinstance(version, str):
        warnings.append(
            f"{k.VERSION} {version!r} is a number to YAML; quote the publisher's "
            f'release string verbatim, version: "{version}"'
        )
    upstream = meta.get(k.UPSTREAM)
    if isinstance(upstream, dict) and upstream.get("status") not in k.UPSTREAM_STATUSES:
        warnings.append(
            f"{k.UPSTREAM}.status is one of {k.UPSTREAM_STATUSES}, "
            f"got {upstream.get('status')!r}"
        )
    return warnings


#: Never published: stripped by ``publish``, looked for by its leak check.
STRIPPED = keys_with(DatasetDescriptor, "published", False)
#: Copied into the index row by the build.
PROMOTED = keys_with(DatasetDescriptor, "promoted")
#: Printed by ``--meta``, the dataset's full description.
USER_FACING = keys_with(DatasetDescriptor, "user_facing")
#: Taken from the enclosing family when a member does not set them.
INHERITED = keys_with(DatasetDescriptor, "inherited")


def described(meta: dict[str, Any]) -> dict[str, Any]:
    """The user-facing part of a descriptor, in the format's order, where present."""
    return {
        key: meta[key] for key in USER_FACING if meta.get(key) not in (None, [], "")
    }
