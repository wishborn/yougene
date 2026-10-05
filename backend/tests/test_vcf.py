"""VCF / gVCF import on invented data, including GRCh38 -> GRCh37 conversion
with a tiny invented chain file."""

import gzip
import shutil
from pathlib import Path

import pytest

from yougene import imports, store
from yougene.importers.base import ImportFailed
from yougene.refdata import manager
from yougene.testing.synth import generate

HEADER_37 = [
    "##fileformat=VCFv4.2",
    "##contig=<ID=chr1,length=249250621>",
    '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">',
]


def vcf_line(chrom, pos, rid, ref, alt, gt, filt="PASS", info=".", extra=""):
    return f"{chrom}\t{pos}\t{rid}\t{ref}\t{alt}\t50\t{filt}\t{info}\tGT:DP\t{gt}:20{extra}"


def to_vcf_rows(calls):
    """Express 23andMe-style calls as VCF rows (single-base calls only)."""
    rows = []
    for probe, chrom, pos, call in calls:
        if set(call) & {"D", "I"}:
            continue
        rid = probe if probe.startswith("rs") else "."
        if call == "--":
            rows.append(vcf_line(chrom, pos, rid, "A", ".", "./."))
        elif len(call) == 1:
            rows.append(vcf_line(chrom, pos, rid, call, ".", "0"))
        elif call[0] == call[1]:
            rows.append(vcf_line(chrom, pos, rid, call[0], ".", "0/0"))
        else:
            rows.append(vcf_line(chrom, pos, rid, call[0], call[1], "0/1"))
    return rows


@pytest.fixture(autouse=True)
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))


def do_import(path: Path) -> dict:
    work = store.tmp_dir() / path.name
    work.mkdir(parents=True, exist_ok=True)
    upload = work / "upload"
    shutil.copy(path, upload)
    return imports.run(upload, imports.sha256_of(upload), lambda *_: None)


def calls(sample_id):
    con = store.open_sample(sample_id)
    try:
        return con.execute(
            "SELECT chrom, pos, alleles, ploidy, call_type FROM calls ORDER BY chrom_order, pos"
        ).fetchall()
    finally:
        con.close()


@pytest.mark.parametrize("sex", ["male", "female"])
def test_vcf_matches_array_calls(tmp_path, sex):
    synthetic, _ = generate(sex, 9, 2000)
    path = tmp_path / "s.vcf"
    path.write_text(
        "\n".join(
            HEADER_37
            + ["#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tME"]
            + to_vcf_rows(synthetic)
        )
        + "\n"
    )
    record = do_import(path)
    assert record["vendor"] == "VCF" and record["build"] == "GRCh37"
    assert record["qc"]["sex"]["inferred"] == ("XY" if sex == "male" else "XX")
    expected = sorted(
        (c, p, "" if g == "--" else "".join(sorted(g)))
        for _, c, p, g in synthetic
        if not set(g) & {"D", "I"}
    )
    got = sorted((c, p, a) for c, p, a, _, _ in calls(record["id"]))
    assert got == expected


def test_vcf_details(tmp_path):
    rows = [
        vcf_line("chr1", 1000, "rs1", "A", "G", "0/1"),
        vcf_line(
            "chr1", 1100, "rs2", "C", "T", "1/1", filt="LowQual"
        ),  # filtered -> no-call
        vcf_line("chr1", 1200, "rs3", "G", "A,<NON_REF>", "0/2"),  # symbolic -> no-call
        vcf_line("chr1", 1300, "rs4", "AT", "A", "0/1"),  # indel: counted, not imported
        vcf_line(
            "chr1", 1400, ".", "C", "<NON_REF>", "0/0", info="END=1500"
        ),  # gVCF block
        vcf_line(
            "chr1", 1600, "rs5", "T", "C", "1|0", extra="\t0/0:9"
        ),  # second sample ignored
        vcf_line("chrM", 50, "rs6", "A", "G", "1"),  # haploid
        vcf_line("chr1", 1700, "rs1", "G", "C", "0/1"),  # repeated rsid
    ]
    for rs, (chrom, pos) in {
        "rs429358": ("19", 45411941),
        "rs7412": ("19", 45412079),
    }.items():
        rows.append(vcf_line(f"chr{chrom}", pos, rs, "C", "T", "0/1"))
    text = (
        "\n".join(
            HEADER_37
            + ["#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tME\tOTHER"]
            + rows
        )
        + "\n"
    )
    path = tmp_path / "d.vcf.gz"
    with gzip.open(path, "wt") as handle:
        handle.write(text)
    record = do_import(path)
    got = {(c, p): (a, pl, t) for c, p, a, pl, t in calls(record["id"])}
    assert got[("1", 1000)] == ("AG", 2, "snp")
    assert got[("1", 1100)][2] == "nocall"
    assert got[("1", 1200)][2] == "nocall"
    assert ("1", 1300) not in got
    assert got[("1", 1600)] == ("CT", 2, "snp")
    assert got[("MT", 50)] == ("G", 1, "snp")
    assert got[("1", 1700)] == ("CG", 2, "snp")
    load = record["qc"]["load"]
    assert load["indels"] == 1 and load["filtered"] == 1 and load["ref_blocks"] == 1
    assert record["qc"]["notes"] == ["2 samples in the file; the first was used."]
    con = store.open_sample(record["id"])
    assert con.execute('SELECT chrom, "start", "end" FROM ref_blocks').fetchall() == [
        ("1", 1400, 1500)
    ]
    con.close()


def test_unknown_build_refused(tmp_path):
    path = tmp_path / "u.vcf"
    path.write_text(
        "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tME\n"
        + vcf_line("1", 5, "rs1", "A", "G", "0/1")
        + "\n"
    )
    with pytest.raises(ImportFailed) as error:
        do_import(path)
    assert error.value.code == "unknown_build"


def chain_file(path: Path) -> Path:
    """Invented hg38 -> hg19 chain: chr1 shifted by -1000 (forward), chr19
    identity, and chr2 on the reverse strand of a 10,000 bp query."""
    text = "\n".join([
        "chain 1000 chr1 248956422 + 0 200000 chr1 249250621 + 1000 201000 1",
        "200000", "",
        "chain 1000 chr19 58617616 + 0 50000000 chr19 59128983 + 0 50000000 2",
        "50000000", "",
        "chain 1000 chr2 242193529 + 0 5000 chr2 10000 - 0 5000 3",
        "5000", "",
    ])  # fmt: skip
    with gzip.open(path, "wt") as handle:
        handle.write(text)
    return path


def test_grch38_vcf_is_converted(tmp_path, monkeypatch):
    chain = chain_file(tmp_path / "chain.gz")

    def fake_download(source, target_dir, progress=lambda d, t: None):
        target = target_dir / source.filename
        shutil.copyfile(chain, target)
        return {"source": source.id, "path": str(target), "bytes": 1, "sha256": "t",
                "released": None, "fetched_at": "now", "url": source.url}  # fmt: skip

    monkeypatch.setattr("yougene.refdata.manager.fetch.download", fake_download)
    header = ["##fileformat=VCFv4.2", "##contig=<ID=chr1,length=248956422>",
              "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tME"]  # fmt: skip
    rows = [
        vcf_line("chr1", 500, "rsA", "A", "G", "0/1"),  # -> chr1:1500
        vcf_line("chr2", 1, "rsB", "A", "C", "1/1"),  # reverse strand -> chr2:10000, GG
        vcf_line("chr3", 100, "rsC", "A", "G", "0/1"),  # no chain -> dropped
        vcf_line("chr19", 45411941, "rs429358", "C", "T", "0/1"),
        vcf_line("chr19", 45412079, "rs7412", "C", "T", "0/0"),
    ]
    path = tmp_path / "g38.vcf"
    path.write_text("\n".join(header + rows) + "\n")
    record = do_import(path)  # downloads the (fake) chain automatically
    assert "liftover" in {
        s["id"] for s in manager.status()["sources"] if s["installed"]
    }
    got = {(c, p): a for c, p, a, _, _ in calls(record["id"])}
    assert got[("1", 1500)] == "AG"
    assert got[("2", 10000)] == "GG"  # complemented on the reverse strand
    assert all(c != "3" for c, _ in got)
    assert record["qc"]["load"]["unmapped_after_liftover"] == 1
    assert record["qc"]["build_evidence"]["lifted_from_grch38"] is True
