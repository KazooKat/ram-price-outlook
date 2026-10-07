"""Blender Open Data benchmark scores (CPU and GPU), median per device.

Blender Open Data (opendata.blender.org) collects runs of the official Blender
Benchmark. Data is CC0. The site's query endpoint returns the median score and run
count per group; we group by device x compute backend x Blender version, which is
the same aggregation the site's own search page shows.

Score = estimated Cycles path-tracing samples per minute, summed over the benchmark
scenes. Scores are only comparable within one Blender version (scenes and the
renderer change between versions).

Output (data/raw/perf_blender/):
  blender_median_scores.csv  device_name, compute_type, blender_version, median_score, n_benchmarks
"""
from __future__ import annotations

import pandas as pd

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "perf_blender"
URL = "https://opendata.blender.org/benchmarks/query/"
PARAMS = [("group_by", "device_name"), ("group_by", "compute_type"),
          ("group_by", "blender_version"), ("response_type", "datatables")]


def main() -> None:
    out = raw_dir(SOURCE)
    j = get(URL, params=PARAMS).json()
    cols = [c["display_name"] for c in j["columns"]]
    expected = ["Device Name", "Compute Type", "Blender Version", "Median Score", "Number of Benchmarks"]
    if cols != expected:
        raise RuntimeError(f"Blender Open Data columns changed: {cols}")
    df = pd.DataFrame(j["rows"], columns=["device_name", "compute_type", "blender_version",
                                          "median_score", "n_benchmarks"])
    df["device_name"] = df["device_name"].str.strip()
    df = df[df["device_name"] != ""]  # a few runs report no device name
    ver = df["blender_version"].str.split(".", expand=True).astype(int)
    df = (df.assign(_a=ver[0], _b=ver[1], _c=ver[2])
            .sort_values(["_a", "_b", "_c", "compute_type", "device_name"])
            .drop(columns=["_a", "_b", "_c"]))
    df.to_csv(out / "blender_median_scores.csv", index=False)
    print(f"blender_median_scores.csv: {len(df)} rows, {df.device_name.nunique()} devices, "
          f"{df.n_benchmarks.sum()} runs, versions {df.blender_version.nunique()}")

    write_source_note(
        SOURCE,
        title="Blender Open Data benchmark medians (CPU and GPU)",
        urls=["https://opendata.blender.org/benchmarks/query/?group_by=device_name&group_by=compute_type"
              "&group_by=blender_version&response_type=datatables",
              "https://opendata.blender.org/about/",
              "https://opendata.blender.org/download/ (CC0 licence; full daily snapshot)"],
        notes="""
Score: "the estimated number of samples per minute, summed for all benchmark scenes"
(Cycles path tracing; opendata.blender.org/about). Higher is better.

- One row per device_name x compute_type (CPU, CUDA, OPTIX, HIP, ONEAPI, METAL)
  x blender_version, with the median over all user-submitted runs and the run count.
- Compare scores only within one blender_version. 4.5.0 has the most runs and covers
  RTX 50 / RX 9000; it is the suggested reference version.
- User-submitted runs: no control over clocks, cooling, OS or drivers. Prefer devices
  with n_benchmarks >= 5. Medians, not means, so single outliers don't dominate.
- GPU backends differ: OPTIX uses Nvidia RT cores, so RTX cards score far above GTX
  cards on OPTIX. This favours hardware ray tracing more than games do.
- CPU device names are as the OS reports them (e.g. "AMD Ryzen 9 7950X 16-Core
  Processor", "13th Gen Intel Core i9-13900K"); match to models with care.
- Rows with an empty device name are dropped.
""",
    )


if __name__ == "__main__":
    main()
