"""Builders the tests share: synthetic catalogues and a local published store.

Two halves, like the package:

* :class:`ReaderCatalogue` writes what a reader sees: a ``datacatalog.json``
  index, one ``datapackage.json`` per dataset, and the bytes, in the public
  cache, on the published store, or both.
* :class:`SourceCatalogue` writes what a catalogue maintainer works on:
  ``catalog.yaml``, and per dataset a ``dataset.yaml`` and the ``status.yaml``
  naming its source directory. It drives the real ``ethos-data catalog``
  commands against them.

:class:`Store` serves a directory over HTTP on the loopback interface, which is
the one place the network guard in ``conftest.py`` lets a test connect to. A
test can therefore run the real download path, checksums and all, offline.

Everything here goes through the public entry points, the ``ethos-data``
command and the ``ethos_data`` package, so the tests that use it keep their
meaning while the code behind those entry points is rearranged.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import http.server
import io
import json
import textwrap
import threading
from pathlib import Path

import pytest
import yaml

from ethos_data.cli import main

#: What every source dataset carries unless a test says otherwise: settled
#: licensing, so that upload and link do not refuse it.
DEFAULT_LICENSES = [
    {"name": "CC-BY-4.0", "path": "https://creativecommons.org/licenses/by/4.0/"}
]


def as_bytes(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode("utf-8")


def digest(content: bytes | str) -> str:
    """The catalogue's spelling of a file's hash."""
    return "sha256:" + hashlib.sha256(as_bytes(content)).hexdigest()


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    """Run ``ethos-data`` as a process would: exit code, standard output, standard error.

    A ``SystemExit`` carrying a message is what the interpreter turns into exit
    status 1 with the message on standard error, so it is reported that way.
    Tests written against this keep their meaning when library code stops
    exiting the process and the command line reports the same refusal itself.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as stop:
            if isinstance(stop.code, int) or stop.code is None:
                code = stop.code or 0
            else:
                print(stop.code, file=err)
                code = 1
    return code, out.getvalue(), err.getvalue()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the store's directory and remembers what was asked for."""

    def log_message(self, format, *args):
        pass

    def send_head(self):
        self.server.requests.append((self.command, self.path))
        return super().send_head()


class Store:
    """The published store's stand-in: a directory served over loopback HTTP.

    Objects live at ``<root>/<remote prefix>/<resource path>``, exactly as on
    dCache below the publication root, and ``url`` is that publication root.
    ``requests`` lists every ``(method, path)`` the server answered, so a test
    can tell a download from a cache hit.
    """

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        handler = functools.partial(_QuietHandler, directory=str(root))
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.requests = []
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )
        self._thread.start()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def requests(self) -> list[tuple[str, str]]:
        return self._server.requests

    def downloads(self) -> list[str]:
        """The paths fetched with GET, in order."""
        return [path for method, path in self.requests if method == "GET"]

    def put(self, prefix: str, relative: str, content: bytes | str) -> Path:
        target = self.root / prefix / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(as_bytes(content))
        return target

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class ReaderCatalogue:
    """A catalogue as a reader sees it, written into ``<root>/catalogue``.

    ``cache`` is the public cache the ``reader`` fixture points
    ``$ETHOS_DATA_DIR`` at. Call :meth:`write` after the last dataset; it may be
    called again after adding more.
    """

    def __init__(
        self,
        root: Path,
        store: Store | None = None,
        environment: pytest.MonkeyPatch | None = None,
    ):
        self.root = root / "catalogue"
        self.environment = environment
        self.cache = root / "cache"
        self.store = store
        self.publication_url = store.url if store else "https://example.invalid"
        self.entries: list[dict] = []
        self.index = self.root / "datacatalog.json"

    def dataset(
        self,
        name: str,
        files: dict[str, bytes | str],
        *,
        access: str = "public",
        visibility: str = "public",
        where: str = "cache",
        license_status: str = "resolved",
        sidecars: dict[str, list[str]] | None = None,
        descriptor: dict | None = None,
        index: dict | None = None,
        remote_prefix: str | None = None,
    ) -> dict[str, dict]:
        """Describe one dataset and put its bytes ``where``: cache, store, both or nowhere.

        Returns the resource records by path, hashes included.
        """
        prefix = remote_prefix or name
        records = {}
        for relative, content in files.items():
            data = as_bytes(content)
            record = {
                "name": relative.replace("/", "-").lower(),
                "path": relative,
                "bytes": len(data),
                "hash": digest(data),
                "mediatype": "application/octet-stream",
            }
            if sidecars and relative in sidecars:
                record["ethos:sidecars"] = sidecars[relative]
            records[relative] = record
            if where in ("cache", "both"):
                target = self.cache / name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            if where in ("store", "both"):
                assert self.store is not None, "this catalogue has no store"
                self.store.put(prefix, relative, data)
        package = {
            "name": name,
            "ethos:access": access,
            "ethos:visibility": visibility,
            **(descriptor or {}),
            "resources": list(records.values()),
        }
        path = self.root / "datasets" / name / "datapackage.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(package, indent=2), encoding="utf-8")
        self.entries.append(
            {
                "name": name,
                "path": f"datasets/{name}/datapackage.json",
                "title": (descriptor or {}).get("title", name),
                "ethos:access": access,
                "ethos:visibility": visibility,
                "ethos:total_bytes": sum(r["bytes"] for r in records.values()),
                "ethos:file_count": len(records),
                "ethos:remote_prefix": prefix,
                "ethos:license_status": license_status,
                **(index or {}),
            }
        )
        return records

    def namespace(self, name: str, title: str = "") -> None:
        path = self.root / "datasets" / name / "datapackage.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": name, "ethos:namespace": True}))
        self.entries.append(
            {
                "name": name,
                "path": f"datasets/{name}/datapackage.json",
                "title": title or name,
                "ethos:namespace": True,
            }
        )

    def write(self, **catalog: object) -> Path:
        self.index.parent.mkdir(parents=True, exist_ok=True)
        self.index.write_text(
            json.dumps(
                {
                    "name": "test",
                    "ethos:publication_url": self.publication_url,
                    **catalog,
                    "datasets": self.entries,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return self.index

    def collections(self, body: str, name: str = "collections.yaml") -> Path:
        """A collections file with ``body`` under ``collections:``.

        The catalogue it reads is this one, named by ``$ETHOS_DATA_CATALOG``
        as a user's settings would name it.
        """
        self.write()
        assert self.environment is not None, "built without the reader fixture"
        self.environment.setenv("ETHOS_DATA_CATALOG", str(self.index))
        path = self.root.parent / name
        path.write_text(
            "collections:\n"
            + textwrap.indent(textwrap.dedent(body).strip("\n") + "\n", "  "),
            encoding="utf-8",
        )
        return path


class SourceCatalogue:
    """A source catalogue checkout in ``<root>/source``, built with the real commands.

    Source bytes go to ``<root>/bytes/<dataset>``, outside the checkout, as a
    maintainer's candidate directories do.
    """

    def __init__(
        self,
        root: Path,
        *,
        publication_url: str = "https://example.invalid/ethos-data",
        **catalog: object,
    ):
        self.root = root / "source"
        self.bytes = root / "bytes"
        (self.root / "datasets").mkdir(parents=True, exist_ok=True)
        self.catalog_yaml = {
            "name": "test-catalogue",
            "title": "Test catalogue",
            "ethos:publication_url": publication_url,
            "ethos:contact": "maintainers",
            **catalog,
        }
        self._write_yaml(self.root / "catalog.yaml", self.catalog_yaml)

    @staticmethod
    def _write_yaml(path: Path, document: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def directory(self, name: str) -> Path:
        return self.root / "datasets" / name

    def dataset(
        self,
        name: str,
        files: dict[str, bytes | str] | None = None,
        *,
        documents: dict[str, bytes | str] | None = None,
        legacy: bool = False,
        **meta: object,
    ) -> Path:
        """Describe a dataset; ``files`` become its ``source_dir`` unless ``meta`` names one.

        Keyword arguments are descriptor keys, with ``ethos_access`` meaning
        ``ethos:access``: an underscore after a leading ``ethos`` is the colon.
        ``documents`` are archived licence files written beside ``dataset.yaml``.

        The ``source_dir`` goes into a ``status.yaml`` saying the dataset is a
        draft, as a catalogue keeps it. ``legacy=True`` writes it into
        ``dataset.yaml`` instead, as before status files, where
        ``ethos_uploaded`` and ``ethos_frozen`` belong too.
        """
        descriptor: dict = {"title": f"The {name} dataset"}
        descriptor["licenses"] = DEFAULT_LICENSES
        for key, value in meta.items():
            descriptor[_key(key)] = value
        if files is not None and "source_dir" not in descriptor:
            source = self.bytes / name
            for relative, content in files.items():
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(as_bytes(content))
            descriptor["source_dir"] = str(source)
        for key in [k for k, v in descriptor.items() if v is None]:
            del descriptor[key]
        if not legacy and {"ethos:uploaded", "ethos:frozen"} & set(descriptor):
            raise TypeError("ethos:uploaded and ethos:frozen need legacy=True")
        source_dir = None if legacy else descriptor.pop("source_dir", None)
        directory = self.directory(name)
        for relative, content in (documents or {}).items():
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(as_bytes(content))
        self._write_yaml(directory / "dataset.yaml", descriptor)
        if source_dir is not None:
            self._write_yaml(
                directory / "status.yaml", {"state": "draft", "source_dir": source_dir}
            )
        return directory

    def status(self, name: str) -> dict:
        """The dataset's ``status.yaml``, as its keys and values."""
        return yaml.safe_load(
            (self.directory(name) / "status.yaml").read_text(encoding="utf-8")
        )

    def freeze(self, name: str, *, location: str | None = None) -> str:
        """Record a built dataset as frozen, its upload the authoritative copy.

        What ``catalog record`` writes, without the upload and the check that
        come before it. ``location`` defaults to the dataset's folder under the
        publication URL; it is returned.
        """
        location = location or f"{self.catalog_yaml['ethos:publication_url']}/{name}/"
        self._write_yaml(
            self.directory(name) / "status.yaml",
            {
                "state": "frozen",
                "authority": location,
                "copies": [{"kind": "uploaded", "location": location}],
            },
        )
        return location

    def edit(self, name: str, **changes: object) -> None:
        """Change keys of a ``dataset.yaml``; a value of ``None`` removes the key."""
        path = self.directory(name) / "dataset.yaml"
        descriptor = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, value in changes.items():
            if value is None:
                descriptor.pop(_key(key), None)
            else:
                descriptor[_key(key)] = value
        self._write_yaml(path, descriptor)

    def namespace(self, name: str, **meta: object) -> Path:
        directory = self.directory(name)
        self._write_yaml(
            directory / "dataset.yaml",
            {"title": f"The {name} family", **{_key(k): v for k, v in meta.items()}},
        )
        return directory

    def catalog(self, *args: str) -> tuple[int, str, str]:
        return run_cli(["catalog", "--catalog-root", str(self.root), *args])

    def build(self, *names: str, check: bool = False) -> tuple[int, str, str]:
        return self.catalog("build", *names, *(["--check"] if check else []))

    def publish(self, target: Path, check: bool = False) -> tuple[int, str, str]:
        return self.catalog("publish", str(target), *(["--check"] if check else []))

    def index(self) -> dict:
        return json.loads((self.root / "datacatalog.json").read_text(encoding="utf-8"))

    def package(self, name: str) -> dict:
        return json.loads(
            (self.directory(name) / "datapackage.json").read_text(encoding="utf-8")
        )


def _key(spelling: str) -> str:
    """``ethos_access`` -> ``ethos:access``; every other keyword stays as written."""
    if spelling.startswith("ethos_"):
        return "ethos:" + spelling.removeprefix("ethos_")
    return spelling
