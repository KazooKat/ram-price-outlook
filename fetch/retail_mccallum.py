"""John C. McCallum's historical memory / disk / flash / SSD price tables.

jcmit.net lapsed in 2025 and now redirects to an unrelated casino site, so we
read the last genuine Wayback Machine captures instead. McCallum's data stops at
2024-07-28 ("Data Last Updated on 2024 July 28" on every page).

Each row is one retail listing McCallum recorded (generally the cheapest he found
at the time, Newegg for recent years). Output: data/raw/mccallum/mccallum_prices.csv
"""
from __future__ import annotations

import re
import time

import lxml.html
import pandas as pd

from fetch._common import get, raw_dir, write_source_note

SOURCE = "mccallum"

# Last captures before the domain was hijacked; all say "Data Last Updated on 2024 July 28".
SNAPSHOTS = {
    "memory": "http://web.archive.org/web/20250716092935id_/http://jcmit.net/memoryprice.htm",
    "disk": "http://web.archive.org/web/20250614051021id_/http://jcmit.net/diskprice.htm",
    "flash_ssd": "http://web.archive.org/web/20250614035024id_/http://jcmit.net/flashprice.htm",
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _num(s: str) -> float | None:
    s = s.replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _date(x: str, year: str, month: str) -> tuple[str, str]:
    """Return (ISO date, precision). Prefer the explicit Year/Month(day) columns; the
    decimal X column has typos (e.g. '2024..8')."""
    y = int(_num(year)) if _num(year) else None
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s*(\d{1,2})?", month.strip())
    if y and m and m.group(1).lower() in MONTHS:
        mo = MONTHS[m.group(1).lower()]
        if m.group(2) and 1 <= int(m.group(2)) <= 31:  # "Jul99" in the source means Jul 1999
            return f"{y:04d}-{mo:02d}-{int(m.group(2)):02d}", "day"
        return f"{y:04d}-{mo:02d}-01", "month"
    xv = _num(x)
    if xv is None and y:
        xv = float(y)
    if xv is None:
        return "", ""
    yr = int(xv)
    mo = min(12, int(round((xv - yr) * 12)) + 1)
    return f"{yr:04d}-{mo:02d}-01", "year" if xv == yr else "month(from decimal year)"


def _rows(html: bytes):
    doc = lxml.html.fromstring(html)
    for tb in doc.xpath("//table"):
        rows = [[c.text_content().strip() for c in tr.xpath("./td|./th")] for tr in tb.xpath(".//tr")]
        yield [r for r in rows if r and re.match(r"^\d{4}\.", r[0] or "")]


def parse(series: str, html: bytes, url: str) -> list[dict]:
    out = []
    tables = list(_rows(html))
    for ti, rows in enumerate(tables):
        if series == "memory":
            kind = "memory"
        elif series == "disk":
            kind = "disk"
        else:
            kind = "flash" if ti == 0 else "ssd"
        for r in rows:
            r = r + [""] * (16 - len(r))
            iso, prec = _date(r[0], r[2], r[3])
            listed = _num(r[1])
            if kind == "memory":
                size_mb = (_num(r[7]) or 0) / 1024 or None
                cost = _num(r[8])
                desc = " | ".join(x for x in (r[10], r[11]) if x)
                vendor = r[6]
                ref = " ".join(x for x in (r[4], r[5]) if x)
            elif kind in ("disk", "flash"):
                size_mb = _num(r[12])
                cost = _num(r[13])
                desc = " | ".join(x for x in (r[7], r[8], r[9], r[10]) if x)
                vendor = r[6]
                ref = " ".join(x for x in (r[4], r[5]) if x)
            else:  # ssd: X Y Year Month Ref page Sales Mfr Series Model Size Type Store IOPS Cost
                sz = re.match(r"([\d.]+)\s*(GB|TB)", r[10], re.I)
                size_mb = float(sz.group(1)) * (1024 if sz.group(2).upper() == "GB" else 1024 * 1024) if sz else None
                cost = _num(r[14])
                desc = " | ".join(x for x in (r[7], r[8], r[9], r[10], r[11], r[12]) if x)
                vendor = r[6]
                ref = " ".join(x for x in (r[4], r[5]) if x)
            calc = cost / size_mb if cost and size_mb else None
            out.append({
                "date": iso,
                "date_precision": prec,
                "decimal_year_listed": r[0],
                "series": kind,
                "price": listed,
                "unit": "USD per MB (nominal)",
                "currency": "USD",
                "usd_per_mb_recomputed": calc,
                "size_mb": size_mb,
                "item_cost_usd": cost,
                "description": desc,
                "seller": vendor,
                "reference": ref,
                "url_of_snapshot": url.replace("id_/", "/"),
            })
    return out


def main() -> None:
    d = raw_dir(SOURCE)
    rows = []
    for series, url in SNAPSHOTS.items():
        html = get(url).content
        if b"Data Last Updated" not in html and b"Last Updated" not in html:
            raise RuntimeError(f"{url} does not look like a McCallum page")
        rows += parse(series, html, url)
        time.sleep(1.5)
    df = pd.DataFrame(rows).sort_values(["series", "date"]).reset_index(drop=True)
    # A few source rows have a cost/size column that disagrees with McCallum's own
    # listed $/MB and description text (data-entry typos upstream). Flag, don't fix.
    ratio = df.usd_per_mb_recomputed / df.price
    df["cost_column_mismatch"] = (ratio < 0.8) | (ratio > 1.25)
    df.to_csv(d / "mccallum_prices.csv", index=False)
    for s, g in df.groupby("series"):
        print(f"{s:7s} rows={len(g):4d} {g.date.min()}..{g.date.max()} "
              f"$/MB {g.price.min():.3g}..{g.price.max():.3g}")
    write_source_note(
        SOURCE,
        title="John C. McCallum - historical memory, disk, flash and SSD prices",
        urls=list(SNAPSHOTS.values()) + ["(original, now hijacked) https://jcmit.net/memoryprice.htm"],
        notes="""
Original site jcmit.net now redirects to an unrelated casino site (checked 2026-10-06);
data read from the last genuine Wayback captures. Data ends 2024-07-28.

Columns: price = McCallum's listed US$/MB (nominal, not inflation-adjusted);
usd_per_mb_recomputed = item_cost_usd / size_mb as a cross-check. Rows are single
retail listings, generally the cheapest price per MB McCallum found that month
(Newegg since ~2009), so the product mix shifts over time (DIMM vs SO-DIMM,
DDR3 -> DDR4, capacity). Sampling is irregular: roughly annual pre-1975, then
monthly-ish. series: memory (DRAM), disk (HDD), flash (USB/cards, ends 2017),
ssd (from 2013). Dates come from the Year/Month columns; decimal-year column has typos.
cost_column_mismatch=True marks rows whose cost/size columns disagree with the listed
$/MB (3 memory rows, 2017-05, 2017-09, 2018-12); the listed $/MB matches the row's
description text in each case, so `price` is trustworthy there. SSD sizes use binary GB
in usd_per_mb_recomputed while McCallum used decimal, hence a ~2.5% gap.
""",
    )


if __name__ == "__main__":
    main()
