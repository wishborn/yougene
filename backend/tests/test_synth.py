import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

from yougene.testing.synth import CHROMS, MARKER, generate, is_x_par, write_fixture


def parse(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == MARKER
    assert "# rsid\tchromosome\tposition\tgenotype" in lines
    assert any("build 37" in line for line in lines if line.startswith("#"))
    records = []
    for line in lines:
        if line.startswith("#"):
            continue
        probe, chrom, pos, call = line.split("\t")
        assert re.fullmatch(r"(?:rs|i)\d+", probe)
        assert re.fullmatch(r"[ACGTDI]{1,2}|--", call)
        records.append((probe, chrom, int(pos), call))
    return records


def assert_cases(records, manifest):
    calls = {row[0]: row for row in records}
    assert len(calls) == len(records) == manifest["rows"]
    assert set(row[1] for row in records) == set(CHROMS)
    cases = manifest["cases"]
    assert set(cases) == {
        "public_anchors",
        "internal_snp",
        "internal_indel",
        "internal_nocall",
        "diploid_indels",
        "haploid_indels",
        "duplicates_agree",
        "duplicates_disagree",
        "palindromic",
        "nocall_block",
        "roh",
        "x_ploidy",
        "y_ploidy",
        "mt_ploidy",
    }
    for planted in manifest["planted"]:
        assert calls[planted[0]] == tuple(planted)
    for probes in cases.values():
        assert all(probe in calls for probe in probes)
    assert calls[cases["internal_snp"][0]][3] == "AG"
    assert calls[cases["internal_indel"][0]][3] == "DI"
    assert calls[cases["internal_nocall"][0]][3] == "--"
    assert {calls[p][3] for p in cases["diploid_indels"]} == {"DD", "DI", "II"}
    assert {calls[p][3] for p in cases["haploid_indels"]} == {"D", "I"}
    for case, agree in [("duplicates_agree", True), ("duplicates_disagree", False)]:
        a, b = [calls[p] for p in cases[case]]
        assert a[1:3] == b[1:3]
        assert (a[3] == b[3]) == agree
        assert {a[0][:1], b[0][:1]} == {"r", "i"}
    assert calls[cases["palindromic"][0]][3] in {"AT", "CG"}
    nocalls = [calls[p] for p in cases["nocall_block"]]
    assert len(nocalls) >= 10 and all(row[3] == "--" for row in nocalls)
    roh = [calls[p] for p in cases["roh"]]
    assert max(row[2] for row in roh) - min(row[2] for row in roh) >= 1000000
    assert all(len(row[3]) == 2 and row[3][0] == row[3][1] for row in roh)
    # Verify every row, not only planted examples.
    for _, chrom, pos, call in records:
        assert pos > 0
        if call == "--":
            continue
        assert call == "".join(sorted(call))
        if (
            chrom == "MT"
            or chrom == "Y"
            or (chrom == "X" and manifest["sex"] == "male" and not is_x_par(pos))
        ):
            assert len(call) == 1
        else:
            assert len(call) == 2
    if manifest["sex"] == "female":
        assert all(call == "--" for _, chrom, _, call in records if chrom == "Y")
    expected = {
        "rs429358": ("19", 45411941),
        "rs7412": ("19", 45412079),
        "rs4988235": ("2", 136608646),
        "rs12913832": ("15", 28365618),
        "rs4244285": ("10", 96541616),
    }
    assert {p: calls[p][1:3] for p in cases["public_anchors"]} == expected
    groups = defaultdict(list)
    for probe, chrom, pos, _ in records:
        groups[chrom, pos].append(probe)
    assert sum(len(probes) > 1 for probes in groups.values()) == 2


@pytest.mark.parametrize("sex", ["male", "female"])
def test_committed_fixtures(sex):
    path = Path(__file__).parent / "fixtures/synthetic" / f"{sex}.txt"
    manifest = json.loads(path.with_suffix(".json").read_text())
    records = parse(path)
    assert_cases(records, manifest)
    generated, generated_manifest = generate(sex, manifest["seed"], manifest["rows"])
    assert generated == records
    assert generated_manifest == manifest


@pytest.mark.parametrize("sex", ["male", "female"])
def test_large_runtime_fixture(tmp_path, sex):
    path = tmp_path / "sample.txt"
    manifest_path = write_fixture(path, sex, 73, 25000)
    assert_cases(parse(path), json.loads(manifest_path.read_text()))
    another = tmp_path / "another.txt"
    write_fixture(another, sex, 73, 25000)
    assert another.read_bytes() == path.read_bytes()


def test_invalid_generation():
    with pytest.raises(ValueError):
        generate("male", 1, 20)
    with pytest.raises(ValueError):
        generate("unknown", 1, 5000)
