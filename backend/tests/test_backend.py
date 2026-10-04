from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from yougene import __version__
from yougene.app import create_app
from yougene.cli import main
from yougene.config import data_dir


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost:8000", "[::1]:9123"])
def test_health(host):
    with TestClient(create_app(), base_url=f"http://{host}") as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


@pytest.mark.parametrize(
    "host",
    [
        "testserver",
        "evil.test",
        "localhost.evil",
        "0.0.0.0",
        "localhost@evil.test",
        "127.0.0.1:abc",
        "::1",
        "",
    ],
)
def test_bad_host(host):
    response = TestClient(create_app()).get("/api/health", headers={"host": host})
    assert response.status_code == 400


def test_duplicate_host():
    response = TestClient(create_app()).get(
        "/api/health", headers=[("host", "localhost"), ("host", "evil.test")]
    )
    assert response.status_code == 400


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.1", "evil.test"])
def test_cli_refuses_nonloopback(host):
    with pytest.raises(SystemExit) as error:
        main(["serve", "--host", host])
    assert error.value.code == 2


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_cli_serve(monkeypatch, tmp_path, host):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr("yougene.cli.uvicorn.run", lambda *a, **k: calls.append((a, k)))
    main(["serve", "--host", host, "--port", "8123"])
    assert calls == [
        (("yougene.app:create_app",), {"factory": True, "host": host, "port": 8123})
    ]


def test_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path.resolve()
    monkeypatch.delenv("YOUGENE_DATA_DIR")
    monkeypatch.setattr(
        "yougene.config.user_data_dir", lambda name: str(tmp_path / name)
    )
    assert data_dir() == tmp_path / "yougene"


def test_data_dir_rejects_checkout(monkeypatch):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(Path(__file__).parent))
    with pytest.raises(ValueError, match="outside"):
        data_dir()


def test_version(capsys):
    main(["version"])
    assert capsys.readouterr().out.strip() == __version__
    assert duckdb.__version__


def test_configurable_allowed_hosts(monkeypatch):
    monkeypatch.setenv("YOUGENE_ALLOWED_HOSTS", "yougene.gen")
    with TestClient(create_app()) as client:
        assert (
            client.get("/api/health", headers={"host": "yougene.gen:443"}).status_code
            == 200
        )
        assert (
            client.get("/api/health", headers={"host": "localhost"}).status_code == 200
        )
        assert (
            client.get("/api/health", headers={"host": "yougene.gen.evil"}).status_code
            == 400
        )
    monkeypatch.delenv("YOUGENE_ALLOWED_HOSTS")
    with TestClient(create_app()) as client:
        assert (
            client.get("/api/health", headers={"host": "yougene.gen"}).status_code
            == 400
        )


@pytest.mark.parametrize(
    "value", ["*", "*.gen", "yougene.gen:443", "https://yougene.gen"]
)
def test_allowed_host_setting_rejects_patterns(monkeypatch, value):
    monkeypatch.setenv("YOUGENE_ALLOWED_HOSTS", value)
    with pytest.raises(ValueError, match="literal hostnames"):
        with TestClient(create_app()):
            pass
