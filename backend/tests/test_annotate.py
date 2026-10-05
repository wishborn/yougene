"""Allele-aware annotation against tiny invented reference data.

Every record here is made up; positions are chosen only so that the
synthetic sample below lines up with them.
"""

import gzip
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_refdata import GWAS_COLUMNS, gwas_row
from yougene import imports, store
from yougene.annotate import runner
from yougene.annotate.engine import _gwas_orientation
from yougene.app import create_app
from yougene.jobs import jobs
from yougene.refdata import manager
from yougene.testing.synth import MARKER

ANCHORS = [
    ("rs429358", "19", 45411941, "CT"),
    ("rs7412", "19", 45412079, "CT"),
    ("rs4988235", "2", 136608646, "AG"),
    ("rs12913832", "15", 28365618, "AG"),
    ("rs4244285", "10", 96541616, "AG"),
]
CALLS = [
    ("rs111", "1", 1000, "AG"),  # carries ALT G (pathogenic, 3 stars), not ALT T
    ("rs222", "2", 2000, "CC"),  # reference only
    ("rs555", "4", 5000, "CT"),  # site is A/G: allele mismatch
    ("i7000099", "5", 6000, "AC"),  # vendor id, matched by position
    ("rs666", "X", 3000, "A"),  # haploid X: hemizygous ALT
    ("rs777", "6", 7000, "AA"),  # GWAS palindromic site, homozygous
    ("rs888", "7", 8000, "AT"),  # GWAS palindromic site, heterozygous
    ("rs999", "8", 9000, "CT"),  # GWAS risk reported on the other strand
    ("rs1010", "9", 10000, "GG"),  # GWAS, no ClinVar site: forward assumed
    ("rs1111", "9", 11000, "DI"),  # indel probe at a ClinVar site: never matched
    *ANCHORS,
]
CLINVAR = [
    ("1", 1000, 11, "A", "G", "Pathogenic", "reviewed_by_expert_panel", "GENEA:1", "111"),
    ("1", 1000, 12, "A", "T", "Benign", "criteria_provided,_single_submitter", "GENEA:1", "111"),
    ("2", 2000, 13, "C", "T", "Pathogenic", "criteria_provided,_single_submitter", "GENEB:2", "222"),
    ("4", 5000, 14, "A", "G", "Benign", "criteria_provided,_single_submitter", "GENEC:3", "555"),
    ("5", 6000, 15, "A", "C", "Likely_pathogenic", "criteria_provided,_single_submitter", "GENED:4", "123456"),
    ("X", 3000, 16, "G", "A", "Pathogenic", "no_assertion_criteria_provided", "GENEE:5", "666"),
    ("6", 7000, 17, "A", "T", "Benign", "criteria_provided,_single_submitter", "GENEF:6", "777"),
    ("9", 11000, 18, "C", "T", "Pathogenic", "reviewed_by_expert_panel", "GENEG:7", "1111"),
    ("19", 45412079, 19, "C", "T", "risk_factor", "criteria_provided,_multiple_submitters,_no_conflicts", "APOE:348", "7412"),
]  # fmt: skip
GWAS = [
    ("rs111", "rs111-G", "9"),
    ("rs222", "rs222-C", "9"),
    ("rs777", "rs777-A", "9"),
    ("rs888", "rs888-A", "9"),
    ("rs999", "rs999-A", "9"),  # site C/T: A is the complement of T
    ("rs1010", "rs1010-G", "9"),
    ("rs1010", "rs1010-T", "5"),  # weak association, below the default threshold
]


def write_sample(path: Path) -> None:
    lines = [
        MARKER,
        "# 23andMe-style synthetic file",
        "# Reference human assembly build 37",
        "# rsid\tchromosome\tposition\tgenotype",
    ]
    lines += [f"{p}\t{c}\t{pos}\t{g}" for p, c, pos, g in CALLS]
    path.write_text("\n".join(lines) + "\n")


def write_reference(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    clinvar = folder / "clinvar.vcf.gz"
    rows = ["##fileformat=VCFv4.1", "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"]
    for chrom, pos, vcv, ref, alt, sig, rev, gene, rs in CLINVAR:
        rows.append(
            f"{chrom}\t{pos}\t{vcv}\t{ref}\t{alt}\t.\t.\tALLELEID={vcv};CLNSIG={sig};"
            f"CLNREVSTAT={rev};CLNDN=Invented_condition_{vcv};GENEINFO={gene};"
            f"ORIGIN=1;RS={rs}"
        )
    with gzip.open(clinvar, "wt") as out:
        out.write("\n".join(rows) + "\n")
    gwas = folder / "gwas.zip"
    body = [
        gwas_row(
            SNPS=snps,
            **{"STRONGEST SNP-RISK ALLELE": risk, "PVALUE_MLOG": p, "OR or BETA": "1.3",
               "95% CI (TEXT)": "[1.1-1.5]", "MAPPED_TRAIT": f"invented trait {snps}"},
        )
        for snps, risk, p in GWAS
    ]  # fmt: skip
    with zipfile.ZipFile(gwas, "w") as z:
        z.writestr("assoc.tsv", "\t".join(GWAS_COLUMNS) + "\n" + "\n".join(body) + "\n")
    cytoband = folder / "cytoBand.txt.gz"
    with gzip.open(cytoband, "wt") as out:
        out.write("chr1\t0\t2300000\tp36.33\tgneg\n")
    return {"clinvar": clinvar, "gwas": gwas, "cytoband": cytoband}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    made = write_reference(tmp_path / "ref")

    def fake_download(source, target_dir, progress=lambda d, t: None):
        target = target_dir / source.filename
        shutil.copyfile(made[source.id], target)
        return {"source": source.id, "path": str(target), "bytes": 1, "sha256": "t",
                "released": None, "fetched_at": "now", "url": source.url}  # fmt: skip

    monkeypatch.setattr("yougene.refdata.manager.fetch.download", fake_download)
    sample_file = tmp_path / "sample.txt"
    write_sample(sample_file)
    return sample_file


def import_sample(path: Path) -> dict:
    work = store.tmp_dir() / "w"
    work.mkdir(parents=True, exist_ok=True)
    upload = work / "upload"
    shutil.copy(path, upload)
    return imports.run(upload, imports.sha256_of(upload), lambda *_: None)


def findings(sample_id: str, table: str) -> list[dict]:
    con = store.open_annotation(sample_id)
    try:
        cursor = con.execute(f"SELECT * FROM {table}")
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
    finally:
        con.close()


def test_no_annotation_without_reference(env):
    sample = import_sample(env)
    assert runner.state(sample["id"])["state"] == "no_reference"


def test_clinvar_matching(env):
    manager.install()
    sample = import_sample(env)  # annotated automatically once reference exists
    assert runner.state(sample["id"])["state"] == "current"
    rows = {r["vcv_id"]: r for r in findings(sample["id"], "clinvar_findings")}

    assert rows[11]["status"] == "carried"
    assert rows[11]["zygosity"] == "heterozygous" and rows[11]["dosage"] == 1
    assert rows[11]["tier"] == "established" and rows[11]["match_via"] == "rsid"
    assert rows[11]["rare_guard"] is True  # no population frequency known
    assert 12 not in rows  # ALT T at the same site isn't carried
    assert 13 not in rows  # homozygous reference
    assert rows[14]["status"] == "allele_mismatch"  # CT at an A/G site
    assert rows[15]["status"] == "carried" and rows[15]["match_via"] == "pos"
    assert rows[16]["zygosity"] == "hemizygous" and rows[16]["tier"] == "research"
    assert 18 not in rows  # indel probe never matched
    assert rows[19]["sensitive_topic"] == "apoe"


def test_gwas_matching(env):
    manager.install()
    sample = import_sample(env)
    rows = {
        (r["probe_id"], r["risk_allele"]): r
        for r in findings(sample["id"], "gwas_findings")
    }
    assert (rows[("rs111", "G")]["dosage"], rows[("rs111", "G")]["strand"]) == (
        1,
        "confirmed",
    )
    assert (rows[("rs222", "C")]["dosage"], rows[("rs222", "C")]["strand"]) == (
        2,
        "confirmed",
    )
    assert rows[("rs777", "A")]["strand"] == "ambiguous"
    assert rows[("rs777", "A")]["dosage"] is None
    assert (rows[("rs888", "A")]["dosage"], rows[("rs888", "A")]["strand"]) == (
        1,
        "confirmed",
    )
    assert (rows[("rs999", "A")]["dosage"], rows[("rs999", "A")]["strand"]) == (
        1,
        "flipped",
    )
    assert (rows[("rs1010", "G")]["dosage"], rows[("rs1010", "G")]["strand"]) == (
        2,
        "assumed",
    )


@pytest.mark.parametrize(
    ("alleles", "ploidy", "site", "risk", "expected"),
    [
        ("AG", 2, set(), "G", (1, "confirmed")),
        ("AG", 2, set(), "C", (1, "flipped")),  # C is the complement of G
        ("AG", 2, set(), "T", (1, "flipped")),
        ("AA", 2, {"G"}, "G", (0, "confirmed")),
        ("AA", 2, {"G"}, "C", (0, "flipped")),
        ("AT", 2, set(), "A", (1, "confirmed")),
        ("AA", 2, {"T"}, "A", (None, "ambiguous")),
        ("CC", 2, set(), "C", (2, "assumed")),
        ("CC", 2, set(), "G", (0, "assumed")),
        ("CC", 2, set(), "A", (0, "confirmed")),
        ("C", 1, set(), "C", (1, "assumed")),
        ("AC", 2, {"G"}, "T", (1, "flipped")),  # T is the complement of A
    ],
)
def test_gwas_orientation(alleles, ploidy, site, risk, expected):
    assert _gwas_orientation(alleles, ploidy, site, risk) == expected


def test_reference_update_makes_findings_stale_then_refreshes(env):
    manager.install()
    sample = import_sample(env)
    manager.install(source_ids=["cytoband"])
    assert runner.state(sample["id"])["state"] == "stale"
    runner.annotate_all()
    assert runner.state(sample["id"])["state"] == "current"


def test_delete_removes_annotation(env):
    manager.install()
    sample = import_sample(env)
    assert store.annotation_path(sample["id"]).exists()
    store.delete_sample(sample["id"])
    assert not store.annotation_path(sample["id"]).exists()


def test_findings_api(env):
    manager.install()
    sample = import_sample(env)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        base = f"/api/samples/{sample['id']}"
        assert client.get(f"{base}/annotation").json()["state"] == "current"

        summary = client.get(f"{base}/clinvar/summary").json()["counts"]
        assert sum(c["count"] for c in summary) == 4  # 11, 15, 16, 19

        default = client.get(f"{base}/clinvar").json()
        assert {r["vcv_id"] for r in default["rows"]} == {11, 15, 16}  # APOE gated
        with_apoe = client.get(f"{base}/clinvar", params={"topic": "apoe"}).json()
        assert 19 in {r["vcv_id"] for r in with_apoe["rows"]}
        strict = client.get(f"{base}/clinvar", params={"min_stars": 3}).json()
        assert [r["vcv_id"] for r in strict["rows"]] == [11]
        mismatches = client.get(f"{base}/clinvar", params={"status": "allele_mismatch"})
        assert [r["vcv_id"] for r in mismatches.json()["rows"]] == [14]

        traits = client.get(f"{base}/traits").json()
        probes = {r["probe_id"] for r in traits["rows"]}
        assert probes == {"rs111", "rs222", "rs888", "rs999", "rs1010"}
        assert all(r["p_mlog"] >= 7.3 for r in traits["rows"])
        everything = client.get(f"{base}/traits", params={"min_p_mlog": 0}).json()
        assert everything["total"] == traits["total"]  # rs1010-T: 0 copies

        assert client.get(f"{base}/clinvar", params={"sig": "nope"}).status_code == 422
        response = client.post(f"{base}/annotate")
        assert response.status_code == 202
        jobs.wait_idle()


def test_sql_macro_matches_python_rules():
    """Every genotype x known-site x risk combination gives the same answer."""
    from itertools import combinations_with_replacement

    from yougene.annotate.engine import GWAS_ORIENT_MACRO
    from yougene.db import connect

    letters = "ACGT"
    genotypes = [("".join(g), 2) for g in combinations_with_replacement(letters, 2)]
    genotypes += [(a, 1) for a in letters]
    sites = [[], *[[a] for a in letters], ["A", "G"], ["C", "T"], ["A", "C", "G"]]
    cases = [(g, p, s, r) for g, p in genotypes for s in sites for r in letters]
    con = connect()
    con.execute(GWAS_ORIENT_MACRO)
    for alleles, ploidy, site, risk in cases:
        got = con.execute(
            "SELECT o.dosage, o.strand FROM (SELECT gwas_orient(?, ?, ?, ?) AS o)",
            [alleles, ploidy, site, risk],
        ).fetchone()
        assert got == _gwas_orientation(alleles, ploidy, set(site), risk), (
            alleles,
            ploidy,
            site,
            risk,
        )
