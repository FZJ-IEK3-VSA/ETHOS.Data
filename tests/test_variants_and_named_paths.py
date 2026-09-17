"""Collection variants (``test:`` / ``full:``), named ``paths:``, and IncompleteCatalog.

The case these exist for: a workflow takes ``era5_path`` and ``gwa_100m_path``;
the maintainer who wrote ``collections.yaml`` knows which catalogue keys those
are, and nobody else should have to. ``paths:`` records it once, and
``ethos_data.paths()`` hands the caller ``{handle: local path}``. The same
workflow must run in seconds on fixtures and for real on the full inputs, so a
collection may be written twice -- and the two versions must offer the same
handles, or code that passed on the fixtures fails on the machine that has the
real data.

Every test here resolves against a synthetic catalogue whose files are already
in the cache, so nothing is downloaded and nothing reaches the network.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import textwrap
import urllib.error
import urllib.request
import warnings
from pathlib import Path

import pytest

import ethos_data
from ethos_data import config, retrieval, selection, tool_main
from ethos_data.cli import main


def _write(path: Path, text: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    data = path.read_bytes()
    return {"bytes": len(data), "hash": "sha256:" + hashlib.sha256(data).hexdigest()}


def _no_network(*args, **kwargs):
    """Stands in for ``urllib.request.urlopen`` where a test must stay offline.

    Nothing here configures a catalogue, so the only way a command could reach
    the network is by falling back to the public one instead of the pin.
    """
    pytest.fail(
        "the public catalogue was contacted; the pinned one should have been read"
    )


#: What the synthetic catalogue holds. The fixture family mirrors the real
#: ``reskit-test-data``; ``era5`` and ``global-wind-atlas-v3`` stand in for the
#: full inputs; ``landcover`` is a plain dataset both variants can share.
LAYOUT = {
    "reskit-test-data/era5": {
        "100m_u_component_of_wind.nc": "u",
        "100m_v_component_of_wind.nc": "v",
        "forecast_surface_roughness.nc": "fsr",
    },
    "reskit-test-data/global-wind-atlas": {
        "gwa100-like.tif": "gwa100",
        "gwa50-like.tif": "gwa50",
        "gwa200-like.tif": "gwa200",
    },
    "era5": {"2015/u.nc": "u2015", "2015/v.nc": "v2015", "2016/u.nc": "u2016"},
    "global-wind-atlas-v3": {
        "gwa3_250_wind-speed_100m.tif": "gwa3-100",
        "gwa3_250_wind-speed_50m.tif": "gwa3-50",
        "gwa3_250_wind-speed_200m.tif": "gwa3-200",
    },
    "landcover": {"clc.tif": "clc", "sites.shp": "shp", "sites.dbf": "dbf"},
}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A catalogue whose every file is already in the cache, so nothing downloads.

    The developer's own configuration must never leak in: a user-level
    ``catalog`` override would replace every pin these tests write.
    """
    monkeypatch.setattr(config, "load_config", lambda: ({}, {}))
    for variable in (
        "ETHOS_DATA_CATALOG",
        "ETHOS_STAGING_DIR",
        "ETHOS_RESTRICTED_DIR",
        "ETHOS_SKIP_UNAVAILABLE",
        "ETHOS_PUBLICATION_URL",
    ):
        monkeypatch.delenv(variable, raising=False)
    cache = tmp_path / "cache"
    monkeypatch.setenv("ETHOS_DATA_DIR", str(cache))

    catalogue = tmp_path / "catalogue"
    entries = [{"name": "reskit-test-data", "ethos:namespace": True}]
    for name, files in LAYOUT.items():
        resources = []
        for relative, text in files.items():
            resource = {
                "name": relative,
                "path": relative,
                **_write(cache / name / relative, text),
            }
            if relative == "sites.shp":
                resource["ethos:sidecars"] = ["sites.dbf"]
            resources.append(resource)
        package = catalogue / "datasets" / name / "datapackage.json"
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_text(json.dumps({"name": name, "resources": resources}))
        entries.append(
            {
                "name": name,
                "path": f"datasets/{name}/datapackage.json",
                "ethos:license_status": "resolved",
            }
        )
    # Licensed data with no restricted cache on this machine: the one way a
    # catalogued file can be unavailable without anything being broken.
    entries.append(
        {
            "name": "licensed",
            "path": "datasets/licensed/datapackage.json",
            "ethos:access": "restricted",
            "ethos:license_status": "resolved",
        }
    )
    licensed = catalogue / "datasets" / "licensed" / "datapackage.json"
    licensed.parent.mkdir(parents=True)
    licensed.write_text(
        json.dumps(
            {
                "name": "licensed",
                "resources": [
                    {
                        "name": "secret.tif",
                        "path": "secret.tif",
                        "bytes": 3,
                        "hash": "sha256:00",
                    }
                ],
            }
        )
    )
    index = catalogue / "datacatalog.json"
    index.write_text(
        json.dumps(
            {
                "name": "test",
                "ethos:publication_url": "https://example.invalid",
                "datasets": entries,
            }
        )
    )
    return tmp_path, cache, index


@pytest.fixture
def define(world):
    """Write a collections file pinned to the synthetic catalogue; returns its path."""
    tmp_path, _, index = world

    def write(
        *bodies: str, catalog: Path = index, name: str = "collections.yaml"
    ) -> Path:
        # Each body is dedented on its own, so a module-level constant can be
        # combined with a literal written at a test method's indentation.
        collections = "".join(
            textwrap.dedent(body).strip("\n") + "\n" for body in bodies
        )
        path = tmp_path / name
        path.write_text(
            f"catalog: {catalog.as_posix()}\ncollections:\n"
            + textwrap.indent(collections, "  "),
            encoding="utf-8",
        )
        return path

    return write


@pytest.fixture
def download_spy(monkeypatch):
    """Records every resource handed to ``download``; the real function still runs."""
    asked: list[list[str]] = []
    real = retrieval.download

    def spy(catalog, resources, **kwargs):
        asked.append([r.key for r in resources])
        return real(catalog, resources, **kwargs)

    monkeypatch.setattr(retrieval, "download", spy)
    return asked


#: The shape the documentation shows: fixtures under test, real inputs under
#: full, the same four handles in both -- plus one inherited from a plain parent.
ONSHORE = """
landcover:
  title: Land cover
  include:
    - dataset: landcover
      files: ["clc.tif"]
  paths:
    clc: landcover/clc.tif
onshore_wind:
  title: Data for onshore wind workflows
  test:
    extends: [landcover]
    include:
      - dataset: reskit-test-data/era5
        files: ["100m_*_component_of_wind.nc"]
      - dataset: reskit-test-data/global-wind-atlas
        files: ["gwa*-like.tif"]
    paths:
      era5: reskit-test-data/era5
      gwa_100m: reskit-test-data/global-wind-atlas/gwa100-like.tif
      gwa_50m: reskit-test-data/global-wind-atlas/gwa50-like.tif
      gwa_200m: reskit-test-data/global-wind-atlas/gwa200-like.tif
  full:
    extends: [landcover]
    include:
      - dataset: era5
      - dataset: global-wind-atlas-v3
        files: ["gwa3_250_wind-speed_*.tif"]
    paths:
      era5: era5
      gwa_100m: global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif
      gwa_50m: global-wind-atlas-v3/gwa3_250_wind-speed_50m.tif
      gwa_200m: global-wind-atlas-v3/gwa3_250_wind-speed_200m.tif
"""

TEST_KEYS = [
    "landcover/clc.tif",
    "reskit-test-data/era5/100m_u_component_of_wind.nc",
    "reskit-test-data/era5/100m_v_component_of_wind.nc",
    "reskit-test-data/global-wind-atlas/gwa100-like.tif",
    "reskit-test-data/global-wind-atlas/gwa200-like.tif",
    "reskit-test-data/global-wind-atlas/gwa50-like.tif",
]
FULL_KEYS = [
    "era5/2015/u.nc",
    "era5/2015/v.nc",
    "era5/2016/u.nc",
    "global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif",
    "global-wind-atlas-v3/gwa3_250_wind-speed_200m.tif",
    "global-wind-atlas-v3/gwa3_250_wind-speed_50m.tif",
    "landcover/clc.tif",
]

#: Variants that do not offer the same handles: the mistake check_variants exists for.
LOPSIDED = """
lopsided:
  test:
    include:
      - dataset: reskit-test-data/global-wind-atlas
    paths:
      gwa_100m: reskit-test-data/global-wind-atlas/gwa100-like.tif
      gwa_50m: reskit-test-data/global-wind-atlas/gwa50-like.tif
  full:
    include:
      - dataset: global-wind-atlas-v3
    paths:
      gwa_100m: global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif
      gwa_200m: global-wind-atlas-v3/gwa3_250_wind-speed_200m.tif
"""


class TestVariants:
    def test_the_test_flag_selects_the_test_variant_and_full_is_the_default(
        self, define
    ):
        """Full is the default: a forgotten flag must download visibly, never
        run a real calculation on fixtures in silence."""
        file = define(ONSHORE)
        assert (
            sorted(ethos_data.fetch("onshore_wind", file, progressbar=False, test=True))
            == TEST_KEYS
        )
        assert (
            sorted(ethos_data.fetch("onshore_wind", file, progressbar=False))
            == FULL_KEYS
        )
        assert (
            sorted(
                ethos_data.fetch("onshore_wind", file, progressbar=False, test=False)
            )
            == FULL_KEYS
        )

    def test_a_plain_collection_is_the_same_either_way(self, define):
        """A test suite's fixtures *are* its test data; there is nothing to switch to."""
        file = define(ONSHORE)
        with_flag = ethos_data.fetch("landcover", file, progressbar=False, test=True)
        without = ethos_data.fetch("landcover", file, progressbar=False)
        assert (
            dict(with_flag)
            == dict(without)
            == {"landcover/clc.tif": with_flag["landcover/clc.tif"]}
        )
        assert (
            with_flag.named == without.named == {"clc": with_flag["landcover/clc.tif"]}
        )

    def test_resolve_lists_a_variant_without_fetching(self, define, download_spy):
        file = define(ONSHORE)
        resources = ethos_data.resolve("onshore_wind", file, test=True)
        assert [r.key for r in resources] == TEST_KEYS
        assert all(isinstance(r, ethos_data.Resource) for r in resources)
        assert download_spy == []

    def test_the_collections_object_reports_its_variants(self, define):
        loaded = ethos_data.load_collections(define(ONSHORE))
        assert loaded.variants("onshore_wind") == ("test", "full")
        assert loaded.variants("landcover") == ()
        assert (
            loaded.definition("onshore_wind", test=True)["paths"]["era5"]
            == "reskit-test-data/era5"
        )
        assert loaded.definition("onshore_wind")["paths"]["era5"] == "era5"
        # A plain collection's definition is the whole thing, title included.
        assert loaded.definition("landcover", test=True) is loaded.describe("landcover")

    def test_the_module_constants_name_exactly_two_variants(self):
        """Two, deliberately: the caller's switch is one boolean."""
        assert (
            selection.VARIANTS
            == (selection.VARIANT_TEST, selection.VARIANT_FULL)
            == ("test", "full")
        )
        assert selection.variant_name(True) == "test"
        assert selection.variant_name(False) == "full"
        assert selection.PATHS_KEY == "paths"
        assert selection.SELECTION_KEYS == ("extends", "include", "paths")

    def test_the_test_flag_propagates_through_extends(self, define):
        """A test selection is built from its parents' test selections; a plain
        parent is used as-is -- so a child need not repeat what its parents chose."""
        file = define("""
            base:
              test:
                include:
                  - dataset: reskit-test-data/era5
                    files: ["forecast_surface_roughness.nc"]
                paths:
                  roughness: reskit-test-data/era5/forecast_surface_roughness.nc
              full:
                include:
                  - dataset: era5
                    files: ["2016/*.nc"]
                paths:
                  roughness: era5/2016/u.nc
            plain:
              include:
                - dataset: landcover
                  files: ["clc.tif"]
              paths:
                clc: landcover/clc.tif
            child:
              test:
                extends: [base, plain]
              full:
                extends: [base, plain]
            """)
        small = ethos_data.fetch("child", file, progressbar=False, test=True)
        assert sorted(small) == [
            "landcover/clc.tif",
            "reskit-test-data/era5/forecast_surface_roughness.nc",
        ]
        assert small.named["roughness"].name == "forecast_surface_roughness.nc"
        large = ethos_data.fetch("child", file, progressbar=False)
        assert sorted(large) == ["era5/2016/u.nc", "landcover/clc.tif"]
        assert large.named["roughness"].parent.name == "2016"
        assert small.named["clc"] == large.named["clc"]

    def test_variants_must_offer_the_same_handles(self, define):
        """The one promise test and full make is interchangeability; a handle
        present in only one breaks it on the machine that has the real data."""
        file = define(LOPSIDED)
        with pytest.raises(
            ethos_data.CollectionError,
            match="only in test: gwa_50m; only in full: gwa_200m",
        ):
            ethos_data.resolve("lopsided", file)
        # Checked whichever variant is asked for: the mistake is in the file, not the call.
        with pytest.raises(
            ethos_data.CollectionError, match="must name the same paths"
        ):
            ethos_data.resolve("lopsided", file, test=True)
        with pytest.raises(ethos_data.CollectionError):
            ethos_data.load_collections(file).check_variants("lopsided")

    def test_a_plain_child_of_lopsided_variants_is_refused_too(
        self, define, download_spy
    ):
        """The check runs for every collection resolve() visits, not only the
        one asked for. A plain ``all`` extending a lopsided ``onshore_wind``
        would otherwise hand a workflow different handles per variant -- the
        one thing the check exists to prevent -- and whoever wrote ``all`` may
        never have looked inside the parent."""
        file = define(
            ONSHORE,
            LOPSIDED,
            """
            all:
              extends: [onshore_wind, lopsided]
            """,
        )
        with pytest.raises(
            ethos_data.CollectionError,
            match="collection 'lopsided': its test and full variants must name",
        ):
            ethos_data.resolve("all", file)
        with pytest.raises(
            ethos_data.CollectionError,
            match="only in test: gwa_50m; only in full: gwa_200m",
        ):
            ethos_data.fetch("all", file, progressbar=False, test=True)
        assert download_spy == []
        # The fault is the parent's alone; its well-formed siblings still resolve.
        assert [
            r.key for r in ethos_data.resolve("onshore_wind", file, test=True)
        ] == TEST_KEYS

    def test_a_variant_that_cannot_be_resolved_is_reported_as_a_failed_comparison(
        self, define
    ):
        """Comparing the variants means resolving both. When the *other* one
        fails, its own message gives advice ("pass test=True") that contradicts
        what the caller typed; the wrapper says what was being compared and
        keeps the inner diagnosis as the cause."""
        file = define("""
            full_only:
              full:
                include:
                  - dataset: landcover
                    files: ["clc.tif"]
                paths:
                  clc: landcover/clc.tif
            wrapped:
              test:
                extends: [full_only]
              full:
                extends: [full_only]
            """)
        # The full variant asked for here is fine on its own; the test one is not.
        with pytest.raises(ethos_data.CollectionError) as caught:
            ethos_data.resolve("wrapped", file)
        assert str(caught.value).startswith(
            "collection 'wrapped': its 'test' variant cannot be resolved, so its test and "
            "full variants cannot be compared: collection 'full_only' has no 'test' variant"
        )
        assert isinstance(caught.value.__cause__, ethos_data.CollectionError)
        # Asked for the test variant: the same wrapper, not a bare "ask for the full data".
        with pytest.raises(ethos_data.CollectionError, match="cannot be compared"):
            ethos_data.resolve("wrapped", file, test=True)
        # The parent alone is fine: nothing to compare.
        assert len(ethos_data.resolve("full_only", file)) == 1

    def test_selection_keys_may_not_sit_both_outside_and_inside_variants(self, define):
        """Otherwise nobody could say which selection a fetch would use."""
        file = define("""
            mixed:
              include:
                - dataset: landcover
              test:
                include:
                  - dataset: landcover
              full:
                include:
                  - dataset: landcover
            """)
        with pytest.raises(
            ethos_data.CollectionError, match="include at the top level"
        ):
            ethos_data.resolve("mixed", file)

    def test_asking_for_a_variant_that_is_not_defined_says_how_to_get_the_other(
        self, define
    ):
        """No silent fall-back: the other variant would download the full inputs
        under a test, or run a real calculation on the fixtures."""
        file = define("""
            test_only:
              test:
                include:
                  - dataset: landcover
            full_only:
              full:
                include:
                  - dataset: landcover
            """)
        with pytest.raises(
            ethos_data.CollectionError, match=r"test=True \(or --test\)"
        ):
            ethos_data.resolve("test_only", file)
        with pytest.raises(ethos_data.CollectionError, match="no small test selection"):
            ethos_data.resolve("full_only", file, test=True)
        # Each is fine when asked for the variant it does define.
        assert len(ethos_data.resolve("test_only", file, test=True)) == 3
        assert len(ethos_data.resolve("full_only", file)) == 3

    def test_circular_extends_is_a_collection_error(self, define):
        file = define("""
            loop_a:
              extends: [loop_b]
            loop_b:
              extends: [loop_a]
            """)
        with pytest.raises(ethos_data.CollectionError, match="circular"):
            ethos_data.resolve("loop_a", file)

    def test_an_unknown_collection_is_an_unknown_collection_error(self, define):
        with pytest.raises(
            ethos_data.UnknownCollection, match="unknown collection 'nope'"
        ):
            ethos_data.resolve("nope", define(ONSHORE))
        # Still a KeyError, for handlers written before the specific type existed.
        assert issubclass(ethos_data.UnknownCollection, KeyError)
        assert issubclass(ethos_data.CollectionError, ValueError)


class TestNamedPaths:
    def test_paths_resolves_every_handle_to_an_absolute_local_path(self, world, define):
        _, cache, _ = world
        file = define(ONSHORE)
        inputs = ethos_data.paths("onshore_wind", file, progressbar=False, test=True)
        assert isinstance(inputs, ethos_data.NamedPaths)
        assert inputs == {
            "clc": cache / "landcover/clc.tif",
            "era5": cache / "reskit-test-data/era5",
            "gwa_100m": cache / "reskit-test-data/global-wind-atlas/gwa100-like.tif",
            "gwa_50m": cache / "reskit-test-data/global-wind-atlas/gwa50-like.tif",
            "gwa_200m": cache / "reskit-test-data/global-wind-atlas/gwa200-like.tif",
        }
        assert all(path.is_absolute() for path in inputs.values())
        assert all(path.exists() for path in inputs.values())

    def test_the_same_handles_come_back_for_the_full_data(self, world, define):
        """What lets a workflow drop ``test=True`` and change nothing else."""
        _, cache, _ = world
        file = define(ONSHORE)
        small = ethos_data.paths("onshore_wind", file, progressbar=False, test=True)
        large = ethos_data.paths("onshore_wind", file, progressbar=False)
        assert set(small) == set(large)
        assert large["era5"] == cache / "era5"
        assert (
            large["gwa_100m"]
            == cache / "global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif"
        )
        assert large["clc"] == small["clc"]

    def test_a_folder_handle_is_the_directory_holding_the_selected_files(
        self, world, define
    ):
        """``era5`` with only the wind components included means *that directory*,
        not a request for everything the catalogue holds there."""
        _, cache, _ = world
        file = define(ONSHORE)
        files = ethos_data.fetch("onshore_wind", file, progressbar=False, test=True)
        assert files.named["era5"] == cache / "reskit-test-data/era5"
        assert "reskit-test-data/era5/forecast_surface_roughness.nc" not in files
        assert files.named["era5"].is_dir()

    def test_dataset_folder_and_family_handles(self, world, define):
        _, cache, _ = world
        file = define("""
            shapes:
              include:
                - dataset: era5
                  files: ["2015/*.nc"]
                - dataset: reskit-test-data/era5
                  files: ["100m_u_component_of_wind.nc"]
                - dataset: reskit-test-data/global-wind-atlas
                  files: ["gwa100-like.tif"]
              paths:
                dataset: era5
                folder: era5/2015
                fixtures: reskit-test-data
                member: reskit-test-data/era5
            """)
        inputs = ethos_data.paths("shapes", file, progressbar=False)
        assert inputs["dataset"] == cache / "era5"
        assert inputs["folder"] == cache / "era5/2015"
        # A family key returns the family directory, even though its files sit in two members.
        assert inputs["fixtures"] == cache / "reskit-test-data"
        assert inputs["member"] == cache / "reskit-test-data/era5"

    def test_fetch_returns_the_handles_beside_the_files(self, world, define):
        _, cache, _ = world
        files = ethos_data.fetch("landcover", define(ONSHORE), progressbar=False)
        assert isinstance(files, ethos_data.DataFiles)
        assert files.named == {"clc": cache / "landcover/clc.tif"}
        assert files.named["clc"] == files["landcover/clc.tif"]

    def test_a_missing_handle_names_the_collection_and_lists_what_it_defines(
        self, define
    ):
        """The handles are the maintainer's vocabulary; a typo should say so, not
        fail three frames later inside a raster reader."""
        inputs = ethos_data.paths(
            "onshore_wind", define(ONSHORE), progressbar=False, test=True
        )
        with pytest.raises(KeyError) as caught:
            inputs["gwa_100"]
        message = caught.value.args[0]
        assert "no named path 'gwa_100'" in message
        assert "collection 'onshore_wind'" in message
        assert "clc, era5, gwa_100m, gwa_200m, gwa_50m" in message
        assert inputs.get("gwa_100") is None  # dict.get still means "or None"

    def test_a_collection_without_paths_has_empty_named_and_refuses_paths(self, define):
        file = define("""
            bare:
              include:
                - dataset: landcover
            """)
        files = ethos_data.fetch("bare", file, progressbar=False)
        assert isinstance(files.named, ethos_data.NamedPaths)
        assert files.named == {}
        assert sorted(files) == [
            "landcover/clc.tif",
            "landcover/sites.dbf",
            "landcover/sites.shp",
        ]
        with pytest.raises(ethos_data.CollectionError, match="declares no named paths"):
            ethos_data.paths("bare", file, progressbar=False)


#: Two plain parents that both name ``raster``, differently, and only one of
#: which names ``speed``.
PARENTS = """
a:
  include:
    - dataset: landcover
      files: ["clc.tif"]
  paths:
    raster: landcover/clc.tif
b:
  include:
    - dataset: global-wind-atlas-v3
      files: ["gwa3_250_wind-speed_100m.tif"]
  paths:
    raster: global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif
    speed: global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif
"""


class TestInheritedHandles:
    def test_handles_are_inherited_through_extends(self, world, define):
        _, cache, _ = world
        file = define(
            PARENTS,
            """
            child:
              extends: [b]
              include:
                - dataset: landcover
                  files: ["clc.tif"]
            """,
        )
        loaded = ethos_data.load_collections(file)
        assert loaded.named_keys("child") == {
            "raster": "global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif",
            "speed": "global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif",
        }
        inputs = ethos_data.paths("child", file, progressbar=False)
        assert (
            inputs["speed"]
            == cache / "global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif"
        )

    def test_a_collections_own_entry_wins_over_an_inherited_one(self, world, define):
        _, cache, _ = world
        file = define(
            PARENTS,
            """
            child:
              extends: [b]
              include:
                - dataset: landcover
                  files: ["clc.tif"]
              paths:
                raster: landcover/clc.tif
            """,
        )
        inputs = ethos_data.paths("child", file, progressbar=False)
        assert inputs["raster"] == cache / "landcover/clc.tif"
        assert (
            inputs["speed"]
            == cache / "global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif"
        )

    def test_two_parents_disagreeing_is_an_error_the_child_can_settle(
        self, world, define, download_spy
    ):
        """Picking one silently would hand a workflow the wrong raster."""
        _, cache, _ = world
        file = define(
            PARENTS,
            """
            conflicted:
              extends: [a, b]
            settled:
              extends: [a, b]
              paths:
                raster: landcover/clc.tif
            """,
        )
        with pytest.raises(
            ethos_data.CollectionError, match="inherits paths.raster from both 'a'"
        ) as caught:
            ethos_data.fetch("conflicted", file, progressbar=False)
        assert "define paths.raster in 'conflicted'" in str(caught.value)
        assert download_spy == [], (
            "the definition was rejected, so nothing may be fetched"
        )
        assert (
            ethos_data.paths("settled", file, progressbar=False)["raster"]
            == cache / "landcover/clc.tif"
        )

    def test_two_parents_agreeing_is_not_a_conflict(self, define):
        file = define(
            PARENTS,
            """
            twin:
              include:
                - dataset: global-wind-atlas-v3
                  files: ["gwa3_250_wind-speed_100m.tif"]
              paths:
                speed: global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif
            child:
              extends: [b, twin]
            """,
        )
        assert (
            ethos_data.load_collections(file)
            .named_keys("child")["speed"]
            .endswith("100m.tif")
        )


#: A handle naming a file the collection does not include: the plainest
#: mistake a maintainer can make under ``paths:``.
FORGOT = """
forgot:
  include:
    - dataset: landcover
      files: ["sites.*"]
  paths:
    clc: landcover/clc.tif
"""

#: Licensed data with no restricted cache on this machine, beside a public
#: file -- both named, so one handle can be honoured here and one cannot.
LICENSED = """
with_licensed:
  include:
    - dataset: licensed
    - dataset: landcover
      files: ["clc.tif"]
  paths:
    secret: licensed/secret.tif
    clc: landcover/clc.tif
"""


class TestValidationBeforeDownload:
    """A mistake in collections.yaml must surface before a 40 GB transfer, not after."""

    def test_a_file_handle_must_be_included_by_the_collection(
        self, define, download_spy
    ):
        file = define(FORGOT)
        with pytest.raises(ethos_data.CollectionError) as caught:
            ethos_data.fetch("forgot", file, progressbar=False)
        message = str(caught.value)
        assert (
            "paths.clc names the file 'landcover/clc.tif', which the collection does not include"
            in message
        )
        assert (
            "add it under 'include:' (dataset: landcover, files: ['clc.tif'])"
            in message
        )
        assert download_spy == []

    def test_a_folder_handle_needs_at_least_one_selected_file_beneath_it(
        self, define, download_spy
    ):
        file = define("""
            hollow:
              include:
                - dataset: era5
                  files: ["2015/*.nc"]
              paths:
                later: era5/2016
            """)
        with pytest.raises(ethos_data.CollectionError, match="folder would be empty"):
            ethos_data.fetch("hollow", file, progressbar=False)
        assert download_spy == []

    @pytest.mark.parametrize(
        "key",
        [
            "nowhere/file.tif",
            "era5/2099",
            "landcover/clc.tiff",
            "reskit-test-data/nobody/x.nc",
        ],
    )
    def test_a_handle_naming_something_the_catalogue_lacks(
        self, define, download_spy, key
    ):
        file = define(f"""
            lost:
              include:
                - dataset: landcover
              paths:
                thing: {key}
            """)
        with pytest.raises(
            ethos_data.CollectionError, match="not in the catalogue"
        ) as caught:
            ethos_data.fetch("lost", file, progressbar=False)
        assert f"paths.thing names {key!r}" in str(caught.value)
        assert download_spy == []

    def test_validation_passes_before_the_download_and_then_downloads_once(
        self, define, download_spy
    ):
        ethos_data.paths("onshore_wind", define(ONSHORE), progressbar=False, test=True)
        assert download_spy == [TEST_KEYS]

    def test_unreachable_data_is_an_access_error_unless_the_caller_said_to_skip_it(
        self, define, monkeypatch
    ):
        """Having no restricted cache is a legitimate state, not a broken one --
        but a result with a hole in it is worse than a command that stops and
        says so. locate() raises before any transfer; the explicit keyword beats
        the configured answer in both directions."""
        file = define(LICENSED)
        with pytest.raises(ethos_data.AccessError) as caught:
            ethos_data.paths("with_licensed", file, progressbar=False)
        message = str(caught.value)
        assert message.startswith(
            "dataset 'licensed' is restricted and is never downloaded."
        )
        assert "--skip-unavailable" in message
        with pytest.raises(ethos_data.AccessError):
            ethos_data.fetch(
                "with_licensed", file, progressbar=False, skip_unavailable=False
            )
        # skip_unavailable=False is forwarded as such, over a configured True.
        monkeypatch.setenv("ETHOS_SKIP_UNAVAILABLE", "true")
        with pytest.raises(ethos_data.AccessError):
            ethos_data.fetch(
                "with_licensed", file, progressbar=False, skip_unavailable=False
            )
        # ...and None takes the configured answer, as download() always has.
        with pytest.warns(UserWarning):
            assert ethos_data.fetch(
                "with_licensed", file, progressbar=False
            ).named.omitted == ["secret"]

    def test_under_skip_unavailable_an_unreachable_handle_is_left_out_and_named(
        self, world, define
    ):
        """The same contract the files themselves get: absent from the mapping,
        never a path to nothing -- and named in a warning, so a workflow hears
        which handle went missing rather than failing on ``inputs["secret"]``
        three frames deep in a raster reader."""
        _, cache, _ = world
        file = define(LICENSED)
        with pytest.warns(UserWarning) as record:
            files = ethos_data.fetch(
                "with_licensed", file, progressbar=False, skip_unavailable=True
            )
        messages = [str(warning.message) for warning in record]
        assert any(
            m.startswith("1 file(s) from licensed are not available on this machine")
            for m in messages
        )
        assert (
            "collection 'with_licensed': the named path(s) secret are not available on this "
            "machine and have been left out -- the mapping has no entry for them."
        ) in messages
        assert sorted(files) == ["landcover/clc.tif"]
        assert files.named == {"clc": cache / "landcover/clc.tif"}
        assert files.named.omitted == ["secret"]

        with pytest.warns(UserWarning) as record:
            inputs = ethos_data.paths(
                "with_licensed", file, progressbar=False, skip_unavailable=True
            )
        assert any("named path(s) secret" in str(w.message) for w in record)
        assert inputs == {"clc": cache / "landcover/clc.tif"}
        assert inputs.omitted == ["secret"]
        with pytest.raises(KeyError) as caught:
            inputs["secret"]
        message = caught.value.args[0]
        assert (
            "named path 'secret' in collection 'with_licensed' is not available on this machine"
            in message
        )
        assert "left out under skip_unavailable" in message
        assert "available: clc" in message
        # A handle nobody defined is still "no such handle", not "unavailable".
        with pytest.raises(KeyError, match="no named path 'nope'"):
            inputs["nope"]
        assert inputs.get("secret") is None

    def test_paths_is_empty_not_an_error_when_every_handle_was_left_out(self, define):
        """ "Declares no named paths" is about the file. A collection whose one
        handle is unreachable *here* declared it fine; the caller who chose to
        skip unavailable data gets an empty mapping that says why."""
        file = define("""
            only_secret:
              include:
                - dataset: licensed
              paths:
                secret: licensed/secret.tif
            """)
        with pytest.warns(UserWarning) as record:
            inputs = ethos_data.paths(
                "only_secret", file, progressbar=False, skip_unavailable=True
            )
        assert any("named path(s) secret" in str(w.message) for w in record)
        assert inputs == {}
        assert inputs.omitted == ["secret"]
        with pytest.raises(KeyError, match="left out under skip_unavailable"):
            inputs["secret"]


class TestListResources:
    def test_a_family_a_folder_and_a_single_file(self, world, download_spy):
        _, _, index = world
        catalog = str(index)
        # In key order whatever the descriptor's order, so `ls` reads the same every time.
        family = ethos_data.catalog(catalog).resources("reskit-test-data")
        assert [r.key for r in family] == [
            "reskit-test-data/era5/100m_u_component_of_wind.nc",
            "reskit-test-data/era5/100m_v_component_of_wind.nc",
            "reskit-test-data/era5/forecast_surface_roughness.nc",
            "reskit-test-data/global-wind-atlas/gwa100-like.tif",
            "reskit-test-data/global-wind-atlas/gwa200-like.tif",
            "reskit-test-data/global-wind-atlas/gwa50-like.tif",
        ]
        folder = ethos_data.catalog(catalog).resources("era5/2015")
        assert [r.key for r in folder] == ["era5/2015/u.nc", "era5/2015/v.nc"]
        # The one file plus its sidecars, which a .shp is unreadable without --
        # sorted like everything else, so the sidecar comes first here.
        single = ethos_data.catalog(catalog).resources("landcover/sites.shp")
        assert [r.key for r in single] == ["landcover/sites.dbf", "landcover/sites.shp"]
        assert download_spy == [], "listing is a catalogue question; it fetches nothing"

    def test_a_typo_and_an_unknown_dataset_raise_their_own_errors(self, world):
        _, _, index = world
        with pytest.raises(KeyError, match="no file or folder 'typo'"):
            ethos_data.catalog(str(index)).resources("era5/typo")
        with pytest.raises(
            ethos_data.UnknownDataset, match="unknown dataset 'nowhere'"
        ):
            ethos_data.catalog(str(index)).resources("nowhere")
        assert issubclass(ethos_data.UnknownDataset, KeyError)


@pytest.fixture
def incomplete(world):
    """The synthetic index plus two datasets whose parts are not where it says.

    Both are how a piecemeal deployment looks: an index from one revision beside
    descriptors from another. Lazy loading means the index reads fine and the
    failure waits for the first thing that touches the dataset.
    """
    _, _, index = world
    catalogue = index.parent
    sharded = catalogue / "datasets" / "sharded" / "datapackage.json"
    sharded.parent.mkdir(parents=True)
    sharded.write_text(
        json.dumps(
            {
                "name": "sharded",
                "ethos:shards": [{"prefix": "a", "path": "manifests/a.json"}],
                "ethos:shard_depth": 1,
            }
        )
    )
    document = json.loads(index.read_text())
    document["datasets"] += [
        {
            "name": "ghost",
            "path": "datasets/ghost/datapackage.json",
            "ethos:license_status": "resolved",
        },
        {
            "name": "sharded",
            "path": "datasets/sharded/datapackage.json",
            "ethos:license_status": "resolved",
        },
    ]
    broken = catalogue / "incomplete.json"
    broken.write_text(json.dumps(document))
    return broken


class TestIncompleteCatalog:
    def test_a_missing_descriptor_is_diagnosed_as_an_incomplete_catalogue(
        self, incomplete
    ):
        """A bare FileNotFoundError here names a path the user never typed and
        gives no hint that the catalogue copy is the problem."""
        catalog = ethos_data.load_catalog(str(incomplete))
        with pytest.raises(ethos_data.IncompleteCatalog) as caught:
            catalog.dataset("ghost").load()
        assert isinstance(caught.value, FileNotFoundError)
        message = str(caught.value)
        assert "dataset 'ghost' is listed in the catalogue index" in message
        assert "descriptor (datapackage.json) is missing" in message
        assert "datasets/ghost/datapackage.json" in message
        assert "incomplete or stale" in message

    def test_a_missing_shard_is_diagnosed_the_same_way(self, incomplete):
        catalog = ethos_data.load_catalog(str(incomplete))
        dataset = catalog.dataset("sharded")
        dataset.load()  # the shard index itself is there
        assert dataset.pending_shards == ["a"]
        with pytest.raises(ethos_data.IncompleteCatalog) as caught:
            _ = dataset.resources
        message = str(caught.value)
        assert "dataset 'sharded'" in message
        assert "shard 'a' is missing" in message
        assert "manifests/a.json" in message

    def test_a_collection_selecting_from_a_ghost_dataset_raises_it(
        self, define, incomplete, download_spy
    ):
        file = define(
            """
            haunted:
              include:
                - dataset: ghost
            """,
            catalog=incomplete,
        )
        with pytest.raises(ethos_data.IncompleteCatalog, match="'ghost'"):
            ethos_data.fetch("haunted", file, progressbar=False)
        assert download_spy == []


@pytest.fixture
def shipped(world, monkeypatch):
    """A tool, fakepkg, whose collections file has variants and paths; returns the file."""
    tmp_path, _, index = world
    package = tmp_path / "site" / "fakepkg"
    (package / "data").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "data" / "__init__.py").write_text("")
    (package / "data" / "collections.yaml").write_text(
        f"catalog: {index.as_posix()}\n"
        "collections:\n"
        "  wind:\n"
        "    title: Wind inputs\n"
        "    test:\n"
        "      include:\n"
        "        - dataset: reskit-test-data/global-wind-atlas\n"
        "          files: ['gwa100-like.tif']\n"
        "      paths:\n"
        "        gwa_100m: reskit-test-data/global-wind-atlas/gwa100-like.tif\n"
        "    full:\n"
        "      include:\n"
        "        - dataset: global-wind-atlas-v3\n"
        "          files: ['gwa3_250_wind-speed_100m.tif']\n"
        "      paths:\n"
        "        gwa_100m: global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif\n"
    )
    return tmp_path / "site" / "fakepkg" / "data" / "collections.yaml"


class TestToolRoute:
    """A tool builds one handle from the file beside its code and calls it; the
    same handle is its command."""

    def test_paths_on_the_handle_with_the_test_flag(self, shipped, world):
        """The call the documentation shows, end to end."""
        _, cache, _ = world
        data = ethos_data.collections(shipped, tool="fakepkg")
        small = data.paths("wind", progressbar=False, test=True)
        assert small == {
            "gwa_100m": cache / "reskit-test-data/global-wind-atlas/gwa100-like.tif"
        }
        large = data.paths("wind", progressbar=False)
        assert large == {
            "gwa_100m": cache / "global-wind-atlas-v3/gwa3_250_wind-speed_100m.tif"
        }

    def test_the_tool_command_takes_the_test_flag(self, shipped, world, capsys):
        _, cache, _ = world
        data = ethos_data.collections(shipped, tool="fakepkg")
        assert data.main(["fetch", "wind", "--test", "--paths"]) == 0
        out = capsys.readouterr().out
        assert out.splitlines() == [
            f"gwa_100m\t{cache / 'reskit-test-data/global-wind-atlas/gwa100-like.tif'}"
        ]
        assert data.main(["show", "wind"]) == 0
        assert capsys.readouterr().out.startswith("wind [full]: 1 files")
        assert data.main(["--test", "show", "wind"]) == 0, (
            "--test before the subcommand too"
        )
        assert capsys.readouterr().out.startswith("wind [test]: 1 files")


class TestCommandLine:
    def test_list_prints_one_row_per_variant_and_flags_what_it_cannot_resolve(
        self, define, incomplete, capsys
    ):
        """One misdefined collection must not hide every other one in the file."""
        file = define(
            ONSHORE,
            """
            lopsided:
              title: Mismatched variants
              test:
                include:
                  - dataset: landcover
                paths:
                  clc: landcover/clc.tif
              full:
                include:
                  - dataset: landcover
            haunted:
              include:
                - dataset: ghost
            """,
            catalog=incomplete,
        )
        assert tool_main(str(file), prog="example-data", argv=["show"]) == 1
        out = capsys.readouterr().out
        assert re.search(
            r"^  landcover\s+1 files\s+\d+ B\s+Land cover$", out, re.MULTILINE
        )
        assert re.search(
            r"^  onshore_wind \[test\]\s+6 files\s+\d+ B\s+Data for onshore wind workflows$",
            out,
            re.MULTILINE,
        )
        # The title is printed once per collection, on its first row.
        assert re.search(
            r"^  onshore_wind \[full\]\s+7 files\s+\d+ B\s*$", out, re.MULTILINE
        )
        assert re.search(
            r"^  lopsided \[test\]\s+\[unresolvable\]\s+collection 'lopsided'",
            out,
            re.MULTILINE,
        )
        assert re.search(r"^  lopsided \[full\]\s+\[unresolvable\]", out, re.MULTILINE)
        assert re.search(
            r"^  haunted\s+\[unresolvable\]\s+dataset 'ghost' is listed",
            out,
            re.MULTILINE,
        )

    def test_list_exits_zero_when_everything_resolves(self, define, capsys):
        assert tool_main(str(define(ONSHORE)), prog="example-data", argv=["show"]) == 0
        assert "[unresolvable]" not in capsys.readouterr().out

    def test_info_labels_the_variant_and_shows_the_named_paths(self, define, capsys):
        file = define(ONSHORE)
        assert (
            tool_main(
                str(file), prog="example-data", argv=["show", "onshore_wind", "--test"]
            )
            == 0
        )
        out = capsys.readouterr().out
        assert out.startswith("onshore_wind [test]: 6 files, ")
        assert "reskit-test-data/global-wind-atlas/gwa100-like.tif" in out
        assert "named paths" in out
        assert re.search(r"^  era5\s+->\s+reskit-test-data/era5$", out, re.MULTILINE)
        assert re.search(
            r"^  gwa_100m\s+->\s+reskit-test-data/global-wind-atlas/gwa100-like.tif$",
            out,
            re.MULTILINE,
        )
        assert re.search(r"^  clc\s+->\s+landcover/clc.tif$", out, re.MULTILINE)

        assert (
            tool_main(str(file), prog="example-data", argv=["show", "onshore_wind"])
            == 0
        )
        out = capsys.readouterr().out
        assert out.startswith("onshore_wind [full]: 7 files, ")
        assert re.search(r"^  era5\s+->\s+era5$", out, re.MULTILINE)

        # A plain collection is not labelled: there is no variant to name.
        assert (
            tool_main(
                str(file), prog="example-data", argv=["show", "landcover", "--test"]
            )
            == 0
        )
        assert capsys.readouterr().out.startswith("landcover: 1 files, ")

    def test_plan_with_the_test_flag_previews_the_test_variant(self, define, capsys):
        assert (
            tool_main(
                str(define(ONSHORE)),
                prog="example-data",
                argv=["fetch", "onshore_wind", "--test", "--plan"],
            )
            == 0
        )
        out = capsys.readouterr().out
        assert re.search(r"already cached:\s+6 files", out)
        assert re.search(r"to download:\s+0 files", out)

    def test_fetch_with_the_test_flag_labels_its_message(self, define, capsys):
        file = define(ONSHORE)
        assert (
            tool_main(
                str(file), prog="example-data", argv=["fetch", "onshore_wind", "--test"]
            )
            == 0
        )
        assert capsys.readouterr().out.startswith(
            "onshore_wind [test]: all 6 available files already present"
        )
        assert (
            tool_main(str(file), prog="example-data", argv=["fetch", "onshore_wind"])
            == 0
        )
        assert capsys.readouterr().out.startswith(
            "onshore_wind [full]: all 7 available files already present"
        )

    def test_paths_prints_tab_separated_handle_and_path_lines(
        self, world, define, capsys
    ):
        """Tab-separated so a shell can read it back: ``while IFS=$'\\t' read handle path``."""
        _, cache, _ = world
        assert (
            tool_main(
                str(define(ONSHORE)),
                prog="example-data",
                argv=["fetch", "onshore_wind", "--test", "--paths"],
            )
            == 0
        )
        captured = capsys.readouterr()
        assert captured.err == ""
        rows = dict(line.split("\t") for line in captured.out.splitlines())
        assert rows == {
            "clc": str(cache / "landcover/clc.tif"),
            "era5": str(cache / "reskit-test-data/era5"),
            "gwa_100m": str(
                cache / "reskit-test-data/global-wind-atlas/gwa100-like.tif"
            ),
            "gwa_50m": str(cache / "reskit-test-data/global-wind-atlas/gwa50-like.tif"),
            "gwa_200m": str(
                cache / "reskit-test-data/global-wind-atlas/gwa200-like.tif"
            ),
        }

    def test_paths_on_a_collection_without_paths_is_an_error_not_a_traceback(
        self, define, capsys
    ):
        file = define("""
            bare:
              include:
                - dataset: landcover
            """)
        assert (
            tool_main(str(file), prog="example-data", argv=["fetch", "bare", "--paths"])
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(
            "error: collection 'bare' declares no named paths"
        )

    def test_ls_lists_the_catalogue_without_fetching(self, world, download_spy, capsys):
        _, _, index = world
        assert main(["--catalog", str(index), "ls", "reskit-test-data/era5"]) == 0
        out = capsys.readouterr().out
        assert out.startswith("reskit-test-data/era5: 3 files, 5 B\n")
        assert re.search(
            r"^  reskit-test-data/era5/100m_u_component_of_wind.nc\s+1 B$",
            out,
            re.MULTILINE,
        )
        assert re.search(
            r"^  reskit-test-data/era5/forecast_surface_roughness.nc\s+3 B$",
            out,
            re.MULTILINE,
        )
        assert main(["--catalog", str(index), "ls", "era5/2015"]) == 0
        assert capsys.readouterr().out.startswith("era5/2015: 2 files, ")
        assert download_spy == []

    def test_ls_of_something_unknown_exits_two(self, world, capsys):
        _, _, index = world
        assert main(["--catalog", str(index), "ls", "nowhere"]) == 2
        assert capsys.readouterr().err.startswith("error: unknown dataset 'nowhere'")
        assert main(["--catalog", str(index), "ls", "era5/2099"]) == 2
        assert "no file or folder '2099'" in capsys.readouterr().err

    def test_verify_all_covers_the_files_of_every_variant(self, define, capsys):
        """What is on disk is one cache; a file only the test variant selects
        is as much a file to check as one the full variant does."""
        file = define(ONSHORE)
        assert tool_main(str(file), prog="example-data", argv=["verify", "--all"]) == 0
        out = capsys.readouterr().out
        expected = len(set(TEST_KEYS) | set(FULL_KEYS))
        assert expected == 12
        assert f"verifying {expected} files from every collection (sizes)" in out
        assert f"{expected} file(s) match the catalogue." in out

        # One variant on its own checks only its own files.
        assert (
            tool_main(
                str(file),
                prog="example-data",
                argv=["verify", "onshore_wind", "--test"],
            )
            == 0
        )
        assert "verifying 6 files from onshore_wind" in capsys.readouterr().out
        assert (
            tool_main(str(file), prog="example-data", argv=["verify", "onshore_wind"])
            == 0
        )
        assert "verifying 7 files from onshore_wind" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "argv",
        [
            ["show", "nope"],
            ["fetch", "nope"],
            ["fetch", "nope", "--plan"],
            ["fetch", "nope", "--paths"],
            ["verify", "nope"],
        ],
    )
    def test_an_unknown_collection_is_a_message_not_a_traceback(
        self, define, capsys, argv
    ):
        assert tool_main(str(define(ONSHORE)), prog="example-data", argv=argv) == 2
        captured = capsys.readouterr()
        assert captured.err.startswith("error: unknown collection 'nope'")
        assert "Traceback" not in captured.err

    def test_a_missing_variant_is_a_message_that_names_the_flag(self, define, capsys):
        file = define("""
            test_only:
              test:
                include:
                  - dataset: landcover
            """)
        assert (
            tool_main(str(file), prog="example-data", argv=["show", "test_only"]) == 2
        )
        err = capsys.readouterr().err
        assert err.startswith("error: collection 'test_only' has no 'full' variant")
        assert "--test" in err
        assert (
            tool_main(
                str(file), prog="example-data", argv=["show", "test_only", "--test"]
            )
            == 0
        )

    def test_an_incomplete_catalogue_is_a_message_not_a_traceback(
        self, define, incomplete, capsys
    ):
        file = define(
            """
            haunted:
              include:
                - dataset: ghost
            """,
            catalog=incomplete,
        )
        assert tool_main(str(file), prog="example-data", argv=["show", "haunted"]) == 2
        err = capsys.readouterr().err
        assert err.startswith("error: dataset 'ghost' is listed in the catalogue index")
        assert "Traceback" not in err

    def test_a_misdefined_collection_is_a_message_not_a_traceback(self, define, capsys):
        assert (
            tool_main(
                str(define(FORGOT)),
                prog="example-data",
                argv=["fetch", "forgot", "--paths"],
            )
            == 2
        )
        assert capsys.readouterr().err.startswith(
            "error: collection 'forgot': paths.clc names the file"
        )

    @pytest.mark.parametrize(
        "argv",
        [["show", "forgot"], ["fetch", "forgot"], ["fetch", "forgot", "--plan"]],
    )
    def test_a_bad_handle_stops_every_command_before_it_reports_or_downloads(
        self, define, download_spy, capsys, argv
    ):
        """The command line refuses exactly what ethos_data.fetch() refuses, and
        as early: show and --plan would otherwise describe a collection that can
        never be fetched, and fetch would move the data before saying so."""
        assert tool_main(str(define(FORGOT)), prog="example-data", argv=argv) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(
            "error: collection 'forgot': paths.clc names the file 'landcover/clc.tif', "
            "which the collection does not include"
        )
        assert "Traceback" not in captured.err
        assert download_spy == []

    def test_list_flags_a_bad_handle_and_a_collection_that_is_not_a_mapping(
        self, define, capsys
    ):
        """Even describing a collection happens inside the per-row try: a
        ``broken: null`` left in the file used to abort the whole listing with
        a traceback and hide every other collection from everybody."""
        file = define(
            ONSHORE,
            FORGOT,
            """
            broken: null
            alsobroken: [a, b]
            """,
        )
        assert tool_main(str(file), prog="example-data", argv=["show"]) == 1
        out = capsys.readouterr().out
        assert re.search(
            r"^  forgot\s+\[unresolvable\]\s+collection 'forgot': paths\.clc names the file",
            out,
            re.MULTILINE,
        )
        assert re.search(
            r"^  broken\s+\[unresolvable\]\s+collection 'broken' must be a mapping .*got NoneType$",
            out,
            re.MULTILINE,
        )
        assert re.search(
            r"^  alsobroken\s+\[unresolvable\]\s+collection 'alsobroken' must be a mapping .*got list$",
            out,
            re.MULTILINE,
        )
        assert out.count("[unresolvable]") == 3
        # Every other row still prints, in full.
        assert re.search(
            r"^  landcover\s+1 files\s+\d+ B\s+Land cover$", out, re.MULTILINE
        )
        assert re.search(r"^  onshore_wind \[test\]\s+6 files", out, re.MULTILINE)
        assert re.search(r"^  onshore_wind \[full\]\s+7 files", out, re.MULTILINE)

    def test_paths_under_skip_unavailable_prints_only_the_handles_this_machine_can_honour(
        self, world, define, capsys
    ):
        """One ``handle<TAB>path`` line per reachable input; the unreachable one
        is a warning, never a path to nothing that a shell loop would hand on."""
        _, cache, _ = world
        file = define(LICENSED)
        with pytest.warns(UserWarning) as record:
            assert (
                tool_main(
                    str(file),
                    prog="example-data",
                    argv=["--skip-unavailable", "fetch", "with_licensed", "--paths"],
                )
                == 0
            )
        assert capsys.readouterr().out.splitlines() == [
            f"clc\t{cache / 'landcover/clc.tif'}"
        ]
        assert any(
            "named path(s) secret are not available on this machine" in str(w.message)
            for w in record
        )
        # Without the flag the command stops, as the API does, before any transfer.
        assert (
            tool_main(
                str(file),
                prog="example-data",
                argv=["fetch", "with_licensed", "--paths"],
            )
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(
            "error: dataset 'licensed' is restricted and is never downloaded."
        )
        assert "--skip-unavailable" in captured.err

    def test_verify_all_skips_what_it_cannot_resolve_and_says_so_in_its_exit_status(
        self, define, incomplete, capsys
    ):
        """One variant naming a dataset this catalogue copy lacks must not stop
        the check of everything else -- but the files checked being fine does
        not make the check complete, and exit 0 would let a CI job believe it was."""
        file = define(
            ONSHORE,
            LOPSIDED,
            """
            spooky:
              test:
                include:
                  - dataset: landcover
                    files: ["clc.tif"]
              full:
                include:
                  - dataset: ghost
            """,
            catalog=incomplete,
        )
        assert tool_main(str(file), prog="example-data", argv=["verify", "--all"]) == 1
        out = capsys.readouterr().out
        assert re.search(
            r"^skipped spooky \[full\]: dataset 'ghost' is listed in the catalogue index",
            out,
            re.MULTILINE,
        )
        assert re.search(
            r"^skipped lopsided \[test\]: collection 'lopsided': its test and full variants "
            r"must name the same paths",
            out,
            re.MULTILINE,
        )
        assert re.search(
            r"^skipped lopsided \[full\]: collection 'lopsided'", out, re.MULTILINE
        )
        assert "skipped spooky [test]" not in out
        # The rest was still checked: ONSHORE's 12 files, which spooky's test file is among.
        assert "verifying 12 files from every collection (sizes)" in out
        assert "12 file(s) match the catalogue." in out
        assert "3 collection variant(s) could not be resolved and were skipped" in out
        # With everything resolvable the exit status is 0, as before.
        assert (
            tool_main(
                str(define(ONSHORE, name="fine.yaml")),
                prog="example-data",
                argv=["verify", "--all"],
            )
            == 0
        )
        assert "skipped" not in capsys.readouterr().out

    def test_the_test_flag_may_come_before_the_subcommand(self, define, capsys):
        """The help says "put global options before the subcommand", so
        ``example-data --test info x`` is what people type; a bare "unrecognized
        arguments: --test" would send them hunting for a typo."""
        file = define(ONSHORE)
        outputs = []
        for argv in (
            ["show", "onshore_wind", "--test"],
            ["--test", "show", "onshore_wind"],
        ):
            assert tool_main(file, prog="example-data", argv=argv) == 0
            outputs.append(capsys.readouterr().out)
        assert outputs[0].startswith("onshore_wind [test]: 6 files, ")
        assert outputs[0] == outputs[1]
        assert (
            tool_main(
                str(file), prog="example-data", argv=["--test", "fetch", "onshore_wind"]
            )
            == 0
        )
        assert capsys.readouterr().out.startswith(
            "onshore_wind [test]: all 6 available files already present"
        )
        # A command without the flag ignores it rather than rejecting it.
        assert tool_main(str(file), prog="example-data", argv=["--test", "show"]) == 0

    def test_the_collection_commands_read_the_catalogue_the_file_pins(
        self, world, define, other_catalog, monkeypatch, capsys
    ):
        """Nothing is configured here, so the alternative to the pin would be
        the public catalogue on the network, which must not be contacted."""
        file = define(ONSHORE)
        monkeypatch.setattr(urllib.request, "urlopen", _no_network)
        assert tool_main(str(file), prog="example-data", argv=["show"]) == 0
        assert "onshore_wind" in capsys.readouterr().out
        # A different working directory cannot change the wrapper's pin.
        monkeypatch.chdir(file.parent)
        assert tool_main(file, prog="example-data", argv=["show", "onshore_wind"]) == 0
        assert capsys.readouterr().out.startswith("onshore_wind [full]: 7 files, ")
        # --catalog and $ETHOS_DATA_CATALOG still win over the pin.
        assert (
            tool_main(
                str(file),
                prog="example-data",
                argv=["--catalog", str(other_catalog), "show", "onshore_wind"],
            )
            == 2
        )
        assert "unknown dataset 'landcover'" in capsys.readouterr().err
        monkeypatch.setenv("ETHOS_DATA_CATALOG", str(other_catalog))
        assert (
            tool_main(str(file), prog="example-data", argv=["show", "onshore_wind"])
            == 2
        )
        assert "unknown dataset 'landcover'" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("retired", "replacement"),
        [
            ("list", "example-data show"),
            ("info", "example-data show <collection>"),
            ("plan", "example-data fetch <collection> --plan"),
            ("paths", "example-data fetch <collection> --paths"),
            ("path", "ethos-data fetch <key>"),
            ("ls", "ethos-data ls [<key>]"),
        ],
    )
    def test_a_retired_command_names_what_replaces_it(
        self, define, capsys, retired, replacement
    ):
        """A hard rename, but not a silent one: the names that went away, and
        the two that moved to ethos-data with the catalogue, each answer with
        the line to type instead rather than argparse's 'invalid choice'."""
        file = define(ONSHORE)
        assert (
            tool_main(str(file), prog="example-data", argv=[retired, "onshore_wind"])
            == 2
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"error: `example-data {retired}` is gone")
        assert replacement in captured.err

    def test_a_retired_name_is_not_read_out_of_an_option_value(self, define, capsys):
        """``--catalog list`` names a file; only the subcommand slot is checked."""
        file = define(ONSHORE)
        assert (
            tool_main(
                str(file), prog="example-data", argv=["--catalog", "list", "show"]
            )
            == 2
        )
        assert "is gone" not in capsys.readouterr().err


@pytest.fixture
def other_catalog(world):
    """A second catalogue describing nothing: proof of which one a call read."""
    tmp_path, _, _ = world
    index = tmp_path / "other" / "datacatalog.json"
    index.parent.mkdir()
    index.write_text(json.dumps({"name": "other", "datasets": []}))
    return index


class TestCollectionsFileRoute:
    """A handle's ``.catalog``: the file's pin, for the key-taking calls."""

    def test_path_and_list_resources_take_a_collections_file(
        self, world, define, monkeypatch
    ):
        """The rule ``fetch`` applies, so a script that fetches a collection and
        then asks for one more key by name reads one catalogue, not two."""
        _, cache, _ = world
        file = define(ONSHORE)
        monkeypatch.setattr(urllib.request, "urlopen", _no_network)
        pinned = ethos_data.collections(file).catalog
        assert pinned.path("landcover/clc.tif") == cache / "landcover/clc.tif"
        assert (
            ethos_data.collections(str(file)).catalog.path("era5/2015")
            == cache / "era5/2015"
        )
        listed = pinned.resources("era5/2015")
        assert [r.key for r in listed] == ["era5/2015/u.nc", "era5/2015/v.nc"]

    def test_an_explicit_or_configured_catalogue_wins_over_the_pin(
        self, define, other_catalog, monkeypatch
    ):
        """Below, not instead of: ``--catalog`` and the environment exist to
        repoint every tool at once, pins included."""
        file = define(ONSHORE)
        with pytest.raises(ethos_data.UnknownDataset, match="unknown dataset 'era5'"):
            ethos_data.collections(file, catalog=str(other_catalog)).catalog.resources(
                "era5"
            )
        monkeypatch.setenv("ETHOS_DATA_CATALOG", str(other_catalog))
        with pytest.raises(ethos_data.UnknownDataset, match="unknown dataset 'era5'"):
            ethos_data.collections(file).catalog.resources("era5")


class TestCatalogUnavailable:
    """No index at all -- unlike IncompleteCatalog, where the index promised a dataset."""

    def test_a_missing_local_index_names_the_path_and_says_how_to_point_elsewhere(
        self, world
    ):
        """The common cause is a pin, not a network fault, and the person hitting
        it usually did not write that pin -- so the message says how to use
        another catalogue for this run, this shell, or for good."""
        tmp_path, _, _ = world
        nowhere = tmp_path / "nowhere" / "datacatalog.json"
        with pytest.raises(ethos_data.CatalogUnavailable) as caught:
            ethos_data.load_catalog(str(nowhere))
        assert isinstance(caught.value, OSError)
        assert isinstance(caught.value.__cause__, FileNotFoundError)
        message = str(caught.value)
        assert message.startswith(f"cannot read the catalogue index at {nowhere}: ")
        for advice in (
            "--catalog",
            "$ETHOS_DATA_CATALOG",
            "ethos-data config set-catalog",
        ):
            assert advice in message
        assert not issubclass(
            ethos_data.IncompleteCatalog, ethos_data.CatalogUnavailable
        )

    def test_an_http_404_and_an_unreachable_host_are_the_same_diagnosis(
        self, world, monkeypatch
    ):
        """HTTPError is a URLError; left alone it reads "HTTP Error 404: Not
        Found" -- nothing about which URL, or that a pin chose it."""
        url = "https://example.invalid/catalogue/v9.9/datacatalog.json"

        def not_found(*args, **kwargs):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", not_found)
        with pytest.raises(ethos_data.CatalogUnavailable) as caught:
            ethos_data.load_catalog(url)
        message = str(caught.value)
        assert message.startswith(
            f"cannot read the catalogue index at {url}: HTTP 404 Not Found"
        )
        assert "pin may name a revision or repository that does not exist" in message
        assert isinstance(caught.value.__cause__, urllib.error.HTTPError)

        def unreachable(*args, **kwargs):
            raise urllib.error.URLError("no such host")

        monkeypatch.setattr(urllib.request, "urlopen", unreachable)
        with pytest.raises(ethos_data.CatalogUnavailable, match="no such host"):
            ethos_data.load_catalog(url)

    def test_the_cli_prints_a_message_and_exits_two(self, world, define, capsys):
        tmp_path, _, _ = world
        file = define(ONSHORE, catalog=tmp_path / "nowhere" / "datacatalog.json")
        for argv in (
            ["show", "onshore_wind"],
            ["show"],
            ["fetch", "onshore_wind", "--plan"],
        ):
            assert tool_main(file, prog="example-data", argv=argv) == 2
            captured = capsys.readouterr()
            assert captured.err.startswith("error: cannot read the catalogue index at ")
            assert "Traceback" not in captured.err


class TestCatalogPin:
    """``catalog_pin``: the one reading of a file's ``catalog:`` key, shared by fetch, path and ls."""

    def test_a_relative_pin_belongs_to_the_file_not_the_working_directory(
        self, tmp_path, monkeypatch
    ):
        """A collections file is committed beside the catalogue it pins; where
        the user happens to stand when running the tool must not change what
        the file means."""
        folder = tmp_path / "project" / "config"
        folder.mkdir(parents=True)
        file = folder / "collections.yaml"
        file.write_text(
            "catalog: ../catalogue/datacatalog.json\ncollections: {}\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        expected = str(
            (tmp_path / "project" / "catalogue" / "datacatalog.json").resolve()
        )
        assert selection.catalog_pin(file) == expected
        assert selection.catalog_pin(str(file)) == expected
        # An absolute path is taken as it is.
        absolute = str((tmp_path / "elsewhere" / "datacatalog.json").resolve())
        assert selection.catalog_pin(file, {"catalog": absolute}) == absolute

    def test_no_pin_is_none_and_a_parsed_document_may_be_handed_in(self, tmp_path):
        file = tmp_path / "collections.yaml"
        file.write_text("collections: {}\n", encoding="utf-8")
        assert selection.catalog_pin(file) is None
        assert selection.catalog_pin(file, {"catalog": ""}) is None
        url = "https://example.invalid/catalogue/v1/datacatalog.json"
        assert selection.catalog_pin(file, {"catalog": url}) == url
        # With a document the file is not read: load_collections has already parsed it.
        assert selection.catalog_pin(
            tmp_path / "never-written.yaml", {"catalog": "index.json"}
        ) == str((tmp_path / "index.json").resolve())

    def test_a_legacy_ref_suffix_is_stripped(self, tmp_path):
        """Collections files used to pin ``<location>@<ref>``. A revision now
        lives in the URL itself, so the suffix is dropped rather than looked for
        on disk -- while a Git host's branch or tag segment is left alone."""
        file = tmp_path / "collections.yaml"
        assert selection.catalog_pin(
            file, {"catalog": "catalogue/datacatalog.json@v1.2"}
        ) == str((tmp_path / "catalogue" / "datacatalog.json").resolve())
        assert (
            selection.catalog_pin(
                file, {"catalog": "https://example.invalid/cat/datacatalog.json@v2"}
            )
            == "https://example.invalid/cat/datacatalog.json"
        )
        tagged = "https://raw.githubusercontent.com/org/repo/v1.2/datacatalog.json"
        assert selection.catalog_pin(file, {"catalog": tagged}) == tagged

    def test_load_collections_follows_the_pin_from_any_working_directory(
        self, world, define, monkeypatch
    ):
        """The relative form is what a committed file carries; it must hold
        wherever the tool is run from, and never fall back to the network."""
        _, cache, index = world
        file = define(ONSHORE, catalog=Path("catalogue/datacatalog.json"))
        monkeypatch.chdir(cache)
        monkeypatch.setattr(urllib.request, "urlopen", _no_network)
        assert selection.catalog_pin(file) == str(index)
        assert ethos_data.load_collections(file).catalog.location == str(index)
        assert [r.key for r in ethos_data.resolve("landcover", file)] == [
            "landcover/clc.tif"
        ]


class TestSecondReviewRound:
    """Loose ends a second adversarial pass found; each was demonstrated first."""

    @pytest.mark.parametrize(
        "body, complaint",
        [
            ("strinclude:\n  include: landcover\n", "include must be a list"),
            (
                'nodataset:\n  include:\n    - files: ["clc.tif"]\n',
                "needs a 'dataset' name",
            ),
            (
                'badfiles:\n  include:\n    - dataset: landcover\n      files: "clc.tif"\n',
                "must be a list of glob strings",
            ),
        ],
    )
    def test_a_malformed_include_is_a_collection_error_not_a_traceback(
        self, define, capsys, body, complaint
    ):
        """These used to escape as TypeError/KeyError from inside the glob loop
        and take every other row of `ethos-data list` down with them."""
        file = define(ONSHORE, body)
        name = body.split(":", 1)[0]
        with pytest.raises(ethos_data.CollectionError, match=complaint):
            ethos_data.resolve(name, file)
        assert tool_main(str(file), prog="example-data", argv=["show"]) == 1
        out = capsys.readouterr().out
        assert f"{name:<28} {'[unresolvable]':>17}" in out
        assert "onshore_wind [test]" in out and "landcover " in out
        assert tool_main(str(file), prog="example-data", argv=["show", name]) == 2
        assert complaint in capsys.readouterr().err

    def test_a_mixed_keys_mistake_is_reported_as_itself(self, define):
        """Not as a failed variant comparison: the definition is checked before
        the variants are compared, so the message names the actual mistake."""
        file = define("""
            mixed:
              include:
                - dataset: landcover
              test:
                include:
                  - dataset: landcover
              full:
                include:
                  - dataset: landcover
        """)
        with pytest.raises(ethos_data.CollectionError) as caught:
            ethos_data.resolve("mixed", file)
        message = str(caught.value)
        assert "at the top level and also the variant(s)" in message
        assert "cannot be compared" not in message

    def test_a_fetch_with_nothing_reachable_says_so(self, define, capsys):
        """ "all 0 available files already present" described a collection none
        of which is on this machine; the sentence now says what happened."""
        file = define("""
            only_licensed:
              include:
                - dataset: licensed
        """)
        assert (
            tool_main(
                str(file),
                prog="example-data",
                argv=["--skip-unavailable", "fetch", "only_licensed"],
            )
            == 0
        )
        out = capsys.readouterr().out
        assert "nothing to fetch" in out and "none of its 1 file(s)" in out

    @pytest.fixture
    def staged_landcover(self, world, monkeypatch):
        """A staging root shadowing ``landcover`` with a copy of its one file."""
        tmp_path, _, _ = world
        staging = tmp_path / "staging"
        (staging / "landcover").mkdir(parents=True)
        (staging / "landcover" / "clc.tif").write_text("clc")
        monkeypatch.setenv("ETHOS_STAGING_DIR", str(staging))
        return staging

    def test_a_handle_warns_about_staging_once_and_its_listing_not_again(
        self, define, staged_landcover
    ):
        """The overlay is applied when the handle is built -- that is the moment
        somebody is about to be handed data -- and never again on its calls."""
        file = define(ONSHORE)
        with _recording() as caught:
            data = ethos_data.collections(file)
            listed = data.catalog.resources("landcover")
            listed_again = data.catalog.resources("landcover")
        assert (
            [r.key for r in listed]
            == [r.key for r in listed_again]
            == ["landcover/clc.tif"]
        )
        assert len([w for w in caught if "staging is active" in str(w.message)]) == 1

    def test_an_already_staged_catalogue_is_not_overlaid_twice(
        self, define, staged_landcover
    ):
        """A tool hands ``load_collections(...).catalog`` back into ``catalog()``;
        the overlay -- and its warning -- must not double up."""
        file = define(ONSHORE)
        with _recording() as first:
            loaded = ethos_data.load_collections(file)
        assert len([w for w in first if "staging is active" in str(w.message)]) == 1
        assert loaded.catalog.staged
        with _recording() as second:
            found = ethos_data.catalog(loaded.catalog).path("landcover/clc.tif")
        assert found == staged_landcover / "landcover" / "clc.tif"
        assert not [w for w in second if "staging is active" in str(w.message)]


@contextlib.contextmanager
def _recording():
    """``warnings.catch_warnings(record=True)`` with every warning let through,
    so a test can count the ones it cares about instead of failing on the first."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield caught
