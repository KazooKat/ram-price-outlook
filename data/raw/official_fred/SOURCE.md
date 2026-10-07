# FRED: US PPI / CPI / import-export price indices, industrial production, M3, trade values

Fetched: 2026-10-06

Sources:
- https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>
- https://fred.stlouisfed.org/series/<SERIES_ID>

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
- Failed series at fetch time: none
