"""The one inventory reader, over the metadata sources it is handed.

Tests for the decision "One inventory reader": a dataset's descriptor and
inventory, inline or in shards, read on demand from a tree in memory, each
shard at most once and only when a request needs it; one error for a missing
part, worded for a maintainer as a build that is due; and the data user and
the maintainer reading the same resources from one tree.
"""

from __future__ import annotations

import json

import pytest
from support import SourceCatalogue

from ethos_data.adapters.fakes import MemorySource
from ethos_data.adapters.metadata import CachedSource, FileSource, moving
from ethos_data.catalogs import load_catalog
from ethos_data.errors import DescriptorError, IncompleteCatalog
from ethos_data.maintain import inventory_of
from ethos_data.model.inventory import (
    ROOT_SHARD,
    Inventory,
    shard_could_match,
    shard_key,
    split_into_shards,
)
from ethos_data.model.resource import Resource

HASH = "sha256:" + "0" * 64


def record(path: str, size: int = 1, **extra) -> dict:
    return {
        "name": path.replace("/", "-"),
        "path": path,
        "bytes": size,
        "hash": HASH,
        "mediatype": "text/csv",
        **extra,
    }


#: A sharded dataset of three tiles and a file at its root, in memory.
TILES = {
    "4/6": [record("4/6/a.csv"), record("4/6/b.csv")],
    "4/7": [record("4/7/a.csv")],
    ROOT_SHARD: [record("readme.txt", 9, licenses=[{"name": "CC0-1.0"}])],
}


def tree(shards: dict[str, list[dict]] = TILES, *, drop: str | None = None) -> dict:
    files = {
        "cat/datacatalog.json": json.dumps(
            {
                "name": "memory",
                "datasets": [
                    {
                        "name": "tiles",
                        "path": "datasets/tiles/datapackage.json",
                        "ethos:remote_prefix": "tiles",
                        "ethos:total_bytes": 12,
                        "ethos:file_count": 4,
                    }
                ],
            }
        ),
        "cat/datasets/tiles/datapackage.json": json.dumps(
            {
                "name": "tiles",
                "ethos:shard_depth": 2,
                "ethos:shards": [
                    {"prefix": prefix, "path": f"shards/{prefix}.json"}
                    for prefix in shards
                ],
            }
        ),
    }
    for prefix, records in shards.items():
        files[f"cat/datasets/tiles/shards/{prefix}.json"] = json.dumps(
            {"resources": records}
        )
    files.pop(drop, None)
    return files


def tiles(source: MemorySource) -> Inventory:
    return (
        load_catalog("cat/datacatalog.json", source=source).dataset("tiles").inventory
    )


class TestReadingOnDemand:
    def test_loading_the_catalogue_reads_only_the_index(self):
        source = MemorySource(tree())

        catalog = load_catalog("cat/datacatalog.json", source=source)

        assert source.reads == ["cat/datacatalog.json"]
        assert catalog.dataset("tiles").file_count == 4, "from the index row"
        assert source.reads == ["cat/datacatalog.json"]

    def test_a_path_reads_the_one_shard_that_can_hold_it(self):
        source = MemorySource(tree())

        assert tiles(source).at("4/7/a.csv").bytes == 1

        assert source.reads[1:] == [
            "cat/datasets/tiles/datapackage.json",
            "cat/datasets/tiles/shards/4/7.json",
        ]

    def test_a_pattern_reads_only_the_shards_it_can_reach(self):
        source = MemorySource(tree())
        inventory = tiles(source)

        found = inventory.matching(["4/6/*.csv"])

        assert sorted(found) == ["4/6/a.csv", "4/6/b.csv"]
        assert inventory.pending_shards == ["4/7", ROOT_SHARD]

    def test_each_shard_is_read_at_most_once(self):
        source = MemorySource(tree())
        inventory = tiles(source)

        inventory.matching(["4/**"])
        inventory.at("4/6/a.csv")
        inventory.resources()

        shard_reads = [read for read in source.reads if "/shards/" in read]
        assert sorted(shard_reads) == sorted(set(shard_reads))
        assert len(shard_reads) == 3

    def test_the_records_come_back_as_written_in_inventory_order(self):
        inventory = tiles(MemorySource(tree()))

        assert inventory.records() == [r for shard in TILES.values() for r in shard]
        assert inventory.record("readme.txt")["licenses"] == [{"name": "CC0-1.0"}]


class TestTheShardRules:
    def test_a_file_lands_in_the_shard_of_its_directory(self):
        assert shard_key("4/6/a.csv", 2) == "4/6"
        assert shard_key("4/6/x/a.csv", 2) == "4/6"
        assert shard_key("a.csv", 2) == ROOT_SHARD

    def test_split_and_read_agree(self):
        records = [record("4/6/a.csv"), record("4/7/a.csv"), record("a.csv")]

        assert list(split_into_shards(records, 2)) == ["4/6", "4/7", ROOT_SHARD]

    @pytest.mark.parametrize(
        "prefix, pattern, reachable",
        [
            ("4/6", "4/6/*.csv", True),
            ("4/6", "4/*/a.csv", True),
            ("4/6", "**", True),
            ("4/6", "5/**", False),
            ("4/6", "4/6", False),
            (ROOT_SHARD, "*.txt", True),
            (ROOT_SHARD, "4/6/*", False),
        ],
    )
    def test_pruning_never_drops_a_shard_that_holds_a_match(
        self, prefix, pattern, reachable
    ):
        assert shard_could_match(prefix, pattern) is reachable


class TestAMissingPart:
    def test_a_missing_shard_names_the_dataset_the_part_and_where(self):
        source = MemorySource(tree(drop="cat/datasets/tiles/shards/4/7.json"))

        with pytest.raises(IncompleteCatalog) as refused:
            tiles(source).at("4/7/a.csv")

        message = refused.value.message
        assert "dataset 'tiles'" in message
        assert "shard '4/7' is missing: cat/datasets/tiles/shards/4/7.json" in message

    def test_a_maintainer_is_told_which_build_is_due(self, tmp_path):
        directory = tmp_path / "datasets" / "tiles"
        directory.mkdir(parents=True)

        with pytest.raises(DescriptorError) as refused:
            inventory_of("tiles", directory).records()

        assert "tiles: its descriptor (datapackage.json) is missing" in (
            refused.value.message
        )
        assert "ethos-data catalog build tiles" in refused.value.message


class TestMadeElsewhere:
    def test_records_in_hand_read_nothing(self):
        inventory = Inventory.from_records(
            "bundled", {"name": "bundled", "resources": [record("a.csv")]}
        )

        assert list(inventory.resources()) == ["a.csv"]
        assert inventory.records() == [record("a.csv")]

    def test_resources_in_hand_read_nothing(self):
        staged = Resource("staged", "a", "a.csv", 1, "", "text/csv")

        inventory = Inventory.from_resources("staged", {"name": "staged"}, [staged])

        assert inventory.at("a.csv") is staged
        assert inventory.descriptor == {"name": "staged"}


class TestBothSidesReadOneTree:
    @pytest.fixture
    def built(self, tmp_path):
        source = SourceCatalogue(tmp_path)
        source.dataset(
            "tiles",
            {"4/6/a.csv": "1", "4/6/b.csv": "22", "4/7/a.csv": "333", "x.txt": "4"},
            ethos_shard_depth=2,
        )
        assert source.build()[0] == 0
        return source.root

    def test_a_reader_and_a_maintainer_see_the_same_records(self, built):
        tree = {
            path.relative_to(built).as_posix(): path.read_bytes()
            for path in built.rglob("*")
            if path.is_file()
        }
        from_disk = (
            load_catalog(str(built / "datacatalog.json")).dataset("tiles").inventory
        )
        in_memory = (
            load_catalog("datacatalog.json", source=MemorySource(tree))
            .dataset("tiles")
            .inventory
        )
        maintainer = inventory_of("tiles", built / "datasets" / "tiles")

        assert from_disk.sharded
        assert from_disk.records() == in_memory.records() == maintainer.records()
        assert [r["path"] for r in maintainer.records()] == [
            "4/6/a.csv",
            "4/6/b.csv",
            "4/7/a.csv",
            "x.txt",
        ]


class TestTheMetadataCache:
    def test_it_keeps_what_names_no_moving_ref(self, tmp_path):
        behind = MemorySource({"https://h/v1.0.0/datacatalog.json": b"{}"})
        cached = CachedSource(behind, tmp_path)

        assert cached.read("https://h/v1.0.0/datacatalog.json") == b"{}"
        assert cached.read("https://h/v1.0.0/datacatalog.json") == b"{}"

        assert behind.reads == ["https://h/v1.0.0/datacatalog.json"]

    def test_a_moving_ref_is_read_every_time(self, tmp_path):
        url = "https://h/main/datacatalog.json"
        behind = MemorySource({url: b"{}"})
        cached = CachedSource(behind, tmp_path)

        cached.read(url)
        cached.read(url)

        assert moving(url) and behind.reads == [url, url]

    def test_files_on_disk_are_read_as_they_are(self, tmp_path):
        (tmp_path / "a.json").write_bytes(b"1")

        assert FileSource().read(str(tmp_path / "a.json")) == b"1"
        with pytest.raises(IncompleteCatalog, match="b.json"):
            FileSource().read(str(tmp_path / "b.json"))
