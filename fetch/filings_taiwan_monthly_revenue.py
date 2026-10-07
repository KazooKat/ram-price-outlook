"""Taiwan monthly revenue filings (MOPS) for memory / storage / foundry companies.

Source: MOPS legacy monthly revenue summary tables (t21sc03), one page per
market (sii = TWSE-listed, otc = TPEx-listed) per month. Every listed company
must file monthly revenue by the 10th of the following month, so these are the
highest-frequency company-reported figures for the memory cycle (Nanya is a
pure-play DRAM maker).

Output: data/raw/taiwan_monthly_revenue/monthly_revenue.csv
"""
from __future__ import annotations

import datetime as dt
import html
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "taiwan_monthly_revenue"
BASE = "https://mopsov.twse.com.tw/nas/t21/{market}/t21sc03_{roc}_{month}{suffix}.html"

COMPANIES = {
    "2408": "Nanya Technology",
    "2344": "Winbond Electronics",
    "2330": "TSMC",
    "2451": "Transcend Information",
    "3260": "ADATA Technology",
    "8299": "Phison Electronics",
    "4967": "TeamGroup",
}
START = (2010, 1)
MARKETS = ("sii", "otc")

_TR = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
_TD = re.compile(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>")


def _clean(cell: str) -> str:
    cell = re.sub(r"(?s)<[^>]+>", " ", cell)
    return re.sub(r"[\s\xa0]+", " ", html.unescape(cell)).strip()


def _num(s: str):
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None  # "不適用" (not applicable) etc.


def fetch_page(market: str, year: int, month: int) -> tuple[str, str] | None:
    roc = year - 1911
    # Pages from ROC 102 (2013, IFRS adoption) use the _0 (domestic companies) suffix;
    # older pages exist without it.
    for suffix in ("_0", ""):
        url = BASE.format(market=market, roc=roc, month=month, suffix=suffix)
        try:
            r = get(url, headers={"User-Agent": "Mozilla/5.0 (ram-price-outlook research)"})
        except (RuntimeError, requests.HTTPError):
            continue
        text = r.content.decode("big5", errors="replace")
        if "營業收入統計表" in text:
            return url, text
    return None


def parse_page(text: str) -> dict[str, list[str]]:
    rows = {}
    for tr in _TR.findall(text):
        cells = [_clean(c) for c in _TD.findall(tr)]
        if len(cells) >= 10 and cells[0] in COMPANIES:
            rows[cells[0]] = cells
    return rows


def main() -> None:
    out = raw_dir(SOURCE)
    today = dt.date.today()
    records = []
    y, m = START
    while (y, m) < (today.year, today.month):
        for market in MARKETS:
            page = fetch_page(market, y, m)
            time.sleep(0.6)
            if page is None:
                print(f"  no page {market} {y}-{m:02d}")
                continue
            url, text = page
            for code, c in parse_page(text).items():
                records.append({
                    "period": f"{y}-{m:02d}",
                    "company": COMPANIES[code],
                    "ticker": code,
                    "market": "TWSE" if market == "sii" else "TPEx",
                    "name_as_filed": c[1],
                    "metric": "revenue",
                    "value": _num(c[2]),
                    "unit": "TWD thousand",
                    "basis": "consolidated_IFRS" if y >= 2013 else "standalone_ROC_GAAP",
                    "prev_month_value_reported": _num(c[3]),
                    "prior_year_same_month_value_reported": _num(c[4]),
                    "mom_pct_reported": _num(c[5]),
                    "yoy_pct_reported": _num(c[6]),
                    "ytd_value": _num(c[7]),
                    "ytd_prior_year_value": _num(c[8]),
                    "ytd_yoy_pct_reported": _num(c[9]),
                    "company_note": c[10] if len(c) > 10 and c[10] not in ("-", "") else "",
                    "source_url": url,
                })
        print(f"{y}-{m:02d}: {sum(1 for r in records if r['period'] == f'{y}-{m:02d}')} companies")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    df = pd.DataFrame(records).sort_values(["ticker", "period"])
    df = df.drop_duplicates(["ticker", "period"], keep="last")
    df.to_csv(out / "monthly_revenue.csv", index=False, encoding="utf-8")
    print(f"wrote {len(df)} rows -> {out / 'monthly_revenue.csv'}")

    write_source_note(
        SOURCE,
        title="Taiwan listed-company monthly revenue (MOPS t21sc03)",
        urls=[
            "https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{ROCyear}_{month}_0.html (TWSE-listed)",
            "https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{ROCyear}_{month}_0.html (TPEx-listed)",
        ],
        notes="""
Company-filed monthly revenue from the Market Observation Post System (MOPS),
monthly summary tables. ROC year = Gregorian year - 1911.

- Unit: TWD thousand (page header "單位：千元").
- Basis: from Jan 2013 (ROC 102, IFRS adoption) companies file CONSOLIDATED
  revenue (standalone if they have no subsidiaries). Before 2013 the figures are
  standalone (ROC GAAP) - a series break; Jan-2013 MoM is reported as "不適用"
  (not applicable). Use `basis` to split.
- yoy_pct_reported / mom_pct_reported are as printed by MOPS, not recomputed.
  prior_year_same_month_value_reported can differ from the earlier-filed value
  if the company restated.
- Markets: the script searches both the TWSE (sii) and TPEx (otc) tables every
  month and records where each code was found (`market`) and the Chinese
  short name printed by MOPS (`name_as_filed`) so market moves / renames are
  auditable. 4967 TeamGroup has gaps in 2011-2012 (not in either table then).
- Unaudited, self-reported monthly figures. The latest month can be partial
  (companies file up to the 10th of the following month); re-run to fill.
- company_note: the company's own explanation of large changes (Chinese).
""",
    )


if __name__ == "__main__":
    main()
