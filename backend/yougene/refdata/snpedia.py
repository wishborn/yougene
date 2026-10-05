"""Optional SNPedia pack (CC BY-NC-SA 3.0; personal, non-commercial use).

Downloaded on request through SNPedia's MediaWiki API (bots.snpedia.com), at
most one request per second, 50 pages per request, resumable.

Privacy: YouGene never asks SNPedia about a person's genotypes. It fetches the
SNP pages for every rsid on the imported chips (which reveals the chip, not
the person) and *all* genotype pages listed for each of those SNPs.

SNPedia states genotypes on the strand given by each SNP page's
``Orientation``; YouGene's calls are plus-strand GRCh37, so lookups complement
the call when the orientation is ``minus``.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from yougene import __version__, store
from yougene.db import connect
from yougene.refdata.fetch import DownloadFailed

API = "https://bots.snpedia.com/api.php"
BATCH = 50
MIN_INTERVAL = 1.0  # seconds between requests: SNPedia asks bots to be gentle
LICENSE = "SNPedia, CC BY-NC-SA 3.0 (non-commercial). https://www.snpedia.com"
COMPLEMENT = str.maketrans("ACGT", "TGCA")

SCHEMA = """
CREATE TABLE IF NOT EXISTS snp (
    rsid VARCHAR PRIMARY KEY, orientation VARCHAR, genotypes VARCHAR[],
    summary VARCHAR, fetched_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS genotype (
    title VARCHAR PRIMARY KEY, rsid VARCHAR, genotype VARCHAR, summary VARCHAR,
    fetched_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value JSON);
"""
GENO = re.compile(r"\|geno\d=\(([ACGTDI-]+);([ACGTDI-]+)\)")


class Client:
    def __init__(
        self, opener=urllib.request.urlopen, sleep=time.sleep, clock=time.monotonic
    ):
        self.opener, self.sleep, self.clock = opener, sleep, clock
        self.last = 0.0

    def get(self, params: dict) -> dict:
        wait = MIN_INTERVAL - (self.clock() - self.last)
        if wait > 0:
            self.sleep(wait)
        self.last = self.clock()
        url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
        request = urllib.request.Request(
            url, headers={"User-Agent": f"YouGene/{__version__} (personal local app)"}
        )
        try:
            with self.opener(request, timeout=60) as response:
                return json.load(response)
        except (OSError, ValueError) as error:
            raise DownloadFailed(
                "Couldn't reach SNPedia. Try again later; pages already fetched are "
                "kept and the download picks up where it stopped."
            ) from error

    def pages(self, titles: list[str]) -> dict[str, str | None]:
        data = self.get(
            {"action": "query", "prop": "revisions", "rvprop": "content",
             "rvslots": "main", "formatversion": "2", "titles": "|".join(titles)}
        )  # fmt: skip
        out: dict[str, str | None] = {}
        for page in data.get("query", {}).get("pages", []):
            revisions = page.get("revisions") or []
            out[page["title"]] = (
                revisions[0]["slots"]["main"]["content"] if revisions else None
            )
        return out


def db_path() -> Path:
    return store.root() / "reference" / "snpedia.duckdb"


def _field(text: str, name: str) -> str | None:
    match = re.search(rf"\|{name}=([^\n|]*)", text)
    return match[1].strip() if match else None


def _orientation(text: str) -> str | None:
    """Genotype pages follow StabilizedOrientation where SNPedia gives it."""
    value = _field(text, "StabilizedOrientation") or _field(text, "Orientation")
    return value.lower() if value else None


def _first_paragraph(text: str) -> str | None:
    body = re.sub(r"\{\{.*?\}\}", "", text, flags=re.S)
    body = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", body)
    for paragraph in body.split("\n\n"):
        paragraph = " ".join(paragraph.split())
        if len(paragraph) > 40:
            return paragraph[:600]
    return None


def chip_rsids() -> list[str]:
    """Every rsid in every imported sample (chip content, no genotypes)."""
    found: set[str] = set()
    for sample in store.list_samples():
        con = store.open_sample(sample["id"])
        try:
            found.update(
                r[0]
                for r in con.execute(
                    "SELECT probe_id FROM calls WHERE id_kind = 'rs'"
                ).fetchall()
            )
        finally:
            con.close()
    return sorted(found)


def install(
    progress: Callable[[float, str], None] = lambda v, m: None,
    client: Client | None = None,
    rsids: Iterable[str] | None = None,
) -> dict:
    client = client or Client()
    db_path().parent.mkdir(parents=True, exist_ok=True)
    con = connect(db_path())
    try:
        con.execute(SCHEMA)
        progress(0.01, "Listing SNPedia SNP pages")
        known = _list_snp_titles(con, client)
        wanted = [r for r in (rsids or chip_rsids()) if r.lower() in known]
        have = {r[0] for r in con.execute("SELECT rsid FROM snp").fetchall()}
        todo = [r for r in wanted if r not in have]
        now = datetime.now(UTC).replace(tzinfo=None)
        for i in range(0, len(todo), BATCH):
            batch = todo[i : i + BATCH]
            pages = client.pages([r.capitalize() for r in batch])
            for rsid in batch:
                text = pages.get(rsid.capitalize())
                if text is None:
                    continue
                genotypes = [f"({a};{b})" for a, b in GENO.findall(text)]
                con.execute(
                    "INSERT OR REPLACE INTO snp VALUES (?, ?, ?, ?, ?)",
                    [rsid, _orientation(text),
                     genotypes, _first_paragraph(text), now],
                )  # fmt: skip
            progress(0.05 + 0.45 * (i + len(batch)) / max(len(todo), 1),
                     f"SNP pages {i + len(batch):,} of {len(todo):,}")  # fmt: skip
        titles = [
            f"{rsid.capitalize()}{g}"
            for rsid, genotypes in con.execute(
                "SELECT rsid, genotypes FROM snp"
            ).fetchall()
            for g in genotypes or []
        ]
        have = {r[0] for r in con.execute("SELECT title FROM genotype").fetchall()}
        todo = [t for t in titles if t not in have]
        for i in range(0, len(todo), BATCH):
            batch = todo[i : i + BATCH]
            pages = client.pages(batch)
            for title in batch:
                text = pages.get(title)
                rsid, genotype = title.split("(", 1)
                con.execute(
                    "INSERT OR REPLACE INTO genotype VALUES (?, ?, ?, ?, ?)",
                    [title, rsid.lower(), "(" + genotype,
                     (_field(text, "summary") if text else None), now],
                )  # fmt: skip
            progress(0.5 + 0.5 * (i + len(batch)) / max(len(todo), 1),
                     f"Genotype pages {i + len(batch):,} of {len(todo):,}")  # fmt: skip
        snps, genos = con.execute(
            "SELECT (SELECT count(*) FROM snp), (SELECT count(*) FROM genotype)"
        ).fetchone()
        meta = {"snps": snps, "genotype_pages": genos, "license": LICENSE,
                "updated_at": datetime.now(UTC).isoformat()}  # fmt: skip
        con.execute(
            "INSERT OR REPLACE INTO meta VALUES ('pack', ?)", [json.dumps(meta)]
        )
        return meta
    finally:
        con.close()


def _list_snp_titles(con, client: Client) -> set[str]:
    row = con.execute("SELECT value FROM meta WHERE key = 'index'").fetchone()
    if row:
        return set(json.loads(row[0]))
    titles: list[str] = []
    params = {"action": "query", "list": "categorymembers",
              "cmtitle": "Category:Is_a_snp", "cmlimit": "500"}  # fmt: skip
    while True:
        data = client.get(params)
        titles += [m["title"].lower() for m in data["query"]["categorymembers"]]
        if "continue" not in data:
            break
        params = {**params, **data["continue"]}
    con.execute("INSERT OR REPLACE INTO meta VALUES ('index', ?)", [json.dumps(titles)])
    return set(titles)


def status() -> dict:
    if not db_path().exists():
        return {"installed": False, "license": LICENSE}
    con = connect(db_path(), read_only=True)
    try:
        row = con.execute("SELECT value FROM meta WHERE key = 'pack'").fetchone()
    except Exception:
        row = None
    finally:
        con.close()
    return {
        "installed": row is not None,
        "license": LICENSE,
        **(json.loads(row[0]) if row else {}),
    }


def lookup(rsid: str, alleles: str) -> dict | None:
    """SNPedia's text for this plus-strand call, or None."""
    if not db_path().exists() or len(alleles) != 2:
        return None
    con = connect(db_path(), read_only=True)
    try:
        snp = con.execute(
            "SELECT orientation, summary, genotypes FROM snp WHERE rsid = ?", [rsid]
        ).fetchone()
        if snp is None:
            return None
        orientation, about, genotypes = snp
        if orientation not in ("plus", "minus"):
            return None  # can't orient the call safely
        letters = alleles.translate(COMPLEMENT) if orientation == "minus" else alleles
        a, b = sorted(letters)
        listed = set(
            "".join(genotypes or []).replace("(", "").replace(")", "").replace(";", "")
        )
        if not {a, b} <= listed:
            return None  # letters don't fit this SNP as SNPedia lists it
        geno = con.execute(
            "SELECT summary FROM genotype WHERE rsid = ? AND genotype IN (?, ?)",
            [rsid, f"({a};{b})", f"({b};{a})"],
        ).fetchone()
    finally:
        con.close()
    return {
        "rsid": rsid,
        "snpedia_genotype": f"({a};{b})",
        "orientation": orientation,
        "about": about,
        "genotype_summary": geno[0] if geno else None,
        "url": f"https://www.snpedia.com/index.php/{rsid.capitalize()}",
        "license": LICENSE,
    }
