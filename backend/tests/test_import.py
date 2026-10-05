import json
import shutil
import socket
import zipfile
from pathlib import Path

import pytest

from yougene import imports, store
from yougene.db import connect
from yougene.importers.base import ImportFailed
from yougene.testing.synth import write_fixture

FIXTURES = Path(__file__).parent / "fixtures/synthetic"


@pytest.fixture(autouse=True)
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def do_import(source: Path, **kwargs) -> dict:
    work = store.tmp_dir() / source.stem
    work.mkdir(parents=True, exist_ok=True)
    upload = work / "upload"
    shutil.copy(source, upload)
    return imports.run(upload, imports.sha256_of(upload), lambda *_: None, **kwargs)


def calls_for(sample_id: str) -> dict[str, tuple]:
    con = store.open_sample(sample_id)
    try:
        rows = con.execute(
            "SELECT probe_id, chrom, pos, alleles, ploidy, call_type, dup_group, "
            "dup_conflict, id_kind FROM calls"
        ).fetchall()
    finally:
        con.close()
    return {r[0]: r[1:] for r in rows}


@pytest.mark.parametrize("sex", ["male", "female"])
def test_planted_cases_survive_import(sex, no_network):
    manifest = json.loads((FIXTURES / f"{sex}.json").read_text())
    record = do_import(FIXTURES / f"{sex}.txt")
    calls = calls_for(record["id"])
    cases = manifest["cases"]

    assert len(calls) == manifest["rows"]  # every probe kept, nothing merged
    for probe in cases["internal_snp"] + cases["internal_indel"]:
        assert calls[probe][7] == "vendor"
    for probe in cases["internal_nocall"] + cases["nocall_block"]:
        assert calls[probe][2:5] == ("", None, "nocall")
    for probe in cases["diploid_indels"]:
        assert calls[probe][3:5] == (2, "indel_code")
    for probe in cases["haploid_indels"]:
        assert calls[probe][3:5] == (1, "indel_code")

    agree = [calls[p] for p in cases["duplicates_agree"]]
    assert agree[0][5] is not None and agree[0][5] == agree[1][5]
    assert not any(c[6] for c in agree)
    disagree = [calls[p] for p in cases["duplicates_disagree"]]
    assert disagree[0][5] == disagree[1][5] and all(c[6] for c in disagree)

    assert calls[cases["palindromic"][0]][2] == "AT"
    for probe in cases["roh"]:
        alleles = calls[probe][2]
        assert alleles[0] == alleles[1]

    qc = record["qc"]
    assert qc["rows"] == manifest["rows"]
    assert qc["duplicate_position_groups"] == 2
    assert qc["duplicate_position_conflicts"] == 1
    assert qc["sex"]["inferred"] == ("XY" if sex == "male" else "XX")
    assert record["build"] == "GRCh37"
    assert qc["build_evidence"]["anchors_matching_grch37"] == 5
    assert sum(c["probes"] for c in qc["per_chromosome"].values()) == qc["rows"]


def test_x_ploidy_follows_par_boundaries():
    record = do_import(FIXTURES / "male.txt")
    calls = calls_for(record["id"])
    by_pos = {c[1]: c[3] for c in calls.values() if c[0] == "X"}
    assert by_pos[2_699_520] == 2  # last base of PAR1
    assert by_pos[2_699_521] == 1
    assert by_pos[154_931_043] == 1
    assert by_pos[155_000_000] == 2  # PAR2


def test_alleles_are_sorted(tmp_path):
    path = tmp_path / "unsorted.txt"
    text = (FIXTURES / "male.txt").read_text()
    path.write_text(text.replace("\tAG\n", "\tGA\n"))
    record = do_import(path)
    con = store.open_sample(record["id"])
    assert (
        con.execute("SELECT count(*) FROM calls WHERE alleles = 'GA'").fetchone()[0]
        == 0
    )
    con.close()


def test_zip_download_is_accepted(tmp_path):
    archive = tmp_path / "download.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(FIXTURES / "female.txt", "raw_data.txt")
    assert do_import(archive)["qc"]["sex"]["inferred"] == "XX"


def test_zip_with_two_files_is_refused(tmp_path):
    archive = tmp_path / "two.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(FIXTURES / "female.txt", "a.txt")
        z.write(FIXTURES / "male.txt", "b.txt")
    with pytest.raises(ImportFailed) as error:
        do_import(archive)
    assert error.value.code == "zip_contents"


def _rewrite(tmp_path, transform) -> Path:
    path = tmp_path / "edited.txt"
    path.write_text(transform((FIXTURES / "male.txt").read_text()))
    return path


@pytest.mark.parametrize(
    ("transform", "code"),
    [
        (lambda t: t.replace("build 37", "build 38"), "unsupported_build"),
        (
            lambda t: t.replace("rs7412\t19\t45412079", "rs7412\t19\t44908822"),
            "build_mismatch",
        ),
        (lambda t: t.replace("\tAG\n", "\tAX\n", 1), "invalid_rows"),
        (
            lambda t: "# YOUGENE\n# 23andMe\n# rsid\tchromosome\tposition\tgenotype\n",
            "empty",
        ),
        (
            lambda t: t.replace("23andMe", "Acme").replace(
                "# rsid\tchromosome\tposition\tgenotype", "# id\tchr\tpos\tgt"
            ),
            "unrecognised_format",
        ),
    ],
)
def test_bad_files_fail_cleanly(tmp_path, transform, code):
    with pytest.raises(ImportFailed) as error:
        do_import(_rewrite(tmp_path, transform))
    assert error.value.code == code
    assert store.list_samples() == []
    assert not list((store.root() / "samples").iterdir())


def test_error_messages_never_contain_genotypes(tmp_path):
    with pytest.raises(ImportFailed) as error:
        do_import(_rewrite(tmp_path, lambda t: t.replace("\tAG\n", "\tAX\n", 1)))
    assert "AX" not in error.value.message


def test_unknown_build_without_header_or_anchors(tmp_path):
    def strip(text):
        lines = [
            line
            for line in text.splitlines()
            if "build" not in line.lower()
            and not line.startswith(
                ("rs429358", "rs7412", "rs4988235", "rs12913832", "rs4244285")
            )
        ]
        return "\n".join(lines) + "\n"

    with pytest.raises(ImportFailed) as error:
        do_import(_rewrite(tmp_path, strip))
    assert error.value.code == "unknown_build"


def test_original_filename_is_not_stored(tmp_path):
    named = tmp_path / "genome_Some_Person_v5_Full.txt"
    shutil.copy(FIXTURES / "male.txt", named)
    record = do_import(named)
    assert "Some_Person" not in json.dumps(record)
    assert record["display_name"].startswith("23andMe sample")


def test_duckdb_cannot_autoload_extensions():
    con = connect()
    settings = dict(
        con.execute(
            "SELECT name, value FROM duckdb_settings() WHERE name IN "
            "('autoinstall_known_extensions', 'autoload_known_extensions')"
        ).fetchall()
    )
    assert settings == {
        "autoinstall_known_extensions": "false",
        "autoload_known_extensions": "false",
    }


@pytest.mark.skipif(
    "not config.getoption('--perf')", reason="performance run: pytest --perf"
)
def test_large_file_performance(tmp_path):
    import time
    import tracemalloc

    path = tmp_path / "large.txt"
    write_fixture(path, "female", 7, 1_400_000)
    tracemalloc.start()
    started = time.perf_counter()
    record = do_import(path)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        f"\nimported {record['qc']['rows']:,} rows in {elapsed:.1f}s, "
        f"python peak {peak / 1e6:.0f} MB"
    )
    assert record["qc"]["rows"] == 1_400_000
    assert elapsed < 60
