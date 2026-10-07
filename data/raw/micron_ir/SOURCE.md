# Micron prepared remarks, 10-Q MD&A and earnings releases

Fetched: 2026-10-06

Sources:
- https://investors.micron.com/feed/FinancialReport.svc/GetFinancialReportList?LanguageId=1&year=<YYYY>
- https://data.sec.gov/submissions/CIK0000723125.json
- https://data.sec.gov/submissions/CIK0000723125-submissions-001.json
- https://www.sec.gov/Archives/edgar/data/723125/<accession>/<exhibit 99.1>

Micron company-reported statements: DRAM/NAND price and bit changes, DIO, results, guidance.

Sources (all published by Micron; no analyst numbers):
1. Earnings-call prepared remarks (PDF, investors.micron.com, FQ1-2019 onward). The CFO
   section states each quarter's DRAM and NAND revenue and the sequential (QoQ) change
   in bit shipments and prices as a verbal range, e.g. "Prices increased high-teens
   percentage range"; it also states days of inventory (DIO).
2. 10-Q MD&A (SEC EDGAR). FY2017-FY2018 10-Qs carry a table "Average selling prices per
   gigabit <change> vs prior quarter"; FY2022+ 10-Qs carry "Sales of DRAM products
   increased X% primarily due to ...". Used for FY2017-18 (before the remarks archive)
   and as a cross-check of the remarks.
3. Earnings press releases (8-K item 2.02, exhibit 99.1, SEC EDGAR): quarterly GAAP
   revenue and gross margin (cross-checked against XBRL companyfacts) and the
   "Business Outlook" table = company guidance for the next quarter (label: guidance).

Verbal ranges are kept verbatim (`phrase`, `statement`) and also mapped to approximate
numbers (`low`, `high`, `mid`) with this convention - it is OUR reading, not Micron's:
  single-digit: low 1-3, mid 4-6, high/upper 7-9;  teens: low 10-13, mid 14-16, high 17-19
  "low/mid/high-N0s" or "N0% range": N0-N3 / N4-N6 / N7-N9 (e.g. low-60s -> 60-63)
  low double-digit 10-13; "approximately N%" -> N; "over N%" -> low N, high blank;
  flat -> 0; "slightly"/"modestly" -> direction only, numbers blank.
Decreases are negative (low = more negative bound).

Outputs in data/raw/micron_ir/:
  price_bit_statements.csv  QoQ ASP and bit-shipment changes by technology
  remarks_metrics.csv       DRAM/NAND revenue (USD bn, rounded as stated), revenue QoQ %, DIO
  press_release_results.csv revenue and gross margin per quarter as printed in the release
  guidance.csv              next-quarter guidance (revenue, gross margin %, EPS)
  validation.csv            press release vs XBRL companyfacts, remarks vs XBRL DRAM/NAND
  remarks_text/*.txt        extracted text of each prepared-remarks PDF

Caveats
- Run filings_sec_companyfacts.py and filings_sec_segments.py first; validation.csv
  compares against their outputs.
- Prepared remarks before FQ1-2019 are not in Micron's IR feed. FQ4 QoQ statements exist only
  in remarks (10-Ks compare full years), so FQ4-FY2017 and FQ4-FY2018 have no QoQ ASP figure.
- Pre-FY2020 remarks report "Trade NAND" (excludes non-trade sales to Intel), so NAND
  revenue there differs from the XBRL NAND total.
- DIO methodology changed: FQ2-FY2021 inventory reporting change cut DIO by ~10 days; from
  FQ4-FY2021 to FQ2-FY2023 Micron quoted *average* days for the quarter, other quarters
  quote ending inventory days. FQ2-FY2023 DIO (153) includes a $1.4bn write-down
  (235 days excluding it). FQ1-FY2019 remarks state no DIO.
- Guidance before FQ1-FY2019 was published only in slides, not in the press-release text.
- `low`/`high` are an approximate numeric reading of verbal ranges (see convention above).
