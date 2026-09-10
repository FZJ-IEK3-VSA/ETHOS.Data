"""ethos:uploaded -- retiring source_dir once dCache is the source of truth.

The case this exists for: source_dir points at a shared-storage mount that
nobody promises to keep around forever. Once a dataset has been uploaded and
verified, a rebuild should not need that mount to still exist -- it should
freeze the inventory (paths, hashes, sizes) exactly as last recorded, and only
re-derive the metadata that never depended on the bytes.

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


def make_dataset(workspace: Path, extra_meta: dict, files: dict[str, bytes]) -> tuple[Path, Path]:
    """A throwaway dataset with a real source_dir, ready to build normally."""
    source = workspace / "src"
    source.mkdir()
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    dataset_dir = workspace / "datasets" / "d"
    dataset_dir.mkdir(parents=True)
    meta = {"name": "d", "title": "t", "source_dir": str(source), "ethos:remote_prefix": "d"}
    meta.update(extra_meta)
    (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))
    return dataset_dir, source


def freeze(dataset_dir: Path, title: str | None = None) -> None:
    """Build once normally, then rewrite dataset.yaml to declare ethos:uploaded."""
    files = render_dataset(dataset_dir)
    write_dataset(dataset_dir, files)

    meta = yaml.safe_load((dataset_dir / "dataset.yaml").read_text())
    del meta["source_dir"]
    meta["ethos:uploaded"] = True
    if title is not None:
        meta["title"] = title
    (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))


class TestFreezingAfterUpload:
    def test_rebuild_without_source_dir_reuses_the_same_inventory(self):
        workspace = Path(tempfile.mkdtemp())
        try:
            dataset_dir, source = make_dataset(workspace, {}, {"a.txt": b"hello", "b.txt": b"world"})
            before = json.loads(render_dataset(dataset_dir)["datapackage.json"])
            write_dataset(dataset_dir, {"datapackage.json": json.dumps(before)})

            freeze(dataset_dir)
            shutil.rmtree(source)  # the shared mount really is gone

            after = json.loads(render_dataset(dataset_dir)["datapackage.json"])
            assert after["resources"] == before["resources"]
        finally:
            shutil.rmtree(workspace)

    def test_metadata_can_still_change_once_frozen(self):
        """A typo fix in the title should not need source access either."""
        workspace = Path(tempfile.mkdtemp())
        try:
            dataset_dir, source = make_dataset(workspace, {}, {"a.txt": b"hello"})
            render_dataset(dataset_dir)
            write_dataset(dataset_dir, render_dataset(dataset_dir))
            freeze(dataset_dir, title="Corrected Title")
            shutil.rmtree(source)

            package = json.loads(render_dataset(dataset_dir)["datapackage.json"])
            assert package["title"] == "Corrected Title"
        finally:
            shutil.rmtree(workspace)

    def test_uploaded_and_source_dir_together_is_rejected(self):
        workspace = Path(tempfile.mkdtemp())
        try:
            dataset_dir, _ = make_dataset(workspace, {"ethos:uploaded": True}, {"a.txt": b"hello"})
            with pytest.raises(SystemExit, match="never read again"):
                render_dataset(dataset_dir)
        finally:
            shutil.rmtree(workspace)

    def test_uploaded_with_no_prior_build_is_rejected(self):
        workspace = Path(tempfile.mkdtemp())
        try:
            dataset_dir = workspace / "datasets" / "d"
            dataset_dir.mkdir(parents=True)
            (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump({
                "name": "d", "title": "t", "ethos:remote_prefix": "d", "ethos:uploaded": True,
            }))
            with pytest.raises(SystemExit, match="no datapackage.json to freeze"):
                render_dataset(dataset_dir)
        finally:
            shutil.rmtree(workspace)

    def test_missing_source_dir_without_uploaded_is_a_clear_error(self):
        workspace = Path(tempfile.mkdtemp())
        try:
            dataset_dir = workspace / "datasets" / "d"
            dataset_dir.mkdir(parents=True)
            (dataset_dir / "dataset.yaml").write_text(
                yaml.safe_dump({"name": "d", "title": "t", "ethos:remote_prefix": "d"}))
            with pytest.raises(SystemExit, match="source_dir is required"):
                render_dataset(dataset_dir)
        finally:
            shutil.rmtree(workspace)

    def test_narrowed_licence_does_not_double_up_across_repeated_freezes(self):
        """Each freeze re-applies licences from scratch, not on top of the last one."""
        workspace = Path(tempfile.mkdtemp())
        try:
            dataset_dir, source = make_dataset(
                workspace,
                {"licenses": [{"name": "CC-BY-4.0", "ethos:applies_to": ["a.txt"]}]},
                {"a.txt": b"hello"},
            )
            write_dataset(dataset_dir, render_dataset(dataset_dir))
            freeze(dataset_dir)
            shutil.rmtree(source)

            write_dataset(dataset_dir, render_dataset(dataset_dir))
            package = json.loads(render_dataset(dataset_dir)["datapackage.json"])
            assert package["resources"][0]["licenses"] == [{"name": "CC-BY-4.0"}]
        finally:
            shutil.rmtree(workspace)

    def test_sharded_dataset_freezes_to_the_same_shards(self):
        workspace = Path(tempfile.mkdtemp())
        try:
            dataset_dir, source = make_dataset(
                workspace,
                {"ethos:shard_depth": 1},
                {"2019/a.tif": b"x", "2020/a.tif": b"y"},
            )
            before_files = render_dataset(dataset_dir)
            write_dataset(dataset_dir, before_files)
            freeze(dataset_dir)
            shutil.rmtree(source)

            after_files = render_dataset(dataset_dir)
            before_package = json.loads(before_files["datapackage.json"])
            after_package = json.loads(after_files["datapackage.json"])
            assert after_package["ethos:shards"] == before_package["ethos:shards"]
            for shard in after_package["ethos:shards"]:
                assert after_files[shard["path"]] == before_files[shard["path"]]
        finally:
            shutil.rmtree(workspace)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
