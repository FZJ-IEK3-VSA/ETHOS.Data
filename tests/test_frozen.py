"""A frozen dataset: its inventory is final, and its build input is retired.

Restricted data is never uploaded: the authorised installation *is* the
permanent copy, and the inventory's hashes are what says it is still intact.
Once the original is retired, there is nothing left to build from -- and
nothing that should be rebuilt, because a rebuild re-hashes whatever it is
pointed at and would write a corrupted copy's bytes into the inventory as
correct. The dataset's ``status.yaml`` says it is frozen.
"""

from __future__ import annotations

import json
import shutil

import pytest
import yaml

from ethos_data.errors import DescriptorError
from ethos_data.maintain.manifest import render_dataset, write_dataset

RESTRICTED = {
    "ethos:access": "restricted",
    "ethos:visibility": "hidden",
    "ethos:embargo": {
        "until": "unspecified",
        "reason": "vendor agreement",
        "becomes": "restricted",
    },
    "licenses": [{"name": "vendor-agreement-2026"}],
}


def _dataset(tmp_path, extra: dict, files: dict[str, bytes]):
    source = tmp_path / "installation"
    source.mkdir()
    for name, content in files.items():
        (source / name).write_bytes(content)

    dataset_dir = tmp_path / "datasets" / "licensed"
    dataset_dir.mkdir(parents=True)
    meta = {"name": "licensed", "title": "Licensed input data", **extra}
    (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))
    _status(dataset_dir, state="draft", source_dir=str(source))
    return dataset_dir, source


def _status(dataset_dir, **status):
    (dataset_dir / "status.yaml").write_text(yaml.safe_dump(status))


def _freeze(dataset_dir):
    """What ``catalog record`` leaves: frozen, its installation the authority."""
    _status(
        dataset_dir,
        state="frozen",
        authority="/restricted/licensed",
        copies=[
            {
                "kind": "linked",
                "location": "/restricted/licensed",
                "target": "/installation",
            }
        ],
    )


def _rewrite(dataset_dir, **changes):
    meta = yaml.safe_load((dataset_dir / "dataset.yaml").read_text())
    meta.update(changes)
    (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))


def _build(dataset_dir) -> dict:
    files = render_dataset(dataset_dir)
    write_dataset(dataset_dir, files)
    return json.loads(files["datapackage.json"])


def test_the_inventory_survives_the_original_going_away(tmp_path):
    dataset_dir, source = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    before = _build(dataset_dir)

    _freeze(dataset_dir)
    shutil.rmtree(source)
    after = _build(dataset_dir)

    assert after["resources"] == before["resources"]
    assert after["ethos:total_bytes"] == before["ethos:total_bytes"]


def test_metadata_is_still_re_derived(tmp_path):
    """Freezing the inventory is not freezing the description."""
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _build(dataset_dir)

    _freeze(dataset_dir)
    _rewrite(dataset_dir, title="Licensed input data (2026 agreement)")
    after = _build(dataset_dir)

    assert after["title"] == "Licensed input data (2026 agreement)"


def test_the_hashes_stay_an_independent_witness(tmp_path):
    """The reason to freeze rather than point source_dir at the copy.

    A rebuild re-hashes what it is pointed at. Pointed at the copy, it would
    record a corrupted copy's bytes as the truth and destroy the evidence;
    frozen, the inventory still describes what left the original.
    """
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    before = _build(dataset_dir)

    copy = tmp_path / "restricted-cache" / "licensed"
    copy.mkdir(parents=True)
    (copy / "a.tif").write_bytes(b"corrupted!!!!!")  # same length, other bytes

    _freeze(dataset_dir)
    frozen = _build(dataset_dir)
    assert frozen["resources"][0]["hash"] == before["resources"][0]["hash"]

    # What pointing the build at the copy would do: the corruption becomes the
    # recorded truth, and nothing can tell afterwards.
    _status(dataset_dir, state="built", source_dir=str(copy))
    repointed = _build(dataset_dir)
    assert repointed["resources"][0]["hash"] != before["resources"][0]["hash"]


def test_freezing_something_never_built_is_refused(tmp_path):
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _freeze(dataset_dir)

    with pytest.raises(DescriptorError, match="no datapackage.json to freeze"):
        render_dataset(dataset_dir)


def test_a_source_dir_in_the_description_is_refused(tmp_path):
    """The status file is the one record of where the bytes are."""
    dataset_dir, source = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _build(dataset_dir)
    _freeze(dataset_dir)
    _rewrite(dataset_dir, source_dir=str(source))

    with pytest.raises(DescriptorError, match="ethos-data catalog migrate licensed"):
        render_dataset(dataset_dir)


def test_nothing_about_the_state_is_published(tmp_path):
    """The status file is maintainer bookkeeping; a consumer never sees it."""
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _build(dataset_dir)
    _freeze(dataset_dir)

    package = _build(dataset_dir)

    assert not {"source_dir", "state", "authority", "copies"} & set(package)
