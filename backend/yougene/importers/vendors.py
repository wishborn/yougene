"""Other consumer array formats. Layouts follow the vendors' downloads (as also
parsed by the BSD-licensed ``snps`` package):

* AncestryDNA: ``#`` comments naming AncestryDNA, then a header row
  ``rsid chromosome position allele1 allele2``; tab-separated; chromosomes
  23=X, 24=Y, 25=X pseudo-autosomal, 26=MT; ``0`` alleles mean no-call. Calls
  on single-copy chromosomes are written as two identical letters.
* MyHeritage: ``#`` comments naming MyHeritage, then
  ``RSID,CHROMOSOME,POSITION,RESULT``; quoted CSV (newer files triple-quote
  each value); ``--`` no-call.
* FamilyTreeDNA (Family Finder): no comments; first line
  ``RSID,CHROMOSOME,POSITION,RESULT``; quoted CSV; the header may repeat
  where two files were concatenated.
* Living DNA: ``#`` comments naming Living DNA; tab-separated
  ``rsid chromosome position genotype`` without a header row.

All are GRCh37 plus-strand; the build is confirmed with reference SNPs.
"""

from pathlib import Path

from yougene.importers import arrays
from yougene.importers.base import Detection
from yougene.importers.twentythree import build_from_header, head


class _Vendor:
    vendor: str
    format: str

    @classmethod
    def detect(cls, path: Path) -> Detection | None:
        lines = head(path)
        if not lines or not cls.matches(lines):
            return None
        return Detection(
            vendor=cls.vendor,
            format=cls.format,
            build_from_header=build_from_header(lines),
        )

    confirm_build = staticmethod(arrays.confirm_build)


class AncestryDNA(_Vendor):
    vendor, format = "AncestryDNA", "ancestrydna-tsv"

    @staticmethod
    def matches(lines):
        return "ancestrydna" in lines[0].lower()

    @staticmethod
    def load(con, path):
        arrays.read_raw(con, path, vendor="AncestryDNA", delim="\t",
                        two_allele_columns=True)  # fmt: skip
        return arrays.build_calls(con, "AncestryDNA")


class MyHeritage(_Vendor):
    vendor, format = "MyHeritage", "myheritage-csv"

    @staticmethod
    def matches(lines):
        return "myheritage" in lines[0].lower()

    @staticmethod
    def load(con, path):
        arrays.read_raw(con, path, vendor="MyHeritage", delim=",", quoted=True)
        return arrays.build_calls(con, "MyHeritage")


class FamilyTreeDNA(_Vendor):
    vendor, format = "FamilyTreeDNA", "ftdna-csv"

    @staticmethod
    def matches(lines):
        first = lines[0].replace('"', "").strip().upper()
        return first == "RSID,CHROMOSOME,POSITION,RESULT"

    @staticmethod
    def load(con, path):
        arrays.read_raw(con, path, vendor="FamilyTreeDNA", delim=",", quoted=True)
        return arrays.build_calls(con, "FamilyTreeDNA")


class LivingDNA(_Vendor):
    vendor, format = "Living DNA", "livingdna-tsv"

    @staticmethod
    def matches(lines):
        return "living dna" in lines[0].lower()

    @staticmethod
    def load(con, path):
        arrays.read_raw(con, path, vendor="Living DNA", delim="\t")
        return arrays.build_calls(con, "Living DNA")


VENDORS = [AncestryDNA, MyHeritage, FamilyTreeDNA, LivingDNA]
