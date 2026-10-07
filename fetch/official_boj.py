"""Bank of Japan Corporate Goods Price Index (2020 base): memory ICs, other ICs,
semiconductors, storage and PCs -- producer, export and import price indices.

Uses the keyless BOJ Time-Series Data Search API (getDataCode, CSV). Series names,
units and categories in the output come from the API response.

Output (data/raw/official_boj/):
  boj_cgpi.csv  date, series_id, value, name, category, unit, last_update
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "official_boj"
API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
START = "200001"

# Codes found via getMetadata?db=PR01 (search for memory / integrated circuits / storage).
CODES = [
    # Import price index, contract currency basis (mostly USD; strips JPY moves)
    "PRCG20_2500850005",  # MOS memory integrated circuits
    "PRCG20_2500850004",  # MOS logic integrated circuits
    "PRCG20_2500850002",  # Semiconductor devices (except photoelectric)
    "PRCG20_2500840002",  # Integrated circuits (class)
    "PRCG20_2500830001",  # Electronic components and devices (subgroup)
    "PRCG20_2500850008",  # Storage media
    "PRCG20_2500850044",  # External storages
    "PRCG20_2500850043",  # Personal computers
    # Import price index, yen basis
    "PRCG20_2600850005", "PRCG20_2600850004", "PRCG20_2600850044", "PRCG20_2600850043",
    # Export price index, contract currency basis
    "PRCG20_2300550006",  # MOS memory integrated circuits
    "PRCG20_2300550005",  # MOS ICs except memory
    "PRCG20_2300540002",  # Integrated circuits (class)
    "PRCG20_2300530001",  # Electronic components and devices (subgroup)
    # Export price index, yen basis
    "PRCG20_2400550006", "PRCG20_2400550005",
    # Domestic producer price index
    "PRCG20_2201550005",  # Integrated circuits
    "PRCG20_2201520001",  # Electronic components and devices (group)
    "PRCG20_2201750008",  # External storages
    "PRCG20_2201750007",  # Personal computers
]


def _fetch(codes: list[str]) -> list[dict]:
    rows, pos = [], None
    while True:
        params = {"format": "csv", "lang": "en", "db": "PR01", "startDate": START,
                  "code": ",".join(codes)}
        if pos:
            params["startPosition"] = pos
        text = get(API, params=params).content.decode("utf-8-sig")
        lines = text.splitlines()
        header = {l.split(",", 1)[0]: l.split(",", 1)[1] if "," in l else "" for l in lines[:12]}
        if header.get("STATUS") != "200":
            raise RuntimeError(f"BOJ API error: {lines[:4]}")
        start = next(i for i, l in enumerate(lines) if l.startswith("SERIES_CODE,"))
        rows += list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))
        pos = header.get("NEXTPOSITION", "").strip()
        if not pos:
            return rows


def main() -> None:
    out = raw_dir(SOURCE)
    rows = []
    for i in range(0, len(CODES), 10):
        rows += _fetch(CODES[i:i + 10])
    df = pd.DataFrame(rows)
    df = df[~df["VALUES"].str.strip().isin(["", "null"])]
    tidy = pd.DataFrame({
        "date": pd.to_datetime(df["SURVEY_DATES"], format="%Y%m").dt.strftime("%Y-%m-%d"),
        "series_id": df["SERIES_CODE"],
        "value": pd.to_numeric(df["VALUES"]),
        "name": df["NAME_OF_TIME_SERIES"].str.replace(r"^[^/]*/_+", "", regex=True),
        "category": df["CATEGORY"].str.replace("Corporate Goods Price Index (2020 Base)/ ", "", regex=False),
        "unit": df["UNIT"],
        "last_update": df["LAST_UPDATE"],
    }).dropna(subset=["value"]).sort_values(["series_id", "date"])
    tidy.to_csv(out / "boj_cgpi.csv", index=False)

    for sid, g in tidy.groupby("series_id", sort=False):
        print(f"{sid} {g['date'].iloc[0]}..{g['date'].iloc[-1]} n={len(g)} last={g['value'].iloc[-1]} "
              f"| {g['category'].iloc[0]} | {g['name'].iloc[0]}")
    missing = set(CODES) - set(tidy["series_id"])
    if missing:
        print("MISSING:", sorted(missing))

    write_source_note(
        SOURCE,
        title="Bank of Japan CGPI (2020 base): memory IC, IC, storage and PC price indices",
        urls=[f"{API}?format=csv&lang=en&db=PR01&startDate={START}&code=<SERIES_CODES>",
              "https://www.stat-search.boj.or.jp/api/v1/getMetadata?format=csv&lang=en&db=PR01"],
        notes="""
Keyless BOJ Time-Series Data Search API. All series are monthly, CY2020 average = 100,
not seasonally adjusted. Columns: date (first of month), series_id (BOJ code), value,
name, category (index type), unit, last_update (BOJ release stamp).

Index types:
- Import / Export Price Index (contract currency basis): prices in the invoicing currency
  (mostly USD for chips) -- best proxy for global contract prices, free of JPY moves.
- Import / Export Price Index (yen basis): same goods converted to JPY.
- Producer Price Index: Japanese domestic producer prices.

Caveats: commodity-level series start between 2000 and 2015 depending on the item;
class/subgroup-level series start 2020. Recent months are preliminary and revised at
the next release. "MOS memory integrated circuits" is a single BOJ commodity covering
memory chips generally (no DRAM vs NAND split); its weight is in the BOJ metadata.
""",
    )


if __name__ == "__main__":
    main()
