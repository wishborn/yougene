"""Reference data build, on tiny invented ClinVar / GWAS / cytoBand files.

The files are generated here (never committed) and only imitate the real
formats; none of the records are real ClinVar or GWAS Catalog entries.
"""

import gzip
import io
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yougene.app import create_app
from yougene.jobs import jobs
from yougene.refdata import fetch, manager
from yougene.refdata.sources import SOURCES

CLINVAR_LINES = [
    "##fileformat=VCFv4.1",
    "##fileDate=2026-01-01",
    '##INFO=<ID=CLNSIG,Number=.,Type=String,Description="x">',
    "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    # multi-allelic site split over two records
    "1\t1000\t11\tA\tG\t.\t.\tALLELEID=1;CLNSIG=Pathogenic;"
    "CLNREVSTAT=reviewed_by_expert_panel;CLNDN=Made-up_disease_one;"
    "GENEINFO=GENEA:1;MC=SO:0001583|missense_variant;ORIGIN=1;RS=111;AF_EXAC=0.00001",
    "1\t1000\t12\tA\tT\t.\t.\tALLELEID=2;CLNSIG=Benign;"
    "CLNREVSTAT=criteria_provided,_multiple_submitters,_no_conflicts;"
    "CLNDN=not_provided;GENEINFO=GENEA:1;ORIGIN=1;RS=111",
    # INFO containing '#', which DuckDB's comment option would truncate
    "2\t2000\t13\tC\tT\t.\t.\tALLELEID=3;CLNSIG=Uncertain_significance;"
    "CLNREVSTAT=criteria_provided,_single_submitter;CLNDN=Syndrome_#4|Other;"
    "GENEINFO=GENEB:2|GENEC:3;ORIGIN=1;RS=222",
    "X\t3000\t14\tG\tA\t.\t.\tALLELEID=4;CLNSIG=Pathogenic/Likely_pathogenic|risk_factor;"
    "CLNREVSTAT=criteria_provided,_conflicting_classifications;ORIGIN=1",
    "3\t4000\t15\tGA\tG\t.\t.\tALLELEID=5;CLNSIG=Likely_pathogenic,_low_penetrance;"
    "CLNREVSTAT=no_assertion_criteria_provided;CLNVC=Deletion;ORIGIN=1",
    "MT\t500\t16\tC\tT\t.\t.\tALLELEID=6;CLNSIG=drug_response;"
    "CLNREVSTAT=practice_guideline;ORIGIN=1",
    "NT_113889.1\t10\t17\tA\tG\t.\t.\tALLELEID=7;CLNSIG=Benign;ORIGIN=1",
]

GWAS_COLUMNS = [
    "DATE ADDED TO CATALOG",
    "PUBMEDID",
    "FIRST AUTHOR",
    "DATE",
    "JOURNAL",
    "LINK",
    "STUDY",
    "DISEASE/TRAIT",
    "INITIAL SAMPLE SIZE",
    "REPLICATION SAMPLE SIZE",
    "REGION",
    "CHR_ID",
    "CHR_POS",
    "REPORTED GENE(S)",
    "MAPPED_GENE",
    "UPSTREAM_GENE_ID",
    "DOWNSTREAM_GENE_ID",
    "SNP_GENE_IDS",
    "UPSTREAM_GENE_DISTANCE",
    "DOWNSTREAM_GENE_DISTANCE",
    "STRONGEST SNP-RISK ALLELE",
    "SNPS",
    "MERGED",
    "SNP_ID_CURRENT",
    "CONTEXT",
    "INTERGENIC",
    "RISK ALLELE FREQUENCY",
    "P-VALUE",
    "PVALUE_MLOG",
    "P-VALUE (TEXT)",
    "OR or BETA",
    "95% CI (TEXT)",
    "PLATFORM [SNPS PASSING QC]",
    "CNV",
    "MAPPED_TRAIT",
    "MAPPED_TRAIT_URI",
    "STUDY ACCESSION",
    "GENOTYPING TECHNOLOGY",
]


def gwas_row(**values):
    row = dict.fromkeys(GWAS_COLUMNS, "")
    row.update(
        {
            "PUBMEDID": "1",
            "DATE": "2020-01-01",
            "STUDY ACCESSION": "GCST0",
            "MAPPED_TRAIT": "made-up trait",
            "INITIAL SAMPLE SIZE": "1,000 European",
        }
    )
    row.update(values)
    return "\t".join(row[c] for c in GWAS_COLUMNS)


GWAS_ROWS = [
    gwas_row(
        **{
            "STRONGEST SNP-RISK ALLELE": "rs111-G",
            "SNPS": "rs111",
            "SNP_ID_CURRENT": "111",
            "OR or BETA": "1.2",
            "95% CI (TEXT)": "[1.1-1.3]",
            "PVALUE_MLOG": "9.2",
            "RISK ALLELE FREQUENCY": "0.3",
        }
    ),
    gwas_row(
        **{
            "STRONGEST SNP-RISK ALLELE": "rs222-?",
            "SNPS": "rs222",
            "OR or BETA": "0.05",
            "95% CI (TEXT)": "[0.01-0.09] unit decrease",
        }
    ),
    gwas_row(**{"STRONGEST SNP-RISK ALLELE": "rs333-T", "SNPS": "rs333; rs444"}),
    gwas_row(**{"STRONGEST SNP-RISK ALLELE": "chr1:5-A", "SNPS": "chr1:5"}),
]

CYTOBAND_LINES = [
    "chr1\t0\t2300000\tp36.33\tgneg",
    "chr1\t2300000\t5400000\tp36.32\tgpos25",
    "chrX\t0\t4300000\tp22.33\tgneg",
    "chrM\t0\t16571\t\tgneg",
    "chr6_apd_hap1\t0\t100\t\tgneg",
]


def make_files(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    clinvar = folder / "clinvar.vcf.gz"
    with gzip.open(clinvar, "wt") as out:
        out.write("\n".join(CLINVAR_LINES) + "\n")
    gwas = folder / "gwas.zip"
    with zipfile.ZipFile(gwas, "w") as z:
        z.writestr(
            "gwas-catalog-download-associations-alt-full.tsv",
            "\t".join(GWAS_COLUMNS) + "\n" + "\n".join(GWAS_ROWS) + "\n",
        )
    cytoband = folder / "cytoBand.txt.gz"
    with gzip.open(cytoband, "wt") as out:
        out.write("\n".join(CYTOBAND_LINES) + "\n")
    return {"clinvar": clinvar, "gwas": gwas, "cytoband": cytoband}


@pytest.fixture
def files(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    made = make_files(tmp_path / "src")

    def fake_download(source, target_dir, progress=lambda d, t: None):
        target = target_dir / source.filename
        shutil.copyfile(made[source.id], target)
        progress(target.stat().st_size, target.stat().st_size)
        return {
            "source": source.id,
            "path": str(target),
            "bytes": target.stat().st_size,
            "sha256": "test",
            "released": None,
            "fetched_at": "now",
            "url": source.url,
        }

    monkeypatch.setattr("yougene.refdata.manager.fetch.download", fake_download)
    return made


def install(**kwargs):
    return manager.install(download=manager.fetch.download, **kwargs)


def test_status_before_install(files):
    status = manager.status()
    assert status["ready"] is False
    assert {s["id"] for s in status["sources"]} == set(SOURCES)
    assert all(s["installed"] is None for s in status["sources"])


def test_install_builds_all_tables(files):
    result = install()
    assert set(result["built"]) == {"clinvar", "gwas", "cytoband"}
    assert manager.status()["ready"] is True
    con = manager.open_reference()
    try:
        rows = {
            r[0]: r[1:]
            for r in con.execute(
                "SELECT vcv_id, chrom, sig_cat, stars, conditions, genes, "
                "consequences, "
                "rsid, af_exac, low_penetrance FROM clinvar"
            ).fetchall()
        }
        assert 17 not in rows  # non-primary contig dropped
        assert rows[11][1:3] == ("pathogenic", 3)
        assert rows[11][5] == ["missense_variant"]
        assert rows[11][6] == "rs111" and rows[11][7] == pytest.approx(0.00001)
        assert rows[12][1:3] == ("benign", 2)
        assert rows[13][3] == ["Syndrome #4", "Other"]  # '#' survived
        assert rows[13][4] == ["GENEB", "GENEC"]
        assert rows[14][1:3] == ("pathogenic_likely", 1)
        assert rows[15][1:3] == ("likely_pathogenic", 0) and rows[15][8] is True
        assert rows[16][1:3] == ("drug_response", 4)

        sites = dict(
            con.execute(
                "SELECT chrom || ':' || pos, alleles FROM site_alleles"
            ).fetchall()
        )
        assert sites["1:1000"] == ["A", "G", "T"]  # both ALTs of the split site
        assert "3:4000" not in sites  # deletions aren't single-base sites

        gwas = con.execute(
            "SELECT snps, risk_allele, effect_type, beta_direction, usable, "
            "rsid_current "
            "FROM gwas ORDER BY assoc_id"
        ).fetchall()
        assert gwas[0] == ("rs111", "G", "or", None, True, "rs111")
        assert gwas[1][1:5] == ("", "beta", "decrease", False)  # '?' risk allele
        assert gwas[2][4] is False  # multi-SNP row
        assert gwas[3][4] is False  # non-rs id

        bands = con.execute(
            "SELECT chrom, band FROM cytoband ORDER BY chrom_order, start"
        ).fetchall()
        assert [b[0] for b in bands] == ["1", "1", "X", "MT"]
    finally:
        con.close()
    assert not (manager.ref_dir() / "work").exists()


def test_failed_build_keeps_previous_db(files, monkeypatch):
    install()
    before = manager.status()

    def broken(con, path):
        raise RuntimeError("boom")

    monkeypatch.setitem(manager.builders.BUILDERS, "cytoband", broken)
    with pytest.raises(RuntimeError):
        install(source_ids=["cytoband"])
    assert manager.status() == before
    assert not manager.db_path().with_name("reference.duckdb.partial").exists()


def test_partial_update_keeps_other_sources(files):
    install()
    result = install(source_ids=["cytoband"])
    assert set(result["built"]) == {"cytoband"}
    assert set(result["kept"]) == {"clinvar", "gwas"}
    assert manager.status()["ready"] is True


class FakeResponse(io.BytesIO):
    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {
            "Content-Length": str(len(body) if length is None else length),
            "Last-Modified": "Tue, 29 Sep 2026 19:57:25 GMT",
        }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_records_provenance(tmp_path):
    body = b"x" * 3_000_000
    seen = []
    meta = fetch.download(
        SOURCES["cytoband"],
        tmp_path,
        lambda done, total: seen.append((done, total)),
        opener=lambda request, timeout: FakeResponse(body),
    )
    assert meta["bytes"] == len(body)
    assert meta["released"].startswith("2026-09-29")
    assert seen[-1] == (len(body), len(body))
    assert (tmp_path / SOURCES["cytoband"].filename).read_bytes() == body


def test_incomplete_download_is_discarded(tmp_path):
    with pytest.raises(fetch.DownloadFailed):
        fetch.download(
            SOURCES["cytoband"],
            tmp_path,
            opener=lambda request, timeout: FakeResponse(b"abc", length=10),
        )
    assert list(tmp_path.iterdir()) == []


def test_network_error_is_friendly(tmp_path):
    def offline(request, timeout):
        raise OSError("no route")

    with pytest.raises(fetch.DownloadFailed, match="internet connection"):
        fetch.download(SOURCES["cytoband"], tmp_path, opener=offline)


def test_api_install(files):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.get("/api/refdata").json()["ready"] is False
        response = client.post("/api/refdata/install", json={})
        assert response.status_code == 202
        jobs.wait_idle()
        job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
        assert job["state"] == "done", job
        assert client.get("/api/refdata").json()["ready"] is True
        bad = client.post("/api/refdata/install", json={"sources": ["nope"]})
        assert bad.status_code == 422
