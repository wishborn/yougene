"""Paternal line: Y-chromosome haplogroup with yhaplo.

yhaplo (23andMe, https://github.com/23andMe/yhaplo) walks the ISOGG 2016
Y tree from the root, following branches whose defining SNPs are derived and
stopping where they're ancestral. It was built for and validated on 23andMe
array data. Licence: non-commercial use (see README); the Yhaplo software
was developed by 23andMe, Inc.

yhaplo keeps its tree and run state on classes, so calls are serialised.
Positions are GRCh37, as in our store.
"""

import logging
import threading

from yhaplo.api.command_line_args import get_command_line_arg_defaults
from yhaplo.config import Config
from yhaplo.sample import TextSample

MIN_INFORMATIVE = 20  # Y positions in the tree needed to try at all
_lock = threading.Lock()
logging.getLogger("yhaplo").setLevel(logging.WARNING)


class _MemorySample(TextSample):
    """A sample from a position -> base mapping, with no input file."""

    def purge_data(self) -> None:
        # Keep the SNP lists: they're the evidence we show.
        self.genotypes.clear()


def _configure() -> type[_MemorySample]:
    args = get_command_line_arg_defaults()
    args.data_fp = "memory.genos.txt"  # selects text mode; never opened
    _MemorySample.configure(Config(command_line_args=args, suppress_output=True))
    return _MemorySample


def classify(calls: dict[int, str]) -> dict:
    """``calls``: GRCh37 chrY position -> single base, for single-copy calls."""
    with _lock:
        sample_class = _configure()
        positions = sorted(p for p in calls if p in sample_class.tree.snp_pos_set)
        summary = {"tested": len(calls), "informative": len(positions)}
        if len(positions) < MIN_INFORMATIVE:
            return {"status": "insufficient", **summary}
        sample_class.position_to_column_index = {p: i for i, p in enumerate(positions)}
        sample = sample_class("sample", [calls[p] for p in positions])
        sample.call_haplogroup()
        if not sample.most_derived_snp:
            return {"status": "unresolved", **summary}
        lineage: list[dict] = []
        for snp in sample.der_snp_list:
            group = snp.node.haplogroup
            if not lineage or lineage[-1]["haplogroup"] != group:
                lineage.append({"haplogroup": group, "markers": []})
            lineage[-1]["markers"].append(
                {
                    "name": snp.label,
                    "mutation": f"{snp.ancestral}{snp.position}{snp.derived}",
                    "status": "present",
                }
            )
        return {
            "status": "ok",
            **summary,
            "haplogroup": sample.haplogroup,  # YCC name, e.g. R1b1a2a1a2
            "short_name": sample.hg_snp,  # e.g. R-M269
            "observed_name": sample.hg_snp_obs,
            "derived": len(sample.der_snp_list),
            "ancestral": len(sample.anc_snp_list),
            "lineage": lineage,
        }
