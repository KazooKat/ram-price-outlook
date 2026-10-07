"""WSTS Historical Billings Report: monthly worldwide / regional semiconductor billings.

The free report (no login) has total semiconductor billings by region only -- no memory
or product split (that is in the paid Blue Book). The xlsx filename changes every month,
so the link is scraped from the report page.

Output (data/raw/official_wsts/):
  wsts_billings.csv  date, region, measure (monthly | 3mma), value_kusd
Requires openpyxl.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "official_wsts"
PAGE = "https://www.wsts.org/67/Historical-Billings-Report"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def _parse(sheet: pd.DataFrame, measure: str) -> pd.DataFrame:
    header_row = next(i for i in range(10) if sheet.iloc[i].tolist()[1:3] == MONTHS[:2])
    cols = sheet.iloc[header_row].tolist()
    month_idx = {m: cols.index(m) for m in MONTHS}
    rows, year = [], None
    for _, r in sheet.iloc[header_row + 1:].iterrows():
        label = r.iloc[0]
        if isinstance(label, (int, float)) and not pd.isna(label):
            year = int(label)
            continue
        if year is None or not isinstance(label, str):
            continue
        for m, j in month_idx.items():
            v = r.iloc[j]
            if pd.notna(v):
                rows.append({"date": f"{year}-{MONTHS.index(m) + 1:02d}-01",
                             "region": label.strip(), "measure": measure, "value_kusd": float(v)})
    return pd.DataFrame(rows)


def main() -> None:
    out = raw_dir(SOURCE)
    page = get(PAGE).text
    m = re.search(r'href="([^"]*Historical-Billings-Report[^"]*\.xlsx)"', page)
    if not m:
        raise RuntimeError("xlsx link not found on WSTS page")
    xlsx_url = m.group(1) if m.group(1).startswith("http") else "https://www.wsts.org" + m.group(1)
    book = pd.read_excel(io.BytesIO(get(xlsx_url).content), sheet_name=None, header=None)
    df = pd.concat([_parse(book["Monthly Data"], "monthly"), _parse(book["3MMA"], "3mma")])
    # the 3MMA sheet carries 0.0 formula placeholders for months not yet reported
    df = df[df["date"] <= df.loc[df["measure"] == "monthly", "date"].max()]
    df = df.sort_values(["measure", "region", "date"]).reset_index(drop=True)
    df.to_csv(out / "wsts_billings.csv", index=False)

    ww = df[(df.region == "Worldwide") & (df.measure == "monthly")]
    print(f"{xlsx_url}\n{len(df)} rows; worldwide monthly {ww.date.iloc[0]}..{ww.date.iloc[-1]}")
    print(ww.tail(14).to_string(index=False))

    write_source_note(
        SOURCE,
        title="WSTS Historical Billings Report (monthly semiconductor billings by region)",
        urls=[PAGE, xlsx_url],
        notes="""
Free WSTS report. Values are in thousands of US dollars (value_kusd), nominal, not
seasonally adjusted. measure = 'monthly' (sheet 'Monthly Data') or '3mma' (sheet '3MMA',
three-month moving average as published by WSTS). Regions: Americas, Europe, Japan,
Asia Pacific, Worldwide (as labelled in the file).

Caveats:
- Total semiconductors only; no memory / logic / product split in the free report.
- Billings are by region of shipment destination; revisions happen when WSTS updates.
- The workbook carries a WSTS copyright notice ("All Rights Reserved"); check terms
  before redistributing the raw numbers.
""",
    )


if __name__ == "__main__":
    main()
