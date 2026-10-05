"""SNPedia pack against a fake MediaWiki API (no network)."""

import pytest

from yougene.refdata import snpedia

PAGES = {
    "Rs111": "{{Rsnum\n|rsid=111\n|Orientation=minus\n|geno1=(C;C)\n|geno2=(C;T)\n|geno3=(T;T)\n}}"
    "\nAn invented SNP used only for testing, with a paragraph long enough to keep.",
    "Rs222": "{{Rsnum\n|rsid=222\n|Orientation=plus\n|geno1=(A;A)\n|geno2=(A;G)\n|geno3=(G;G)\n}}"
    "\nAnother invented SNP for tests, also with a sufficiently long paragraph.",
    "Rs111(C;C)": "{{Genotype\n|summary=invented summary CC\n}}",
    "Rs111(C;T)": "{{Genotype\n|summary=invented summary CT\n}}",
    "Rs111(T;T)": "{{Genotype\n|summary=invented summary TT\n}}",
    "Rs222(A;G)": "{{Genotype\n|summary=invented summary AG\n}}",
}


class FakeClient:
    def __init__(self):
        self.requests = []

    def get(self, params):
        self.requests.append(params)
        if params.get("list") == "categorymembers":
            if "cmcontinue" not in params:
                return {"continue": {"cmcontinue": "x", "continue": "-||"},
                        "query": {"categorymembers": [{"title": "Rs111"}]}}  # fmt: skip
            return {
                "query": {"categorymembers": [{"title": "Rs222"}, {"title": "Rs999"}]}
            }
        raise AssertionError(params)

    def pages(self, titles):
        self.requests.append({"titles": titles})
        return {t: PAGES.get(t) for t in titles}


@pytest.fixture(autouse=True)
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))


def test_install_and_lookup():
    client = FakeClient()
    meta = snpedia.install(client=client, rsids=["rs111", "rs222", "rs333"])
    assert meta["snps"] == 2 and meta["genotype_pages"] == 6
    # Only SNP-level pages and *every* listed genotype page were requested:
    # nothing about which genotype a person has.
    asked = [t for r in client.requests if "titles" in r for t in r["titles"]]
    assert set(asked) == {"Rs111", "Rs222", "Rs111(C;C)", "Rs111(C;T)", "Rs111(T;T)",
                          "Rs222(A;A)", "Rs222(A;G)", "Rs222(G;G)"}  # fmt: skip

    # rs111 is minus-oriented on SNPedia: our plus-strand AG is its (C;T).
    note = snpedia.lookup("rs111", "AG")
    assert note["snpedia_genotype"] == "(C;T)"
    assert note["genotype_summary"] == "invented summary CT"
    assert "invented SNP" in note["about"]
    plus = snpedia.lookup("rs222", "AG")
    assert (
        plus["snpedia_genotype"] == "(A;G)"
        and plus["genotype_summary"] == "invented summary AG"
    )
    assert snpedia.lookup("rs222", "AA")["genotype_summary"] is None  # page missing
    assert snpedia.lookup("rs333", "AG") is None
    assert snpedia.lookup("rs222", "CT") is None  # letters SNPedia doesn't list
    assert snpedia.status()["installed"] is True


def test_resume_skips_fetched_pages():
    client = FakeClient()
    snpedia.install(client=client, rsids=["rs111"])
    again = FakeClient()
    snpedia.install(client=again, rsids=["rs111", "rs222"])
    asked = [t for r in again.requests if "titles" in r for t in r["titles"]]
    assert "Rs111" not in asked and "Rs222" in asked
    assert not any(r.get("list") for r in again.requests)  # index cached


def test_client_is_rate_limited():
    import io
    import json

    sleeps = []
    now = [0.0]

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    client = snpedia.Client(
        opener=lambda request, timeout: Response(json.dumps({"ok": 1}).encode()),
        sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)),
        clock=lambda: now[0],
    )
    client.get({"a": 1})
    client.get({"a": 2})
    assert sleeps and abs(sleeps[-1] - snpedia.MIN_INTERVAL) < 1e-9
