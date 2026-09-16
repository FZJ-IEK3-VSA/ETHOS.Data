"""The repository workflow stays offline once a bundle has been exported."""

import hashlib
import json
import urllib.request

import pytest

from ethos_data import config
from ethos_data.cli import main
from ethos_data.bundles import ModifiedBundleWarning


def test_cli_export_verify_development_override(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "load_config", lambda: ({}, {}))

    def no_network(*args, **kwargs):
        pytest.fail("fixture workflow attempted network access")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    source = tmp_path / "source"
    source.mkdir()
    (source / "value.txt").write_bytes(b"3")
    package = {
        "name": "lesson",
        "ethos:access": "public",
        "ethos:license_status": "resolved",
        "resources": [
            {
                "name": "value",
                "path": "value.txt",
                "bytes": 1,
                "hash": "sha256:" + hashlib.sha256(b"3").hexdigest(),
            }
        ],
    }
    (tmp_path / "datapackage.json").write_text(json.dumps(package))
    (tmp_path / "datacatalog.json").write_text(
        json.dumps(
            {
                "ethos:publication_url": "https://example.invalid/data",
                "datasets": [
                    {
                        "name": "lesson",
                        "path": "datapackage.json",
                        "ethos:access": "public",
                    }
                ],
            }
        )
    )
    collections = tmp_path / "collections.yaml"
    collections.write_text(
        "catalog: datacatalog.json\ncollections:\n  small:\n    include:\n      - dataset: lesson\n"
    )
    target = tmp_path / "bundle"
    assert (
        main(
            [
                "-c",
                str(collections),
                "bundle",
                "export",
                str(target),
                "small",
                "--source-root",
                f"lesson={source}",
                "--source-revision",
                "test",
            ]
        )
        == 0
    )
    snapshot = (target / "bundle.json").read_bytes()
    assert main(["bundle", "verify", str(target), "small"]) == 0
    fixture = target / "data/lesson/value.txt"
    fixture.write_bytes(b"4")
    assert main(["bundle", "verify", str(target), "small"]) == 1
    assert main(["bundle", "fetch", str(target), "small"]) == 2
    with pytest.warns(ModifiedBundleWarning, match="lesson/value.txt"):
        assert main(["bundle", "fetch", str(target), "small", "--allow-modified"]) == 0
    assert (target / "bundle.json").read_bytes() == snapshot
    assert fixture.read_bytes() == b"4"
    fixture.unlink()
    assert main(["bundle", "fetch", str(target), "small", "--allow-modified"]) == 2
    assert "missing" in capsys.readouterr().err
