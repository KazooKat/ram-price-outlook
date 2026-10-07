"""DRAMeXchange / TrendForce free memory price tables, rebuilt as time series from
Wayback Machine captures.

dramexchange.com (and trendforce.com/price/...) show today's free DRAM/NAND spot
prices, monthly contract prices, module/GDDR spot and SSD street prices. Only the
latest value is free; the history charts are member-only. Every archived capture
of those pages is one observation, so we sample captures across 2000-2026.

Output: data/raw/dramexchange/dramexchange_prices.csv (one row per table row per
capture). Extracted rows are cached per capture in _cache.jsonl.gz so re-runs only
fetch new captures.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import re
import sys
import time
from collections import defaultdict

import lxml.html
import pandas as pd
import requests

from fetch._common import USER_AGENT, get, raw_dir, write_source_note

SOURCE = "dramexchange"
PARSER_VERSION = 3  # bump when parse_html changes: cached rows from older parsers are re-fetched
CDX = "http://web.archive.org/cdx/search/cdx"

# (cdx url, captures to keep per month before 2024, from 2024 on)
PAGES = [
    ("dramexchange.com/", 2, 4),
    ("dramexchange.com/default2.asp", 2, 2),  # 2000-2004 the homepage redirected here
    ("dramexchange.com/default.asp", 2, 2),
    ("dramexchange.com/default.aspx", 1, 1),
    ("dramexchange.com/Common/Json/PriceOpt.aspx?type=NationalDramSpot", 2, 2),
    ("trendforce.com/price", 1, 2),
    ("trendforce.com/price/dram", 1, 2),
    ("trendforce.com/price/dram/dram_spot", 2, 2),
    ("trendforce.com/price/dram/dram_contract", 2, 2),
    ("trendforce.com/price/dram/module_spot", 2, 2),
    ("trendforce.com/price/flash", 1, 2),
    ("trendforce.com/price/flash/flash_spot", 2, 2),
    ("trendforce.com/price/flash/flash_contract", 2, 2),
    ("trendforce.com/price/flash/ssd_street", 2, 2),
    ("trendforce.com/price/flash/pcc_oem_ssd_contract", 2, 2),
]

SECTION_RE = re.compile(
    r"(PC-Client OEM SSD Contract|SSD Street|NAND Flash Wafer Contract|NAND Flash Contract|"
    r"NAND Flash Spot|DRAM Spot|DRAM Contract|Module Spot|Flash Spot|Flash Contract|GDDR Spot|"
    r"Wafer Spot|LPDDR Spot|eMMC Spot|eMMC Contract|mCOB Spot|Memory Card(?: Spot)?|Mobile DRAM Contract|"
    r"Spot|Contract)"  # bare "Spot Price"/"Contract Price": 2000-2004 pages listed DRAM only
    r"\s*Price", re.I)
LASTUPD_RE = re.compile(r"Last\s?Update\s*:?\s*([A-Za-z]{3}\.?\s?\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{4})?)")
DXI_RE = re.compile(r"DXI\s*([A-Z][a-z]{2})\.?\s?(\d{1,2}),?\s+\d{1,2}:\d{2}\s*(?:[AP]M)?\s*\(GMT\+8\)\s*([\d,]+\.\d+)")
NUM_RE = re.compile(r"^-?[\d,]*\.?\d+$")
LEAD_RE = re.compile(r"^([\d,]*\.?\d+)\s*\(\s*[+-]?[\d.]+\s*%\s*\)$")
# blocks that are not memory prices (stock quotes, FX, DRAMeXchange's moving-average "DPI")
STOP_RE = re.compile(r"(Stock Price|Exchange Rate|\bDPI\b)")
TREND_RE = re.compile(r"^(Up|Down|Stable)\s*\(", re.I)
MON = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _norm_section(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = s.replace("nand flash", "flash").replace("memory card spot", "memory card")
    if s in ("spot", "contract"):
        s = "dram " + s
    return s.replace(" ", "_")


def _parse_date(s: str, snap: dt.date) -> dt.date | None:
    s = s.strip()
    try:
        if re.match(r"\d{4}-\d{2}-\d{2}", s):
            return dt.date.fromisoformat(s[:10])
        m = re.match(r"([A-Za-z]{3})\.?\s?(\d{1,2}),?\s+(\d{4})", s)
        if m:
            return dt.date(int(m.group(3)), MON[m.group(1).lower()], int(m.group(2)))
        m = re.match(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", s)
        if m:
            y = int(m.group(3)) if m.group(3) else snap.year
            d = dt.date(y, int(m.group(1)), int(m.group(2)))
            if d > snap + dt.timedelta(days=2):  # e.g. "12/30" seen in a January capture
                d = d.replace(year=y - 1)
            return d
    except (KeyError, ValueError):
        return None
    return None


def _f(s: str) -> float | None:
    s = s.replace(",", "").strip()
    m = LEAD_RE.match(s)  # 2001-02 contract cells look like "6.00(-27.27%)"
    if m:
        s = m.group(1)
    return float(s) if NUM_RE.match(s) else None


def _events(el):
    """Document-order stream of ('text', str) and ('row', [cells])."""
    if not isinstance(el.tag, str) or el.tag in ("script", "style"):
        return
    if el.tag == "tr" and not el.xpath(".//tr"):
        yield "row", [re.sub(r"\s+", " ", c.text_content()).strip() for c in el.xpath("./td|./th")]
        return
    if el.text:
        yield "text", el.text
    for ch in el:
        yield from _events(ch)
        if ch.tail:
            yield "text", ch.tail


def parse_html(html: bytes, snap: dt.date) -> list[dict]:
    doc = lxml.html.fromstring(html)
    out = []
    section, upd, header = None, None, None
    full = []
    for kind, val in _events(doc):
        if kind == "row" and sum(_f(c) is not None for c in val) < 2 and (
                SECTION_RE.search(" ".join(val)) or LASTUPD_RE.search(" ".join(val))
                or STOP_RE.search(" ".join(val))):
            kind, val = "text", " ".join(val)  # headings that live inside table rows
        if kind == "text":
            full.append(val)
            hits = [(m.start(), _norm_section(m.group(1))) for m in SECTION_RE.finditer(val)]
            hits += [(m.start(), None) for m in STOP_RE.finditer(val)]
            if hits:
                section, upd, header = max(hits, key=lambda h: h[0])[1], None, None
            m = LASTUPD_RE.search(val)
            if m:
                upd = _parse_date(m.group(1), snap)
            continue
        cells = val
        if any(c.lower() == "item" for c in cells) or (
                cells and cells[0].lower() in ("brand", "manufacturer")):
            header = cells
            continue
        nums = [(i, _f(c)) for i, c in enumerate(cells) if _f(c) is not None]
        if len(nums) < 2 or section is None:
            continue
        first_num = nums[0][0]
        item = " ".join(c for c in cells[:first_num] if c).strip()
        if not item or _f(item) is not None:
            continue
        # value columns: prefer the header's (Session) Average column
        avg = hi = lo = None
        col = ""
        if header and len(header) == len(cells):
            names = [h.lower() for h in header]
            for want in ("session average", "average", "avg"):
                if want in names and _f(cells[names.index(want)]) is not None:
                    avg, col = _f(cells[names.index(want)]), header[names.index(want)]
                    break
        vals = [v for _, v in nums]
        trend = next((i for i, c in enumerate(cells) if TREND_RE.match(c)), None)
        if avg is None and trend is not None:  # 2000s: "... hi lo avg Down( -2.22%) wk_hi wk_lo"
            before = [v for i, v in nums if i < trend]
            if len(before) >= 3:  # 3 numbers (hi lo avg) or 5 (hi lo sess_hi sess_lo avg)
                avg, col, vals = before[-1], "average (last value before change cell)", before
        if avg is None:
            if len(vals) >= 5:     # daily hi, lo, session hi, lo, session avg
                avg, col = vals[4], "session average (positional)"
            elif len(vals) >= 3:   # hi, lo, avg (2000s spot, contract, SSD street)
                avg, col = vals[2], "average (positional)"
            else:                  # 2000s contract tables publish only high/low
                col = "high/low only (no average published)"
        hi, lo = vals[0], vals[1]
        chg = next((c for c in cells[first_num:] if "%" in c), "")
        out.append({
            "section": section, "item": item, "price": avg, "high": hi, "low": lo,
            "value_column": col, "change": re.sub(r"[^\d.%+-]", "", chg),
            "price_date": (upd or snap).isoformat(), "date_from": "last_update" if upd else "capture",
        })
    text = re.sub(r"\s+", " ", " ".join(full))
    m = DXI_RE.search(text)
    if m:
        d = _parse_date(f"{m.group(1)} {m.group(2)}, {snap.year}", snap)
        if d and d > snap + dt.timedelta(days=2):
            d = d.replace(year=d.year - 1)
        out.append({"section": "dxi_index", "item": "DXI (DRAMeXchange index)", "price": _f(m.group(3)),
                    "high": None, "low": None, "value_column": "index", "change": "",
                    "price_date": (d or snap).isoformat(), "date_from": "last_update" if d else "capture"})
    return out


def parse_json(body: bytes, snap: dt.date) -> list[dict]:
    """2009-2012 AJAX endpoint (NationalDramSpot)."""
    out = []
    data = json.loads(body.decode("utf-8", "replace"))
    for tb in data.get("Table", []):
        for row in tb.get("Rows", []):
            c = {k: v for cell in row["Cell"] for k, v in cell.items()}
            day = re.match(r"([A-Za-z]{3}\.?\s?\d{1,2}\s+\d{4})", c.get("show_day", ""))
            d = _parse_date(day.group(1).replace(" ", ", ", 1).replace(".", ". "), snap) if day else None
            if d is None and day:
                d = _parse_date(day.group(1), snap)
            out.append({
                "section": "dram_spot", "item": re.sub(r"<[^>]+>", "", c.get("spec", "")).strip(),
                "price": _f(c.get("spot_mid", "")), "high": _f(c.get("spot_hi", "")),
                "low": _f(c.get("spot_lo", "")), "value_column": "spot_mid",
                "change": re.sub(r"<[^>]+>", "", c.get("spot_trend", "")),
                "price_date": (d or snap).isoformat(), "date_from": "last_update" if d else "capture"})
    return out


def reclassify(page: str, section: str, item: str) -> str | None:
    """Fix section labels the heading-based parser gets wrong; None drops the row.
    - 2007-10 homepages list share prices ("Micron USD", "Samsung KRW") in a table
      that follows the contract-price table without its own heading.
    - trendforce.com/price/flash headed its tables with bare "Spot Price"/"Contract
      Price", which parse_html maps to DRAM (correct only for 2000-04 pages).
    - 2007-08 homepages put NAND contract rows under the DRAM contract heading, and
      their DRAM spot table has no heading of its own (the nearest text is a nav bar
      ending in "Memory Card")."""
    if re.search(r"\b(USD|KRW|JPY|TWD|HKD|EUR)$", item):
        return None
    if section == "memory_card" and re.match(r"(DDR|SDRAM)", item):
        return "dram_spot"
    if re.search(r"micro\s?sd", item, re.I):
        return "memory_card"
    if section.startswith("dram_") and (
            page.startswith("trendforce.com/price/flash")
            or re.search(r"\b(MLC|SLC|TLC|QLC|NAND|Speedns)\b", item)):
        return "flash_" + section.split("_", 1)[1]
    if section == "dram_spot" and re.search(r"\d\s*GB\b", item):  # e.g. "Kingston DDR3 2GB 1333MHz"
        return "module_spot"
    return section


def _fetch(url: str) -> bytes:
    try:
        return get(url, timeout=90).content
    except requests.exceptions.ContentDecodingError:
        # some 2008 captures are plain HTML served with a bogus "Content-Encoding: gzip"
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=90)
        r.raise_for_status()
        return r.raw.read(decode_content=False)


def pick_captures(url: str, per_month_old: int, per_month_new: int) -> list[str]:
    r = get(CDX, params={"url": url, "output": "json", "filter": "statuscode:200",
                         "collapse": "timestamp:8", "fl": "timestamp"})
    ts = [x[0] for x in r.json()[1:]] if r.text.strip() else []
    by_month = defaultdict(list)
    for t in ts:
        by_month[t[:6]].append(t)
    keep = []
    for ym, lst in by_month.items():
        n = per_month_new if ym >= "202401" else per_month_old
        targets = [1 + round(i * 30 / n) for i in range(n)]  # e.g. days 1,16 or 1,9,16,24
        chosen = set()
        for day in targets:
            chosen.add(min(lst, key=lambda t: abs(int(t[6:8]) - day)))
        keep += sorted(chosen)
    return sorted(keep)


def _load_cache(path) -> dict:
    cache = {}
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                # v2 differed from v3 only for rows parsed by the change-cell rule
                stale_v2 = rec.get("parser") == 2 and any(
                    r["value_column"] == "average (before change cell)" for r in rec["rows"])
                if (rec.get("parser") in (2, PARSER_VERSION) and not stale_v2
                        and rec["status"].startswith("ok")):  # errors are retried
                    cache[(rec["url"], rec["ts"])] = rec
    return cache


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    d = raw_dir(SOURCE)
    cache_path = d / "_cache.jsonl.gz"
    cache = _load_cache(cache_path)
    new = 0
    for url, n_old, n_new in PAGES:
        try:
            caps = pick_captures(url, n_old, n_new)
        except Exception as e:  # CDX hiccup: keep what is cached, report
            print(f"CDX failed for {url}: {e}")
            continue
        todo = [t for t in caps if (url, t) not in cache]
        print(f"{url}: {len(caps)} captures selected, {len(todo)} to fetch")
        time.sleep(1.5)
        for t in todo:
            wb = f"http://web.archive.org/web/{t}id_/http://{url}"
            snap = dt.date(int(t[:4]), int(t[4:6]), int(t[6:8]))
            try:
                body = _fetch(wb)
                if not body.strip():
                    rows, status = [], "ok: archived document is empty"
                else:
                    rows = parse_json(body, snap) if "Json" in url else parse_html(body, snap)
                    status = "ok"
            except Exception as e:
                rows, status = [], f"error: {e}"[:200]
            rec = {"url": url, "ts": t, "status": status, "parser": PARSER_VERSION, "rows": rows}
            cache[(url, t)] = rec
            with gzip.open(cache_path, "at", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            new += 1
            if new % 25 == 0:
                print(f"  fetched {new} new captures (last {url} {t}: {len(rows)} rows)", flush=True)
            time.sleep(1.5)

    with gzip.open(cache_path, "wt", encoding="utf-8") as f:  # compact: drop stale-parser lines
        for rec in cache.values():
            f.write(json.dumps(rec) + "\n")

    out = []
    for (url, t), rec in cache.items():
        for r in rec["rows"]:
            section = reclassify(url, r["section"], r["item"])
            if section is None:
                continue
            out.append({
                "date": r["price_date"], "section": section, "section_as_parsed": r["section"],
                "item": r["item"],
                "price": r["price"], "high": r["high"], "low": r["low"], "currency": "USD",
                "value_column": r["value_column"], "change": r["change"], "date_from": r["date_from"],
                "capture_ts": t, "page": url,
                "url_of_snapshot": f"http://web.archive.org/web/{t}/http://{url}",
            })
    df = pd.DataFrame(out)
    df = df[df.price.notna() | df.high.notna()]
    # the same published price shows up in several captures/pages; keep the first capture
    df = (df.sort_values(["date", "section", "item", "capture_ts"])
            .drop_duplicates(["date", "section", "item", "price", "high", "low"]).reset_index(drop=True))
    df.to_csv(d / "dramexchange_prices.csv", index=False)
    errs = sum(1 for r in cache.values() if not r["status"].startswith("ok"))
    empty = sum(1 for r in cache.values() if r["status"].startswith("ok") and not r["rows"])
    print(f"captures cached={len(cache)} errors={errs} parsed-but-empty={empty}; rows={len(df)}")
    print(df.groupby("section").agg(rows=("price", "size"), first=("date", "min"), last=("date", "max"))
            .to_string())
    write_source_note(
        SOURCE,
        title="DRAMeXchange / TrendForce free spot & contract memory prices (via Wayback Machine)",
        urls=["https://www.dramexchange.com/", "https://www.trendforce.com/price/dram/dram_spot",
              "https://www.trendforce.com/price/dram/dram_contract",
              "http://web.archive.org/cdx/search/cdx (captures of the pages above)"]
             + [f"page sampled: {u}" for u, _, _ in PAGES],
        notes="""
Only the current day's prices are free on these pages; history is member-only. Each
Wayback capture is one observation. Captures sampled: ~2/month (4/month from 2024 for
the dramexchange homepage). Coverage has gaps: 2009-2015 the homepage loaded tables by
AJAX (only 11 AJAX captures exist), so those years are thin.

price = the table's (Session) Average in USD: per chip for DRAM/NAND spot & contract
(e.g. "DDR4 8Gb (1Gx8) 3200" = one 8-gigabit chip), per module for module spot/contract
(e.g. "DDR5 UDIMM 16GB"), per drive for SSD street price. high/low = daily (spot) or
period (contract) range. date = the table's own "Last Update" date when parseable
(date_from=last_update), else the capture date. Spot prices are a thin secondary
market and are more volatile than contract prices (where most volume trades).
DXI (section dxi_index) is DRAMeXchange's DRAM price index; its composition/base is
not documented on the page, so treat levels across decades with caution.
section is assigned from the nearest table heading, then corrected by reclassify()
(NAND/microSD rows mislabelled DRAM on some pages, share-price rows dropped);
section_as_parsed keeps the raw label. DXI is only captured to 2020-12: from ~2021 the
homepage keeps the DXI value inside an HTML comment (not displayed), so it is not parsed.
Item names change as products roll (SDRAM -> DDR -> DDR2 -> DDR3 -> DDR4 -> DDR5),
so long series must be chained across items.
""",
    )


if __name__ == "__main__":
    main()
