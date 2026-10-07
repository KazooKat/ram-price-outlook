# SEC EDGAR XBRL companyfacts - quarterly financials

Fetched: 2026-10-06

Sources:
- https://data.sec.gov/api/xbrl/companyfacts/CIK0000723125.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0000106040.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0002023554.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0001137789.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0000002488.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0000050863.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0001018724.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0001326801.json
- https://data.sec.gov/api/xbrl/companyfacts/CIK0001341439.json
- https://www.sec.gov/files/company_tickers.json

Quarterly financials from SEC EDGAR XBRL companyfacts (memory makers, AI demand, hyperscalers).

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
