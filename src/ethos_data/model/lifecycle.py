"""A dataset's lifecycle in a source catalogue: its states and the steps between them.

    draft --build--> built --upload, link, materialize--> available --record--> frozen

and from any of those four, ``remove`` to withdrawn and then ``purge`` to
purged. Rules only: a command reads the dataset's ``status.yaml``, asks
:func:`step` whether the step it is about to take is allowed and which state
it leads to, acts, and records the step. Nothing here reads a file or prints.

Some steps keep the state: a rebuild of a built dataset, a second link, a
check of an upload already recorded. They are steps all the same, so a command
cannot take one in a state that does not allow it: a draft has no inventory to
upload, and a frozen dataset has no build input left to upload from.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from ..errors import TransitionError
from ..formats import keys as k

__all__ = [
    "AVAILABLE",
    "BUILT",
    "DRAFT",
    "FROZEN",
    "MEANING",
    "PURGED",
    "STATES",
    "STEPS",
    "WITHDRAWN",
    "Step",
    "freezable",
    "next_step",
    "step",
]

DRAFT = k.STATE_DRAFT
BUILT = k.STATE_BUILT
AVAILABLE = k.STATE_AVAILABLE
FROZEN = k.STATE_FROZEN
WITHDRAWN = k.STATE_WITHDRAWN
PURGED = k.STATE_PURGED
STATES = k.STATES

#: What each state says about the dataset.
MEANING: Mapping[str, str] = {
    DRAFT: "described, not built",
    BUILT: "inventory built from its source_dir",
    AVAILABLE: "bytes reachable for its access class",
    FROZEN: "inventory final, authoritative copy recorded",
    WITHDRAWN: "out of the catalogue, bytes not yet deleted",
    PURGED: "bytes deleted",
}


@dataclass(frozen=True)
class Step:
    """One kind of step: the command that takes it, and where it leads from each state it allows."""

    name: str
    command: str
    leads: Mapping[str, str]

    def allows(self, state: str) -> bool:
        return state in self.leads


_IN_CATALOGUE = (DRAFT, BUILT, AVAILABLE, FROZEN)

STEPS: Mapping[str, Step] = {
    each.name: each
    for each in (
        Step("build", "ethos-data catalog build",
             {DRAFT: BUILT, BUILT: BUILT, AVAILABLE: AVAILABLE, FROZEN: FROZEN}),
        # A rebuild that found other bytes than the ones made available: what
        # was checked is no longer what the inventory describes.
        Step("change", "ethos-data catalog build", {BUILT: BUILT, AVAILABLE: BUILT}),
        Step("upload", "ethos-data catalog upload", {BUILT: AVAILABLE, AVAILABLE: AVAILABLE}),
        Step("verify", "ethos-data catalog upload --verify-only",
             {BUILT: AVAILABLE, AVAILABLE: AVAILABLE, FROZEN: FROZEN}),
        Step("link", "ethos-data link", {BUILT: AVAILABLE, AVAILABLE: AVAILABLE, FROZEN: FROZEN}),
        Step("materialize", "ethos-data materialize",
             {BUILT: AVAILABLE, AVAILABLE: AVAILABLE, FROZEN: FROZEN}),
        Step("record", "ethos-data catalog record", {AVAILABLE: FROZEN, FROZEN: FROZEN}),
        # A new revision: new bytes, built and not yet published.
        Step("revise", "ethos-data catalog build --revision", {AVAILABLE: BUILT, FROZEN: BUILT}),
        Step("check-source", "ethos-data catalog check-source",
             {BUILT: BUILT, AVAILABLE: AVAILABLE, FROZEN: FROZEN}),
        Step("remove", "ethos-data catalog remove", dict.fromkeys(_IN_CATALOGUE, WITHDRAWN)),
        Step("purge", "ethos-data catalog remove --purge", {WITHDRAWN: PURGED}),
        # A release holds every step before it, whatever state they left.
        Step("release", "ethos-data catalog release", {state: state for state in STATES}),
    )
}  # fmt: skip


def step(name: str, state: str, dataset: str = "the dataset") -> str:
    """The state step ``name`` leads to from ``state``.

    Raises :class:`~ethos_data.errors.TransitionError` when the state does not
    allow it, saying what the dataset needs first.
    """
    kind = STEPS[name]
    if state not in STATES:
        raise TransitionError(
            f"{dataset}: status.yaml says state {state!r}, which is not one of "
            f"{', '.join(STATES)}."
        )
    if kind.allows(state):
        return kind.leads[state]
    allowed = " or ".join(each for each in STATES if kind.allows(each))
    message = (
        f"{dataset} is {state} ({MEANING[state]}), and `{kind.command}` "
        f"needs it {allowed}."
    )
    first = _first(name, state, dataset)
    raise TransitionError(f"{message}\n{first}" if first else message)


def _first(name: str, state: str, dataset: str) -> str:
    """What to do before step ``name`` can be taken from ``state``."""
    if state == DRAFT:
        return f"Build it first:\n    ethos-data catalog build {dataset}"
    if state == BUILT and name == "record":
        return (
            "Make its bytes available first: upload it, or link or materialize it "
            "with --catalog-root, which records the copy."
        )
    if state == FROZEN and name == "upload":
        return (
            "Its inventory is final and no source_dir is left to upload from. To "
            f"recheck the copy on dCache:\n    ethos-data catalog upload {dataset} --verify-only"
        )
    if state in (WITHDRAWN, PURGED):
        return "It was removed from the catalogue."
    return ""


def freezable(access: str, kinds: Collection[str]) -> bool:
    """Whether one of the recorded copies can be a dataset's authoritative one.

    An upload, a copy the cache owns, or for restricted data the authorised
    installation registered in the restricted cache. A link to public or
    internal data borrows the build input, which a rebuild still reads.
    """
    return (
        k.COPY_UPLOADED in kinds
        or k.COPY_MATERIALIZED in kinds
        or (access == k.RESTRICTED and k.COPY_LINKED in kinds)
    )


def next_step(
    dataset: str,
    state: str | None,
    *,
    access: str = k.PUBLIC,
    kinds: Collection[str] = (),
    authority: str | None = None,
    licensed: bool = True,
    checkout: str = ".",
) -> str:
    """What the dataset needs next, as ``catalog status`` prints it; empty for nothing.

    ``state`` is None for a dataset without a status file; ``kinds`` are the
    kinds of its recorded copies; ``checkout`` is the catalogue root to name in
    a command that takes ``--catalog-root``.
    """
    if state is None:
        return f"ethos-data catalog migrate {dataset}"
    if state == DRAFT:
        return f"ethos-data catalog build {dataset}"
    if state == BUILT:
        if not licensed:
            return "settle its licensing in dataset.yaml, then rebuild"
        if access == k.RESTRICTED:
            return f"register its installation: ethos-data link {dataset} DIR --catalog-root {checkout}"
        if access == k.INTERNAL:
            return f"link it into the shared cache: ethos-data link {dataset} --catalog-root {checkout}"
        return f"ethos-data catalog upload {dataset}"
    if state == AVAILABLE:
        if freezable(access, kinds):
            return f"ethos-data catalog record {dataset}"
        return "none while its source_dir stays; materialize it before that goes"
    if state == FROZEN:
        if authority:
            return ""
        return f"record its authoritative copy: ethos-data catalog record {dataset}"
    if state == WITHDRAWN:
        return (
            f"ethos-data catalog remove {dataset} --purge, after a release without it"
        )
    return ""
