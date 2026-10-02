"""Fixtures every test gets, and the builders tests ask for by name.

Two guarantees apply to every test without being asked for:

* **No network.** A connection or a name lookup for anything but the loopback
  interface fails, so a test that would quietly fall back to the public
  catalogue or reach dCache fails instead. The local :class:`support.Store`
  serves on loopback and keeps working.
* **No dCache.** rclone and ``oidc-token`` are never run: code that
  uploads is handed a :class:`~ethos_data.adapters.fakes.FakeStore`.
* **No settings from the person running the tests.** Every ``ETHOS_*``
  variable is cleared, and the settings files and the default cache directory
  are moved into a temporary directory. Without this a configured catalogue on
  the developer's account replaces the catalogue a test wrote, and a test
  writes into the developer's real cache.
"""

from __future__ import annotations

import errno
import socket
import types

import platformdirs
import pytest
from support import ReaderCatalogue, SourceCatalogue, Store

from ethos_data import config

#: Every variable that changes what ethos_data reads or where it writes.
ETHOS_VARIABLES = (
    "ETHOS_DATA_DIR",
    "ETHOS_RESTRICTED_DIR",
    "ETHOS_STAGING_DIR",
    "ETHOS_DATA_CATALOG",
    "ETHOS_PUBLICATION_URL",
    "ETHOS_SKIP_UNAVAILABLE",
    "ETHOS_CATALOG_NO_CACHE",
    "ETHOS_DATA_CONFIG",
    "ETHOS_DATA_DOWNLOAD",
)

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host in _LOOPBACK:
            return real_connect(self, address)
        raise OSError(errno.ENETUNREACH, f"tests do not reach the network: {address}")

    def getaddrinfo(host, *args, **kwargs):
        if host is None or host in _LOOPBACK:
            return real_getaddrinfo(host, *args, **kwargs)
        raise socket.gaierror(socket.EAI_NONAME, f"tests do not resolve {host}")

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


@pytest.fixture(autouse=True)
def _no_dcache(monkeypatch):
    """No test runs rclone or oidc-token: dCache is a FakeStore in tests."""
    from ethos_data.adapters import dcache

    def refuse(command, *args, **kwargs):
        raise AssertionError(
            f"tests do not run {command[0]}; give the code under test a FakeStore"
        )

    monkeypatch.setattr(dcache, "_run", refuse)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("settings")
    for variable in ETHOS_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(
        platformdirs, "user_config_dir", lambda *a, **k: str(home / "user-config")
    )
    monkeypatch.setattr(
        platformdirs, "site_config_dir", lambda *a, **k: str(home / "site-config")
    )
    monkeypatch.setattr(
        platformdirs, "user_cache_dir", lambda *a, **k: str(home / "user-cache")
    )
    # The environment scope lives under sys.prefix, which config reads for
    # nothing else.
    monkeypatch.setattr(config, "sys", types.SimpleNamespace(prefix=str(home / "env")))
    return home


@pytest.fixture
def store(tmp_path):
    """A published store on loopback HTTP; see :class:`support.Store`."""
    served = Store(tmp_path / "store")
    yield served
    served.close()


@pytest.fixture
def reader(tmp_path, monkeypatch, store):
    """A reader-side catalogue whose public cache is ``$ETHOS_DATA_DIR``."""
    built = ReaderCatalogue(tmp_path, store)
    monkeypatch.setenv("ETHOS_DATA_DIR", str(built.cache))
    return built


@pytest.fixture
def source(tmp_path):
    """A source catalogue checkout; see :class:`support.SourceCatalogue`."""
    return SourceCatalogue(tmp_path)
