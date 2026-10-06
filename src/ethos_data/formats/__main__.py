"""Rewrite the committed JSON Schemas: ``python -m ethos_data.formats``."""

from __future__ import annotations

from .registry import write_schemas

if __name__ == "__main__":
    for path in write_schemas():
        print(path)
