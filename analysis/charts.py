"""Render report charts in light and dark variants (charts/<name>-light.png, -dark.png).

Palette: validated categorical slots (blue, orange, aqua, yellow) against GitHub's
light (#ffffff) and dark (#0d1117) surfaces. Light-mode aqua and yellow sit below
3:1 contrast, so every chart is direct-labeled and its data is in data/processed/.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import series as S

CHARTS = S.ROOT / "charts"

THEMES = {
    "light": dict(surface="#ffffff", text="#0b0b0b", text2="#52514e", grid="#e6e5e1", muted="#b4b2ab",
                  s=["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]),
    "dark": dict(surface="#0d1117", text="#e6edf3", text2="#9198a1", grid="#262c33", muted="#4f5761",
                 s=["#3987e5", "#d95926", "#199e70", "#c98500"]),
}


def setup(theme: str, figsize=(9, 4.8), nrows=1, ncols=1, **kw):
    t = THEMES[theme]
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10, "axes.edgecolor": t["grid"], "axes.labelcolor": t["text2"],
        "xtick.color": t["text2"], "ytick.color": t["text2"], "text.color": t["text"],
        "axes.titlecolor": t["text"], "figure.facecolor": t["surface"], "axes.facecolor": t["surface"],
        "savefig.facecolor": t["surface"], "lines.linewidth": 2, "lines.solid_capstyle": "round",
        "axes.titleweight": "semibold", "axes.titlesize": 11, "axes.titlelocation": "left",
        "legend.frameon": False, "legend.labelcolor": t["text2"],
    })
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, **kw)
    for ax in np.atleast_1d(axes).ravel():
        ax.grid(True, color=t["grid"], linewidth=0.8, linestyle="-")
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(t["grid"])
        ax.tick_params(length=0)
    return fig, axes, t


def save(fig, name: str, theme: str):
    CHARTS.mkdir(exist_ok=True)
    fig.savefig(CHARTS / f"{name}-{theme}.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def _at(s: pd.Series, when: str) -> float:
    ts = pd.Timestamp(when)
    return float(s.reindex(s.index.union([ts])).interpolate("time")[ts])


def end_label(ax, x, y, text, t, dx=6, dy=0, color=None):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", va="center",
                fontsize=9, color=color or t["text2"])


def dot(ax, x, y, color, t):
    ax.plot([x], [y], "o", ms=6, color=color, mec=t["surface"], mew=2, zorder=5)


# ---------------------------------------------------------------- charts

def ram_outlook(theme):
    """Retail 2x16GB DDR5-6000 kit: history and scenarios."""
    fig, ax, t = setup(theme, figsize=(10, 5.2))
    base = pd.read_csv(S.PROC / "forecast_dates.csv").set_index("scenario")
    paths = pd.read_csv(S.PROC / "forecast_paths.csv", parse_dates=["month"])
    kit = S.basket_ddr5_32gb()
    pre = kit["2024-01-01":"2025-06-01"].mean()

    ax.axhline(pre, color=t["text2"], lw=1)
    ax.text(pd.Timestamp("2022-10-01"), pre * 0.9, f"Normal (2024 to mid-2025 avg): ${pre:.0f}", fontsize=9,
            color=t["text2"], va="top")
    ax.plot(kit.index, kit.values, color=t["s"][0], lw=2)
    end_label(ax, kit.index[-1], kit.iloc[-1], f"${kit.iloc[-1]:.0f} (Sep 2026)", t, dx=-8, dy=-16)
    ax.annotate("ChatGPT launch\n(Nov 2022)", (pd.Timestamp("2022-11-01"), _at(kit, "2022-11-01")), xytext=(14, 30),
                textcoords="offset points", fontsize=8.5, color=t["text2"],
                arrowprops=dict(arrowstyle="-", color=t["text2"], lw=0.8))

    names = {"fast": "Fast", "base": "Base", "slow": "Slow"}
    colors = {"fast": t["s"][2], "base": t["s"][1], "slow": t["s"][3]}
    for sc in ["fast", "base", "slow"]:
        p = paths[(paths.scenario == sc) & paths.ratio_to_pre_spike.notna()]
        p = p[p.ratio_to_pre_spike >= 0.95]
        start = pd.DataFrame({"month": [kit.index[-1]], "ratio_to_pre_spike": [kit.iloc[-1] / pre]})
        p = pd.concat([start, p[["month", "ratio_to_pre_spike"]]])
        ax.plot(p.month, p.ratio_to_pre_spike * pre, color=colors[sc], lw=2, ls="-")
        d = pd.Timestamp(base.loc[sc, "date_1.0x_adj"])
        dot(ax, d, pre, colors[sc], t)
        ax.annotate(f"{names[sc]}: {d:%b %Y}", (d, pre), xytext=(0, -16 if sc != "base" else -30),
                    textcoords="offset points", ha="center", fontsize=9, color=t["text"])
    ax.set_ylim(0, 760)
    ax.set_xlim(pd.Timestamp("2022-09-01"), pd.Timestamp("2032-01-01"))
    ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("${x:,.0f}"))
    ax.set_title("32GB (2x16GB) DDR5-6000 kit: lowest US retail price and forecast")
    handles = [matplotlib.lines.Line2D([], [], color=t["s"][0], lw=2, label="Measured (PCPartPicker, archived)")]
    handles += [matplotlib.lines.Line2D([], [], color=colors[s], lw=2, label=f"{names[s]} scenario") for s in names]
    ax.legend(handles=handles, loc="upper right", fontsize=9)
    save(fig, "ram-outlook", theme)


def cycles_compared(theme):
    """Every DRAM spike since 2003, aligned at the pre-spike low, vs the current one."""
    fig, ax, t = setup(theme, figsize=(10, 5))
    cyc = pd.read_csv(S.PROC / "cycles.csv", parse_dates=["trough0", "peak", "trough1"])
    past = cyc[(cyc.series == "spot_chain") & (cyc.peak >= "2003-01-01")]
    s = S.spot_index()
    for _, r in past.iterrows():
        end = r.trough1 if pd.notna(r.trough1) else r.peak + pd.DateOffset(months=30)
        seg = s[(s.index >= r.trough0) & (s.index <= end)]
        x = (seg.index.year - r.trough0.year) * 12 + (seg.index.month - r.trough0.month)
        ax.plot(x, seg.values / r.p_trough0, color=t["muted"], lw=1.5)
        end_label(ax, x[np.argmax(seg.values)], seg.max() / r.p_trough0, f"{r.peak:%Y}", t, dx=4, dy=6)
    cur = S.ddr5_16gb_spot()
    low = cur["2024-10-01":"2025-03-01"]
    t0 = low.idxmin()
    seg = cur[cur.index >= t0]
    x = (seg.index.year - t0.year) * 12 + (seg.index.month - t0.month)
    ax.plot(x, seg.values / low.min(), color=t["s"][1], lw=2.5)
    dot(ax, x[-1], seg.iloc[-1] / low.min(), t["s"][1], t)
    end_label(ax, x[-1], seg.iloc[-1] / low.min(), f"DDR5 now: {seg.iloc[-1] / low.min():.1f}x", t, dy=0)
    con = S.ddr5_sodimm_contract()
    seg = con[con.index >= t0]
    lowc = con["2024-10-01":"2025-06-01"].min()
    x = (seg.index.year - t0.year) * 12 + (seg.index.month - t0.month)
    ax.plot(x, seg.values / lowc, color=t["s"][0], lw=2.5)
    dot(ax, x[-1], seg.iloc[-1] / lowc, t["s"][0], t)
    end_label(ax, x[-1], seg.iloc[-1] / lowc, f"DDR5 contract: {seg.iloc[-1] / lowc:.1f}x", t)
    ax.set_yscale("log")
    ax.set_yticks([1, 2, 3, 5, 10])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}x"))
    ax.set_xlim(0, 75)
    ax.set_xlabel("Months since the pre-spike low")
    ax.set_title("DRAM price vs its pre-spike low: past spikes (gray) and now")
    handles = [matplotlib.lines.Line2D([], [], color=t["muted"], lw=1.5, label="Past spikes, chained spot index"),
               matplotlib.lines.Line2D([], [], color=t["s"][1], lw=2.5, label="DDR5 16Gb chip, spot"),
               matplotlib.lines.Line2D([], [], color=t["s"][0], lw=2.5, label="DDR5 8GB SO-DIMM, contract")]
    ax.set_ylim(0.45, 16)
    ax.legend(handles=handles, loc="lower right", fontsize=9)
    save(fig, "cycles-compared", theme)


def momentum(theme):
    """Quarterly price change: past cycles decayed to zero within a few quarters of the fastest rise."""
    fig, axes, t = setup(theme, figsize=(10, 4.2), ncols=2)
    con = S.ddr5_sodimm_contract()
    q = np.log(con.resample("QS").mean()).diff().dropna()
    q = q[q.index >= "2025-07-01"]
    ax = axes[0]
    labels = [f"Q{(d.month - 1) // 3 + 1} {d:%y}" for d in q.index]
    vals = 100 * (np.exp(q.values) - 1)
    ax.bar(labels, vals, width=0.5, color=t["s"][0])
    for i, v in enumerate(vals):
        ax.text(i, v + 3, f"+{v:.0f}%", ha="center", fontsize=9, color=t["text"])
    ax.set_title("DDR5 contract price, change vs prior quarter")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_ylim(0, max(vals) * 1.18)

    ax = axes[1]
    nan = S.taiwan_revenue("Nanya Technology")
    mom = 100 * nan.pct_change()
    mom = mom[mom.index >= "2025-06-01"]
    xs = np.arange(len(mom))
    ax.bar(xs, mom.values, width=0.6, color=t["s"][2])
    ax.set_xticks(xs[::3], [f"{d:%b %y}" for d in mom.index[::3]])
    ax.set_title("Nanya (DRAM maker) revenue, change vs prior month")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    for i in (len(mom) - 1,):
        ax.text(i, max(mom.iloc[i], 0) + 1.2, f"{mom.iloc[i]:+.1f}%", ha="center", fontsize=8.5, color=t["text"])
    fig.tight_layout()
    save(fig, "momentum", theme)


def micron_margin(theme):
    fig, axes, t = setup(theme, figsize=(10, 4.2), ncols=2)
    pr = pd.read_csv(S.RAW / "micron_ir" / "press_release_results.csv")
    gm = pr[(pr.metric.isin(["gross_margin_pct"])) & (pr.basis == "GAAP")].copy()
    if gm.empty:
        rev = pr[(pr.metric == "revenue") & (pr.basis == "GAAP")].set_index("period").value
        gp = pr[(pr.metric == "gross_profit") & (pr.basis == "GAAP")].set_index("period").value
        gm = (100 * gp / rev).dropna().rename("value").reset_index()
        gm = gm.merge(pr[["period", "release_date"]].drop_duplicates("period"), on="period")
    gm["release_date"] = pd.to_datetime(gm.release_date)
    gm = gm.sort_values("release_date")
    ax = axes[0]
    ax.plot(gm.release_date, gm.value, color=t["s"][0])
    dot(ax, gm.release_date.iloc[-1], gm.value.iloc[-1], t["s"][0], t)
    end_label(ax, gm.release_date.iloc[-1], gm.value.iloc[-1], f"{gm.value.iloc[-1]:.0f}%", t, dx=-28, dy=8)
    ax.axhline(0, color=t["text2"], lw=0.8)
    ax.set_title("Micron gross margin by quarter (GAAP)")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))

    q = pd.read_csv(S.RAW / "sec_companyfacts" / "quarterly_financials.csv")
    q = q[(q.metric == "capex") & q.company.isin(["MSFT", "GOOGL", "AMZN", "META", "ORCL"])]
    q = q.sort_values("filed").drop_duplicates(["company", "calendar_quarter"], keep="last")
    cap = q.groupby("calendar_quarter").agg(v=("value", "sum"), n=("company", "nunique"))
    cap = cap[(cap.n == 5) & (cap.index >= "2019Q1")]
    x = pd.PeriodIndex(cap.index, freq="Q").to_timestamp()
    ax = axes[1]
    ax.bar(x, cap.v / 1e9, width=60, color=t["s"][1])
    end_label(ax, x[-1], cap.v.iloc[-1] / 1e9, f"${cap.v.iloc[-1] / 1e9:.0f}B", t, dx=-14, dy=10)
    ax.set_title("Capex, MSFT+GOOGL+AMZN+META+ORCL, per quarter")
    ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("${x:,.0f}B"))
    fig.tight_layout()
    save(fig, "margin-capex", theme)


def gpu_memory(theme):
    g = pd.read_csv(S.PROC / "gpu_memory_cost.csv")
    g = g.sort_values("change")
    fig, ax, t = setup(theme, figsize=(10, 4.6))
    y = np.arange(len(g))
    h = 0.32
    ax.barh(y + h / 2, g.change, height=h, color=t["s"][0], label="Deal price change")
    ax.barh(y - h / 2, g.memory_cost_change, height=h, color=t["s"][1], label="Memory cost change (GDDR6 spot)")
    for i, (c, m) in enumerate(zip(g.change, g.memory_cost_change)):
        ax.text(c + (25 if c >= 0 else -25), i + h / 2, f"{c:+,.0f}", va="center", ha="left" if c >= 0 else "right",
                fontsize=8.5, color=t["text"])
    ax.set_yticks(y, g.card)
    ax.axvline(0, color=t["text2"], lw=0.8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("${x:,.0f}"))
    ax.set_title("GPU deal prices, Apr-Aug 2025 to Jun-Oct 2026, vs added memory cost")
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(-250, 2200)
    save(fig, "gpu-memory", theme)


def aging(theme):
    n = pd.read_csv(S.PROC / "aging_now.csv")
    n = n[n.n >= 4].sort_values("vs_normal_pct")
    fig, ax, t = setup(theme, figsize=(10, 5))
    y = np.arange(len(n))
    colors = [t["s"][0] if k == "CPU" else t["s"][1] for k in n.kind]
    ax.barh(y, n.vs_normal_pct, height=0.55, color=colors)
    for i, v in enumerate(n.vs_normal_pct):
        ax.text(v + (3 if v >= 0 else -3), i, f"{v:+.0f}%", va="center", ha="left" if v >= 0 else "right",
                fontsize=8.5, color=t["text"])
    ax.set_yticks(y, [f"{m} ({k})" for m, k in zip(n.model, n.kind)])
    ax.axvline(0, color=t["text2"], lw=0.8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    ax.set_xlim(min(-45, n.vs_normal_pct.min() - 18), n.vs_normal_pct.max() + 22)
    ax.set_title("Deal price vs a normal product of the same age (Jun-Oct 2026)")
    handles = [matplotlib.patches.Patch(color=t["s"][0], label="CPU"), matplotlib.patches.Patch(color=t["s"][1], label="GPU")]
    ax.legend(handles=handles, loc="lower right", fontsize=9)
    save(fig, "aging", theme)


def ssd_outlook(theme):
    fig, ax, t = setup(theme, figsize=(10, 4.6))
    ssd = pd.read_csv(S.PROC / "ssd_forecast.csv").set_index("scenario")
    for i, name in enumerate(["990 Pro", "SN850X"]):
        s = S.basket(name)
        s = s[s.index >= "2023-01-01"]
        ax.plot(s.index, s.values, color=t["s"][i])
        end_label(ax, s.index[-1], s.iloc[-1], f"{'Samsung 990 Pro' if i == 0 else 'WD SN850X'} 2TB ${s.iloc[-1]:.0f}", t)
    pre = np.mean([S.basket(n)["2024-01-01":"2025-06-01"].mean() for n in ["990 Pro", "SN850X"]])
    ax.axhline(pre, color=t["text2"], lw=1)
    ax.text(pd.Timestamp("2026-01-20"), pre - 10, f"Normal: ${pre:.0f}\n(2024 to mid-2025 avg of both)", fontsize=9,
            color=t["text2"], va="top")
    ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("${x:,.0f}"))
    ax.set_xlim(pd.Timestamp("2023-01-01"), pd.Timestamp("2027-03-01"))
    ax.set_ylim(0, 560)
    ax.set_title("2TB NVMe SSD, lowest US retail price (PCPartPicker, archived)")
    save(fig, "ssd-prices", theme)


def perf_per_dollar(theme):
    d = pd.read_csv(S.RAW / "perf_crosswalk" / "perf_per_launch_dollar.csv", parse_dates=["release_date"])
    fig, axes, t = setup(theme, figsize=(10, 4.4), ncols=2)
    groups = {"CPU": [("AMD", "flagship"), ("Intel", "flagship")],
              "GPU": [("Nvidia", "x70"), ("Nvidia", "x80"), ("AMD", "top")]}
    for ax, (kind, tiers) in zip(axes, groups.items()):
        for i, (v, tier) in enumerate(tiers):
            x = d[(d.kind == kind.lower()) & (d.vendor == v) & (d.tier == tier)].sort_values("release_date")
            if x.empty:
                continue
            ax.plot(x.release_date, x.score_per_100usd, color=t["s"][i], marker="o", ms=5, mec=t["surface"], mew=1.5)
            lab = {"flagship": "flagship", "x70": "RTX xx70", "x80": "RTX xx80", "top": "top Radeon"}[tier]
            mdl = x.model.iloc[-1].replace("GeForce RTX ", "").replace("Radeon RX ", "")
            ax.lines[-1].set_label(f"{v} {lab} (latest: {mdl})")
        ax.legend(loc="upper left", fontsize=8.5)
        ax.set_title(f"{kind}: Blender score per $100 of launch price")
    fig.tight_layout()
    save(fig, "perf-per-dollar", theme)


def sentiment(theme):
    df = pd.read_csv(S.PROC / "sentiment_monthly.csv", parse_dates=["month"]).set_index("month")
    fig, axes, t = setup(theme, figsize=(10, 4.2), ncols=2)
    ax = axes[0]
    q = df["hn_ram_prices_per_100k"].resample("QS").mean().dropna()
    q = q[q.index >= "2015-01-01"]
    ax.bar(q.index, q.values, width=70, color=t["s"][0])
    for when in ["2018-01-01", q.idxmax()]:
        when = pd.Timestamp(when)
        ax.annotate(f"{q[when]:.1f} ({when:%Y} Q{(when.month - 1) // 3 + 1})", (when, q[when]), xytext=(0, 6),
                    textcoords="offset points", ha="center", fontsize=8.5, color=t["text"])
    ax.set_title('Hacker News comments with "RAM prices",\nper 100k items, quarterly')
    ax = axes[1]
    g = df["gt_ram_prices"].dropna()
    g = g[g.index >= "2024-01-01"]
    ax.plot(g.index, g.values, color=t["s"][1])
    dot(ax, g.idxmax(), g.max(), t["s"][1], t)
    end_label(ax, g.idxmax(), g.max(), f"peak {g.idxmax():%b %Y}", t, dx=8)
    dot(ax, g.index[-1], g.iloc[-1], t["s"][1], t)
    ax.set_title('Google searches for "RAM prices", US\n(0-100 relative scale)')
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    fig.tight_layout()
    save(fig, "sentiment", theme)


ALL = [ram_outlook, cycles_compared, momentum, micron_margin, gpu_memory, aging, ssd_outlook, perf_per_dollar,
       sentiment]


def main(only: list[str] | None = None):
    for fn in ALL:
        if only and fn.__name__ not in only:
            continue
        for theme in THEMES:
            fn(theme)
        print("chart:", fn.__name__)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:] or None)
