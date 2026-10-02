"""Where a long-running command's progress and warnings go.

Library code does not print. It says what it is doing through :func:`info` and
what deserves a look through :func:`warning`, and the reporter of the command
being run decides where that goes: the command line prints it, a test records
it, a script that wants quiet passes :class:`NullReporter`. The entry points of
the maintainer commands take a ``reporter=`` and install it for their duration
with :func:`reporting`, the way :mod:`logging` routes records to handlers, so
the helpers they call need no extra argument.

Refusals are not reported: they are raised, as the typed errors of
:mod:`ethos_data.errors`.
"""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

__all__ = [
    "ConsoleReporter",
    "NullReporter",
    "RecordingReporter",
    "Reporter",
    "current",
    "info",
    "reported",
    "reporting",
    "warning",
]


class Reporter:
    """Receives a command's progress and warnings; subclasses decide where they go."""

    def info(self, message: str = "") -> None:
        """Progress and results, for the person running the command."""

    def warning(self, message: str) -> None:
        """Something to look at that does not stop the command."""


class ConsoleReporter(Reporter):
    """Progress to standard output, warnings to standard error.

    The streams are looked up when a message is written, not when the reporter
    is made, so output that a caller redirects meanwhile goes where they sent it.
    """

    def info(self, message: str = "") -> None:
        print(message, file=sys.stdout)

    def warning(self, message: str) -> None:
        print(message, file=sys.stderr)


class NullReporter(Reporter):
    """Drops everything: for a caller that only wants the return value."""


@dataclass
class RecordingReporter(Reporter):
    """Keeps every message, for a test or a caller that shows them its own way."""

    infos: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def info(self, message: str = "") -> None:
        self.infos.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


_CONSOLE = ConsoleReporter()
_current: ContextVar[Reporter | None] = ContextVar("reporter", default=None)


def current() -> Reporter:
    """The reporter of the command being run; the console one outside any."""
    return _current.get() or _CONSOLE


@contextmanager
def reporting(reporter: Reporter | None) -> Iterator[Reporter]:
    """Send everything reported inside the block to ``reporter``.

    ``None`` keeps the reporter already in effect, so an entry point called
    from another passes its caller's choice on.
    """
    if reporter is None:
        yield current()
        return
    token = _current.set(reporter)
    try:
        yield reporter
    finally:
        _current.reset(token)


def reported(function: Callable) -> Callable:
    """Give an entry point a ``reporter=`` keyword, in effect while it runs.

    Without one, the call reports to the reporter already in effect: the
    console, unless a caller has installed another.
    """

    @functools.wraps(function)
    def wrapper(*args, reporter: Reporter | None = None, **kwargs):
        with reporting(reporter):
            return function(*args, **kwargs)

    return wrapper


def info(message: str = "") -> None:
    """Report progress to the reporter in effect."""
    current().info(message)


def warning(message: str) -> None:
    """Report a warning to the reporter in effect."""
    current().warning(message)
