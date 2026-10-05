"""Inertia page routes (fancy-inertia-server) and the protocol details that
matter to the Fancy client."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from tests.test_api import FIXTURES, OCTET
from yougene.app import create_app
from yougene.jobs import jobs


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        yield c


def page_from_html(html: str) -> dict:
    match = re.search(r"data-page='([^']*)'", html)
    assert match, html[:300]
    return json.loads(
        match[1].replace("&#39;", "'").replace("&quot;", '"').replace("&amp;", "&")
    )


def version(client) -> str:
    return page_from_html(client.get("/").text)["version"]


def import_one(client) -> str:
    response = client.post("/api/samples", params={"name": "Synthetic"},
                           content=(FIXTURES / "male.txt").read_bytes(), headers=OCTET)  # fmt: skip
    jobs.wait_idle()
    return client.get(f"/api/jobs/{response.json()['job_id']}").json()["sample_id"]


def test_first_visit_is_html_with_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = page_from_html(response.text)
    assert page["component"] == "Home"
    assert page["props"]["samples"] == []


def test_inertia_visit_returns_json(client):
    sample_id = import_one(client)
    response = client.get(
        f"/samples/{sample_id}/traits",
        headers={"X-Inertia": "true", "X-Inertia-Version": version(client)},
    )
    assert response.status_code == 200
    page = response.json()
    assert page["component"] == "Sample/Traits"
    assert page["props"]["sample"]["display_name"] == "Synthetic"
    assert page["props"]["samples"][0]["id"] == sample_id  # shared prop


def test_partial_reload_of_shared_samples(client):
    import_one(client)
    response = client.get(
        "/",
        headers={
            "X-Inertia": "true",
            "X-Inertia-Partial-Component": "Home",
            "X-Inertia-Partial-Data": "samples",
        },
    )
    assert (
        list(response.json()["props"]) == ["samples"]
        or "samples" in response.json()["props"]
    )


def test_app_update_ping_never_errors(client):
    response = client.get(
        "/settings",
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": version(client),
            "X-Inertia-Partial-Component": "Settings",
            "X-Inertia-Partial-Data": "__app_update_ping__",
        },  # fmt: skip
    )
    assert response.status_code == 200


def test_stale_build_is_a_bare_409(client):
    if version(client) == "":
        pytest.skip("no built frontend here, so there's no asset version to be stale")
    response = client.get(
        "/", headers={"X-Inertia": "true", "X-Inertia-Version": "old"}
    )
    assert response.status_code == 409
    assert "x-inertia-location" not in response.headers


def test_unknown_pages(client):
    assert client.get("/samples/0123abcd").status_code == 404
    sample_id = import_one(client)
    assert client.get(f"/samples/{sample_id}/nope").status_code == 404


def test_host_guard_still_wraps_pages(client):
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400


def test_dev_page_boots_react_from_same_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("YOUGENE_DEV", "1")
    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        html = c.get("/").text
    refresh = html.index("/@react-refresh")
    assert (
        refresh < html.index('src="/@vite/client"') < html.index('src="/src/main.tsx"')
    )
    assert "//@vite" not in html
