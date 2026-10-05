import shutil

import pytest
from fastapi.testclient import TestClient

from yougene import imports, store
from yougene.analysis.known_traits import KNOWN_TRAITS
from yougene.app import create_app
from yougene.testing.synth import MARKER

ANCHORS = [
    ("rs429358", "19", 45411941, "CT"),
    ("rs7412", "19", 45412079, "CC"),
    ("rs4244285", "10", 96541616, "AG"),
]


@pytest.fixture
def sample(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUGENE_DATA_DIR", str(tmp_path / "data"))
    calls = [
        *ANCHORS,
        ("rs4988235", "2", 136608646, "AA"),  # lactase: 2 copies
        ("rs12913832", "15", 28365618, "AG"),  # eye colour: 1 copy
        ("rs17822931", "16", 48258198, "--"),  # earwax: no call
        ("rs671", "12", 112241766, "CT"),  # ALDH2: letters not G/A
        ("i5000123", "11", 66328095, "TT"),  # ACTN3 via a vendor id, by position
        # FUT2 rs601338 absent: not tested
    ]
    text = "\n".join(
        [
            MARKER,
            "# 23andMe-style synthetic",
            "# build 37",
            "# rsid\tchromosome\tposition\tgenotype",
        ]
        + [f"{p}\t{c}\t{pos}\t{g}" for p, c, pos, g in calls]
    )
    source = tmp_path / "s.txt"
    source.write_text(text + "\n")
    work = store.tmp_dir() / "w"
    work.mkdir(parents=True)
    upload = work / "upload"
    shutil.copy(source, upload)
    return imports.run(upload, imports.sha256_of(upload), lambda *a: None)


def test_known_traits(sample):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        traits = {
            t["id"]: t
            for t in client.get(f"/api/samples/{sample['id']}/known-traits").json()[
                "traits"
            ]
        }
    assert set(traits) == {t.id for t in KNOWN_TRAITS}
    assert traits["lactase"]["status"] == "ok" and traits["lactase"]["copies"] == 2
    assert traits["eye_colour"]["copies"] == 1
    assert traits["earwax"]["status"] == "no_call"
    assert traits["alcohol_flush"]["status"] == "unexpected"
    assert traits["alcohol_flush"]["summary"] is None
    assert traits["actn3"]["copies"] == 2  # matched by position
    assert traits["secretor"]["status"] == "not_tested"


def test_every_trait_has_three_outcomes_and_distinct_alleles():
    for trait in KNOWN_TRAITS:
        assert set(trait.outcomes) == {0, 1, 2}
        assert trait.effect_allele != trait.other_allele
        assert {trait.effect_allele, trait.other_allele} <= set("ACGT")
        # Palindromic pairs couldn't be oriented from the call alone.
        assert {trait.effect_allele, trait.other_allele} not in ({"A", "T"}, {"C", "G"})
