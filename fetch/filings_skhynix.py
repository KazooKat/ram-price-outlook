"""SK hynix quarterly results from the company's own earnings press releases.

Source: SK hynix newsroom (news.skhynix.com, WordPress REST API) - the official
English earnings releases, one per quarter. DART needs an API key, so it is not
used. Figures are K-IFRS consolidated, as stated in the release text.

Each value keeps the sentence it was parsed from (`source_text`) so it can be
audited against the release.

Output: data/raw/skhynix_results/quarterly_results.csv
"""
from __future__ import annotations

import html
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "skhynix_results"
API = "https://news.skhynix.com/en/wp-json/wp/v2/posts"
START_YEAR = 2015
UA = {"User-Agent": "Mozilla/5.0 (ram-price-outlook research)"}

TITLE_RE = re.compile(r"(?i)(announces|reports).*(results|quarter)")
WORD_Q = {"first": 1, "second": 2, "third": 3, "fourth": 4}


def list_posts() -> list[dict]:
    posts, page = [], 1
    while True:
        try:
            r = get(API, params={"search": "results", "per_page": 100, "page": page,
                                 "_fields": "id,date,link,title"}, headers=UA)
        except (RuntimeError, requests.HTTPError):
            break  # WP returns 400 past the last page
        batch = r.json()
        if not batch:
            break
        posts += batch
        page += 1
        time.sleep(0.5)
    return [p for p in posts if TITLE_RE.search(p["title"]["rendered"])]


def quarter_from_title(title: str) -> tuple[int, int] | None:
    t = html.unescape(title)
    m = re.search(r"(?i)\b([1-4])Q\s?(\d{2,4})\b", t)  # 2Q25, 2Q 2026, 4Q23
    if m:
        y = int(m.group(2))
        return (y + 2000 if y < 100 else y), int(m.group(1))
    m = re.search(r"(?i)(first|second|third|fourth) quarter (?:of )?(?:FY ?)?(\d{4})", t)
    if m:
        return int(m.group(2)), WORD_Q[m.group(1).lower()]
    # "Fiscal Year 2017 and Fourth Quarter Results", "2022 and Fourth Quarter", "FY25"
    m = re.search(r"(?i)(?:fiscal year |FY ?)?(\d{4}|\d{2}) and fourth quarter", t) or \
        re.search(r"(?i)\bFY ?(\d{2,4}) Financial Results", t)
    if m:
        y = int(m.group(1))
        return (y + 2000 if y < 100 else y), 4
    return None


def text_of(post_id: int) -> str:
    r = get(f"{API}/{post_id}", params={"_fields": "content"}, headers=UA)
    c = re.sub(r"(?s)<[^>]+>", " ", r.json()["content"]["rendered"])
    return re.sub(r"\s+", " ", html.unescape(c)).strip()


AMT = r"(-?[\d][\d,]*(?:\.\d+)?)\s*(trillion|billion)\s*(?:Korean )?won"
# Up to 70 chars between the metric word and its verb, never crossing another metric word.
GAP = r"(?:(?!profit|income|loss|revenue|sales)[^.;·▪])"
VERB = r"(?:of|was|were|at|totaled|amounted to|reached|recorded|to)"
METRICS = {
    # (metric, sign) -> patterns; group 1 = amount, group 2 = unit
    ("revenue", 1): [rf"(?:revenues?|sales)\b{GAP}{{0,70}}?\b{VERB}\s+{AMT}",
                     rf"{AMT}\s+in\s+(?:revenues?|sales)"],
    ("operating_profit", 1): [rf"operating (?:profit|income)\b{GAP}{{0,40}}?\s{AMT}",
                              rf"{AMT}\s+in\s+operating (?:profit|income)"],
    ("operating_profit", -1): [rf"operating loss(?:es)?\b{GAP}{{0,40}}?\s{AMT}",
                               rf"{AMT}\s+in\s+operating loss"],
    ("net_profit", 1): [rf"net (?:profit|income)\b{GAP}{{0,40}}?\s{AMT}",
                        rf"{AMT}\s+in\s+net (?:profit|income)"],
    ("net_profit", -1): [rf"net loss(?:es)?\b{GAP}{{0,40}}?\s{AMT}",
                         rf"{AMT}\s+in\s+net loss"],
}
ANNUAL = re.compile(r"(?i)fiscal year|for the year|full year|annual|yearly|\bFY ?\d|for 20\d\d\b|"
                    r"revenues? for 20\d\d|20\d\d revenues?|in 20\d\d\b")
QUARTER_WORD = re.compile(r"(?i)\b(?:first|second|third|fourth) quarter|\b[1-4]Q|\bQ[1-4]\b|three months|"
                          r"three-month|the quarter|quarterly")
Q4_WORD = re.compile(r"(?i)fourth quarter|\b4Q|\bQ4\b|three months|three-month|the quarter|quarterly")
SENT_SPLIT = re.compile(r"(?<=[.!?])[\"”’]?\s+(?=[A-Z“\"‘(])|\s[·▪–]\s|▲|\s•\s")


def extract(text: str, q: int) -> dict:
    """First matching sentence per metric. Q4 releases lead with full-year figures, so for Q4
    only sentences that name the quarter count; for Q1-Q3, sentences framed as annual are skipped."""
    out = {}
    for i, sent in enumerate(SENT_SPLIT.split(text)):
        if not sent:
            continue
        if q == 4 and not Q4_WORD.search(sent):
            continue
        if q != 4 and ANNUAL.search(sent) and not QUARTER_WORD.search(sent):
            continue
        for (metric, sign), pats in METRICS.items():
            if metric in out:
                continue
            for pat in pats:
                m = re.search(pat, sent, flags=re.I)
                if m:
                    val = float(m.group(1).replace(",", "")) * (1 if m.group(2).lower() == "trillion" else 0.001)
                    out[metric] = (sign * val, sent.strip())
                    break
    return out


N = r"(\d+(?:\.\d+)?)\s?%"
UPV = ("increased", "rose", "grew", "climbed", "surged", "jumped")
DOWNV = ("declined", "decreased", "fell", "dropped", "slipped", "lowered")
V = r"(" + "|".join(UPV + DOWNV) + r")(?: only)?"
BITS = r"bit shipments?"
ASP = r"(?:average selling prices?|ASPs?)"


def _sign(verb: str) -> int:
    return -1 if verb.lower() in DOWNV else 1


def extract_dram_nand(text: str) -> list[tuple[str, float | None, str]]:
    """QoQ bit-shipment / ASP statements (mainly 2015-2021 releases).

    Numbers are emitted only for unambiguous constructions; any other sentence
    mentioning DRAM/NAND bits or ASP is kept as a text-only `statement` row.
    """
    rows = []
    for sent in re.split(r"(?<=[.!?])[\"”’]?\s+", text):
        if not re.search(rf"(?i){BITS}|{ASP}", sent):
            continue
        prods = [p for p in ("DRAM", "NAND") if p in sent]
        got: list[tuple[str, float]] = []
        # "DRAM and NAND Flash bit shipments increased 4% and 8% but the ASP slipped 8% and 6% respectively"
        m = re.search(rf"(?i)DRAM and NAND(?: Flash)? {BITS} {V}(?: by)? {N} and {N}.*?{ASP} {V}(?: by)? {N} and {N}", sent)
        if m:
            got = [("dram_bit_shipments_qoq_pct", _sign(m[1]) * float(m[2])),
                   ("nand_bit_shipments_qoq_pct", _sign(m[1]) * float(m[3])),
                   ("dram_asp_qoq_pct", _sign(m[4]) * float(m[5])),
                   ("nand_asp_qoq_pct", _sign(m[4]) * float(m[6]))]
        elif len(prods) == 1:
            p = prods[0].lower()
            # "bit shipments and the average selling price decreased 5% and 4% respectively/each"
            m = re.search(rf"(?i){BITS} and (?:the )?(?:DRAM )?{ASP} {V}(?: by)? {N} and {N}", sent)
            if m:
                got = [(f"{p}_bit_shipments_qoq_pct", _sign(m[1]) * float(m[2])),
                       (f"{p}_asp_qoq_pct", _sign(m[1]) * float(m[3]))]
            else:
                # verb + % must follow "bit shipments" without passing an ASP mention, and vice versa
                mb = re.search(rf"(?i){BITS}(?:(?!average selling|ASP)[^%])*?\b{V}(?: by)? {N}", sent)
                if mb:
                    got.append((f"{p}_bit_shipments_qoq_pct", _sign(mb[1]) * float(mb[2])))
                ma = re.search(rf"(?i){ASP}\s+(?:{V}\s+)?(?:by )?{N}", sent) or \
                    re.search(rf"(?i){ASP}(?:(?!bit shipment)[^%])*?\b{V}(?: by)? {N}", sent)
                if ma:
                    verb = ma[1] if ma[1] else (mb[1] if mb else None)
                    if verb:  # "...and the average selling price by 6%" inherits the bit-shipment verb
                        got.append((f"{p}_asp_qoq_pct", _sign(verb) * float(ma[2])))
        if got:
            rows += [(k, v, sent.strip()) for k, v in got]
        elif prods:
            rows.append((f"{'_'.join(x.lower() for x in prods)}_statement", None, sent.strip()))
    return rows


def main() -> None:
    out = raw_dir(SOURCE)
    posts = list_posts()
    by_q: dict[tuple[int, int], list[dict]] = {}
    for p in posts:
        yq = quarter_from_title(p["title"]["rendered"])
        if yq and yq[0] >= START_YEAR:
            by_q.setdefault(yq, []).append(p)
    rows = []
    for (y, q), plist in sorted(by_q.items()):
        # Some quarters have several posts (infographic-only duplicates); keep the longest text.
        texts = []
        for p in plist:
            texts.append((text_of(p["id"]), p))
            time.sleep(0.4)
        text, p = max(texts, key=lambda t: len(t[0]))
        base = {"period": f"{y}Q{q}", "period_end": pd.Period(f"{y}Q{q}").end_time.date().isoformat(),
                "company": "SK hynix", "release_date": p["date"][:10], "source_url": p["link"]}
        for metric, (val, sent) in extract(text, q).items():
            rows.append({**base, "metric": metric, "value": round(val, 6), "unit": "KRW trillion",
                         "basis": "K-IFRS consolidated, quarter", "source_text": sent[:600]})
        for metric, val, sent in extract_dram_nand(text):
            rows.append({**base, "metric": metric, "value": val,
                         "unit": "text only" if val is None else "pct QoQ (company-stated)",
                         "basis": "company-stated approx", "source_text": sent[:600]})
        print(f"{y}Q{q}: {sum(1 for r in rows if r['period'] == f'{y}Q{q}')} values", flush=True)

    df = pd.DataFrame(rows)
    stmt = df["metric"].str.endswith("_statement")
    df = pd.concat([df[~stmt].drop_duplicates(["period", "metric"], keep="first"),
                    df[stmt].drop_duplicates(["period", "metric", "source_text"])]).sort_values(["period", "metric"])
    df.to_csv(out / "quarterly_results.csv", index=False, encoding="utf-8")
    print(f"wrote {len(df)} rows -> {out / 'quarterly_results.csv'}")

    write_source_note(
        SOURCE,
        title="SK hynix quarterly results (company earnings press releases)",
        urls=[API + "?search=results", "https://news.skhynix.com/en/"],
        notes="""
Parsed from SK hynix's official English earnings press releases (newsroom).
DART (Korea FSS) was not used because its API requires a key.

- revenue / operating_profit / net_profit: KRW trillion, K-IFRS consolidated,
  for the quarter (Q4 releases also state full-year figures; the parser skips
  sentences framed as annual). Losses are negative.
- dram_/nand_ bit_shipments_qoq_pct and asp_qoq_pct: quarter-over-quarter
  changes as stated in the release (mostly 2015-2020 releases; later releases
  stopped giving numeric ASP/bit figures). Company-stated, rounded.
- source_text holds the sentence each value was parsed from - audit there.
- Regex extraction from prose: a quarter missing a metric means the parser
  did not find a matching sentence, not that the value is zero.
- SK hynix listed ADRs on Nasdaq in July 2026 (CIK 2120882) and now files 6-Ks
  on EDGAR; quarterly history before that is only on the company site / DART.
""",
    )


if __name__ == "__main__":
    main()
