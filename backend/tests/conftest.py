import socket

import pytest

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def pytest_addoption(parser):
    parser.addoption(
        "--perf", action="store_true", help="run the 1.4M-row import performance test"
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test may reach the network; downloads are always faked.

    Loopback stays allowed: asyncio's event loop on Windows talks to itself
    through a loopback socket pair.
    """
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def is_loopback(address) -> bool:
        return isinstance(address, tuple) and str(address[0]) in LOOPBACK

    def connect(self, address):
        if not is_loopback(address):
            raise AssertionError(f"a test tried to reach {address!r}")
        return original_connect(self, address)

    def connect_ex(self, address):
        if not is_loopback(address):
            raise AssertionError(f"a test tried to reach {address!r}")
        return original_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
