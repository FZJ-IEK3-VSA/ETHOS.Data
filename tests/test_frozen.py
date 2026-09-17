"""ethos:frozen -- an inventory that is final, without claiming dCache holds it.

Restricted data is never uploaded: the authorised installation *is* the permanent
copy, and this manifest's hashes are what says it is still intact. Once such a
dataset has been moved into the restricted cache and the original retired, there
is nothing left to build from -- and nothing that should be rebuilt, because a
rebuild re-hashes whatever it is pointed at and would write a corrupted copy's
bytes into the manifest as correct.

``ethos:uploaded`` froze the inventory but said something false about restricted
data. This says the true half on its own.
"""

from __future__ import annotations

import json

import pytest
import yaml

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
    meta = {
        "name": "licensed",
        "title": "Licensed input data",
        "source_dir": str(source),
    }
    meta.update(extra)
    (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))
    return dataset_dir, source


def _rewrite(dataset_dir, **changes):
    meta = yaml.safe_load((dataset_dir / "dataset.yaml").read_text())
    for key, value in changes.items():
        if value is None:
            meta.pop(key.replace("__", ":"), None)
        else:
            meta[key.replace("__", ":")] = value
    (dataset_dir / "dataset.yaml").write_text(yaml.safe_dump(meta))


def _build(dataset_dir) -> dict:
    files = render_dataset(dataset_dir)
    write_dataset(dataset_dir, files)
    return json.loads(files["datapackage.json"])


def test_the_inventory_survives_the_original_going_away(tmp_path):
    dataset_dir, source = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    before = _build(dataset_dir)

    # The installation has been copied into the restricted cache and retired.
    _rewrite(dataset_dir, source_dir=None, ethos__frozen=True)
    import shutil

    shutil.rmtree(source)

    after = _build(dataset_dir)

    assert after["resources"] == before["resources"]
    assert after["ethos:total_bytes"] == before["ethos:total_bytes"]


def test_metadata_is_still_re_derived(tmp_path):
    """Freezing the inventory is not freezing the description."""
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _build(dataset_dir)

    _rewrite(
        dataset_dir,
        source_dir=None,
        ethos__frozen=True,
        title="Licensed input data (2026 agreement)",
    )
    after = _build(dataset_dir)

    assert after["title"] == "Licensed input data (2026 agreement)"


def test_the_hashes_stay_an_independent_witness(tmp_path):
    """The reason to freeze rather than repoint source_dir at the copy.

    A rebuild re-hashes what it is pointed at. Pointed at the copy, it would
    record a corrupted copy's bytes as the truth and destroy the evidence; frozen,
    the manifest still describes what left the original.
    """
    dataset_dir, source = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    before = _build(dataset_dir)

    copy = tmp_path / "restricted-cache" / "licensed"
    copy.mkdir(parents=True)
    (copy / "a.tif").write_bytes(b"corrupted!!!!!")  # same length, different bytes

    # Freezing first, from the inventory as built: the manifest still describes
    # what left the original, so `verify --deep` against the copy can still fail,
    # which is the point.
    _rewrite(dataset_dir, source_dir=None, ethos__frozen=True)
    frozen = _build(dataset_dir)
    assert frozen["resources"][0]["hash"] == before["resources"][0]["hash"]

    # What repointing would have done instead: the corruption becomes the
    # recorded truth, and nothing can tell afterwards.
    _rewrite(dataset_dir, source_dir=str(copy), ethos__frozen=None)
    repointed = _build(dataset_dir)
    assert repointed["resources"][0]["hash"] != before["resources"][0]["hash"]


def test_a_frozen_dataset_may_not_keep_a_source_dir(tmp_path):
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _build(dataset_dir)

    _rewrite(dataset_dir, ethos__frozen=True)

    with pytest.raises(SystemExit, match="never rebuilt from local files"):
        render_dataset(dataset_dir)


def test_freezing_something_never_built_is_refused(tmp_path):
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _rewrite(dataset_dir, source_dir=None, ethos__frozen=True)

    with pytest.raises(SystemExit, match="no datapackage.json to freeze"):
        render_dataset(dataset_dir)


def test_restricted_data_cannot_claim_it_was_uploaded(tmp_path):
    """The freeze was right; the claim attached to it was not."""
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _build(dataset_dir)
    _rewrite(dataset_dir, source_dir=None, ethos__uploaded=True)

    with pytest.raises(SystemExit, match="never uploaded"):
        render_dataset(dataset_dir)


def test_the_refusal_names_the_key_that_is_right(tmp_path):
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _build(dataset_dir)
    _rewrite(dataset_dir, source_dir=None, ethos__uploaded=True)

    with pytest.raises(SystemExit, match="ethos:frozen"):
        render_dataset(dataset_dir)


def test_uploading_still_implies_it(tmp_path):
    """Public data keeps working exactly as it did."""
    dataset_dir, source = _dataset(
        tmp_path, {"ethos:remote_prefix": "licensed"}, {"a.tif": b"public bytes"}
    )
    before = _build(dataset_dir)

    _rewrite(dataset_dir, source_dir=None, ethos__uploaded=True)
    import shutil

    shutil.rmtree(source)

    assert _build(dataset_dir)["resources"] == before["resources"]


def test_neither_key_is_published(tmp_path):
    """Both are maintainer bookkeeping; a consumer never sees them."""
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _build(dataset_dir)
    _rewrite(dataset_dir, source_dir=None, ethos__frozen=True)

    package = _build(dataset_dir)

    assert "ethos:frozen" not in package
    assert "source_dir" not in package


def test_the_message_for_a_missing_source_dir_offers_both(tmp_path):
    dataset_dir, _ = _dataset(tmp_path, RESTRICTED, {"a.tif": b"licensed bytes"})
    _rewrite(dataset_dir, source_dir=None)

    with pytest.raises(SystemExit, match="ethos:frozen"):
        render_dataset(dataset_dir)
