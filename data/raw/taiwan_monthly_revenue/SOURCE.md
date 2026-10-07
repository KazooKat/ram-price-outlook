# Taiwan listed-company monthly revenue (MOPS t21sc03)

Fetched: 2026-10-06

Sources:
- https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{ROCyear}_{month}_0.html (TWSE-listed)
- https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{ROCyear}_{month}_0.html (TPEx-listed)

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
