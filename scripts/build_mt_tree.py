"""Rebuild backend/yougene/haplogroups/data/phylotree17.json from the
haplogrep team's rCRS-oriented PhyloTree Build 17 (MIT licence).

Development tool, not part of the app: it downloads four pinned files and
checks their SHA-256 before converting. The app only reads the JSON.

    python scripts/build_mt_tree.py
"""

import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

TAG = "17.3"
BASE = f"https://raw.githubusercontent.com/genepi/phylotree-rcrs-17/{TAG}/"
FILES = {
    "src/tree.xml": "5490d3756503654001d07ed3a733bcfa8ee9ee225c50cd07c8c4260d239d85b1",
    "src/weights.txt": "d0962699365c7fe6f0b41f7c1793513fa950597c971c859beeb7dc0e3f8ab92a",
    "src/rcrs.fasta": "d166066fe1de9ea37680965c96bfbf07858527269d85c3ca62c78926b2456844",
    "src/tree.yaml": "169273ff3e6a5a41e50d21704be54f29a2d5b2b1a60235dcd220f261af7e2e07",
}
OUT = Path(__file__).resolve().parents[1] / "backend/yougene/haplogroups/data"


def fetch(name: str) -> bytes:
    with urllib.request.urlopen(BASE + name, timeout=60) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != FILES[name]:
        raise SystemExit(f"{name}: checksum {digest} doesn't match the pinned one")
    return data


# Re-rooting the tree at rCRS shifted three labels at the top by one node:
# the node labelled L1'2'3'4'5'6 has L0 as its child (so it is the root,
# mt-MRCA), the one labelled L2'3'4'5'6 has L1 (so it is L1'2'3'4'5'6), and
# "L2'3'4'6+" has L5 (so it is L2'3'4'5'6). Restore PhyloTree's names.
RELABEL = {
    "L1'2'3'4'5'6": ("mt-MRCA", "L0"),
    "L2'3'4'5'6": ("L1'2'3'4'5'6", "L1"),
    "L2'3'4'6+": ("L2'3'4'5'6", "L5"),
}


def relabel_root(nodes: list[list]) -> None:
    index = {node[0]: i for i, node in enumerate(nodes)}
    for old, (new, child) in RELABEL.items():
        if nodes[index[child]][1] != index[old]:
            raise SystemExit(f"tree layout changed: {child} isn't under {old}")
    for old, (new, _) in RELABEL.items():
        nodes[index[old]][0] = new


def main() -> None:
    raw = {name: fetch(name) for name in FILES}
    root = ET.fromstring(raw["src/tree.xml"])
    nodes: list[list] = []

    def walk(element: ET.Element, parent: int) -> None:
        for child in element.findall("haplogroup"):
            details = child.find("details")
            polys = (
                [p.text.strip() for p in details.findall("poly")]
                if details is not None
                else []
            )
            nodes.append([child.get("name"), parent, polys])
            walk(child, len(nodes) - 1)

    walk(root, -1)
    relabel_root(nodes)
    # How often each mutation recurs across the tree (column 3): fast,
    # recurrent sites are weaker evidence of a haplogroup.
    occurrences = {}
    for line in raw["src/weights.txt"].decode().splitlines():
        fields = line.split("\t")
        if len(fields) >= 3 and fields[0]:
            occurrences[fields[0]] = int(float(fields[2]))
    settings = yaml.safe_load(raw["src/tree.yaml"])
    rcrs = "".join(raw["src/rcrs.fasta"].decode().splitlines()[1:]).strip().upper()
    if len(rcrs) != 16569:
        raise SystemExit(f"rCRS has {len(rcrs)} bases, expected 16569")
    data = {
        "source": {
            "name": "PhyloTree Build 17, rCRS-oriented (haplogrep phylotree-rcrs-17)",
            "version": TAG,
            "url": "https://github.com/genepi/phylotree-rcrs-17",
            "licence": "MIT (Institute of Genetic Epidemiology); see LICENSE-phylotree-rcrs-17.txt",
            "citations": settings["source"],
        },
        "rcrs": rcrs,
        "hotspots": settings["hotspots"],
        "occurrences": occurrences,
        "nodes": nodes,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "phylotree17.json").write_text(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"{len(nodes)} haplogroups, {len(occurrences)} mutations")


if __name__ == "__main__":
    main()
