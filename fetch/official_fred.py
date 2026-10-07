"""Official US price indices, production, shipments and trade series via FRED.

Uses FRED's keyless CSV endpoint (fredgraph.csv) for values and scrapes each
series page for title / units / seasonal adjustment / frequency, so the
metadata in fred_meta.csv comes from FRED itself, not from this file.

Outputs (data/raw/official_fred/):
  fred_series.csv  long format: date, series_id, value
  fred_meta.csv    series_id, group, title, units, seasonal_adjustment,
                   frequency, first_date, last_date, n_obs
"""
from __future__ import annotations

import html
import io
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "official_fred"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
PAGE_URL = "https://fred.stlouisfed.org/series/{}"

# group -> series ids. IDs were confirmed against FRED search / series pages.
SERIES = {
    "ppi_semiconductors": [
        "PCU334413334413",     # Semiconductor and related device mfg (industry)
        "PCU334413334413P",    # ... primary products
        "PCU3344133344131",    # ... integrated circuit packages
        "PCU33441333441312",   # ... microprocessors (discontinued 2015)
        "PCU33441333441314",   # ... all other integrated microcircuits (discontinued 2015)
        "PCU33443344",         # Semiconductor and other electronic component mfg
        "PCU334334",           # Computer and electronic product mfg
        "WPU1178",             # Commodity: electronic components and accessories
        "WPU117839",           # Commodity: integrated circuit packages incl. microprocessors
        "WPU117839111",
        "WPU117839112",
        "WPU117847",           # Commodity: other semiconductor devices incl. wafers
    ],
    "ppi_computers_storage": [
        "PCU334111334111",     # Electronic computer mfg
        "PCU3341113341115",    # ... host computers / servers
        "PCU33411133411172",   # ... portable computers
        "PCU33411133411173",   # ... PCs and workstations
        "PCU334112334112",     # Computer storage device mfg
        "PCU3341123341121",    # ... computer storage devices
        "WPU115",              # Commodity: computers and computer equipment
        "WPU1151",
    ],
    "cpi": [
        "CUUR0000SEEE01",      # Computers, peripherals, smart home assistants (NSA)
        "CUSR0000SEEE01",      # same, SA
        "CUUR0000SEEE",        # Information technology commodities (NSA)
    ],
    "import_export_price": [
        "IR21320", "IQ21320",  # End use: semiconductors (import / export)
        "IR213", "IR213COM", "IR21300", "IR21301",
        "IQ21300", "IQ21301",
        "IZ3344", "IY3344",    # NAICS 3344 import / export
        "IZ3341", "IZ334",
        "COOASZ3344", "COPRIMZ3344", "COINDUSZ3344", "COJPNZ3344", "COCHNZ3344",
        "COOASZ334", "COASEANZ334",
        "IP8542", "ID8542",    # HS 8542 electronic integrated circuits
        "IP8471", "ID8471",    # HS 8471 ADP machines
        "IP8473",              # HS 8473 parts for computers
        "IP8523",              # HS 8523 incl. solid-state storage
        "IP8541",
    ],
    "production_capacity": [
        "IPG3344S", "IPG3341S", "IPHITEK2S", "IPB53122S",
        "CAPUTLG3344S", "CAPG3344S",
    ],
    "census_m3": [
        "A34SVS", "A34SNO", "A34STI", "A34SIS",
        "A34AVS", "A34ATI",    # electronic computers
        "A34BVS", "A34BTI",    # computer storage devices
        "A34HVS", "A34HTI",    # other electronic components
        "A34GVS",              # semiconductors (discontinued 2010)
    ],
    "trade_values": [
        "IMPKR", "IMP5830", "IMPJP",          # US goods imports from Korea / Taiwan / Japan
        "VALEXPKRM052N", "VALEXPTWM052N",     # Korea / Taiwan total goods exports (IMF)
        "XTEXVA01KRM664S",                    # Korea goods exports (OECD MEI)
    ],
}


def _meta(series_id: str) -> dict:
    page = get(PAGE_URL.format(series_id)).text
    title = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    units = re.search(r'series-meta-value-units">([^<]*)<', page)
    sa = re.search(r'series-meta-value-units">[^<]*</span>,</div><div class="default-text">([^<]*)<', page)
    freq = re.search(r'series-meta-value-frequency">\s*([^<]*?)\s*<', page)
    clean = lambda m: html.unescape(m.group(1)).strip() if m else ""
    return {"title": clean(title), "units": clean(units),
            "seasonal_adjustment": clean(sa), "frequency": clean(freq).rstrip(",")}


def main() -> None:
    out = raw_dir(SOURCE)
    frames, meta, failed = [], [], []
    for group, ids in SERIES.items():
        for sid in ids:
            try:
                r = get(CSV_URL, params={"id": sid})
            except RuntimeError as e:
                failed.append((sid, str(e)))
                continue
            if not r.text.startswith("observation_date"):
                failed.append((sid, "no CSV returned"))
                continue
            df = pd.read_csv(io.StringIO(r.text), na_values=["."])
            df.columns = ["date", "value"]
            df = df.dropna(subset=["value"])
            df.insert(1, "series_id", sid)
            frames.append(df)
            m = {"series_id": sid, "group": group, **_meta(sid),
                 "first_date": df["date"].iloc[0], "last_date": df["date"].iloc[-1],
                 "n_obs": len(df)}
            meta.append(m)
            print(f"{sid:20s} {m['first_date']}..{m['last_date']} n={len(df):4d} "
                  f"last={df['value'].iloc[-1]} | {m['units']} | {m['title'][:70]}")
            time.sleep(0.3)

    pd.concat(frames).to_csv(out / "fred_series.csv", index=False)
    pd.DataFrame(meta).to_csv(out / "fred_meta.csv", index=False)
    if failed:
        print("FAILED:", failed)

    write_source_note(
        SOURCE,
        title="FRED: US PPI / CPI / import-export price indices, industrial production, M3, trade values",
        urls=[CSV_URL + "?id=<SERIES_ID>", PAGE_URL.format("<SERIES_ID>")],
        notes=f"""
Keyless FRED CSV download, one request per series. Original publishers: BLS (PPI, CPI,
import/export price indexes), Federal Reserve Board (industrial production, capacity),
Census (M3 shipments/inventories, US imports by country), IMF / OECD (Korea, Taiwan exports).

Files:
- fred_series.csv: long format (date = first day of period, series_id, value). Missing
  observations ('.') dropped.
- fred_meta.csv: per-series title, units, seasonal adjustment, frequency, coverage, scraped
  from the FRED series page at fetch time.

Caveats:
- PPI/MXP indexes have different base periods (see units column); rebase before comparing.
- PPI values for the most recent 4 months are preliminary and get revised.
- Several HS-based import price indexes end before 2026 on FRED (IP8542 2022-12, IP8471
  2023-12, IP8523 2024-12, IP8473 2025-12); check last_date in fred_meta.csv. Memory-
  specific PPI detail (WPU117839112 / PCU33441333441314, "all other integrated
  microcircuits") ends 2015; no current memory-chip PPI was found on FRED.
- No 2025-10 observation for CPI and BLS import/export price series (missing on FRED;
  cause presumed to be the Oct-2025 US federal shutdown, not verified). PPI series do
  have 2025-10.
- Census M3 values are seasonally adjusted, millions of dollars, and are revised.
- Failed series at fetch time: {failed or 'none'}
""",
    )


if __name__ == "__main__":
    main()
