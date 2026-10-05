"""Haplogroups on invented samples built from the trees themselves: a
haplogroup's expected bases, thinned to array-like coverage, with genotyping
errors and recurrent private mutations added."""

import random
from collections import Counter, defaultdict

import pytest

from yougene import haplogroups
from yougene.db import connect
from yougene.haplogroups import mt, y
from yougene.importers.base import CALLS_SCHEMA


@pytest.fixture(scope="module")
def tree():
    return mt.tree()


def profile_calls(t, node: int, positions) -> dict[int, str]:
    return {p: t.base(node, p) for p in positions}


def test_bundled_tree(tree):
    assert tree.source["version"] == "17.3"
    assert len(tree.rcrs) == 16569 and tree.rcrs.startswith("GATCACAGGTCTATCACCC")
    assert len(tree.names) == 5435
    # Orientation check with textbook facts: rCRS is H2a2a1; H lacks the
    # 2706G/7028T that every non-H haplogroup carries relative to rCRS.
    h, u5 = tree.index["H"], tree.index["U5"]
    assert 2706 not in tree.profiles[h] and 7028 not in tree.profiles[h]
    assert tree.profiles[u5][2706] == "G" and tree.profiles[u5][7028] == "T"
    assert tree.profiles[tree.index["H2a2a1"]] == {}


def test_lineage_is_conventional(tree):
    lineage = [tree.names[n] for n in tree.lineages[tree.index["U5b1"]]]
    assert lineage[0] == "L1'2'3'4'5'6"
    for group in ["L3", "N", "R", "U", "U5", "U5b", "U5b1"]:
        assert group in lineage
    assert lineage.index("N") < lineage.index("R") < lineage.index("U5")
    assert [tree.names[n] for n in tree.lineages[tree.index["L0a"]]][:2] == [
        "L0",
        "L0a'b'f'g'k",
    ]


@pytest.mark.parametrize("group", ["H2a2a1", "U5b1", "L3e1", "D4a1", "J1c", "L0a"])
def test_full_coverage_is_exact(tree, group):
    node = tree.index[group]
    result = mt.classify(profile_calls(tree, node, range(1, 16570)))
    assert result["status"] == "ok"
    assert result["haplogroup"] == group
    assert result["lineage"][-1]["haplogroup"] == group
    statuses = {m["status"] for step in result["lineage"] for m in step["markers"]}
    assert statuses <= {"present", "reverted"}


def test_untested_branch_is_not_claimed(tree):
    """If none of a branch's own mutations were tested, stay one level up."""
    node = tree.index["U5b1"]
    defining = {pos for pos, _, _ in tree.defining(node)}
    positions = [p for p in range(1, 16570) if p not in defining]
    result = mt.classify(profile_calls(tree, node, positions))
    assert result["haplogroup"] != "U5b1"
    assert (
        node not in [tree.index[result["haplogroup"]]]
        and tree.index[result["haplogroup"]] in tree.lineages[node]
    )


def test_too_few_positions(tree):
    node = tree.index["U5b1"]
    result = mt.classify(profile_calls(tree, node, sorted(tree.positions)[:10]))
    assert result["status"] == "insufficient"


def test_yoruba_coordinates_are_refused(tree):
    node = tree.index["U5b1"]
    calls = profile_calls(tree, node, range(1, 16570))
    shifted = {p + 2: b for p, b in calls.items() if p + 2 <= 16569}
    assert mt.classify(shifted)["status"] == "reference_mismatch"


def simulate(t, rng, node, fraction, error):
    tree_positions = sorted(t.positions)
    others = [p for p in range(1, 16570) if p not in t.positions]
    alleles = defaultdict(set)
    for profile in t.profiles:
        for pos, base in profile.items():
            alleles[pos].add(base)
    tested = set(rng.sample(tree_positions, int(len(tree_positions) * fraction)))
    tested |= set(rng.sample(others, int(len(others) * fraction * 0.1)))
    calls = profile_calls(t, node, tested)
    weights = [t.occurrences.get(p, 0) + 0.01 for p in tree_positions]
    for pos in rng.choices(tree_positions, weights=weights, k=rng.randint(0, 6)):
        options = sorted((alleles[pos] | {t.rcrs[pos - 1]}) - {calls.get(pos)})
        if pos in calls and options:
            calls[pos] = rng.choice(options)  # a recurrent private mutation
    for pos in calls:
        if rng.random() < error:
            calls[pos] = rng.choice([b for b in "ACGT" if b != calls[pos]])
    return calls


@pytest.mark.parametrize("fraction,error", [(0.5, 0.001), (0.1, 0.005)])
def test_simulated_arrays_are_rarely_wrong(tree, fraction, error):
    rng = random.Random(2026)
    outcome = Counter()
    for node in rng.sample(range(len(tree.names)), 150):
        result = mt.classify(simulate(tree, rng, node, fraction, error))
        if result["status"] != "ok":
            outcome[result["status"]] += 1
            continue
        call = tree.index[result["haplogroup"]]
        outcome[
            "exact"
            if call == node
            else "ancestor"
            if call in tree.lineages[node]
            else "wrong"
        ] += 1
    # Calls stop at a broader branch rather than guess (measured: 0-1 in 400).
    assert outcome["wrong"] <= 2, outcome
    assert outcome["exact"] + outcome["ancestor"] >= 140, outcome


# Paternal line ------------------------------------------------------------


def y_sample(target_snp: str, fraction: float, seed: int) -> dict[int, str]:
    """Derived at every SNP on the target's path, ancestral elsewhere."""
    sample_class = y._configure()
    tree = sample_class.tree
    path = set(tree.snp_dict[target_snp].node.back_trace_path())
    calls: dict[int, str] = {}
    for snp in tree.snp_list:
        base = snp.derived if snp.node in path else snp.ancestral
        if snp.node in path or snp.position not in calls:
            calls[snp.position] = base
    rng = random.Random(seed)
    return {p: b for p, b in calls.items() if rng.random() < fraction}


@pytest.mark.parametrize("snp,expected", [("M269", "R-M269"), ("M253", "I-M253")])
def test_y_haplogroup(snp, expected):
    result = y.classify(y_sample(snp, 0.3, 1))
    assert result["status"] == "ok"
    assert result["short_name"] == expected
    assert result["lineage"][0]["haplogroup"].startswith("A")
    assert result["lineage"][-1]["markers"]


def test_y_too_few_positions():
    calls = dict(list(y_sample("M269", 1.0, 1).items())[:5])
    assert y.classify(calls)["status"] == "insufficient"


# Sample level ------------------------------------------------------------


def sample_db(mt_calls: dict[int, str], y_calls: dict[int, str]):
    con = connect()
    con.execute(CALLS_SCHEMA)
    rows = [("MT", 25, p, b) for p, b in mt_calls.items()]
    rows += [("Y", 24, p, b) for p, b in y_calls.items()]
    con.executemany(
        "INSERT INTO calls VALUES (?, 'vendor', ?, ?, ?, ?, 1, 'snp', NULL, false)",
        [(f"i{i}", c, o, p, b) for i, (c, o, p, b) in enumerate(rows)],
    )
    return con


def test_for_sample(tree):
    mt_calls = profile_calls(tree, tree.index["U5b1"], sorted(tree.positions)[::3])
    con = sample_db(mt_calls, y_sample("M269", 0.3, 2))
    male = haplogroups.for_sample(con, "23andMe", "XY")
    assert male["maternal"]["status"] == "ok"
    assert male["maternal"]["haplogroup"].startswith("U5")
    assert male["maternal"]["assumed_reference"] is False
    assert male["paternal"]["short_name"] == "R-M269"
    assert "23andMe" in male["sources"]["paternal"]["licence"]
    assert haplogroups.for_sample(con, "23andMe", "XX")["paternal"] == {
        "status": "no_y"
    }
    unknown = haplogroups.for_sample(con, "23andMe", "unknown")
    assert unknown["paternal"] == {"status": "sex_unknown"}


def test_plain_vcf_assumes_rcrs_where_unlisted(tree):
    node = tree.index["U5b1"]
    differences = tree.profiles[node]  # a variants-only VCF lists just these
    con = sample_db(dict(differences), {})
    result = haplogroups.maternal(con, "VCF")
    assert result["assumed_reference"] is True
    assert result["haplogroup"] == "U5b1"


def test_api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from tests.test_pages import import_one
    from yougene.app import create_app

    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        sample_id = import_one(client)
        body = client.get(f"/api/samples/{sample_id}/haplogroups").json()
        assert body["maternal"]["status"] in {"ok", "insufficient", "unresolved"}
        assert body["paternal"]["status"] in {"ok", "insufficient", "unresolved"}
        assert body["sources"]["maternal"]["tree"]["version"] == "17.3"
        assert client.get("/api/samples/0123abcd/haplogroups").status_code == 404
