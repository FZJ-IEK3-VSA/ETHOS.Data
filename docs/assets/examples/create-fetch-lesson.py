"""Create the disposable, synthetic inputs for the first-fetch tutorial."""

import hashlib
import json
from pathlib import Path


def create_lesson(destination: Path) -> None:
    destination = destination.resolve()
    destination.mkdir()  # Refuse an existing lesson rather than replace work.
    data = b"station,value\nA,12.5\nB,13.0\n"
    dataset = "lesson-stations"
    source = destination / "server" / "data" / dataset
    source.mkdir(parents=True)
    (source / "temperatures.csv").write_bytes(data)
    catalogue = destination / "catalogue"
    catalogue.mkdir()
    package = {
        "name": dataset,
        "title": "Invented station observations",
        "ethos:access": "public",
        "ethos:visibility": "public",
        "ethos:license_status": "resolved",
        "licenses": [{"name": "CC0-1.0"}],
        "resources": [
            {
                "name": "temperatures",
                "path": "temperatures.csv",
                "bytes": len(data),
                "hash": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        ],
    }
    index = {
        "name": "first-fetch-lesson",
        "ethos:publication_url": "http://127.0.0.1:8765/data",
        "datasets": [
            {
                "name": dataset,
                "path": "datapackage.json",
                "ethos:access": "public",
                "ethos:remote_prefix": dataset,
                "ethos:license_status": "resolved",
            }
        ],
    }
    for name, content in (("datapackage.json", package), ("datacatalog.json", index)):
        (catalogue / name).write_text(
            json.dumps(content, indent=2) + "\n", encoding="utf-8"
        )
    (destination / "collections.yaml").write_text(
        "catalog: catalogue/datacatalog.json\ncollections:\n"
        "  observations:\n    include:\n      - dataset: lesson-stations\n",
        encoding="utf-8",
    )
    # The access lesson uses synthetic restricted data, never a real licence.
    restricted = destination / "restricted-installation" / "lesson-licensed"
    restricted.mkdir(parents=True)
    restricted_bytes = b"factor\n2\n"
    (restricted / "factor.csv").write_bytes(restricted_bytes)
    internal = destination / "internal-catalogue"
    internal.mkdir()
    (internal / "datapackage.json").write_text(json.dumps(package), encoding="utf-8")
    restricted_package = {
        "name": "lesson-licensed",
        "title": "Synthetic access-control example",
        "ethos:access": "restricted",
        "ethos:visibility": "hidden",
        "ethos:license_status": "resolved",
        "ethos:restriction": "Practice data: use the lesson's restricted-installation directory.",
        "licenses": [{"name": "CC0-1.0"}],
        "resources": [
            {
                "name": "factor",
                "path": "factor.csv",
                "bytes": len(restricted_bytes),
                "hash": "sha256:" + hashlib.sha256(restricted_bytes).hexdigest(),
            }
        ],
    }
    (internal / "restricted.json").write_text(
        json.dumps(restricted_package), encoding="utf-8"
    )
    internal_index = {
        **index,
        "datasets": [
            *index["datasets"],
            {
                "name": "lesson-licensed",
                "path": "restricted.json",
                "ethos:access": "restricted",
                "ethos:license_status": "resolved",
            },
        ],
    }
    (internal / "datacatalog.json").write_text(
        json.dumps(internal_index), encoding="utf-8"
    )
    (destination / "restricted-collections.yaml").write_text(
        "catalog: internal-catalogue/datacatalog.json\ncollections:\n"
        "  licensed_input:\n    include:\n      - dataset: lesson-licensed\n",
        encoding="utf-8",
    )
    # Give project-scoped lesson commands a local file to update.
    (destination / "ethos-data.yaml").write_text(
        "publication_url: http://127.0.0.1:8765/data\nskip_unavailable: false\n",
        encoding="utf-8",
    )
    print(f"Created {destination}")


if __name__ == "__main__":
    create_lesson(Path("first-fetch-lesson"))
