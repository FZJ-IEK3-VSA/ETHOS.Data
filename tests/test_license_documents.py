"""The digest of an archived licence document is derived by the build; a hand-written one is a pin.

Three catalogued documents once carried a hash no version of their file ever had,
and nothing noticed until a bundle export checked. A licence document is a file
the catalogue ships, so its digest is taken from the file exactly as a resource's
is. Writing one into dataset.yaml is still allowed: it says "these are the terms
somebody reviewed", and the build verifies it rather than copying it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ethos_data.maintain.manifest import render_dataset
from ethos_data.maintain.manifest import run as build_run
from ethos_data.maintain.manifest import write_dataset

TERMS = b"You may use these bytes, with attribution.\n"
DIGEST = hashlib.sha256(TERMS).hexdigest()
CATALOG = "name: t\nethos:catalog_role: source\nethos:publication_url: https://example.invalid/store\n"


def _catalogue(root: Path, licence_yaml: str) -> Path:
    """A one-dataset source catalogue whose licence block is ``licence_yaml``."""
    source = root / "src"
    source.mkdir(parents=True)
    (source / "a.txt").write_bytes(b"hello")
    dataset = root / "datasets" / "d"
    (dataset / "licenses").mkdir(parents=True)
    (dataset / "licenses" / "terms.txt").write_bytes(TERMS)
    (root / "catalog.yaml").write_text(CATALOG, encoding="utf-8")
    (dataset / "dataset.yaml").write_text(
        "name: d\ntitle: T\ndescription: D\n"
        f"source_dir: {source.as_posix()}\nethos:remote_prefix: d\n" + licence_yaml,
        encoding="utf-8",
    )
    return root


def _licence(*extra: str) -> str:
    lines = [
        "licenses:",
        "  - name: Bespoke",
        "    path: https://example.invalid/terms",
        *extra,
        "",
    ]
    return "\n".join(lines)


def _package(root: Path) -> dict:
    return json.loads(render_dataset(root / "datasets" / "d")["datapackage.json"])


def test_the_digest_is_derived_from_the_archived_file(tmp_path):
    root = _catalogue(tmp_path, _licence("    ethos:document: licenses/terms.txt"))
    licence = _package(root)["licenses"][0]
    assert licence["ethos:document"] == "licenses/terms.txt"
    assert licence["ethos:document_sha256"] == DIGEST


@pytest.mark.parametrize("spelling", [DIGEST, DIGEST.upper(), "sha256:" + DIGEST])
def test_a_matching_pin_is_verified_and_kept_canonical(tmp_path, spelling):
    root = _catalogue(
        tmp_path,
        _licence(
            "    ethos:document: licenses/terms.txt",
            f"    ethos:document_sha256: {spelling}",
        ),
    )
    assert _package(root)["licenses"][0]["ethos:document_sha256"] == DIGEST


def test_a_stale_pin_stops_the_build_and_says_what_to_do(tmp_path):
    stale = "f" * 64
    root = _catalogue(
        tmp_path,
        _licence(
            "    ethos:document: licenses/terms.txt",
            f"    ethos:document_sha256: {stale}",
        ),
    )
    with pytest.raises(SystemExit) as stopped:
        _package(root)
    message = str(stopped.value)
    assert DIGEST in message and stale in message
    assert "delete ethos:document_sha256" in message
    assert "licenses/terms.txt" in message


def test_an_unquoted_all_digit_pin_is_refused_rather_than_misread(tmp_path):
    """YAML reads 0000...0 as an integer; comparing it would silently never match."""
    root = _catalogue(
        tmp_path,
        _licence(
            "    ethos:document: licenses/terms.txt",
            "    ethos:document_sha256: " + "0" * 64,
        ),
    )
    with pytest.raises(SystemExit, match="in quotes"):
        _package(root)


def test_a_missing_document_fails_in_the_build_not_in_publish(tmp_path):
    root = _catalogue(tmp_path, _licence("    ethos:document: licenses/absent.txt"))
    with pytest.raises(SystemExit, match="licenses/absent.txt"):
        _package(root)


def test_a_hash_with_no_document_to_hash_is_refused(tmp_path):
    root = _catalogue(tmp_path, _licence(f"    ethos:document_sha256: {DIGEST}"))
    with pytest.raises(SystemExit, match="ethos:document"):
        _package(root)


@pytest.mark.parametrize(
    "outside", ["../terms.txt", "/etc/terms.txt", "C:/terms.txt", "licenses/../../x"]
)
def test_a_document_outside_the_dataset_directory_is_refused(tmp_path, outside):
    root = _catalogue(tmp_path, _licence(f"    ethos:document: {outside}"))
    with pytest.raises(SystemExit, match="relative path inside the dataset directory"):
        _package(root)


def test_the_documents_digest_is_written_and_a_changed_text_is_reported_stale(tmp_path):
    """--check re-hashes the archived text like everything else it regenerates."""
    root = _catalogue(tmp_path, _licence("    ethos:document: licenses/terms.txt"))
    assert build_run(root, []) == 0
    on_disk = json.loads(
        (root / "datasets" / "d" / "datapackage.json").read_text(encoding="utf-8")
    )
    assert on_disk["licenses"][0]["ethos:document_sha256"] == DIGEST
    assert build_run(root, [], check=True) == 0

    (root / "datasets" / "d" / "licenses" / "terms.txt").write_bytes(
        TERMS + b"revised upstream\n"
    )
    assert build_run(root, [], check=True) == 1
    assert build_run(root, []) == 0
    rebuilt = json.loads(
        (root / "datasets" / "d" / "datapackage.json").read_text(encoding="utf-8")
    )
    assert rebuilt["licenses"][0]["ethos:document_sha256"] != DIGEST


def test_a_narrowed_licence_carries_the_digest_onto_its_files(tmp_path):
    """The per-resource copy is taken after hashing, so files see the same digest."""
    root = _catalogue(
        tmp_path,
        _licence(
            "    ethos:document: licenses/terms.txt", '    ethos:applies_to: ["a.txt"]'
        ),
    )
    files = render_dataset(root / "datasets" / "d")
    write_dataset(root / "datasets" / "d", files)
    package = json.loads(files["datapackage.json"])
    assert package["resources"][0]["licenses"][0]["ethos:document_sha256"] == DIGEST
