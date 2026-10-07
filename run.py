"""Rebuild everything.

  python run.py              analysis + charts from the data in data/raw (fast)
  python run.py --fetch      re-download every source first (slow: about an hour,
                             plus several hours if the UN Comtrade backfill is incomplete)
  python run.py --fetch official_fred,deals_buildapcsales   re-download only these sources
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# order matters only where a script reads another's output (perf_crosswalk reads perf_wikipedia + perf_blender)
FETCH = [
    "official_fred", "official_boj", "official_eurostat_comext", "official_wsts", "official_comtrade",
    "filings_sec_companyfacts", "filings_sec_segments", "filings_sec_validate", "filings_micron_ir",
    "filings_taiwan_monthly_revenue", "filings_skhynix", "filings_samsung",
    "retail_mccallum", "retail_owid", "retail_dramexchange", "retail_pcpartpicker_products",
    "deals_buildapcsales",
    "sentiment_wikipedia", "sentiment_hn", "sentiment_google_trends", "sentiment_gdelt", "sentiment_reddit",
    "perf_wikipedia", "perf_blender", "perf_crosswalk", "perf_manual",
]

ANALYSIS = ["parse_deals", "dram_index", "cycles", "forecast", "components", "sentiment", "charts"]


def run(path: Path) -> None:
    print(f"\n=== {path.relative_to(ROOT)}", flush=True)
    r = subprocess.run([sys.executable, str(path)], cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"failed: {path.name} (exit {r.returncode})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", nargs="?", const="all", default=None)
    args = ap.parse_args()
    if args.fetch:
        names = FETCH if args.fetch == "all" else args.fetch.split(",")
        for n in names:
            p = ROOT / "fetch" / f"{n}.py"
            if p.exists():
                run(p)
            else:
                print(f"skip: no fetch/{n}.py")
    for n in ANALYSIS:
        p = ROOT / "analysis" / f"{n}.py"
        if p.exists():
            run(p)


if __name__ == "__main__":
    main()
