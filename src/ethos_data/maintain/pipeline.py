"""Catalogue maintenance as pipelines: every stage plans before any of them acts.

    pipeline = Pipeline("add", [Intake(), Place(), Build()])
    pipeline.run(context)                 # plan every stage, then carry them out
    pipeline.run(context, dry_run=True)   # the plans alone

A stage looks at the catalogue and returns its plan: the actions it would
take, each a line to show and the work to do. Planning may read anything --
hash files, ask the store -- and writes nothing, so a dry run is the plan, and
a refusal, a dataset in the wrong state or a draft the build would reject,
comes before anything is touched. The one thing planning may keep is a
cache of what it read, outside a dry run: the build saves each dataset's
hashes as it computes them, so a refusal does not cost that work again. The
pipeline asks every stage for its plan first and only then carries the plans
out, in order, checking each action's result as it goes.

A stage records what it did in the datasets' status files, and plans nothing
for work that is done already, so a pipeline run again after an interruption
does only what is left.

An action that belongs to one dataset of a batch names it as its subject.
When such an action fails, the dataset's later actions are skipped and the
other datasets go on: a batch is not a transaction, and what is done stays
done. The run's result names each dataset that failed, and why.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from .. import report
from ..errors import EthosDataError, MaintenanceError

__all__ = ["Action", "Pipeline", "Run", "Stage"]

Context = TypeVar("Context")


@dataclass(frozen=True)
class Action:
    """One thing a stage will do: the line that says so, and how to do it."""

    text: str
    perform: Callable[[], None]
    #: Checks the result once performed: what is wrong, or "".
    check: Callable[[], str] | None = None
    #: The dataset of a batch the action belongs to; None for an action whose
    #: failure stops the pipeline.
    subject: str | None = None


class Stage(Protocol[Context]):
    """A step of a pipeline: a name, and the actions it plans for a context.

    ``plan`` raises :class:`~ethos_data.errors.MaintenanceError` when the stage
    cannot go ahead, and may set what later stages need on the context.
    """

    name: str

    def plan(self, context: Context) -> list[Action]: ...


@dataclass
class Run:
    """What a pipeline run planned, and the datasets whose actions failed."""

    planned: int
    #: Why each subject failed, by subject.
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed


@dataclass(frozen=True)
class Pipeline(Generic[Context]):
    """Stages planned together and carried out in order."""

    name: str
    stages: Sequence[Stage[Context]]

    def plan(self, context: Context) -> list[tuple[str, list[Action]]]:
        """Every stage's plan, in order; nothing is written."""
        return [(stage.name, stage.plan(context)) for stage in self.stages]

    def run(self, context: Context, *, dry_run: bool = False) -> Run:
        """Plan every stage, report the plan and, unless ``dry_run``, carry it out.

        Raises :class:`~ethos_data.errors.MaintenanceError` when a stage
        refuses, or when an action without a subject fails or its check finds
        its result wrong; the actions before it stay done, and the status
        files say how far the pipeline got. An action with a subject that
        fails is reported, and the result names its subject.
        """
        planned = self.plan(context)
        actions = sum(len(stage_actions) for _, stage_actions in planned)
        for stage, stage_actions in planned:
            for action in stage_actions:
                report.info(f"  {stage:<12} {action.text}")
        if dry_run:
            report.info(
                f"\n{actions} action(s) planned. Nothing was written."
                if actions
                else "\nnothing to do."
            )
            return Run(actions)
        failed: dict[str, str] = {}
        for stage, stage_actions in planned:
            for action in stage_actions:
                if action.subject in failed:
                    continue
                try:
                    action.perform()
                    problem = action.check() if action.check is not None else ""
                except EthosDataError as error:
                    if action.subject is None:
                        raise
                    problem = error.message
                if not problem:
                    continue
                if action.subject is None:
                    raise MaintenanceError(f"{self.name}, {stage}: {problem}")
                failed[action.subject] = problem
                report.warning(f"{self.name}, {stage}, {action.subject}: {problem}")
        if not actions:
            report.info("\nnothing to do.")
        return Run(actions, failed)
