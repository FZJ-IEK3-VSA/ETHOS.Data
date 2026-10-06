"""The format reference, rendered from the specifications when the docs are built.

Tests for "Every file format is specified once": the key tables in File
formats come from the models, every key in them is described, and every
generated block a page asks for exists.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from ethos_data import formats
from ethos_data.formats import reference
from ethos_data.formats.status_file import Event
from ethos_data.model import lifecycle

DOCS = Path(__file__).resolve().parents[1] / "docs"


def rows(text: str) -> list[list[str]]:
    """The cells of a rendered table, header and rule left out."""
    return [
        [cell.strip() for cell in line.strip("|").split(" | ")]
        for line in text.splitlines()[2:]
    ]


def load_hook():
    spec = importlib.util.spec_from_file_location(
        "formats_hook", DOCS / "hooks" / "formats.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTables:
    @pytest.mark.parametrize("name", list(formats.FORMATS))
    def test_every_key_of_a_format_has_a_described_row(self, name):
        table = rows(reference.table(name))
        keys = {cells[0].strip("`") for cells in table}
        for key in formats.schema(name).get("properties", {}):
            assert key in keys, f"{name}: {key} has no row"
        for cells in table:
            assert cells[3], f"{name}: {cells[0]} has no description"

    def test_the_properties_of_a_key_are_named(self):
        table = {cells[0]: cells for cells in rows(reference.table("dataset"))}

        assert table["`source_dir`"][3].endswith("*Never published.*")
        assert "Inherited from the family." in table["`ethos:contact`"][3]
        assert "In the index row." in table["`ethos:access`"][3]
        assert table["`ethos:access`"][2] == "`public`"
        assert table["`contributors[].title`"][2] == "required"

    def test_nested_keys_are_spelled_as_a_reader_writes_them(self):
        keys = {cells[0] for cells in rows(reference.table("collections"))}

        assert "`collections.<name>.include[].dataset`" in keys
        assert "`catalog.min_version`" in keys

    def test_a_part_met_twice_points_at_the_first(self):
        table = {cells[0]: cells for cells in rows(reference.table("status"))}

        assert table["`history[].copy`"][1] == "mapping, as `copies[]`"
        assert "`history[].copy.kind`" not in table

    def test_a_file_that_is_one_mapping_starts_with_the_name(self):
        keys = [cells[0] for cells in rows(reference.table("staging"))]

        assert keys[0] == "`<name>.target`"

    def test_a_model_of_a_format_by_its_path(self):
        assert "`ethos:license_status`" in reference.table("package:IndexRow")
        with pytest.raises(ValueError, match="no model Nothing"):
            reference.table("package:Nothing")
        with pytest.raises(ValueError, match="unknown format"):
            reference.table("nothing")

    def test_a_cell_cannot_end_early_or_turn_into_html(self):
        assert reference._cell("a | b at <url>, `<name>`") == (
            "a \\| b at &lt;url&gt;, `<name>`"
        )


class TestLifecycle:
    def test_every_state_and_every_step_has_a_row(self):
        states = {cells[0] for cells in rows(reference.states())}
        steps = {cells[0] for cells in rows(reference.steps())}

        assert states == {f"`{state}`" for state in lifecycle.STATES}
        assert steps == {f"`{name}`" for name in lifecycle.STEPS}

    def test_a_state_says_which_steps_lead_into_it(self):
        table = {cells[0]: cells for cells in rows(reference.states())}

        assert table["`available`"][2] == (
            "`upload`, `verify`, `link` or `materialize` from `built`"
        )

    def test_the_history_names_every_step(self):
        described = Event.model_fields["step"].description
        for name in ("add", "migrate", *lifecycle.STEPS):
            assert name in described, f"history[].step does not name {name}"


class TestPages:
    def test_every_block_a_page_asks_for_renders(self):
        hook = load_hook()
        asked = []
        for page in sorted(DOCS.rglob("*.md")):
            text = page.read_text(encoding="utf-8")
            asked += [match[0] for match in hook.MARKER.finditer(text)]
            expanded = hook.expand(text, str(page))
            assert "<!-- ethos-data:" not in expanded, page

        assert "<!-- ethos-data: table dataset -->" in asked
        assert "<!-- ethos-data: table settings -->" in asked
        assert "<!-- ethos-data: steps -->" in asked

    def test_an_unknown_block_stops_the_build(self):
        with pytest.raises(ValueError, match="unknown block"):
            reference.render("tables", "dataset")
        with pytest.raises(ValueError, match="needs a format"):
            reference.render("table")
