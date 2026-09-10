"""ethos:include / ethos:exclude -- narrowing a manifest to part of source_dir.

The case these exist for: source_dir is a shared download directory holding the
dataset *and* the zip it came out of, a wget log, and somebody's test clip, and
we have neither the write access nor the standing to tidy it up.

Run with pytest, or directly:  python tests/test_manifest_filters.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from ethos_data.maintain.manifest import expand_pattern, render_dataset

CATALOG = "name: t\nethos:catalog_role: source\nethos:publication_url: https://example.invalid/x\n"

# Shaped like /shared_data/Global_Wind_Atlas/GWA_4.0: five rasters worth keeping,
# a 67 GB derivative that is a different dataset, and the download plumbing.
GWA_FILES = [
    "wind_speed_cog_10m.tif",
    "wind_speed_cog_50m.tif",
    "wind_speed_cog_100m.tif",
    "wind_speed_cog_150m.tif",
    "wind_speed_cog_200m.tif",
    "wind_speed_cog_100m.tif.aux.xml",
    "wind_speed_cog_100m_expanded_by_ERA5_x_mean_global.tif",
    "url_list.txt",
    "url_list2.txt",
    "download.sh",
    "wget-log",
    "54313655?private_link=abc",
]
GWA_RASTERS = sorted(GWA_FILES[:6])


def gwa_tree(root: Path) -> None:
    for name in GWA_FILES:
        (root / name).write_bytes(b"x")
    nested = root / "test"
    nested.mkdir()
    for name in ("100", "download.sh", "wget-log"):
        (nested / name).write_bytes(b"")


def shapefile_tree(root: Path) -> None:
    for extension in (".shp", ".shx", ".dbf", ".prj"):
        (root / f"sites{extension}").write_bytes(b"x")
    (root / "notes.txt").write_bytes(b"x")


def vintage_tree(root: Path) -> None:
    for vintage in ("v1", "v2"):
        directory = root / vintage
        directory.mkdir()
        (directory / "data.tif").write_bytes(b"x")
        (directory / "download.zip").write_bytes(b"x")


def inventory(extra_yaml: str, tree=gwa_tree) -> list[str]:
    """Build a throwaway dataset and return the resource paths it inventoried."""
    workspace = Path(tempfile.mkdtemp())
    try:
        source = workspace / "src"
        source.mkdir()
        tree(source)
        dataset_dir = workspace / "datasets" / "d"
        dataset_dir.mkdir(parents=True)
        (workspace / "catalog.yaml").write_text(CATALOG)
        (dataset_dir / "dataset.yaml").write_text(
            f"name: d\ntitle: t\nsource_dir: {source}\nethos:remote_prefix: d\n" + extra_yaml)

        files = render_dataset(dataset_dir)
        package = json.loads(files["datapackage.json"])
        if "resources" in package:
            return sorted(resource["path"] for resource in package["resources"])
        paths: list[str] = []
        for shard in package["ethos:shards"]:
            paths += [r["path"] for r in json.loads(files[shard["path"]])["resources"]]
        return sorted(paths)
    finally:
        shutil.rmtree(workspace)


class TestExpandPattern:
    def test_literal_means_the_path_and_its_subtree(self):
        # "exclude test" has to drop the directory's contents, not just a file
        # that happens to be called test.
        assert expand_pattern("test") == ["test", "test/**"]

    def test_trailing_slash_means_the_subtree_only(self):
        assert expand_pattern("test/") == ["test/**"]

    def test_wildcards_are_used_as_written(self):
        assert expand_pattern("*.tif") == ["*.tif"]

    def test_leading_slash_is_refused(self):
        with pytest.raises(SystemExit, match="relative to source_dir"):
            expand_pattern("/absolute.tif")


class TestSelection:
    def test_no_filter_takes_everything(self):
        assert len(inventory("")) == len(GWA_FILES) + 3

    def test_include_selects_only_what_it_names(self):
        listed = "".join(f'  - "{name}"\n' for name in GWA_RASTERS)
        assert inventory(f"ethos:include:\n{listed}") == GWA_RASTERS

    def test_star_stays_inside_one_segment_and_matches_a_whole_name(self):
        # The point of borrowing the reader's matcher: *m.tif must anchor at the
        # end, so the 67 GB ..._mean_global.tif derivative is not swept in.
        assert inventory('ethos:include:\n  - "wind_speed_cog_*m.tif"\n') == sorted(
            name for name in GWA_RASTERS if name.endswith("m.tif"))

    def test_exclude_by_bare_folder_name_drops_the_subtree(self):
        assert inventory(
            'ethos:exclude:\n  - "test"\n  - "url_list*.txt"\n  - "download.sh"\n'
            '  - "wget-log"\n  - "54313655?private_link=abc"\n'
            '  - "*expanded_by_ERA5*"\n') == GWA_RASTERS

    def test_double_star_reaches_into_subdirectories(self):
        assert inventory(
            'ethos:include:\n  - "**"\nethos:exclude:\n  - "**/wget-log"\n  - "test/"\n'
            '  - "*expanded*"\n  - "url_list*"\n  - "download.sh"\n'
            '  - "54313655*"\n') == GWA_RASTERS

    def test_two_datasets_can_share_one_source_dir(self):
        # global-wind-atlas and global-wind-atlas-era5-expanded both live in
        # GWA_4.0; neither may see the other's files.
        assert inventory('ethos:include:\n  - "*expanded_by_ERA5*"\n') == [
            "wind_speed_cog_100m_expanded_by_ERA5_x_mean_global.tif"]

    def test_filter_applies_before_sharding(self):
        assert inventory(
            'ethos:shard_depth: 1\nethos:exclude:\n  - "**/*.zip"\n',
            tree=vintage_tree) == ["v1/data.tif", "v2/data.tif"]


class TestGuardRails:
    """A silently smaller manifest is the failure mode worth spending errors on."""

    def test_include_matching_nothing_is_an_error_that_names_the_pattern(self):
        with pytest.raises(SystemExit, match="typo_"):
            inventory('ethos:include:\n  - "wind_speed_cog_*.tif"\n  - "typo_*.tif"\n')

    def test_exclude_matching_nothing_is_only_a_warning(self, capsys):
        # The stray it named may simply have been cleaned up since.
        assert inventory('ethos:exclude:\n  - "already-gone.txt"\n')
        assert "matches nothing" in capsys.readouterr().err

    def test_empty_list_is_refused_rather_than_ignored(self):
        with pytest.raises(SystemExit, match="empty list"):
            inventory("ethos:include: []\n")

    def test_wrong_type_is_refused(self):
        with pytest.raises(SystemExit, match="must be a list"):
            inventory('ethos:include: "*.tif"\n')

    def test_filtering_everything_out_is_an_error(self):
        with pytest.raises(SystemExit, match="filtered out every one"):
            inventory('ethos:exclude:\n  - "**"\n')

    def test_shapefile_companions_survive_an_include_of_just_the_shp(self):
        # A .shp without its .dbf/.shx is unreadable, and an include list is
        # exactly where somebody would forget them.
        assert inventory('ethos:include:\n  - "*.shp"\n', tree=shapefile_tree) == [
            "sites.dbf", "sites.prj", "sites.shp", "sites.shx"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
