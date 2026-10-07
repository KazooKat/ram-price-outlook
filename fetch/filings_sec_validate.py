"""Cross-check data/raw/sec_companyfacts against each company's earnings press release.

For every company in filings_sec_companyfacts.COMPANIES, three values are checked:
  1. the latest quarter's revenue (reported directly in a 10-Q/10-K),
  2. the latest revenue quarter that was *derived* (FY/YTD minus prior YTD, usually Q4),
  3. the latest *derived* capex quarter (cash-flow statements are YTD-only in 10-Qs).
The check looks for the exact value in USD millions (e.g. "54,229") in exhibit 99.x of
the first 8-K item 2.02 (results of operations) filed 1-100 days after the quarter end.
A hit means the press release prints the same number (match_type "exact"); derived
quarters may match within $1M (rounding of FY and YTD totals), or - when a release prints
only year-to-date cash flows - the YTD sum of our quarters is matched instead
(match_type "ytd_sum_<value>"). Misses keep the release URL for inspection.

Output: data/raw/sec_companyfacts/validation_press_releases.csv
Run after filings_sec_companyfacts.py.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import RAW, get, raw_dir  # noqa: E402
from fetch.filings_micron_ir import html_text  # noqa: E402
from fetch.filings_sec_companyfacts import COMPANIES, SEC_HEADERS, TICKERS_URL  # noqa: E402

SOURCE = "sec_companyfacts"


def earnings_releases(cik: int) -> list[dict]:
    sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=SEC_HEADERS).json()
    r = sub["filings"]["recent"]
    return [{"filed": r["filingDate"][i], "accn": r["accessionNumber"][i], "primary": r["primaryDocument"][i]}
            for i, f in enumerate(r["form"]) if f == "8-K" and "2.02" in r["items"][i]]


def release_text(cik: int, accn: str, primary: str) -> tuple[str, str]:
    """Text of every exhibit document (all .htm files except the 8-K cover and R pages)."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/"
    items = get(base + "index.json", headers=SEC_HEADERS).json()["directory"]["item"]
    ex = [i["name"] for i in items if i["name"].lower().endswith((".htm", ".html"))
          and i["name"] != primary and not re.match(r"R\d+\.htm$", i["name"]) and "index" not in i["name"]]
    texts = [html_text(get(base + n, headers=SEC_HEADERS).text) for n in ex]
    return " ".join(texts), (base + ex[0]) if ex else base


def fmt_millions(m: int) -> list[str]:
    return [f"{abs(m):,}", f"{abs(m)}"] if abs(m) >= 1000 else [f"{abs(m)}"]


KEYWORDS = {"revenue": r"revenue|sales", "capex": r"property|equipment|capital"}


def find_value(text: str, m: int, metric: str):
    """First occurrence of m (USD mn) preceded within 200 chars by a keyword for the metric,
    so that a small number does not match an unrelated line item."""
    for s in fmt_millions(m):
        for hit in re.finditer(r"(?<![\d,.])\(?\$?\s?" + re.escape(s) + r"(?![\d,]|\.\d)", text):
            if re.search(KEYWORDS[metric], text[max(0, hit.start() - 200):hit.start()], re.I):
                return hit
    return None


def main() -> None:
    df = pd.read_csv(RAW / SOURCE / "quarterly_financials.csv")
    tick = get(TICKERS_URL, headers=SEC_HEADERS).json()
    cik_of = {v["ticker"]: int(v["cik_str"]) for v in tick.values()}
    rows = []
    for t in COMPANIES:
        c = df[df.company == t]
        picks = []
        rev = c[c.metric == "revenue"].sort_values("period_end")
        picks.append(("latest revenue (reported)", rev[rev.derivation == "reported"].iloc[-1]))
        if (rev.derivation == "ytd_diff").any():
            picks.append(("latest derived revenue quarter", rev[rev.derivation == "ytd_diff"].iloc[-1]))
        cap = c[(c.metric == "capex") & (c.derivation == "ytd_diff")].sort_values("period_end")
        if not cap.empty:
            picks.append(("latest derived capex quarter", cap.iloc[-1]))
        rels = earnings_releases(cik_of[t])
        cache: dict = {}
        for what, r in picks:
            end = dt.date.fromisoformat(r.period_end)
            rel = next((x for x in sorted(rels, key=lambda x: x["filed"])
                        if 1 <= (dt.date.fromisoformat(x["filed"]) - end).days <= 100), None)
            row = {"company": t, "check": what, "metric": r.metric, "period_end": r.period_end,
                   "fiscal": f"FY{int(r.fiscal_year)} {r.fiscal_quarter}", "derivation": r.derivation,
                   "xbrl_value_usd_mn": round(r.value / 1e6)}
            if rel is None:
                rows.append({**row, "found_in_release": None, "release_url": None, "context": "no 8-K 2.02 found"})
                continue
            if rel["accn"] not in cache:
                cache[rel["accn"]] = release_text(cik_of[t], rel["accn"], rel["primary"])
                time.sleep(0.2)
            text, url = cache[rel["accn"]]
            v = round(r.value / 1e6)
            how, hit = "exact", find_value(text, v, r.metric)
            if hit is None and r.derivation == "ytd_diff":
                # derived quarters can differ by $1M from rounding (FY and 9M are each rounded)
                hit = find_value(text, v + 1, r.metric) or find_value(text, v - 1, r.metric)
                how = "within_1mn"
                if hit is None:
                    # release prints only the YTD / full-year cash flow: check the YTD sum
                    q = c[(c.metric == r.metric) & (c.fiscal_year == r.fiscal_year)
                          & (c.period_end <= r.period_end)]
                    ytd = round(q.value.sum() / 1e6)
                    hit, how = find_value(text, ytd, r.metric), f"ytd_sum_{ytd:,}"
            rows.append({**row, "found_in_release": bool(hit), "match_type": how if hit else None,
                         "release_url": url,
                         "context": text[max(0, hit.start() - 120):hit.end() + 30] if hit else ""})
        print(f"[validate] {t}: " + ", ".join(f"{x['check'].split()[1]}={x['found_in_release']}" for x in rows if x["company"] == t))
    out = pd.DataFrame(rows)
    out.to_csv(raw_dir(SOURCE) / "validation_press_releases.csv", index=False)
    print(f"[validate] {out.found_in_release.value_counts(dropna=False).to_dict()}")


if __name__ == "__main__":
    main()
