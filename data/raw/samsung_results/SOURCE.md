# Samsung Electronics quarterly segment sales / operating profit (IR decks)

Fetched: 2026-10-06

Sources:
- https://www.samsung.com/global/ir/financial-information/earnings-release/
- https://images.samsung.com/is/content/samsung/assets/global/ir/docs/<YYYY>_<Q>Q_conference_eng.pdf

Parsed from the segment table in each quarterly earnings-call deck.

- Units: KRW trillion. Sales of each business include intersegment sales.
- memory_sales: Memory business sales (Samsung does not disclose Memory
  operating profit separately; ds_operating_profit covers all of Device
  Solutions = Memory + System LSI + Foundry, and before 2017 also Display).
- DS composition break: through 2021Q3 decks, DS = Semiconductor + Display
  Panel (DP); from the Dec-2021 reorganisation DS = semiconductors only
  (Display reported as SDC). 2022 decks restate 2021 DS on the new basis
  (e.g. 2021Q3 DS sales 35.09 old vs 26.74 restated). For a consistent chip
  series use semiconductor_* (2013-2021) spliced with ds_* (2021Q4+).
- quarterly_segments.csv takes each quarter's value from its own deck (as
  first reported). Where that deck's table cannot be parsed (several Q4 decks
  and the 2016 decks print row labels detached from the numbers), the value
  comes from the next deck that reprints the quarter (prior-quarter or
  year-ago column) - see reported_in_deck / as_first_reported.
  n_decks / max_abs_diff_across_decks show how consistently the same quarter
  is reprinted across decks (restatements / reorganisations show up here).
- segment_observations.csv keeps every parsed (deck, column) value.
- Table parsing is positional (header tokens vs row tokens); rows whose token
  count does not match the header are skipped, so some quarters can be missing.
