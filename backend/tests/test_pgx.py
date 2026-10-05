import shutil

import pytest
from fastapi.testclient import TestClient

from yougene import imports, store
from yougene.analysis.pgx import GENES, _phenotype
from yougene.app import create_app
from yougene.testing.synth import MARKER

BY_GENE = {g.gene: g for g in GENES}


@pytest.mark.parametrize(
    ("gene", "counts", "expected"),
    [
        ("CYP2C19", {}, "Normal metabolizer"),
        ("CYP2C19", {"*2": 1}, "Intermediate metabolizer"),
        ("CYP2C19", {"*2": 1, "*17": 1}, "Intermediate metabolizer"),
        ("CYP2C19", {"*2": 1, "*3": 1}, "Poor metabolizer"),
        ("CYP2C19", {"*17": 1}, "Rapid metabolizer"),
        ("CYP2C19", {"*17": 2}, "Ultrarapid metabolizer"),
        ("CYP2C9", {"*2": 1}, "Intermediate metabolizer"),  # AS 1.5
        ("CYP2C9", {"*2": 2}, "Intermediate metabolizer"),  # AS 1
        ("CYP2C9", {"*3": 1}, "Intermediate metabolizer"),  # AS 1
        ("CYP2C9", {"*2": 1, "*3": 1}, "Poor metabolizer"),  # AS 0.5
        ("CYP2C9", {"*3": 2}, "Poor metabolizer"),
        ("DPYD", {"c.2846A>T": 1}, "Intermediate metabolizer"),
        ("DPYD", {"*2A": 1}, "Intermediate metabolizer"),
        ("DPYD", {"*2A": 1, "HapB3": 1}, "Poor metabolizer"),
        ("TPMT", {"*3B": 1, "*3C": 1}, "Intermediate metabolizer"),  # one *3A
        ("TPMT", {"*3C": 2}, "Poor metabolizer"),
        ("TPMT", {"*2": 1, "*3C": 1}, "Poor metabolizer"),
        ("NUDT15", {"*3": 1}, "Intermediate metabolizer"),
        ("CYP3A5", {"*3": 2}, "Poor metabolizer"),
        ("CYP3A5", {"*3": 0}, "Normal metabolizer"),
        ("SLCO1B1", {"c.521C": 1}, "Decreased function"),
        ("VKORC1", {"-1639A": 2}, "Highly increased warfarin sensitivity"),
    ],
)
def test_phenotype_rules(gene, counts, expected):
    base = {v.star: 0 for v in BY_GENE[gene].variants}
    base.update(counts)
    assert _phenotype(BY_GENE[gene], base)[0] == expected


def test_definitions_are_consistent():
    for gene in GENES:
        for v in gene.variants:
            assert v.normal != v.variant and {v.normal, v.variant} <= set("ACGT")
            assert v.rsid.startswith("rs") and v.clinvar_vcv > 0


@pytest.fixture
def sample(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    calls = [
        ("rs429358", "19", 45411941, "CT"),
        ("rs7412", "19", 45412079, "CC"),
        ("rs4244285", "10", 96541616, "AG"),  # CYP2C19 *2 het
        ("rs4986893", "10", 96540410, "GG"),
        ("rs12248560", "10", 96521657, "CT"),  # *17 het
        ("rs1799853", "10", 96702047, "CC"),
        ("rs1057910", "10", 96741053, "--"),  # CYP2C9 *3 no-call -> not determined
        ("rs9923231", "16", 31107689, "CT"),
        ("i9000001", "12", 21331549, "CC"),  # SLCO1B1 by position, 2 copies
        ("rs776746", "7", 99270539, "CC"),  # CYP3A5 *3/*3
    ]
    text = "\n".join(
        [MARKER, "# synthetic", "# build 37", "# rsid\tchromosome\tposition\tgenotype"]
        + [f"{p}\t{c}\t{pos}\t{g}" for p, c, pos, g in calls]
    )
    (tmp_path / "s.txt").write_text(text + "\n")
    work = store.tmp_dir() / "w"
    work.mkdir(parents=True)
    shutil.copy(tmp_path / "s.txt", work / "upload")
    return imports.run(
        work / "upload", imports.sha256_of(work / "upload"), lambda *a: None
    )


def test_pgx_api(sample):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        genes = {
            g["gene"]: g
            for g in client.get(f"/api/samples/{sample['id']}/pgx").json()["genes"]
        }
    assert genes["CYP2C19"]["phenotype"] == "Intermediate metabolizer"
    assert genes["CYP2C9"]["status"] == "not_determined"
    assert genes["VKORC1"]["phenotype"] == "Increased warfarin sensitivity"
    assert genes["SLCO1B1"]["phenotype"] == "Poor function"
    assert genes["CYP3A5"]["phenotype"] == "Poor metabolizer"
    assert genes["DPYD"]["status"] == "not_determined"  # positions not on this file
    assert all("drugs" in g for g in genes.values())
