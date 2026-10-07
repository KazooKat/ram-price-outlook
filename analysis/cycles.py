"""Measure past memory price cycles.

A turning point is a local extreme after which the price reverses by at least
`threshold` (log terms) before making a new extreme. For each spike we record:

  trough0   the low before the rise ("pre-spike price")
  peak      the high
  rise_x    peak / trough0
  up_months trough0 -> peak
  back_months  peak -> first month at or below trough0 (price back to pre-spike level)
  back_months_120  peak -> first month at or below 1.2 x trough0
  fall_rate  average log decline per month from peak to the next trough
  half_life  months to give back half the log rise

Output: data/processed/cycles.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import series as S

OUT = S.PROC / "cycles.csv"


def turning_points(s: pd.Series, threshold: float) -> list[tuple[pd.Timestamp, str]]:
    """Zig-zag turning points on log prices with a reversal threshold."""
    x = np.log(s.dropna())
    pts = []
    mode = None
    hi_t = lo_t = x.index[0]
    hi = lo = x.iloc[0]
    for t, v in x.items():
        if mode is None:
            if v > hi:
                hi_t, hi = t, v
            if v < lo:
                lo_t, lo = t, v
            if v - lo >= threshold:
                pts.append((lo_t, "T")); mode = "up"; hi_t, hi = t, v
            elif hi - v >= threshold:
                pts.append((hi_t, "P")); mode = "down"; lo_t, lo = t, v
        elif mode == "up":
            if v > hi:
                hi_t, hi = t, v
            elif hi - v >= threshold:
                pts.append((hi_t, "P")); mode = "down"; lo_t, lo = t, v
        else:
            if v < lo:
                lo_t, lo = t, v
            elif v - lo >= threshold:
                pts.append((lo_t, "T")); mode = "up"; hi_t, hi = t, v
    return pts


def months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def cycle_table(s: pd.Series, name: str, threshold: float = np.log(1.3)) -> pd.DataFrame:
    s = s.dropna()
    pts = turning_points(s, threshold)
    rows = []
    for i, (t, kind) in enumerate(pts):
        if kind != "P":
            continue
        prev_t = [p for p in pts[:i] if p[1] == "T"]
        if not prev_t:
            continue
        t0 = prev_t[-1][0]
        nxt = [p for p in pts[i + 1:] if p[1] == "T"]
        t1 = nxt[0][0] if nxt else None
        p0, pk = s[t0], s[t]
        after = s[s.index > t]
        back = after[after <= p0]
        back120 = after[after <= 1.2 * p0]
        rise = np.log(pk / p0)
        half = after[np.log(after / p0) <= rise / 2]
        row = dict(
            series=name, trough0=t0.date(), peak=t.date(), trough1=t1.date() if t1 is not None else None,
            p_trough0=p0, p_peak=pk, p_trough1=s[t1] if t1 is not None else np.nan,
            rise_x=pk / p0, up_months=months_between(t0, t),
            back_months=months_between(t, back.index[0]) if len(back) else np.nan,
            back_months_120=months_between(t, back120.index[0]) if len(back120) else np.nan,
            half_life=months_between(t, half.index[0]) if len(half) else np.nan,
        )
        if t1 is not None:
            m = months_between(t, t1)
            row["fall_months"] = m
            row["fall_rate"] = np.log(pk / s[t1]) / m if m else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


SERIES = {
    "boj_memory_import": (S.boj_memory_import, np.log(1.25)),
    "spot_chain": (S.spot_index, np.log(1.3)),
    "contract_chain": (S.contract_index, np.log(1.3)),
    "ddr4_8gb_spot": (S.ddr4_8gb_spot, np.log(1.3)),
    "ddr3_2gb_spot": (lambda: S.spot_chip(r"^ddr32gb256mx8", "DDR3 2Gb spot"), np.log(1.3)),
    "ddr3_4gb_spot": (lambda: S.spot_chip(r"^ddr34gb512mx8", "DDR3 4Gb spot"), np.log(1.3)),
    "ddr2_1gb_spot": (lambda: S.spot_chip(r"^ddr21gb128mx8", "DDR2 1Gb spot"), np.log(1.3)),
    "ddr_256mb_spot": (lambda: S.spot_chip(r"^ddr256mb32mx8", "DDR 256Mb spot"), np.log(1.3)),
    "nand_spot_chain": (S.nand_index, np.log(1.3)),
    "nand_512_wafer": (S.nand_wafer_512, np.log(1.3)),
    "retail_ssd_mccallum": (lambda: S.mccallum("ssd"), np.log(1.3)),
    "retail_mccallum": (lambda: S.mccallum_memory()[lambda x: x.index >= "1984-01-01"], np.log(1.3)),
}


def main():
    out = []
    for name, (fn, thr) in SERIES.items():
        s = fn()
        t = cycle_table(s, name, thr)
        out.append(t)
    df = pd.concat(out, ignore_index=True)
    df.to_csv(OUT, index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(df.round(3).to_string())
    return df


if __name__ == "__main__":
    main()
