"""Every supported vendor layout imports to the same calls as 23andMe."""

import gzip
import shutil
import zipfile
from pathlib import Path

import pytest

from yougene import imports, store
from yougene.testing.synth import VENDOR_FORMATS, write_fixture, write_vendor_fixture

ROWS = 3000
VENDOR_NAMES = {
    "ancestrydna": "AncestryDNA",
    "myheritage": "MyHeritage",
    "ftdna": "FamilyTreeDNA",
    "livingdna": "Living DNA",
}


@pytest.fixture(autouse=True)
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))


def do_import(source: Path) -> dict:
    work = store.tmp_dir() / source.name
    work.mkdir(parents=True, exist_ok=True)
    upload = work / "upload"
    shutil.copy(source, upload)
    return imports.run(upload, imports.sha256_of(upload), lambda *_: None)


def calls(sample_id: str) -> dict[str, tuple]:
    con = store.open_sample(sample_id)
    try:
        rows = con.execute(
            "SELECT probe_id, chrom, pos, alleles, ploidy, call_type, dup_conflict "
            "FROM calls"
        ).fetchall()
    finally:
        con.close()
    return {r[0]: r[1:] for r in rows}


@pytest.mark.parametrize("sex", ["male", "female"])
@pytest.mark.parametrize("vendor", VENDOR_FORMATS)
def test_vendor_matches_23andme(tmp_path, vendor, sex):
    reference = do_import(
        write_fixture(tmp_path / "ref.txt", sex, 5, ROWS).with_suffix(".txt")
    )
    other = do_import(
        write_vendor_fixture(tmp_path / f"{vendor}.txt", vendor, sex, 5, ROWS)
    )
    assert other["vendor"] == VENDOR_NAMES[vendor]
    assert other["build"] == "GRCh37"
    assert other["qc"]["sex"]["inferred"] == ("XY" if sex == "male" else "XX")
    assert calls(other["id"]) == calls(reference["id"])
    assert other["qc"]["rows"] == ROWS


def test_ftdna_gzip_download(tmp_path):
    plain = write_vendor_fixture(tmp_path / "ftdna.csv", "ftdna", "female", 6, ROWS)
    packed = tmp_path / "ftdna.csv.gz"
    with plain.open("rb") as source, gzip.open(packed, "wb") as out:
        shutil.copyfileobj(source, out)
    assert do_import(packed)["vendor"] == "FamilyTreeDNA"


def test_myheritage_zip_with_csv(tmp_path):
    plain = write_vendor_fixture(tmp_path / "mh.csv", "myheritage", "male", 7, ROWS)
    archive = tmp_path / "mh.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(plain, "MyHeritage_raw_dna_data.csv")
    assert do_import(archive)["vendor"] == "MyHeritage"


def test_ancestry_doubled_haploid_calls_become_single_copy(tmp_path):
    record = do_import(
        write_vendor_fixture(tmp_path / "a.txt", "ancestrydna", "male", 8, ROWS)
    )
    con = store.open_sample(record["id"])
    try:
        diploid_y = con.execute(
            "SELECT count(*) FROM calls WHERE chrom = 'Y' AND ploidy = 2"
        ).fetchone()[0]
        mt = con.execute(
            "SELECT DISTINCT ploidy FROM calls WHERE chrom = 'MT' AND ploidy IS NOT NULL"
        ).fetchall()
    finally:
        con.close()
    assert diploid_y == 0 and mt == [(1,)]
    assert record["qc"]["ploidy_normalisation"]["made_single_copy"] > 0
