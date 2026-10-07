# Design

## Question

When will prices for high-end PC components (RAM first, then SSDs, GPUs, CPUs) return to where they were before the AI boom, and what price and performance changes should a buyer expect?

## Audience

PC buyers deciding whether to buy now or wait. Plain writing: explain concepts, not obvious implications.

## Rules

- All numbers come from data pulled and processed in this repo. Outside forecasts appear only in one section, where each is checked against our own results.
- Only free, reliable sources: government statistics, company filings, archived retail prices, public APIs.
- Every number in the report is labeled measured or modeled.

## Method

Cycle-indicator model.

1. Rebuild past memory cycles from long-run price data and measure peak-to-normal durations and decline rates.
2. Locate the current cycle with indicators: producer and import price indices, memory makers' margins and inventory, hyperscaler AI capex, retail deal prices, sentiment.
3. Forecast normalization dates as scenarios (fast, base, slow), conditioned on how the indicators looked at comparable points in past cycles.
4. Backtest on the 2018-19 and 2022-23 downturns.
5. Time-series models (ETS/ARIMA) as a sanity check only.

"Normal" is defined from the data (a pre-boom trend line, not a single date) because the AI boom started in late 2022 but memory prices bottomed in 2023.

## Layout

- `fetch/` one script per source, writing to `data/raw/<source>/` with a `SOURCE.md`
- `analysis/` processing, cycle analysis, forecast, sentiment, performance
- `data/processed/` tidy outputs
- `charts/` figures used in the report
- `run.py` rebuilds everything from a fresh clone
- `README.md` the report

## Report order

1. Answer: dates and ranges per component
2. Buy now or wait
3. What happened
4. How past cycles ended
5. Forecast scenarios
6. Performance per dollar outlook
7. Sentiment
8. Outside forecasts and whether they hold
9. Method and limitations
