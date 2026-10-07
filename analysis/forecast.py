"""Forecast when DRAM prices return to normal, with a backtest.

Two pieces, both estimated from past cycles (cycles.py):

1. Peak timing. During an upswing the quarterly price increase peaks, then
   shrinks by a roughly constant ratio each quarter until prices stop rising.
   We measure that decay ratio in past cycles and apply it to the current
   cycle's contract prices, which is what retail tracks.

2. The fall. After the peak, prices decline at a roughly constant log rate
   that does not depend on how big the spike was (tested in cycles.py; see
   README). So months from peak back to the pre-spike price is about
   ln(peak / pre-spike) / fall_rate.

Scenarios use the 25th/50th/75th percentiles of the historical decay ratio and
fall rate. The slow scenario also caps the peak at the arrival of announced new
fab capacity (company-stated dates, see data/raw/perf_manual/announced_products.csv
and docs/external_views_notes.md).

Outputs (data/processed/):
  forecast_params.csv     historical decay ratios and fall rates used
  forecast_backtest.csv   method applied at the same point in past cycles
  forecast_paths.csv      monthly retail price ratio path per scenario
  forecast_dates.csv      dates retail DDR5 crosses 2x / 1.5x / 1.2x / 1.0x of normal
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import series as S

OUT = S.PROC
ASOF = pd.Timestamp("2026-09-01")  # last month with contract data in the window

# Modern era: after the 2001-03 industry consolidation; matches today's market structure.
MODERN_FROM = pd.Timestamp("2003-01-01")
# Series whose cycles define the fall rate. BOJ is an aggregate DRAM+NAND index
# with long-term contracts, so its amplitude and fall rates are structurally
# smaller; it is used for peak timing only.
FALL_SERIES = ["spot_chain", "ddr4_8gb_spot", "retail_mccallum", "ddr_256mb_spot", "contract_chain"]
TIMING_SERIES = {
    "boj_memory_import": S.boj_memory_import,
    "contract_chain": S.contract_index,
    "spot_chain": S.spot_index,
}
SUPPLY_CAP = pd.Timestamp("2028-04-01")  # announced cleanrooms online: Micron Idaho mid-2027 + "several quarters"; SK hynix Yongin 2027; Micron Singapore 2H28


def quarterly_increments(s: pd.Series) -> pd.Series:
    q = np.log(s.resample("QS").mean()).dropna()
    return q.diff().dropna()


def upswing_decay(s: pd.Series, peak: pd.Timestamp, trough0: pd.Timestamp) -> dict | None:
    """Within one upswing: the max-increase quarter, lag to the peak, and decay ratios after it."""
    inc = quarterly_increments(s)
    up = inc[(inc.index > trough0) & (inc.index <= peak + pd.offsets.QuarterBegin(0))]
    if len(up) < 2:
        return None
    qmax = up.idxmax()
    after = inc[inc.index > qmax]
    ratios = []
    prev = up.max()
    for v in after:
        if v <= 0 or prev <= 0:
            break
        ratios.append(v / prev)
        prev = v
    pk_q = pd.Timestamp(peak).to_period("Q").start_time
    lag = (pk_q.to_period("Q") - qmax.to_period("Q")).n
    return dict(max_q=qmax.date(), max_inc=up.max(), peak_q=pk_q.date(), lag_q=lag,
                decay_ratios=ratios, decay_first=ratios[0] if ratios else 0.0)


def load_cycles() -> pd.DataFrame:
    cyc = pd.read_csv(OUT / "cycles.csv", parse_dates=["trough0", "peak", "trough1"])
    # the contract index has no overlapping items across 2009-2012, so its
    # cycles before 2015 are artifacts of the gap
    bad = (cyc.series == "contract_chain") & (cyc.peak < "2015-01-01")
    return cyc[~bad]


def history_params():
    cyc = load_cycles()
    fall = cyc[cyc.series.isin(FALL_SERIES) & (cyc.peak >= MODERN_FROM) & (cyc.rise_x >= 1.3)]
    fall = fall.dropna(subset=["fall_rate"])

    timing = []
    for name, fn in TIMING_SERIES.items():
        s = fn()
        for _, r in cyc[(cyc.series == name) & (cyc.peak >= MODERN_FROM)].iterrows():
            d = upswing_decay(s, r.peak, r.trough0)
            if d:
                timing.append(dict(series=name, peak=r.peak.date(), **d))
    timing = pd.DataFrame(timing)
    return fall, timing


def decay_path(last_inc: float, ratio: float, start: pd.Timestamp, stop_inc: float = 0.02,
               cap: pd.Timestamp | None = None) -> tuple[pd.Timestamp, float, list]:
    """Quarterly increments shrinking by `ratio` until below `stop_inc` (or the cap date)."""
    q = start
    inc = last_inc
    total = 0.0
    steps = []
    while True:
        inc = inc * ratio
        q = q + pd.offsets.QuarterBegin(1, startingMonth=1)
        if inc < stop_inc or (cap is not None and q > cap):
            break
        total += inc
        steps.append((q, inc))
    peak_q = steps[-1][0] if steps else start
    return peak_q, total, steps


def current_contract_increments() -> pd.Series:
    """DDR5 SO-DIMM contract (the product closest to a retail DIMM), quarterly log changes."""
    return quarterly_increments(S.ddr5_sodimm_contract())


def retail_baselines() -> dict:
    kit = S.basket_ddr5_32gb()
    pre_spike = kit["2024-01-01":"2025-06-01"].mean()
    pre_ai = kit["2022-10-01":"2022-12-01"].mean()
    now = kit[kit.index > ASOF - pd.DateOffset(months=3)].mean()
    dq = S.deals_quarterly("ram_ddr5_32gb_kit_usd")
    deal_pre = dq.loc["2024Q1":"2025Q2", "median"].median()
    return dict(kit_pre_spike=pre_spike, kit_pre_ai=pre_ai, kit_now=now,
                deal_kit_pre_spike=deal_pre, deal_kit_now=dq["median"].iloc[-1])


def months_to(level_ratio_now: float, target: float, rate: float) -> float:
    if level_ratio_now <= target:
        return 0.0
    return np.log(level_ratio_now / target) / rate


def scenario_table(fall: pd.DataFrame, timing: pd.DataFrame, base: dict,
                   bias_m: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_ratios = [r for rs in timing.decay_ratios for r in rs]
    # cycles where increases stopped dead after the max quarter count as ratio 0
    all_ratios += [0.0] * int((timing.decay_ratios.map(len) == 0).sum())
    dq = np.quantile(all_ratios, [0.25, 0.5, 0.75])
    fq = np.quantile(fall.fall_rate, [0.25, 0.5, 0.75])

    inc = current_contract_increments()
    last_q, last_inc = inc.index[-1], inc.iloc[-1]
    ratio_now = base["kit_now"] / base["kit_pre_spike"]

    scen = {
        "fast": dict(decay=dq[0], fall=fq[2], cap=None),
        "base": dict(decay=dq[1], fall=fq[1], cap=None),
        "slow": dict(decay=dq[2], fall=fq[0], cap=SUPPLY_CAP),
        # sensitivity: increases stop now and prices fall at the fastest modern rate
        # (what a demand shock such as an AI capex pullback would look like)
        "crash": dict(decay=0.0, fall=float(fall.fall_rate.max()), cap=None),
    }
    rows, paths = [], []
    for name, p in scen.items():
        peak_q, more, steps = decay_path(last_inc, p["decay"], last_q, cap=p["cap"])
        # retail kit tracks contract with a stable premium (premium fell to ~7% by Aug 2026)
        peak_ratio = ratio_now * np.exp(more)
        # mid-quarter; prices were still rising in the latest data, so the peak is no earlier than next month
        peak_m = max(peak_q + pd.DateOffset(months=1), ASOF + pd.DateOffset(months=1))
        row = dict(scenario=name, decay_ratio=p["decay"], fall_rate=p["fall"], peak=peak_m.date(),
                   further_rise_pct=100 * (np.exp(more) - 1), peak_ratio=peak_ratio,
                   peak_kit_usd=peak_ratio * base["kit_pre_spike"])
        for tgt in (2.0, 1.5, 1.2, 1.0):
            m = months_to(peak_ratio, tgt, p["fall"])
            row[f"date_{tgt}x"] = (peak_m + pd.DateOffset(months=int(round(m)))).date()
            # backtests put the return date early by a median of bias_m months
            row[f"date_{tgt}x_adj"] = (peak_m + pd.DateOffset(months=int(round(m)) + bias_m)).date()
        pre_ai_ratio = base["kit_pre_ai"] / base["kit_pre_spike"]
        m = months_to(peak_ratio, pre_ai_ratio, p["fall"])
        row["date_pre_ai_level"] = (peak_m + pd.DateOffset(months=int(round(m)))).date()
        row["date_pre_ai_level_adj"] = (peak_m + pd.DateOffset(months=int(round(m)) + bias_m)).date()
        rows.append(row)

        # monthly path for charts
        months = pd.date_range("2024-01-01", "2032-12-01", freq="MS")
        lvl = []
        for t in months:
            if t <= ASOF:
                lvl.append(np.nan)
            elif t <= peak_m:
                # interpolate the remaining rise linearly in log between now and the peak
                span = max((peak_m.to_period("M") - ASOF.to_period("M")).n, 1)
                k = (t.to_period("M") - ASOF.to_period("M")).n / span
                lvl.append(ratio_now * np.exp(more * k))
            else:
                # backtest correction: prices have stayed near the peak longer than the
                # model assumes, so hold the peak for bias_m months before the decline
                k = (t.to_period("M") - peak_m.to_period("M")).n - bias_m
                lvl.append(peak_ratio * np.exp(-p["fall"] * max(k, 0)))
        paths.append(pd.DataFrame({"month": months, "scenario": name, "ratio_to_pre_spike": lvl}))
    return pd.DataFrame(rows), pd.concat(paths, ignore_index=True)


def backtest(fall_all: pd.DataFrame, timing: pd.DataFrame) -> pd.DataFrame:
    """Apply the base method at the same stage of past cycles, using only earlier data.

    Decision point: the quarter after the first quarter whose increase shrank, i.e.
    two quarters after the max-increase quarter (today: max Q1 2026, now Q3 2026).
    """
    rows = []
    cyc = load_cycles()
    # only series whose own cycles feed the fall rates (BOJ falls structurally slower)
    for name, fn in [("spot_chain", S.spot_index), ("contract_chain", S.contract_index),
                     ("ddr4_8gb_spot", S.ddr4_8gb_spot)]:
        s = fn()
        inc = quarterly_increments(s)
        for _, r in cyc[(cyc.series == name) & (cyc.peak >= MODERN_FROM)].iterrows():
            d = upswing_decay(s, r.peak, r.trough0)
            if not d or pd.isna(r.back_months):
                continue
            max_q = pd.Timestamp(d["max_q"])
            decide_q = max_q + pd.offsets.QuarterBegin(2, startingMonth=1)
            known = inc[inc.index <= decide_q]
            # prior information only
            prior_t = timing[pd.to_datetime(timing.peak) < max_q]
            prior_f = fall_all[(fall_all.peak < max_q)]
            if len(prior_f) < 3 or len(prior_t) < 2:
                continue
            ratios = [x for rs in prior_t.decay_ratios for x in rs] + [0.0] * int((prior_t.decay_ratios.map(len) == 0).sum())
            ratio = float(np.median(ratios))
            rate = float(prior_f.fall_rate.median())
            last_inc = known.iloc[-1]
            if last_inc <= 0:
                pred_peak_q, more = known.index[-1], 0.0
                # already falling at the decision point: peak was the last rising quarter
                rising = known[known > 0]
                pred_peak_q = rising.index[-1] if len(rising) else known.index[-1]
            else:
                pred_peak_q, more, _ = decay_path(last_inc, ratio, known.index[-1])
            q_level = np.log(s.resample("QS").mean()).dropna()
            lvl_now = q_level[q_level.index <= decide_q].iloc[-1]
            pred_peak_lvl = np.exp(lvl_now + more)
            pred_back = np.log(pred_peak_lvl / r.p_trough0) / rate
            pred_peak_m = pred_peak_q + pd.DateOffset(months=1)
            pred_back_date = pred_peak_m + pd.DateOffset(months=int(round(pred_back)))
            actual_back = r.peak + pd.DateOffset(months=int(r.back_months))
            rows.append(dict(series=name, actual_peak=r.peak.date(), decision_q=decide_q.date(),
                             pred_peak=pred_peak_m.date(), actual_back=actual_back.date(),
                             pred_back=pred_back_date.date(),
                             peak_err_m=(pred_peak_m.to_period("M") - r.peak.to_period("M")).n,
                             back_err_m=(pred_back_date.to_period("M") - actual_back.to_period("M")).n,
                             decay_used=ratio, fall_used=rate))
    return pd.DataFrame(rows)


def main():
    fall, timing = history_params()
    base = retail_baselines()

    params = pd.concat([
        fall.assign(kind="fall")[["kind", "series", "peak", "rise_x", "fall_rate", "back_months"]],
        timing.assign(kind="timing")[["kind", "series", "peak", "max_q", "lag_q", "decay_first"]],
    ], ignore_index=True)
    params.to_csv(OUT / "forecast_params.csv", index=False)

    bt = backtest(fall, timing)
    bt.to_csv(OUT / "forecast_backtest.csv", index=False)

    bias = int(-round(bt.back_err_m.median()))
    table, paths = scenario_table(fall, timing, base, bias_m=bias)
    table["backtest_bias_months"] = bias
    table.to_csv(OUT / "forecast_dates.csv", index=False)
    paths.to_csv(OUT / "forecast_paths.csv", index=False)

    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print("baselines:", {k: round(v, 2) for k, v in base.items()})
        print("contract increments:", current_contract_increments().tail(5).round(3).to_dict())
        print("\nfall rates (modern):", fall.fall_rate.describe().round(3).to_dict())
        print(timing[["series", "peak", "max_q", "lag_q", "decay_ratios"]].to_string())
        print("\nbacktest:\n", bt.to_string())
        print("  mean abs error months: peak", bt.peak_err_m.abs().mean().round(1), " back", bt.back_err_m.abs().mean().round(1),
              " median error: peak", bt.peak_err_m.median(), " back", bt.back_err_m.median())
        print("\nscenarios:\n", table.round(3).to_string())


if __name__ == "__main__":
    main()
