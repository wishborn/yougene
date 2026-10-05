from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yougene import store
from yougene.app import create_app
from yougene.jobs import jobs

FIXTURES = Path(__file__).parent / "fixtures/synthetic"
OCTET = {"content-type": "application/octet-stream"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        yield c


def upload(client, sex="male", **params):
    response = client.post(
        "/api/samples",
        params=params,
        content=(FIXTURES / f"{sex}.txt").read_bytes(),
        headers={"content-type": "application/octet-stream"},
    )
    return response


def import_ok(client, sex="male", **params) -> dict:
    response = upload(client, sex, **params)
    assert response.status_code == 202, response.text
    jobs.wait_idle()
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["state"] == "done", job
    return client.get(f"/api/samples/{job['sample_id']}").json()


def test_import_lifecycle(client):
    sample = import_ok(client, "male", name="Me", relationship="me")
    assert sample["display_name"] == "Me"
    assert sample["relationship"] == "me"
    assert sample["qc"]["sex"]["inferred"] == "XY"
    second = import_ok(client, "female", name="Mum")
    listed = client.get("/api/samples").json()["samples"]
    assert [s["id"] for s in listed] == [sample["id"], second["id"]]

    renamed = client.patch(
        f"/api/samples/{sample['id']}",
        json={"display_name": " Wish ", "relationship": ""},
    ).json()
    assert renamed["display_name"] == "Wish"
    assert renamed["relationship"] is None
    assert (
        client.patch(
            f"/api/samples/{sample['id']}", json={"display_name": "  "}
        ).status_code
        == 422
    )

    assert client.delete(f"/api/samples/{sample['id']}").status_code == 204
    assert client.get(f"/api/samples/{sample['id']}").status_code == 404
    assert not store.sample_path(sample["id"]).exists()


def test_reimport_same_file(client):
    first = import_ok(client)
    response = upload(client)
    assert response.status_code == 409
    assert response.json()["sample_id"] == first["id"]
    replaced = import_ok(client, on_duplicate="replace", name="Again")
    samples = client.get("/api/samples").json()["samples"]
    assert [s["id"] for s in samples] == [replaced["id"]]
    assert not store.sample_path(first["id"]).exists()


def test_failed_import_reports_safely(client):
    response = client.post(
        "/api/samples", content=b"not a genome file\n", headers=OCTET
    )
    jobs.wait_idle()
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["state"] == "failed"
    assert job["error_code"] == "unrecognised_format"
    assert client.get("/api/samples").json()["samples"] == []
    assert not any((store.tmp_dir()).iterdir())  # upload cleaned up


def test_empty_upload(client):
    assert client.post("/api/samples", content=b"", headers=OCTET).status_code == 400


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr("yougene.api.MAX_UPLOAD_BYTES", 1000)
    assert upload(client).status_code == 413
    assert not any(store.tmp_dir().iterdir())


def test_calls_paging_sorting_filtering(client):
    sample = import_ok(client)
    base = f"/api/samples/{sample['id']}/calls"
    page = client.get(base, params={"page_size": 10}).json()
    assert page["total"] == 5000 and len(page["rows"]) == 10
    assert page["rows"][0]["chrom"] == "1"

    last = client.get(base, params={"sort": "-chrom,-pos", "page_size": 1}).json()
    assert last["rows"][0]["chrom"] == "MT"

    x = client.get(base, params={"chrom": "X", "page_size": 500}).json()
    assert {r["chrom"] for r in x["rows"]} == {"X"}

    nocalls = client.get(base, params={"call_type": "nocall"}).json()
    assert all(r["alleles"] == "" for r in nocalls["rows"])

    by_probe = client.get(base, params={"probe": "RS42935"}).json()
    assert [r["probe_id"] for r in by_probe["rows"]] == ["rs429358"]

    ga = client.get(base, params={"alleles": "GA"}).json()  # normalised to AG
    assert ga["total"] > 0 and {r["alleles"] for r in ga["rows"]} == {"AG"}

    window = client.get(
        base, params={"chrom": "19", "pos_min": 45411941, "pos_max": 45412079}
    ).json()
    assert {"rs429358", "rs7412"} <= {r["probe_id"] for r in window["rows"]}

    dups = client.get(base, params={"duplicates_only": True}).json()
    assert dups["total"] == 4


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "evil; DROP TABLE calls"},
        {"chrom": "23"},
        {"probe": "rs1'--"},
        {"page_size": 501},
    ],
)
def test_calls_rejects_bad_params(client, params):
    sample = import_ok(client)
    assert (
        client.get(f"/api/samples/{sample['id']}/calls", params=params).status_code
        == 422
    )


def test_unknown_ids(client):
    assert client.get("/api/samples/0123abcd").status_code == 404
    assert client.get("/api/samples/..%2Fregistry").status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404


def test_delete_all_requires_phrase(client):
    import_ok(client)
    assert (
        client.request("DELETE", "/api/data", json={"confirm": "yes"}).status_code
        == 422
    )
    assert (
        client.request(
            "DELETE", "/api/data", json={"confirm": "DELETE ALL"}
        ).status_code
        == 204
    )
    assert client.get("/api/samples").json()["samples"] == []
    assert not any((store.root() / "samples").iterdir())


def test_upload_needs_octet_stream(client):
    body = (FIXTURES / "male.txt").read_bytes()
    for content_type in ["text/plain", "application/x-www-form-urlencoded", None]:
        headers = {"content-type": content_type} if content_type else {}
        response = client.post("/api/samples", content=body, headers=headers)
        assert response.status_code == 415
    assert not any(store.tmp_dir().iterdir())


@pytest.mark.parametrize(
    ("origin", "status"),
    [
        ("https://evil.example", 403),
        ("http://127.0.0.1.evil.example", 403),
        ("null", 403),
        ("http://127.0.0.1:5190", 202),
        ("http://localhost:5180", 202),
    ],
)
def test_cross_site_writes_are_refused(client, origin, status):
    response = client.post(
        "/api/samples",
        content=(FIXTURES / "male.txt").read_bytes(),
        headers={**OCTET, "origin": origin},
    )
    assert response.status_code == status
    jobs.wait_idle()


def test_cross_site_delete_refused(client):
    response = client.request(
        "DELETE",
        "/api/data",
        json={"confirm": "DELETE ALL"},
        headers={"origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_gen_origin_allowed_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("YOUGENE_ALLOWED_HOSTS", "yougene.gen")
    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        response = c.request(
            "DELETE",
            "/api/data",
            json={"confirm": "DELETE ALL"},
            headers={"origin": "https://yougene.gen"},
        )
    assert response.status_code == 204


def test_consent_round_trip_and_withdrawal(client):
    assert client.get("/api/consent").json() == {}
    client.put("/api/consent", json={"name": "health", "granted": True})
    state = client.put(
        "/api/consent", json={"name": "topic.apoe", "granted": True}
    ).json()
    assert state == {"health": True, "topic.apoe": True}
    state = client.put("/api/consent", json={"name": "health", "granted": False}).json()
    assert state == {
        "health": False,
        "topic.apoe": False,
    }  # withdrawing health withdraws topics
    assert (
        client.put(
            "/api/consent", json={"name": "everything", "granted": True}
        ).status_code
        == 422
    )
    bad = client.put(
        "/api/consent",
        json={"name": "health", "granted": True},
        headers={"origin": "https://evil.example"},
    )
    assert bad.status_code == 403
    client.put("/api/consent", json={"name": "health", "granted": True})
    client.request("DELETE", "/api/data", json={"confirm": "DELETE ALL"})
    assert client.get("/api/consent").json() == {}  # delete-all clears consent


def test_refuses_upload_when_disk_is_low(client, monkeypatch):
    import collections

    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(
        "yougene.api.shutil.disk_usage", lambda p: usage(1, 1, 10 * 1024 * 1024)
    )
    assert upload(client).status_code == 507
    assert not any(store.tmp_dir().iterdir())
