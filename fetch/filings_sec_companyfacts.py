"""Quarterly financials from SEC EDGAR XBRL companyfacts (memory makers, AI demand, hyperscalers).

Output: data/raw/sec_companyfacts/quarterly_financials.csv (tidy, one row per
company x metric x fiscal quarter).

Method
- companyfacts returns every value each 10-Q/10-K reported, including prior-period
  comparatives and restatements. For each (tag, period) we keep the value from the
  most recently *filed* report (so restatements win; amended filings are deduped).
- Flow metrics (revenue, costs, capex) are reported as discrete quarters in 10-Qs
  but only as fiscal-year / year-to-date totals in 10-Ks and cash-flow statements.
  Missing discrete quarters are derived as YTD(start, end) - YTD(start, prior end);
  such rows carry derivation="ytd_diff".
- Tag fallbacks: companies switched tags over time (e.g. SalesRevenueNet ->
  RevenueFromContractWithCustomerExcludingAssessedTax after ASC 606). Equivalent total
  tags form a group; per period the most recently filed reported value in the group
  wins (so ASC 606 full-retrospective restatements, e.g. AMD and MSFT 2017, replace the
  originals). Product-only subtotals are used only when no total exists. Same-period
  disagreements >0.5% between equivalent tags are logged to tag_conflicts.csv.
- Fiscal labels come from the company's own 10-K fiscal-year periods, not from the
  "fy"/"fp" fields (those describe the filing, not the fact).
- Derived metrics: gross_margin_pct = gross_profit/revenue (gross_profit computed as
  revenue - cost_of_revenue when the GrossProfit tag is absent); inventory_days =
  ending inventory / quarterly cost_of_revenue * days in quarter.
"""
from __future__ import annotations

import os
import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "sec_companyfacts"
# SEC asks for a contact email in the User-Agent: set SEC_USER_AGENT="your-name your@email"
SEC_HEADERS = {"User-Agent": os.environ.get("SEC_USER_AGENT", "ram-price-outlook research")}
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

COMPANIES = {
    # ticker: role
    "MU": "memory (DRAM+NAND)",
    "WDC": "storage (HDD; NAND until Sandisk spin-off Feb 2025)",
    "SNDK": "NAND flash (spun off from WDC Feb 2025)",
    "STX": "storage (HDD)",
    "NVDA": "AI accelerators",
    "AMD": "CPU/GPU",
    "INTC": "CPU",
    "MSFT": "hyperscaler",
    "GOOGL": "hyperscaler",
    "AMZN": "hyperscaler",
    "META": "hyperscaler",
    "ORCL": "hyperscaler",
}

# metric -> (kind, [tag groups]). Tags within a group are equivalent totals (the
# company switched tags over time): per period the most recently filed reported value
# wins, so restated figures (e.g. ASC 606 full-retrospective) replace originals.
# Later groups are fallbacks only (product-only subtotals such as SalesRevenueGoodsNet).
METRICS = {
    "revenue": ("duration", [
        ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        ["SalesRevenueGoodsNet"],
    ]),
    "cost_of_revenue": ("duration", [
        ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
        ["CostOfGoodsSold"],
    ]),
    "gross_profit": ("duration", [["GrossProfit"]]),
    "operating_income": ("duration", [["OperatingIncomeLoss"]]),
    "capex": ("duration", [[
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ]]),
    "inventory": ("instant", [["InventoryNet"]]),
}

QUARTER_DAYS = (75, 105)
START_YEAR = 2014  # keep fiscal quarters ending on/after this year


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def latest_by_period(units: list[dict], kind: str) -> dict:
    """{(start, end) or end: fact} keeping the most recently filed value."""
    out: dict = {}
    for f in units:
        if f.get("form") not in ("10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-QT"):
            continue
        if kind == "duration":
            if "start" not in f:
                continue
            key = (f["start"], f["end"])
        else:
            key = f["end"]
        prev = out.get(key)
        if prev is None or (f["filed"], f["accn"]) > (prev["filed"], prev["accn"]):
            out[key] = f
    return out


def discrete_quarters(facts: dict) -> dict:
    """{(start, end): (value, derivation, fact)} discrete quarters, deriving from YTD."""
    q = {}
    for (s, e), f in facts.items():
        days = (_d(e) - _d(s)).days
        if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
            q[(s, e)] = (f["val"], "reported", f)
    # YTD differencing: (S, E) - (S, E') where E' is ~one quarter before E
    by_start: dict = {}
    for (s, e), f in facts.items():
        by_start.setdefault(s, []).append((e, f))
    for s, lst in by_start.items():
        lst.sort(key=lambda x: x[0])
        for i, (e, f) in enumerate(lst):
            for e_prev, f_prev in lst[:i]:
                gap = (_d(e) - _d(e_prev)).days
                if QUARTER_DAYS[0] <= gap <= QUARTER_DAYS[1]:
                    qs = (_d(e_prev) + dt.timedelta(days=1)).isoformat()
                    if (qs, e) not in q:
                        q[(qs, e)] = (f["val"] - f_prev["val"], "ytd_diff", f)
    return q


def fiscal_years(facts_by_tag: dict) -> list[tuple[dt.date, dt.date]]:
    """Fiscal-year (start, end) pairs from ~annual duration facts reported in 10-Ks.

    10-Q facts are excluded: some filers (e.g. Amazon) report trailing-twelve-month
    figures in 10-Qs, which would otherwise look like fiscal years.
    """
    fys = set()
    for facts in facts_by_tag.values():
        for key, f in facts.items():
            if isinstance(key, tuple) and f.get("form", "").startswith("10-K"):
                s, e = _d(key[0]), _d(key[1])
                if 350 <= (e - s).days <= 380:
                    fys.add((s, e))
    fys = sorted(fys)
    if fys:  # current fiscal year has no 10-K yet: provisional year (labelled by its ~end)
        last_end = fys[-1][1]
        fys.append((last_end + dt.timedelta(days=1), last_end + dt.timedelta(days=364)))
    return fys


def fiscal_label(start: dt.date, end: dt.date, fys) -> tuple[int | None, int | None]:
    for fs, fe in fys:
        if fs <= start and end <= fe + dt.timedelta(days=8):  # 53-week years end up to 7 days later
            qn = round(((end - fs).days + 1) / 91.3)
            return fe.year, max(1, min(4, qn))
    return None, None


def cal_quarter(start: dt.date, end: dt.date) -> str:
    mid = start + (end - start) / 2
    return f"{mid.year}Q{(mid.month - 1) // 3 + 1}"


def company_rows(ticker: str, cik: int, conflicts: list) -> list[dict]:
    url = FACTS_URL.format(cik=cik)
    data = get(url, headers=SEC_HEADERS).json()
    gaap = data["facts"].get("us-gaap", {})
    rows = []

    tag_facts = {}
    for metric, (kind, groups) in METRICS.items():
        for tag in sum(groups, []):
            if tag in gaap and "USD" in gaap[tag]["units"]:
                tag_facts[(metric, tag)] = latest_by_period(gaap[tag]["units"]["USD"], kind)
    fys = fiscal_years({k: v for k, v in tag_facts.items() if METRICS[k[0]][0] == "duration"})

    def rank(c):  # reported beats ytd_diff, then latest filing
        return (c[1] == "reported", c[2]["filed"], c[2]["accn"])

    quarter_periods: set = set()
    per_metric: dict = {}
    for metric, (kind, groups) in METRICS.items():
        chosen: dict = {}
        for group in groups:
            group_best: dict = {}
            for tag in group:
                facts = tag_facts.get((metric, tag))
                if not facts:
                    continue
                if kind == "duration":
                    # key by quarter end: filers occasionally mis-tag a start date by a day
                    cand = {}
                    for (qs, qe), (v, how, f) in discrete_quarters(facts).items():
                        c = (v, how, f, tag, qs)
                        if qe not in cand or rank(c) > rank(cand[qe]):
                            cand[qe] = c
                else:
                    cand = {k: (f["val"], "reported", f, tag, None) for k, f in facts.items()}
                for k, c in cand.items():
                    prev = group_best.get(k)
                    if prev is not None and prev[1] == c[1] == "reported" and prev[0]                             and abs(prev[0] - c[0]) / abs(prev[0]) > 0.005:
                        new, old = (c, prev) if rank(c) > rank(prev) else (prev, c)
                        conflicts.append({"company": ticker, "metric": metric, "period": str(k),
                                          "kept_tag": new[3], "kept_value": new[0],
                                          "kept_filed": new[2]["filed"],
                                          "other_tag": old[3], "other_value": old[0],
                                          "other_filed": old[2]["filed"]})
                    if prev is None or rank(c) > rank(prev):
                        group_best[k] = c
            for k, c in group_best.items():
                chosen.setdefault(k, c)  # earlier (total) groups take precedence
        per_metric[metric] = chosen
        if kind == "duration":
            quarter_periods.update((c[4], e) for e, c in chosen.items())

    ends = {}
    for s, e in sorted(quarter_periods):
        ends.setdefault(e, s)

    def emit(metric, s, e, val, how, f, tag):
        sd, ed = _d(s), _d(e)
        if ed.year < START_YEAR:
            return
        fy, fq = fiscal_label(sd, ed, fys)
        rows.append({
            "period_start": s, "period_end": e, "fiscal_year": fy,
            "fiscal_quarter": f"Q{fq}" if fq else None, "calendar_quarter": cal_quarter(sd, ed),
            "company": ticker, "metric": metric, "value": val, "unit": "USD",
            "xbrl_tag": tag, "derivation": how, "accn": f["accn"], "form": f["form"],
            "filed": f["filed"],
            "source_url": url,
        })

    for metric, chosen in per_metric.items():
        kind = METRICS[metric][0]
        for k, (val, how, f, tag, qs) in chosen.items():
            if kind == "duration":
                emit(metric, qs, k, val, how, f, tag)
            else:
                if k in ends:
                    emit(metric, ends[k], k, val, how, f, tag)
    return rows


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    key = ["company", "period_start", "period_end", "fiscal_year", "fiscal_quarter",
           "calendar_quarter"]
    df = df.assign(fiscal_year=df["fiscal_year"].fillna(-1), fiscal_quarter=df["fiscal_quarter"].fillna(""))
    wide = df.pivot_table(index=key, columns="metric", values="value", aggfunc="first").reset_index()
    wide = wide.dropna(subset=["revenue"])
    wide["fiscal_year"] = wide["fiscal_year"].replace(-1, None)
    wide["fiscal_quarter"] = wide["fiscal_quarter"].replace("", None)
    out = []
    for _, r in wide.iterrows():
        gp = r.get("gross_profit")
        how = "gross_profit/revenue"
        if pd.isna(gp) and pd.notna(r.get("cost_of_revenue")):
            gp = r["revenue"] - r["cost_of_revenue"]
            how = "(revenue-cost_of_revenue)/revenue"
        base = {k: r[k] for k in key}
        if pd.notna(gp) and r["revenue"]:
            out.append({**base, "metric": "gross_margin_pct", "value": round(100 * gp / r["revenue"], 2),
                        "unit": "pct", "derivation": how})
        inv, cogs = r.get("inventory"), r.get("cost_of_revenue")
        if pd.isna(cogs) and pd.notna(gp):
            cogs = r["revenue"] - gp
        if pd.notna(inv) and pd.notna(cogs) and cogs > 0:
            days = (_d(r["period_end"]) - _d(r["period_start"])).days + 1
            out.append({**base, "metric": "inventory_days", "value": round(inv / cogs * days, 1),
                        "unit": "days", "derivation": "inventory/cost_of_revenue*days_in_quarter"})
    d = pd.DataFrame(out)
    d["source_url"] = "derived from rows above"
    return d


def main() -> None:
    out = raw_dir(SOURCE)
    tick = get(TICKERS_URL, headers=SEC_HEADERS).json()
    cik_of = {v["ticker"]: int(v["cik_str"]) for v in tick.values()}
    rows, conflicts = [], []
    for t in COMPANIES:
        print(f"[{SOURCE}] {t} CIK {cik_of[t]}")
        rows += company_rows(t, cik_of[t], conflicts)
        time.sleep(0.3)
    df = pd.DataFrame(rows)
    df = pd.concat([df, add_derived(df)], ignore_index=True)
    df["role"] = df["company"].map(COMPANIES)
    df = df.sort_values(["company", "metric", "period_end"]).reset_index(drop=True)
    df.to_csv(out / "quarterly_financials.csv", index=False)
    pd.DataFrame(conflicts).to_csv(out / "tag_conflicts.csv", index=False)
    print(f"[{SOURCE}] {len(df)} rows, {len(conflicts)} tag conflicts")

    write_source_note(
        SOURCE,
        title="SEC EDGAR XBRL companyfacts - quarterly financials",
        urls=[FACTS_URL.format(cik=cik_of[t]) for t in COMPANIES] + [TICKERS_URL],
        notes=__doc__ + """
Caveats
- capex = cash paid for PP&E (PaymentsToAcquirePropertyPlantAndEquipment, or
  PaymentsToAcquireProductiveAssets for AMZN/NVDA). It excludes finance-lease additions,
  which are large for MSFT and AMZN; company "capex incl. finance leases" figures are higher.
- Micron's press-release "capex, net" nets out government incentives and equipment
  sale proceeds; the XBRL gross cash figure here is larger.
- Values reflect the latest filing that reported each period (restated values win).
- The most recent fiscal quarter appears only after the 10-Q/10-K is filed (earnings
  press releases come first; see data/raw/micron_ir for Micron's latest quarter).
- calendar_quarter = calendar quarter containing the midpoint of the fiscal quarter
  (ORCL/MU/NVDA fiscal quarters are offset 1-2 months from calendar quarters).
""",
    )


if __name__ == "__main__":
    main()
