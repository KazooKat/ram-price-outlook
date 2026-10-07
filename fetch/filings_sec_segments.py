"""Dimensional (segment / product) revenue from SEC 10-Q and 10-K XBRL instances.

companyfacts omits dimensional facts, so this script downloads the XBRL instance of
every 10-Q/10-K and keeps revenue facts qualified by a product or segment axis:
- Micron (MU): revenue by technology (DRAM / NAND / Other, srt:ProductOrServiceAxis)
  and by business unit (StatementBusinessSegmentsAxis; units were reorganised in
  FY2023 and FY2026, so member names change over time).
- Nvidia (NVDA): revenue by market platform (Data Center, Gaming, ...) and segment.
- Western Digital (WDC) / Sandisk (SNDK): revenue by end market / product.

Output: data/raw/sec_segments/segment_revenue.csv - one row per company x axis x
member x fiscal quarter. Discrete quarters for Q4 (10-K reports only full year) are
derived as FY - 9M YTD, flagged derivation="ytd_diff". Per period the most recently
filed value wins (restatements/recasts replace originals).
"""
from __future__ import annotations

import datetime as dt
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402
from fetch.filings_sec_companyfacts import (  # noqa: E402
    SEC_HEADERS, cal_quarter, discrete_quarters, fiscal_label, fiscal_years,
)

SOURCE = "sec_segments"
COMPANIES = {"MU": 723125, "NVDA": 1045810, "WDC": 106040, "SNDK": 2023554}
SINCE = "2015-06-01"  # filing date floor
REVENUE_TAGS = {
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
    "SalesRevenueGoodsNet",
}
AXES = {"srt:ProductOrServiceAxis", "us-gaap:StatementBusinessSegmentsAxis",
        "srt:StatementGeographicalAxis"}
XI = "{http://www.xbrl.org/2003/instance}"
XD = "{http://xbrl.org/2006/xbrldi}"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


def filings(cik: int) -> list[dict]:
    sub = get(SUBMISSIONS.format(cik=cik), headers=SEC_HEADERS).json()
    blocks = [sub["filings"]["recent"]]
    for f in sub["filings"].get("files", []):
        blocks.append(get("https://data.sec.gov/submissions/" + f["name"], headers=SEC_HEADERS).json())
    out = []
    for b in blocks:
        for i, form in enumerate(b["form"]):
            if form in ("10-Q", "10-K", "10-Q/A", "10-K/A") and b["filingDate"][i] >= SINCE:
                out.append({"form": form, "filed": b["filingDate"][i], "accn": b["accessionNumber"][i],
                            "primary": b["primaryDocument"][i]})
    return sorted(out, key=lambda x: x["filed"])


def instance_url(cik: int, accn: str) -> str | None:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/"
    items = get(base + "index.json", headers=SEC_HEADERS).json()["directory"]["item"]
    names = [i["name"] for i in items]
    cands = [n for n in names if n.endswith("_htm.xml")]
    if not cands:
        cands = [n for n in names if n.endswith(".xml") and not n.startswith("FilingSummary")
                 and not any(n.endswith(s) for s in ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml"))]
    return base + cands[0] if cands else None


def parse_instance(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    ctx = {}
    for c in root.findall(f"{XI}context"):
        mem = [(e.get("dimension"), e.text.strip()) for e in c.iter(f"{XD}explicitMember")]
        p = c.find(f"{XI}period")
        s, e = p.find(f"{XI}startDate"), p.find(f"{XI}endDate")
        if s is None or e is None:
            continue
        ctx[c.get("id")] = (mem, s.text.strip(), e.text.strip())
    out = []
    for el in root:
        if "}" not in el.tag:
            continue
        tag = el.tag.split("}")[1]
        if tag not in REVENUE_TAGS or el.get("contextRef") not in ctx or el.text is None:
            continue
        mem, s, e = ctx[el.get("contextRef")]
        dims = {d: m for d, m in mem if d != "srt:ConsolidationItemsAxis"}
        if len(dims) != 1:  # single-axis breakdowns only
            continue
        (axis, member), = dims.items()
        if axis not in AXES:
            continue
        out.append({"tag": tag, "axis": axis, "member": member, "start": s, "end": e,
                    "val": float(el.text)})
    return out


def company_rows(ticker: str, cik: int) -> list[dict]:
    rows = []
    facts: dict = {}  # (axis, member) -> {(start, end): fact}
    fy_facts: dict = {}
    for f in filings(cik):
        try:
            url = instance_url(cik, f["accn"])
        except RuntimeError as e:
            print(f"  skip {f['accn']}: {e}")
            continue
        if not url:
            print(f"  no instance in {f['accn']}")
            continue
        time.sleep(0.15)
        for x in parse_instance(get(url, headers=SEC_HEADERS).content):
            fact = {"val": x["val"], "filed": f["filed"], "accn": f["accn"], "form": f["form"],
                    "tag": x["tag"], "url": url}
            d = facts.setdefault((x["axis"], x["member"]), {})
            k = (x["start"], x["end"])
            prev = d.get(k)
            if prev is None or (fact["filed"], fact["accn"]) > (prev["filed"], prev["accn"]):
                d[k] = fact
            fy_facts.setdefault("all", {})[k] = fact
        print(f"  {ticker} {f['form']} {f['filed']} ok")
    fys = fiscal_years(fy_facts)
    for (axis, member), d in facts.items():
        for (qs, qe), (val, how, fact) in discrete_quarters(d).items():
            sd, ed = dt.date.fromisoformat(qs), dt.date.fromisoformat(qe)
            fy, fq = fiscal_label(sd, ed, fys)
            rows.append({
                "period_start": qs, "period_end": qe, "fiscal_year": fy,
                "fiscal_quarter": f"Q{fq}" if fq else None, "calendar_quarter": cal_quarter(sd, ed),
                "company": ticker, "axis": axis, "member": member, "metric": "revenue",
                "value": val, "unit": "USD", "xbrl_tag": fact["tag"], "derivation": how,
                "accn": fact["accn"], "form": fact["form"], "filed": fact["filed"],
                "source_url": fact["url"],
            })
    return rows


def main() -> None:
    out = raw_dir(SOURCE)
    rows = []
    for t, cik in COMPANIES.items():
        print(f"[{SOURCE}] {t}")
        rows += company_rows(t, cik)
    df = pd.DataFrame(rows)
    # keep one row per quarter end (filers occasionally shift a start date by a day)
    df["_rank"] = (df["derivation"] == "reported").astype(int)
    df = (df.sort_values(["_rank", "filed"]).drop_duplicates(
        ["company", "axis", "member", "period_end"], keep="last").drop(columns="_rank"))
    df = df.sort_values(["company", "axis", "member", "period_end"]).reset_index(drop=True)
    df.to_csv(out / "segment_revenue.csv", index=False)
    print(f"[{SOURCE}] {len(df)} rows")
    write_source_note(
        SOURCE,
        title="SEC 10-Q/10-K XBRL instances - revenue by product / segment",
        urls=[SUBMISSIONS.format(cik=c) for c in COMPANIES.values()]
        + ["https://www.sec.gov/Archives/edgar/data/<cik>/<accession>/<instance>.xml"],
        notes=__doc__ + """
Caveats
- Member names are the filer's own (e.g. mu:DRAMProductsMember, nvda:DataCenterMember);
  business-unit structures change (Micron FY2023 and FY2026 reorganisations), and recast
  history appears only as far back as the recasting filing presented it.
- Only single-axis facts are kept (plus ConsolidationItemsAxis), so cross-tabs such as
  segment x geography are excluded.
- The newest quarter appears only after its 10-Q/10-K is filed; Micron's FQ4 FY2026
  10-K was not yet filed on the fetch date (see data/raw/micron_ir for FQ4 figures from
  the prepared remarks).
""",
    )


if __name__ == "__main__":
    main()
