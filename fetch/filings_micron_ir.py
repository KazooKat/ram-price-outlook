"""Micron company-reported statements: DRAM/NAND price and bit changes, DIO, results, guidance.

Sources (all published by Micron; no analyst numbers):
1. Earnings-call prepared remarks (PDF, investors.micron.com, FQ1-2019 onward). The CFO
   section states each quarter's DRAM and NAND revenue and the sequential (QoQ) change
   in bit shipments and prices as a verbal range, e.g. "Prices increased high-teens
   percentage range"; it also states days of inventory (DIO).
2. 10-Q MD&A (SEC EDGAR). FY2017-FY2018 10-Qs carry a table "Average selling prices per
   gigabit <change> vs prior quarter"; FY2022+ 10-Qs carry "Sales of DRAM products
   increased X% primarily due to ...". Used for FY2017-18 (before the remarks archive)
   and as a cross-check of the remarks.
3. Earnings press releases (8-K item 2.02, exhibit 99.1, SEC EDGAR): quarterly GAAP
   revenue and gross margin (cross-checked against XBRL companyfacts) and the
   "Business Outlook" table = company guidance for the next quarter (label: guidance).

Verbal ranges are kept verbatim (`phrase`, `statement`) and also mapped to approximate
numbers (`low`, `high`, `mid`) with this convention - it is OUR reading, not Micron's:
  single-digit: low 1-3, mid 4-6, high/upper 7-9;  teens: low 10-13, mid 14-16, high 17-19
  "low/mid/high-N0s" or "N0% range": N0-N3 / N4-N6 / N7-N9 (e.g. low-60s -> 60-63)
  low double-digit 10-13; "approximately N%" -> N; "over N%" -> low N, high blank;
  flat -> 0; "slightly"/"modestly" -> direction only, numbers blank.
Decreases are negative (low = more negative bound).

Outputs in data/raw/micron_ir/:
  price_bit_statements.csv  QoQ ASP and bit-shipment changes by technology
  remarks_metrics.csv       DRAM/NAND revenue (USD bn, rounded as stated), revenue QoQ %, DIO
  press_release_results.csv revenue and gross margin per quarter as printed in the release
  guidance.csv              next-quarter guidance (revenue, gross margin %, EPS)
  validation.csv            press release vs XBRL companyfacts, remarks vs XBRL DRAM/NAND
  remarks_text/*.txt        extracted text of each prepared-remarks PDF
"""
from __future__ import annotations

import os
import html
import io
import re
import sys
import time
from pathlib import Path

import pandas as pd
import pypdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import RAW, get, raw_dir, write_source_note  # noqa: E402

SOURCE = "micron_ir"
CIK = 723125
# SEC asks for a contact email in the User-Agent: set SEC_USER_AGENT="your-name your@email"
SEC_HEADERS = {"User-Agent": os.environ.get("SEC_USER_AGENT", "ram-price-outlook research")}
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                 "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
IR_FEED = "https://investors.micron.com/feed/FinancialReport.svc/GetFinancialReportList"
SUBMISSIONS = ["https://data.sec.gov/submissions/CIK0000723125.json",
               "https://data.sec.gov/submissions/CIK0000723125-submissions-001.json"]
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/723125/{acc}/"
QWORD = {"first": 1, "second": 2, "third": 3, "fourth": 4}


# ---------------------------------------------------------------- text helpers
def html_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[\s\xa0]+", " ", s)


def norm(s: str) -> str:
    """Undo PDF extraction artefacts: 'mid -20%' -> 'mid-20%', 'f lat' -> 'flat'."""
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\bf lat\b", "flat", s)
    s = s.replace("single digit", "single-digit").replace("double digit", "double-digit")
    return s


# ---------------------------------------------------------------- range parsing
LEVEL = {"low": 0, "lower": 0, "mid": 1, "middle": 1, "high": 2, "upper": 2}
DOWN = r"declin|decreas|down|lower|fell|drop"
UP = r"increas|\bup\b|grew|grow|rose|higher|improv|\bgain"


def magnitude(c: str) -> tuple[float | None, float | None, str]:
    """(low, high, phrase) of the first unsigned percentage magnitude in clause c.

    The earliest phrase in the clause wins, so "grew approximately 30% sequentially and in
    the mid-teens percent range year-on-year" reads as 30 (the sequential figure).
    """
    lv = r"(low|lower|mid|middle|high|upper)"
    cands = []
    m = re.search(lv + r"(?:-to-" + lv + r")?[- ]?(single-digits?|double-digits?|teens?|(\d+)0s\b|(\d+)0(?:%|-percent| percent))", c)
    if m:
        a, b, kind = m.group(1), m.group(2) or m.group(1), m.group(3)
        if kind.startswith("single"):
            lo, hi = {0: 1, 1: 4, 2: 7}[LEVEL[a]], {0: 3, 1: 6, 2: 9}[LEVEL[b]]
        elif kind.startswith(("double", "teen")):  # 10-13, 14-16, 17-19
            lo, hi = {0: 10, 1: 14, 2: 17}[LEVEL[a]], {0: 13, 1: 16, 2: 19}[LEVEL[b]]
        else:  # N0s: N0-N3, N4-N6, N7-N9
            base = int(m.group(4) or m.group(5)) * 10
            lo, hi = base + {0: 0, 1: 4, 2: 7}[LEVEL[a]], base + {0: 3, 1: 6, 2: 9}[LEVEL[b]]
        cands.append((m.start(), lo, hi, m.group(0)))
    for rx, over in ((r"(?:approximately|about|roughly|nearly|almost|close to|approached|approximate)\s+(\d+)\s?(?:%| percent)", False),
                     (r"(?:slightly over|over|more than|above)\s+(\d+)\s?(?:%| percent)", True),
                     (r"in the (\d+)-percent(?:age)? range", False),
                     (r"(\d+(?:\.\d+)?)\s?(?:%| percent)", False)):
        m = re.search(rx, c)
        if m:
            v = float(m.group(1))
            cands.append((m.start(), v, None if over else v, m.group(0)))
    for rx, lo, hi in ((r"more than doubled", 100, None),
                       (r"\b(?:roughly |approximately |relatively )?(?:flat|flattish|unchanged)\b", 0, 0),
                       (r"\b(?:slight(?:ly)?|modest(?:ly)?)\b", None, None)):
        m = re.search(rx, c)
        if m:
            cands.append((m.start(), lo, hi, m.group(0)))
    if not cands:
        return None, None, ""
    _, lo, hi, phrase = min(cands, key=lambda x: (x[0], -len(x[3])))  # earliest, then longest
    return lo, hi, phrase


def signed_change(clause: str, subject_rx: str) -> dict:
    c = norm(clause)
    # direction: first direction word after the subject (else anywhere in the clause)
    s = re.search(subject_rx, c, re.I)
    tail = c[s.start():] if s else c
    d = re.search(f"({DOWN})|({UP})|(flat|flattish|unchanged)", tail, re.I) or \
        re.search(f"({DOWN})|({UP})|(flat|flattish|unchanged)", c, re.I)
    sign = 0 if d is None else (-1 if d.group(1) else (1 if d.group(2) else 0))
    lo, hi, phrase = magnitude(tail)
    if not phrase and not re.search(r"revenue", c, re.I):  # e.g. "flattish bit shipments"
        lo, hi, phrase = magnitude(c)
    if sign < 0:  # "declined over 30%" -> low blank, high -30
        lo, hi = (-hi if hi is not None else None), (-lo if lo is not None else None)
    mid = (lo + hi) / 2 if lo is not None and hi is not None else None
    direction = {1: "increase", -1: "decrease", 0: "flat"}[sign] if d is not None else "unknown"
    if re.search(r"flat|unchanged", phrase):
        direction = "flat"
    return {"direction": direction, "low": lo, "high": hi, "mid": mid, "phrase": phrase}


PRICE_RX = r"\bASPs?\b|average selling prices?|\bprices?\b"
BITS_RX = r"bit shipments?|shipment quantities|\bbits\b|gigabits sold|gigabytes sold|sales volumes?"


def clauses(paragraph: str) -> list[str]:
    sents = re.split(r"(?<=[a-z%)\d])\.\s+(?=[A-Z])", paragraph)
    out = []
    for s in sents:
        if re.match(r"\s*(For (the |full )?(fiscal year|FY)|Fiscal 20\d\d|Year-over-year|Year-on-year)", s):
            continue  # annual / YoY sentences
        out += re.split(r",\s*(?:and\s+|while\s+|with\s+)?|\s+while\s+|;\s*|\s+and\s+(?!prices? both)(?=(?:ASPs?|average selling|prices?|bit|shipment))", s)
    return [c for c in out if c.strip()]


def first_clause(paragraph: str, rx: str, exclude: str | None = None) -> str | None:
    for c in clauses(paragraph):
        if re.search(rx, c, re.I) and (exclude is None or not re.search(exclude, c, re.I)):
            if re.search(f"{DOWN}|{UP}|flat|unchanged|%|percent|digit|teens", c, re.I):
                return c.strip()
    return None


# ---------------------------------------------------------------- prepared remarks
def tech_paragraph(t: str, tech: str, start: int = 0) -> tuple[str | None, int]:
    end_rx = {"DRAM": r"(?:Fiscal Q\d |FQ\d |Trade |Our overall )?NAND\b",
              "NAND": r"Revenue by [Bb]usiness [Uu]nit|Now turning|BUSINESS UNIT|REVENUE BY|Revenue by|"
                      r"Gross margin|GROSS MARGIN|Consolidated gross|Business unit|Financial performance|"
                      r"Turning to"}[tech]
    for m in re.finditer(r"(?:Fiscal Q\d |FQ\d )?(?:Trade )?" + tech + r" revenues? ", t[start:]):
        a = start + m.start()
        w = t[a:a + 700]
        if re.search(r"ASP|[Pp]rice", w) and re.search(r"[Bb]it|shipment", w):
            rest = t[a:]
            e = re.search(end_rx, rest[40:])
            stop = 40 + e.start() if e and e.start() < 1500 else 900
            return rest[:stop], a + stop
    return None, start


def remarks_list() -> list[dict]:
    out = []
    for y in range(2018, 2031):
        r = get(IR_FEED, params={"LanguageId": 1, "reportTypes": "", "reportSubTypeList": "",
                                 "includeTags": "true", "year": y, "excludeSelection": 1},
                headers=BROWSER_HEADERS).json()
        for rep in r.get("GetFinancialReportListResult", []):
            q = QWORD.get(rep["ReportSubType"].split()[0].lower())
            for d in rep["Documents"]:
                if d["DocumentCategory"] == "remarks" and q:
                    out.append({"fy": rep["ReportYear"], "fq": q, "url": d["DocumentPath"]})
        time.sleep(0.3)
    return out


def dio(t: str) -> tuple[float | None, str]:
    pats = [r"days of inventory (?:\(DIO\) )?at (\d{2,3})",
            r"(?:[Aa]verage days(?: of inventory)?(?: for the quarter)?|average DIO for the quarter)"
            r"[^.]{0,30}?(?:were|was)(?: down to)? (\d{2,3}) days",
            r"\$[\d.]+ billion(?: of inventory)?,? or (\d{2,3}) days",
            r"[Dd]ays of inventory (?:was|were) (\d{2,3})",
            r"ended with (\d{2,3}) days of inventory"]
    for p in pats:
        m = re.search(p, t)
        if m:
            return float(m.group(1)), t[max(0, m.start() - 80):m.end() + 40]
    return None, ""


def parse_remarks(items: list[dict], out_dir: Path) -> tuple[list[dict], list[dict]]:
    stmts, metrics = [], []
    tdir = out_dir / "remarks_text"
    tdir.mkdir(exist_ok=True)
    for it in items:
        label = f"FQ{it['fq']}-FY{it['fy']}"
        pdf = get(it["url"], headers=BROWSER_HEADERS).content
        t = " ".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
        t = re.sub(r"\s+", " ", t)
        (tdir / f"{label}.txt").write_text(t, encoding="utf-8")
        base = {"fiscal_year": it["fy"], "fiscal_quarter": f"Q{it['fq']}", "period": label,
                "company": "MU", "source_type": "prepared_remarks", "source_url": it["url"]}
        pos = 0
        for tech in ("DRAM", "NAND"):
            para, pos = tech_paragraph(t, tech, pos)
            if not para:
                print(f"  {label} {tech}: paragraph not found")
                continue
            pnorm = norm(para)
            for measure, rx, excl in (("asp_qoq_pct", PRICE_RX, None), ("bits_qoq_pct", BITS_RX, None)):
                c = first_clause(pnorm, rx, excl)
                row = {**base, "technology": tech, "metric": measure, "comparison": "QoQ",
                       "unit": "pct (approx range)", "statement": c, "paragraph": para}
                if c:
                    # "bit shipments and prices both ..." clauses carry both subjects
                    row.update(signed_change(c, rx))
                stmts.append(row)
            m = re.search(tech + r" revenues? (?:was|were) (?:a record |approximately |an all-time high of )?\$([\d.]+) (billion|million)", pnorm)
            if m:
                v = float(m.group(1)) / (1000 if m.group(2) == "million" else 1)
                metrics.append({**base, "technology": tech, "metric": "revenue", "value": v,
                                "unit": "USD bn (as stated, rounded)", "statement": m.group(0)})
            m = re.search(r"(?:Sequentially, )?" + tech + r" revenues? (increased|decreased|declined|grew|was down|was up)"
                          r" (?:by )?(\d+)\s?(?:%|percent)(?: sequentially| quarter over quarter| quarter-over-quarter|"
                          r" from the prior quarter|\.)", pnorm)
            m2 = re.search(r"Sequentially, " + tech + r" revenues? (increased|decreased|declined) (\d+)%", pnorm)
            m3 = re.search(tech + r" revenues? (?:increased|decreased|declined|was down|was up|grew) \d+\s?(?:%|percent) "
                           r"(?:year[- ]over[- ]year|year-on-year|relative to [^ ]+ \d{4}) and (?:was )?(increased|decreased|declined|up|down)? ?(\d+)\s?(?:%|percent) "
                           r"(?:sequentially|from the prior quarter|quarter[- ]over[- ]quarter)", pnorm)
            m4 = re.search(tech + r" revenues? (increased|decreased|declined|grew) (\d+)\s?(?:%|percent) (?:sequentially|quarter over quarter|quarter-over-quarter)", pnorm)
            mm = m2 or m4 or m3 or m
            if mm:
                verb = (mm.group(1) or "")
                if mm is m3 and not verb:  # "down 28 percent year-over-year and 30 percent sequentially"
                    verb = re.search(tech + r" revenues? (increased|decreased|declined|was down|was up|grew)", pnorm).group(1)
                sgn = -1 if re.search(DOWN, verb) else 1
                metrics.append({**base, "technology": tech, "metric": "revenue_qoq_pct",
                                "value": sgn * float(mm.group(2)), "unit": "pct", "statement": mm.group(0)})
        d, ctx = dio(t)
        metrics.append({**base, "technology": "total", "metric": "dio_days", "value": d,
                        "unit": "days", "statement": ctx})
        print(f"  remarks {label} ok (DIO {d})")
        time.sleep(0.3)
    return stmts, metrics


# ---------------------------------------------------------------- SEC filings
def sec_filings(forms: tuple, since: str) -> list[dict]:
    out = []
    for u in SUBMISSIONS:
        b = get(u, headers=SEC_HEADERS).json()
        b = b["filings"]["recent"] if "filings" in b else b
        for i, f in enumerate(b["form"]):
            if f in forms and b["filingDate"][i] >= since:
                out.append({"form": f, "filed": b["filingDate"][i], "accn": b["accessionNumber"][i],
                            "primary": b["primaryDocument"][i], "items": b.get("items", [""] * len(b["form"]))[i],
                            "report_date": b["reportDate"][i]})
    return sorted(out, key=lambda x: x["filed"])


def quarter_label(t: str) -> tuple[int | None, int | None, str | None]:
    m = re.search(r"results for (?:its|the) (first|second|third|fourth) quarter (?:and full year )?of (?:fiscal )?(\d{4})"
                  r"(?:,)? which ended ([A-Z][a-z]+ \d{1,2}, \d{4})", t)
    if m:
        return int(m.group(2)), QWORD[m.group(1)], m.group(3)
    m = re.search(r"(first|second|third|fourth) quarter of (?:fiscal )?(\d{4})", t, re.I)
    if m:
        return int(m.group(2)), QWORD[m.group(1).lower()], None
    return None, None, None


def micron_fiscal(report_date: str) -> tuple[int, int]:
    """Fiscal (year, quarter) of a Micron period end; FY ends on the Thursday nearest Aug 31."""
    d = pd.Timestamp(report_date)
    if d.month >= 10:
        return d.year + 1, 1
    if d.month <= 1:
        return d.year, 1
    return d.year, {2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: 3, 8: 4, 9: 4}[d.month]


def money_m(s: str) -> float:
    neg = s.strip().startswith("(")
    v = float(re.sub(r"[^\d.]", "", s))
    return -v if neg else v


def parse_press_releases() -> tuple[list[dict], list[dict]]:
    res, guid = [], []
    for f in sec_filings(("8-K",), "2016-06-01"):
        if "2.02" not in f["items"]:
            continue
        base = ARCHIVE.format(acc=f["accn"].replace("-", ""))
        items = get(base + "index.json", headers=SEC_HEADERS).json()["directory"]["item"]
        ex = [i["name"] for i in items if re.search(r"ex(hibit)?\.?99\.?1|ex991|exhibit991", i["name"], re.I)]
        if not ex:
            print(f"  8-K {f['filed']}: no exhibit 99.1")
            continue
        url = base + ex[0]
        t = html_text(get(url, headers=SEC_HEADERS).text)
        fy, fq, ended = quarter_label(t)
        period = f"FQ{fq}-FY{fy}" if fy else None
        common = {"fiscal_year": fy, "fiscal_quarter": f"Q{fq}" if fq else None, "period": period,
                  "period_end": pd.to_datetime(ended).date().isoformat() if ended else None,
                  "company": "MU", "release_date": f["filed"], "source_type": "press_release_8-K_ex99.1",
                  "source_url": url}
        m = re.search(r"Quarterly Financial Results.{0,200}?(?:Net sales|Revenue) \$ ([\d,]+) .{0,80}?Gross margin \$? ?(\(?[\d,]+\)?) "
                      r".{0,120}?(?:percent|Percent) of (?:net sales|revenue) (\(?[\d.]+ ?%\)?).{0,40}?(\(?[\d.]+ ?%\)?) (\(?[\d.]+ ?%\)?) "
                      r"(\(?[\d.]+ ?%\)?)", t)
        if m:
            g = m.groups()
            res += [
                {**common, "metric": "revenue", "value": money_m(g[0]), "unit": "USD mn", "basis": "GAAP"},
                {**common, "metric": "gross_profit", "value": money_m(g[1]), "unit": "USD mn", "basis": "GAAP"},
                {**common, "metric": "gross_margin_pct", "value": money_m(g[2]), "unit": "pct", "basis": "GAAP"},
                {**common, "metric": "gross_margin_pct", "value": money_m(g[5]), "unit": "pct", "basis": "non-GAAP"},
            ]
        else:
            m = re.search(r"CONSOLIDATED FINANCIAL SUMMARY.{0,300}?Net sales \$ ([\d,]+) .{0,200}?Gross margin (\(?[\d,]+ ?\)?) ", t)
            if m:
                res += [
                    {**common, "metric": "revenue", "value": money_m(m.group(1)), "unit": "USD mn", "basis": "GAAP"},
                    {**common, "metric": "gross_profit", "value": money_m(m.group(2)), "unit": "USD mn", "basis": "GAAP"},
                ]
            else:
                print(f"  8-K {f['filed']} {period}: results table not parsed")
        # ---- guidance (Business Outlook table)
        o = re.search(r"(?:Business )?Outlook The (?:following )?table (?:below )?presents Micron.{0,20}s guidance for the "
                      r"(first|second|third|fourth) quarter (?:of )?(?:fiscal )?(\d{4})(.{0,900})", t)
        if not o:
            continue
        tgt = f"FQ{QWORD[o.group(1)]}-FY{o.group(2)}"
        body = o.group(3)
        g = {**common, "metric": None, "label": "guidance", "guidance_for": tgt, "period": period}
        r = re.search(r"Revenue \$([\d.]+) billion ?(?:±|\+/-) ?\$([\d.]+) (million|billion)", body)
        if r:
            mid = float(r.group(1)) * 1000
            pm = float(r.group(2)) * (1000 if r.group(3) == "billion" else 1)
            guid.append({**g, "metric": "revenue", "basis": "GAAP", "mid": mid, "plus_minus": pm,
                         "low": mid - pm, "high": mid + pm, "unit": "USD mn", "text": r.group(0)})
        else:
            r = re.search(r"Revenue \$([\d.]+) billion ?[-–] ?\$([\d.]+) billion", body)
            if r:
                lo, hi = float(r.group(1)) * 1000, float(r.group(2)) * 1000
                guid.append({**g, "metric": "revenue", "basis": "GAAP", "mid": (lo + hi) / 2, "plus_minus": (hi - lo) / 2,
                             "low": lo, "high": hi, "unit": "USD mn", "text": r.group(0)})
        gm = re.search(r"Gross margin (?:Approximately )?(\(?[\d.]+%\)?)(?: ?± ?([\d.]+)%)? (?:Approximately )?(\(?[\d.]+%\)?)(?: ?± ?([\d.]+)%)?", body)
        if gm:
            for basis, v, pm in (("GAAP", gm.group(1), gm.group(2)), ("non-GAAP", gm.group(3), gm.group(4))):
                mid = money_m(v)
                pmv = float(pm) if pm else None
                guid.append({**g, "metric": "gross_margin_pct", "basis": basis, "mid": mid, "plus_minus": pmv,
                             "low": mid - pmv if pmv is not None else None,
                             "high": mid + pmv if pmv is not None else None, "unit": "pct", "text": gm.group(0)})
        eps = re.search(r"Diluted earnings(?: \(loss\))? per share (\(?\$\(?[\d.]+\)?) ?± ?\$([\d.]+) (\(?\$\(?[\d.]+\)?) ?± ?\$([\d.]+)", body)
        if eps:
            for basis, v, pm in (("GAAP", eps.group(1), eps.group(2)), ("non-GAAP", eps.group(3), eps.group(4))):
                mid = money_m(v)
                guid.append({**g, "metric": "diluted_eps", "basis": basis, "mid": mid, "plus_minus": float(pm),
                             "low": mid - float(pm), "high": mid + float(pm), "unit": "USD", "text": eps.group(0)})
        print(f"  8-K {f['filed']} {period} ok; guidance for {tgt}")
        time.sleep(0.2)
    return res, guid


def parse_10q_mdna() -> list[dict]:
    """QoQ ASP / bit statements from 10-Q MD&A (FY2017+). 10-Ks compare full years only."""
    rows = []
    for f in sec_filings(("10-Q",), "2016-12-01"):
        url = ARCHIVE.format(acc=f["accn"].replace("-", "")) + f["primary"]
        t = norm(html_text(get(url, headers=SEC_HEADERS).text))
        fy, fq = micron_fiscal(f["report_date"])
        base = {"fiscal_year": fy, "fiscal_quarter": f"Q{fq}", "period": f"FQ{fq}-FY{fy}", "company": "MU",
                "source_type": "10-Q MD&A", "source_url": url, "comparison": "QoQ", "unit": "pct (approx range)"}
        found = False
        # FY2017-18 table: "DRAM <Q> Quarter YYYY Versus ... Average selling prices per gigabit <qoq> <yoy> Gigabits sold <qoq> <yoy>"
        # FQ1-FQ2 FY2017 label NAND (incl. MCP) as "Trade Non-Volatile Memory"
        for tech, unit_word in (("DRAM", "gigabit"), ("Trade NAND", "gigabyte"), ("Trade Non-Volatile Memory", "gigabit")):
            # FY2017 numeric table: "... (percentage change from period indicated) Net sales 20 % ...
            #   Average selling prices per gigabit 14 % 37 % 6 % Gigabits sold 5 % 51 % 60 %"
            tn = re.search(tech + r" (?:First|Second|Third) Quarter \d{4} Versus .{0,200}?percentage change from period "
                           r"indicated\) .{0,60}?Average selling prices per giga(?:bit|byte) (\(?\d+ ?\)?) ?%.{0,40}?"
                           r"Giga(?:bit|byte)s sold (\(?\d+ ?\)?) ?%", t)
            if tn:
                found = True
                for metric, cell in (("asp_qoq_pct", tn.group(1)), ("bits_qoq_pct", tn.group(2))):
                    v = money_m(cell)
                    rows.append({**base, "technology": "DRAM" if tech == "DRAM" else "NAND", "metric": metric,
                                 "statement": f"{cell.strip()}% vs prior quarter ({tech} table)", "paragraph": tn.group(0),
                                 "direction": "increase" if v > 0 else "decrease" if v < 0 else "flat",
                                 "low": v, "high": v, "mid": v, "phrase": f"{cell.strip()}%"})
                continue
            tb = re.search(tech + r" (?:First|Second|Third) Quarter \d{4} Versus .{0,120}?Average selling prices per "
                           + unit_word + r" (.+?) Giga" + unit_word[4:] + r"s sold (.+?)(?: [A-Z][a-z]+ )", t)
            if tb:
                found = True
                for metric, cell in (("asp_qoq_pct", tb.group(1)), ("bits_qoq_pct", tb.group(2))):
                    # first column (vs prior quarter): up to the second direction word
                    parts = re.split(r"(?=\b(?:increased|decreased|relatively unchanged)\b)", cell.strip())
                    parts = [p for p in parts if p.strip()]
                    qoq = parts[0] if parts else cell
                    rows.append({**base, "technology": "DRAM" if tech == "DRAM" else "NAND", "metric": metric,
                                 "statement": qoq.strip(), "paragraph": tb.group(0),
                                 **signed_change(qoq, r".")})
        for tech in ("DRAM", "NAND"):
            s = re.search(r"Sales of " + tech + r" products (?:increased|decreased|declined) \d+%[^•]*?\.(?= |$)", t)
            if s and not found:
                for metric, rx in (("asp_qoq_pct", r"average selling prices"), ("bits_qoq_pct", r"bit shipments")):
                    sent = s.group(0)
                    # isolate the phrase around the subject, e.g. "a low-60% range increase in average selling prices"
                    seg = re.split(r",| and | partially offset by | primarily due to | driven by ", sent)
                    c = next((x for x in seg if re.search(rx, x)), None)
                    row = {**base, "technology": tech, "metric": metric, "statement": c, "paragraph": sent}
                    if c:
                        row.update(signed_change(c, r"."))
                    rows.append(row)
        print(f"  10-Q {f['filed']} FQ{fq}-FY{fy}: {'table' if found else 'sentence' if rows and rows[-1]['source_url'] == url else 'no QoQ ASP statement parsed'}")
        time.sleep(0.2)
    return rows


# ---------------------------------------------------------------- validation
def validate(res: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    out = []
    cf_path = RAW / "sec_companyfacts" / "quarterly_financials.csv"
    if cf_path.exists() and not res.empty:
        cf = pd.read_csv(cf_path)
        cf = cf[cf.company == "MU"]
        for _, r in res[res.basis == "GAAP"].iterrows():
            xm = {"revenue": "revenue", "gross_profit": "gross_profit", "gross_margin_pct": "gross_margin_pct"}[r.metric]
            x = cf[(cf.metric == xm) & (cf.fiscal_year == r.fiscal_year) & (cf.fiscal_quarter == r.fiscal_quarter)]
            if x.empty:
                out.append({"check": "press_release_vs_xbrl", "period": r.period, "metric": r.metric,
                            "press_release": r.value, "xbrl": None, "match": "xbrl_not_yet_filed"})
                continue
            xv = x.value.iloc[0] / (1e6 if r.unit == "USD mn" else 1)
            tol = 0.051 if r.metric == "gross_margin_pct" else 0.5
            out.append({"check": "press_release_vs_xbrl", "period": r.period, "metric": r.metric,
                        "press_release": r.value, "xbrl": round(xv, 2),
                        "match": "ok" if abs(xv - r.value) <= tol else "MISMATCH"})
    seg_path = RAW / "sec_segments" / "segment_revenue.csv"
    if seg_path.exists() and not metrics.empty:
        seg = pd.read_csv(seg_path)
        seg = seg[(seg.company == "MU") & seg.member.isin(["mu:DRAMProductsMember", "mu:NANDProductsMember"])]
        for _, r in metrics[metrics.metric == "revenue"].iterrows():
            mem = "mu:DRAMProductsMember" if r.technology == "DRAM" else "mu:NANDProductsMember"
            x = seg[(seg.member == mem) & (seg.fiscal_year == r.fiscal_year) & (seg.fiscal_quarter == r.fiscal_quarter)]
            if x.empty:
                continue
            xv = x.value.iloc[0] / 1e9
            # remarks round to 0.1bn (and "approximately"); NAND pre-FY20 was "Trade NAND"
            out.append({"check": "remarks_vs_xbrl_segment", "period": r.period, "metric": f"{r.technology}_revenue_bn",
                        "press_release": r.value, "xbrl": round(xv, 3),
                        "match": "ok" if abs(xv - r.value) <= max(0.06, 0.03 * xv)
                        else "basis_differs" if r.fiscal_year < 2020 else "MISMATCH"})
    return pd.DataFrame(out)
# basis_differs: from FQ1-FY2020 Micron split MCP/SSD revenue into DRAM and NAND and restated
# history; XBRL keeps the restated values, pre-FY2020 remarks quote the original basis.


def main() -> None:
    out = raw_dir(SOURCE)
    print(f"[{SOURCE}] prepared remarks")
    stmts, metrics = parse_remarks(remarks_list(), out)
    print(f"[{SOURCE}] 10-Q MD&A")
    stmts += parse_10q_mdna()
    print(f"[{SOURCE}] press releases")
    res, guid = parse_press_releases()

    st = pd.DataFrame(stmts)
    st.loc[st["statement"].isna(), "direction"] = "not_stated"
    # period_end from press releases where known
    res_df = pd.DataFrame(res)
    pe = res_df.dropna(subset=["period_end"]).drop_duplicates("period")[["period", "period_end"]] if not res_df.empty else None
    met = pd.DataFrame(metrics)
    for name, df in (("price_bit_statements", st), ("remarks_metrics", met)):
        if pe is not None:
            df = df.merge(pe, on="period", how="left")
        df.sort_values(["fiscal_year", "fiscal_quarter"]).to_csv(out / f"{name}.csv", index=False)
    res_df.to_csv(out / "press_release_results.csv", index=False)
    pd.DataFrame(guid).to_csv(out / "guidance.csv", index=False)
    val = validate(res_df, met)
    val.to_csv(out / "validation.csv", index=False)
    if not val.empty:
        print(f"[{SOURCE}] validation: {val.match.value_counts().to_dict()}")
    print(f"[{SOURCE}] statements {len(st)}, metrics {len(met)}, results {len(res_df)}, guidance {len(guid)}")

    write_source_note(
        SOURCE,
        title="Micron prepared remarks, 10-Q MD&A and earnings releases",
        urls=[IR_FEED + "?LanguageId=1&year=<YYYY>", *SUBMISSIONS,
              "https://www.sec.gov/Archives/edgar/data/723125/<accession>/<exhibit 99.1>"],
        notes=__doc__ + """
Caveats
- Run filings_sec_companyfacts.py and filings_sec_segments.py first; validation.csv
  compares against their outputs.
- Prepared remarks before FQ1-2019 are not in Micron's IR feed. FQ4 QoQ statements exist only
  in remarks (10-Ks compare full years), so FQ4-FY2017 and FQ4-FY2018 have no QoQ ASP figure.
- Pre-FY2020 remarks report "Trade NAND" (excludes non-trade sales to Intel), so NAND
  revenue there differs from the XBRL NAND total.
- DIO methodology changed: FQ2-FY2021 inventory reporting change cut DIO by ~10 days; from
  FQ4-FY2021 to FQ2-FY2023 Micron quoted *average* days for the quarter, other quarters
  quote ending inventory days. FQ2-FY2023 DIO (153) includes a $1.4bn write-down
  (235 days excluding it). FQ1-FY2019 remarks state no DIO.
- Guidance before FQ1-FY2019 was published only in slides, not in the press-release text.
- `low`/`high` are an approximate numeric reading of verbal ranges (see convention above).
""",
    )


if __name__ == "__main__":
    main()
