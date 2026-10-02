"""The four layers: each module imports only from its own layer and the ones below.

Tests for the decision "Four layers". From the bottom: the model
(``formats``, ``model``), the adapters (``adapters``), the services, and the
presentation (``cli``, ``maintain.cli`` and the package facade). The typed
errors and the reporter are what every layer speaks, so any layer imports
them. An import inside a function counts as much as one at the top.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "ethos_data"

MODEL, ADAPTERS, SERVICES, PRESENTATION = range(4)
NAMES = ("model", "adapters", "services", "presentation")

#: Modules every layer may import.
SHARED = {"ethos_data.errors", "ethos_data.report"}

#: Imports that go up, each with its reason. Keep this list short.
EXCEPTIONS = {
    # The handle's own command: `Collections.main()` runs the package command
    # bound to the handle, so a script can offer it without a console script.
    ("ethos_data.selection", "ethos_data.cli"),
}


def layer(module: str) -> int | None:
    if module in SHARED:
        return None
    if module.startswith(("ethos_data.formats", "ethos_data.model")):
        return MODEL
    if module.startswith("ethos_data.adapters"):
        return ADAPTERS
    if module in ("ethos_data", "ethos_data.cli", "ethos_data.maintain.cli"):
        return PRESENTATION
    return SERVICES


def module_of(path: Path) -> str:
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def is_module(name: str) -> bool:
    relative = Path(*name.split(".")[1:])
    return (PACKAGE / relative).with_suffix(".py").is_file() or (
        PACKAGE / relative / "__init__.py"
    ).is_file()


def imported(path: Path) -> set[str]:
    """Every ``ethos_data`` module ``path`` imports, as a module name."""
    module = module_of(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                target = ".".join([*base, *([node.module] if node.module else [])])
            else:
                target = node.module or ""
            # `from . import keys` imports a module; `from .x import name` a name.
            names = [f"{target}.{alias.name}" for alias in node.names]
            names = [name if is_module(name) else target for name in names]
        else:
            continue
        found.update(name for name in names if name.split(".")[0] == "ethos_data")
    found.discard(module)
    return found


MODULES = sorted(
    path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts
)


@pytest.mark.parametrize("path", MODULES, ids=lambda p: module_of(p))
def test_a_module_imports_nothing_above_its_layer(path):
    module = module_of(path)
    own = layer(module)
    if own is None:
        assert imported(path) <= {"ethos_data"} | SHARED, module
        return
    upward = sorted(
        target
        for target in imported(path)
        if (layer(target) or MODEL) > own and (module, target) not in EXCEPTIONS
    )
    assert not upward, f"{module} ({NAMES[own]}) imports " + ", ".join(
        f"{t} ({NAMES[layer(t)]})" for t in upward
    )


def test_every_exception_is_still_needed():
    for module, target in EXCEPTIONS:
        path = PACKAGE / Path(*module.split(".")[1:]).with_suffix(".py")
        assert target in imported(path), f"{module} no longer imports {target}"
