from fastapi.testclient import TestClient

from tests.test_annotate import env, import_sample  # noqa: F401  (pytest fixture)
from yougene.analysis.genome import ROH_MIN_SNPS, _scan
from yougene.app import create_app
from yougene.refdata import manager


def run(n, step, het_at=()):
    return [(1_000_000 + i * step, i not in het_at) for i in range(n)]


def test_roh_found_when_long_and_dense():
    segments = _scan("1", run(600, 2_000))  # 600 SNPs over 1.2 Mb
    assert len(segments) == 1
    assert segments[0]["snps"] == 600
    assert segments[0]["end"] - segments[0]["start"] == 599 * 2_000


def test_roh_tolerates_one_het_but_not_two():
    assert len(_scan("1", run(600, 2_000, het_at={300}))) == 1
    pieces = _scan("1", run(600, 2_000, het_at={200, 400}))
    assert all(p["end"] - p["start"] < 1_000_000 for p in pieces)


def test_roh_rejects_short_or_sparse_runs():
    assert _scan("1", run(ROH_MIN_SNPS - 1, 20_000)) == []  # too few SNPs
    assert _scan("1", run(400, 1_000)) == []  # only 0.4 Mb
    gap = run(300, 2_000) + [(1_000_000 + 300 * 2_000 + 2_000_000, True)]
    assert _scan("1", gap) == []  # a 2 Mb probe gap breaks the run


def test_genome_endpoints(env):  # noqa: F811
    manager.install()
    sample = import_sample(env)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        bands = client.get("/api/reference/cytobands").json()
        assert bands["lengths"]["1"] == 2_300_000
        assert bands["bands"]["1"][0]["band"] == "p36.33"

        base = f"/api/samples/{sample['id']}/genome"
        bins = client.get(f"{base}/bins", params={"bin_kb": 1000}).json()
        assert (
            sum(b["probes"] for chrom in bins["chroms"].values() for b in chrom) == 15
        )
        assert client.get(f"{base}/bins", params={"bin_kb": 10}).status_code == 422

        roh = client.get(f"{base}/roh").json()
        assert roh["segments"] == [] and roh["params"]["min_kb"] == 1000

        markers = client.get(f"{base}/markers").json()
        assert {m["probe_id"] for m in markers["traits"]} >= {"rs111", "rs222"}
        assert markers["health"] == []  # not without opt-in
        no_consent = client.get(f"{base}/markers", params={"health": True}).json()
        assert no_consent["health"] == []  # opt-in is enforced server-side
        client.put("/api/consent", json={"name": "health", "granted": True})
        health = client.get(f"{base}/markers", params={"health": True}).json()
        assert {m["probe_id"] for m in health["health"]} == {"rs111"}  # 3-star P

        cov = client.get(
            f"/api/samples/{sample['id']}/coverage",
            params={"gene": ["genea", "GENEB", "NONE"]},
        ).json()["genes"]
        assert cov["GENEA"] == {"known_pathogenic_snvs": 1, "tested": 1}
        assert cov["GENEB"] == {"known_pathogenic_snvs": 1, "tested": 1}
        assert cov["NONE"] == {"known_pathogenic_snvs": 0, "tested": 0}
        bad = client.get(
            f"/api/samples/{sample['id']}/coverage", params={"gene": "a'b"}
        )
        assert bad.status_code == 422


def test_variant_detail(env):  # noqa: F811
    manager.install()
    sample = import_sample(env)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        url = f"/api/samples/{sample['id']}/variant"
        hidden = client.get(url, params={"chrom": "1", "pos": 1000}).json()
        assert [c["probe_id"] for c in hidden["calls"]] == ["rs111"]
        assert hidden["clinvar"] == [] and hidden["clinvar_hidden"] == 2
        assert {t["risk_allele"] for t in hidden["traits"]} == {"G"}

        client.put("/api/consent", json={"name": "health", "granted": True})
        shown = client.get(url, params={"chrom": "1", "pos": 1000}).json()
        copies = {r["vcv_id"]: r["your_copies"] for r in shown["clinvar"]}
        assert copies == {11: 1, 12: 0}  # ALT G carried once, ALT T not at all

        apoe = client.get(url, params={"chrom": "19", "pos": 45412079}).json()
        assert apoe["clinvar"] == [] and apoe["clinvar_hidden"] == 1  # topic gate
        assert apoe["curated"] == []

        assert client.get(url, params={"chrom": "1", "pos": 5}).status_code == 404
        assert client.get(url, params={"chrom": "99", "pos": 5}).status_code == 422
