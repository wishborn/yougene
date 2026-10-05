"""Maternal line: mtDNA haplogroup from array or sequencing calls.

Tree: PhyloTree Build 17, rCRS-oriented (from the haplogrep project). Each
haplogroup's expected bases follow from the mutations on its path.

Method: a likelihood over every haplogroup in the tree, using only the
positions the file actually tested. A tested base that disagrees with a
haplogroup costs it a per-position error rate: genotyping error plus how
often that mutation recurs across the tree (recurrent sites are weak
evidence). That gives each haplogroup a probability; a branch's probability
is the sum over everything under it.

The answer is the most specific branch that

* holds at least ``CONFIDENT`` of the probability, and
* has at least one of its own defining mutations tested and present
  (otherwise its sub-branch is only "not ruled out", so we stay one up).

With sparse arrays that is often a broad branch (e.g. "U5" rather than
"U5b1b2"); that's deliberate. In simulations of array data (see
tests/test_haplogroups.py) this was wrong well under 1% of the time, where
nearest-match scoring (haplogrep's Kulczynski, built for full sequences)
was wrong 3-20% of the time on the same sparse data.

Only single-base calls are used: indels and two-letter (heteroplasmic or
noisy) calls aren't. Positions are rCRS, as in GRCh37's MT.
"""

import json
import math
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DATA = Path(__file__).with_name("data") / "phylotree17.json"
# The human root ("mt-MRCA") isn't a node in the rCRS-oriented tree: it sits
# on the edge between these two, the first split of every human lineage.
L0, L1_6 = "L0", "L1'2'3'4'5'6"
MIN_INFORMATIVE = 20  # tested tree positions needed to try at all
MIN_RCRS_MATCH = 0.8  # below this the positions aren't rCRS coordinates
GENOTYPING_ERROR = 0.002
MAX_ERROR = 0.3
CONFIDENT = 0.99
POSSIBLE = 0.8


@dataclass
class Tree:
    names: list[str]
    profiles: list[dict[int, str]]  # differences from rCRS, single bases only
    lineages: list[list[int]]  # conventional path from L0 / L1'2'3'4'5'6
    rcrs: str
    occurrences: dict[int, int]  # recurrent mutation events per position
    hotspots: frozenset[int]
    source: dict
    index: dict[str, int]
    positions: frozenset[int]  # every position the tree uses

    def base(self, node: int, pos: int) -> str:
        return self.profiles[node].get(pos, self.rcrs[pos - 1])

    def parent(self, node: int) -> int | None:
        lineage = self.lineages[node]
        return lineage[-2] if len(lineage) > 1 else None

    def defining(self, node: int) -> list[tuple[int, str, str]]:
        """(position, from, to) for the mutations that define ``node``."""
        before = self.parent(node)
        if before is None:  # top split: compare with the other side
            before = self.index[L1_6 if self.names[node] == L0 else L0]
        out = []
        for pos in sorted(set(self.profiles[node]) | set(self.profiles[before])):
            if self.base(node, pos) != self.base(before, pos):
                out.append((pos, self.base(before, pos), self.base(node, pos)))
        return out


def _snv(poly: str) -> tuple[int, str] | None:
    poly = poly.rstrip("!")
    if len(poly) >= 2 and poly[:-1].isdigit() and poly[-1] in "ACGT":
        return int(poly[:-1]), poly[-1]
    return None


@cache
def tree() -> Tree:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    rcrs = data["rcrs"]
    names, parent, profiles = [], [], []
    for name, up, polys in data["nodes"]:
        profile = dict(profiles[up]) if up >= 0 else {}
        for poly in polys:
            snv = _snv(poly)
            if snv is None:
                continue  # indels: arrays can't type them reliably
            pos, base = snv
            if base == rcrs[pos - 1]:
                profile.pop(pos, None)
            else:
                profile[pos] = base
        names.append(name)
        parent.append(up)
        profiles.append(profile)
    index = {n: i for i, n in enumerate(names)}

    def ancestors(node: int) -> list[int]:
        out = [node]
        while parent[out[-1]] >= 0:
            out.append(parent[out[-1]])
        return out

    # The stored tree is rooted at rCRS's own haplogroup (H2a2a1); turn it
    # back into the conventional orientation.
    l0, l1_6 = index[L0], index[L1_6]
    top = ancestors(l1_6)
    lineages = []
    for node in range(len(names)):
        down = ancestors(node)
        if l0 in down:
            lineages.append(list(reversed(down[: down.index(l0) + 1])))
            continue
        down_set = set(down)
        common = next(n for n in top if n in down_set)
        lineages.append(
            top[: top.index(common) + 1] + list(reversed(down[: down.index(common)]))
        )

    occurrences: Counter[int] = Counter()
    for poly, count in data["occurrences"].items():
        snv = _snv(poly)
        if snv:
            occurrences[snv[0]] += count
    return Tree(
        names=names,
        profiles=profiles,
        lineages=lineages,
        rcrs=rcrs,
        occurrences=dict(occurrences),
        hotspots=frozenset(s[0] for h in data["hotspots"] if (s := _snv(h))),
        source=data["source"],
        index=index,
        positions=frozenset(p for prof in profiles for p in prof),
    )


def classify(calls: dict[int, str]) -> dict:
    """``calls``: rCRS position -> single base (A/C/G/T) for every tested
    mtDNA position. No-calls and two-letter calls are left out by the caller."""
    t = tree()
    tested = {p: b for p, b in calls.items() if 1 <= p <= len(t.rcrs)}
    used = {p: b for p, b in tested.items() if p in t.positions and p not in t.hotspots}
    summary = {"tested": len(tested), "informative": len(used)}
    if len(used) < MIN_INFORMATIVE:
        return {"status": "insufficient", **summary}
    rcrs_match = sum(b == t.rcrs[p - 1] for p, b in tested.items()) / len(tested)
    if rcrs_match < MIN_RCRS_MATCH:
        # e.g. hg19 chrM (Yoruba) coordinates labelled as MT.
        return {"status": "reference_mismatch", **summary}

    probability = _posterior(t, used)
    clade: Counter[int] = Counter()
    for node, p in enumerate(probability):
        if p > 1e-12:
            for ancestor in t.lineages[node]:
                clade[ancestor] += p

    def deepest(threshold: float) -> int | None:
        best = max(
            (n for n, p in clade.items() if p >= threshold),
            key=lambda n: len(t.lineages[n]),
            default=None,
        )
        while best is not None and not _supported(t, best, used):
            best = t.parent(best)
        return best

    call = deepest(CONFIDENT)
    if call is None:
        return {"status": "unresolved", **summary}
    result = {
        "status": "ok",
        **summary,
        "haplogroup": t.names[call],
        "probability": round(min(clade[call], 1.0), 4),
        "possibly": None,
        "lineage": _lineage(t, call, tested),
    }
    deeper = deepest(POSSIBLE)
    if deeper is not None and deeper != call and call in t.lineages[deeper]:
        result["possibly"] = {
            "haplogroup": t.names[deeper],
            "probability": round(clade[deeper], 4),
        }
    return result


def _posterior(t: Tree, used: dict[int, str]) -> list[float]:
    """Probability of each haplogroup given the tested bases (flat prior)."""
    nodes = len(t.names)
    match, mismatch = {}, {}
    for pos in used:
        error = min(MAX_ERROR, GENOTYPING_ERROR + t.occurrences.get(pos, 0) / nodes)
        match[pos], mismatch[pos] = math.log(1 - error), math.log(error / 3)

    def term(pos: int, base: str) -> float:
        return match[pos] if used[pos] == base else mismatch[pos]

    # Most haplogroups match rCRS at most positions: start from an all-rCRS
    # score and adjust only where a haplogroup differs.
    baseline = sum(term(p, t.rcrs[p - 1]) for p in used)
    scores = []
    for profile in t.profiles:
        score = baseline
        for pos, base in profile.items():
            if pos in used:
                score += term(pos, base) - term(pos, t.rcrs[pos - 1])
        scores.append(score)
    top = max(scores)
    weights = [math.exp(s - top) for s in scores]
    total = sum(weights)
    return [w / total for w in weights]


def _supported(t: Tree, node: int, used: dict[int, str]) -> bool:
    """At least one of the branch's own defining mutations is tested and present."""
    return any(used.get(pos) == base for pos, _, base in t.defining(node))


def _lineage(t: Tree, node: int, tested: dict[int, str]) -> list[dict]:
    """Each branch from the top of the tree to the call, with its defining
    mutations and whether the file shows them."""
    steps = []
    for i, step in enumerate(t.lineages[node]):
        markers = []
        # The top branch's differences from the other side span the whole
        # root edge, not just this branch: shown as the top of the tree.
        for pos, before, after in t.defining(step) if i else []:
            seen = tested.get(pos)
            if t.base(node, pos) != after:
                status = "reverted"  # changed again further down this line
            elif seen is None:
                status = "untested"
            else:
                status = "present" if seen == after else "absent"
            markers.append({"mutation": f"{before}{pos}{after}", "status": status})
        steps.append({"haplogroup": t.names[step], "markers": markers})
    return steps
