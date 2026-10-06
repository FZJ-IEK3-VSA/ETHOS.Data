"""Retiring source_dir once dCache holds the authoritative copy.

The case this exists for: source_dir points at a shared-storage mount that
nobody promises to keep around forever. Once a dataset has been uploaded and
verified, ``catalog record`` freezes it, and a rebuild does not need that
mount: it keeps the inventory (paths, hashes, sizes) exactly as last recorded,
and re-derives only the metadata that never depended on the bytes.

Run with pytest, or directly:  python tests/test_uploaded.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from ethos_data.maintain.manifest import render_dataset, write_dataset


def make_dataset(
    workspace: Path, extra_meta: dict, files: dict[str, bytes]
) -> tuple[Path, Path]:
    """A throwaway draft with a real source_dir, ready to build normally."""
    source = workspace / "src"
    source.mkdir()
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    dataset_dir = workspace / "datasets" / "d"
    dataset_dir.mkdir(parents=True)
    meta = {"name": "d", "title": "t", "ethos:remote_prefix": "d"}
    meta.update(extra_meta)
    (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))
    (dataset_dir / "status.yaml").write_text(
        yaml.safe_dump({"state": "draft", "source_dir": str(source)})
    )
    return dataset_dir, source


def freeze(dataset_dir: Path, title: str | None = None) -> None:
    """Build once normally, then record the upload as the authoritative copy."""
    write_dataset(dataset_dir, render_dataset(dataset_dir))
    location = "https://store.invalid/ethos-data/d/"
    (dataset_dir / "status.yaml").write_text(
        yaml.safe_dump(
            {
                "state": "frozen",
                "authority": location,
                "copies": [{"kind": "uploaded", "location": location}],
            }
        )
    )
    if title is not None:
        meta = yaml.safe_load((dataset_dir / "dataset.yaml").read_text())
        meta["title"] = title
        (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))


@pytest.fixture
def workspace():
    path = Path(tempfile.mkdtemp())
    yield path
    shutil.rmtree(path)


class TestFreezingAfterUpload:
    def test_rebuild_without_source_dir_reuses_the_same_inventory(self, workspace):
        dataset_dir, source = make_dataset(
            workspace, {}, {"a.txt": b"hello", "b.txt": b"world"}
        )
        before = json.loads(render_dataset(dataset_dir)["datapackage.json"])

        freeze(dataset_dir)
        shutil.rmtree(source)  # the shared mount really is gone

        after = json.loads(render_dataset(dataset_dir)["datapackage.json"])
        assert after["resources"] == before["resources"]

    def test_metadata_can_still_change_once_frozen(self, workspace):
        """A typo fix in the title needs no access to the source either."""
        dataset_dir, source = make_dataset(workspace, {}, {"a.txt": b"hello"})
        freeze(dataset_dir, title="Corrected Title")
        shutil.rmtree(source)

        package = json.loads(render_dataset(dataset_dir)["datapackage.json"])
        assert package["title"] == "Corrected Title"

    def test_narrowed_licence_does_not_double_up_across_repeated_freezes(
        self, workspace
    ):
        """Each rebuild applies the licences from scratch, not on top of the last."""
        dataset_dir, source = make_dataset(
            workspace,
            {"licenses": [{"name": "CC-BY-4.0", "ethos:applies_to": ["a.txt"]}]},
            {"a.txt": b"hello"},
        )
        freeze(dataset_dir)
        shutil.rmtree(source)

        write_dataset(dataset_dir, render_dataset(dataset_dir))
        package = json.loads(render_dataset(dataset_dir)["datapackage.json"])
        assert package["resources"][0]["licenses"] == [{"name": "CC-BY-4.0"}]

    def test_sharded_dataset_freezes_to_the_same_shards(self, workspace):
        dataset_dir, source = make_dataset(
            workspace,
            {"ethos:shard_depth": 1},
            {"2019/a.tif": b"x", "2020/a.tif": b"y"},
        )
        before_files = render_dataset(dataset_dir)
        freeze(dataset_dir)
        shutil.rmtree(source)

        after_files = render_dataset(dataset_dir)
        before_package = json.loads(before_files["datapackage.json"])
        after_package = json.loads(after_files["datapackage.json"])
        assert after_package["ethos:shards"] == before_package["ethos:shards"]
        for shard in after_package["ethos:shards"]:
            assert after_files[shard["path"]] == before_files[shard["path"]]


class TestShardDirectory:
    def test_shards_are_written_under_shards(self, workspace):
        dataset_dir, _ = make_dataset(
            workspace,
            {"ethos:shard_depth": 1},
            {"2019/a.tif": b"x", "2020/a.tif": b"y"},
        )
        files = render_dataset(dataset_dir)
        write_dataset(dataset_dir, files)

        package = json.loads(files["datapackage.json"])
        assert [s["path"] for s in package["ethos:shards"]] == [
            "shards/2019.json",
            "shards/2020.json",
        ]
        assert (dataset_dir / "shards" / "2019.json").is_file()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
