"""Korea monthly semiconductor / memory export values (UN Comtrade, keyless preview API).

Korea is the largest memory exporter (Samsung, SK hynix), so HS 854232 (memory
ICs) export value is a monthly, customs-based proxy for memory revenue x price.

Output: data/raw/korea_exports/korea_exports_monthly.csv
"""
from __future__ import annotations

import datetime as dt
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import raw_dir, write_source_note  # noqa: E402

SOURCE = "korea_exports"
API = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
REPORTER = 410  # Republic of Korea
HS = {
    "854232": "Electronic integrated circuits: memories",
    "8542": "Electronic integrated circuits (all)",
    "852351": "Semiconductor media: solid-state non-volatile storage devices (SSD/flash cards)",
    "847330": "Parts and accessories of computers (HS 8471); includes memory modules",
}
START = (2015, 1)
PACE = 4.0  # seconds between calls; the keyless preview API rate-limits hard


def fetch_month(period: str) -> list[dict]:
    params = {"reporterCode": REPORTER, "period": period, "partnerCode": 0,
              "flowCode": "X", "cmdCode": ",".join(HS)}
    for attempt in range(10):
        try:
            r = requests.get(API, params=params, timeout=60,
                             headers={"User-Agent": "ram-price-outlook research"})
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
            continue
        body = r.text
        quota = re.search(r"replenished in (\d+):(\d+):(\d+)", body)
        if quota:  # keyless call-volume quota (403); wait for the window to reset
            h, m, sec = map(int, quota.groups())
            wait = h * 3600 + m * 60 + sec + 30
            print(f"  quota exhausted; sleeping {wait}s", flush=True)
            time.sleep(wait)
            continue
        if "Rate limit" in body or r.status_code == 429:
            m = re.search(r"Try again in (\d+) seconds", body)
            time.sleep((int(m.group(1)) if m else 5) + 2 + 5 * attempt)
            continue
        if r.status_code != 200:
            time.sleep(5 * (attempt + 1))
            continue
        js = r.json()
        if js.get("error"):
            raise RuntimeError(f"{period}: {js['error']}")
        return js.get("data") or []
    raise RuntimeError(f"Comtrade: gave up on {period} after retries")


def _row(y: int, m: int, period: str, d: dict) -> dict:
    return {
        "period": f"{y}-{m:02d}",
        "reporter": "Republic of Korea",
        "partner": "World",
        "flow": "export",
        "hs_code": d["cmdCode"],
        "hs_description": HS.get(d["cmdCode"], ""),
        "metric": "export_value_fob",
        "value": d["primaryValue"],
        "unit": "USD",
        "net_weight_kg": d.get("netWgt"),
        "hs_classification": d.get("classificationCode"),
        "source_url": f"{API}?reporterCode={REPORTER}&period={period}&partnerCode=0"
                      f"&flowCode=X&cmdCode={d['cmdCode']}",
    }


def main() -> None:
    out = raw_dir(SOURCE)
    path = out / "korea_exports_monthly.csv"
    write_source_note(
        SOURCE,
        title="Korea monthly IC / memory export values (UN Comtrade)",
        urls=[API, "https://comtradeplus.un.org/"],
        notes=f"""
UN Comtrade keyless "preview" endpoint, reporter 410 (Republic of Korea),
partner 0 (World), flow X (exports), monthly, HS classification as reported
(H5/H6 depending on year). Values are FOB USD as reported by Korea Customs to
the UN.

HS codes:
{chr(10).join(f'- {k}: {v}' for k, v in HS.items())}

Caveats:
- Comtrade monthly data lags several months; months not yet published are
  simply absent (re-run to extend).
- HS 854232 is the closest customs category to "memory chips" (DRAM, NAND,
  HBM die/stacks, MCPs). Memory modules usually fall under 847330 (mixed with
  other computer parts) and SSDs under 852351 - both are noisy proxies.
- Korea's own MOTIE/KITA "semiconductor" figures use MTI product codes, not HS,
  so they will not match these numbers exactly.
- The keyless preview API is rate-limited (~1 call / few seconds) AND has a
  call-volume quota (~40 calls, then a 403 with a reset timer of up to ~1h).
  The script paces, sleeps through quota resets, checkpoints after every month
  and on re-run only refetches the most recent 18 months. A full fresh-clone
  run (~135 months) therefore takes a few hours of mostly sleeping.
""",
    )
    today = dt.date.today()
    # Resume: keep months already on disk except the most recent 18, which Comtrade may revise.
    cutoff = str(pd.Period(today, freq="M") - 18)
    have = pd.read_csv(path, dtype={"hs_code": str}) if path.exists() else pd.DataFrame()
    kept = have[have["period"] < cutoff] if len(have) else have
    done = set(kept["period"]) if len(kept) else set()
    rows = kept.to_dict("records") if len(kept) else []
    empty_tail = 0
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    if len(have):
        # Comtrade lags several months; probing far past the newest month on disk wastes quota.
        latest = pd.Period(have["period"].max(), freq="M") + 4
        y, m = min((y, m), (latest.year, latest.month))
    while (y, m) >= START:
        period = f"{y}{m:02d}"
        if f"{y}-{m:02d}" not in done:
            data = fetch_month(period)
            time.sleep(PACE)
            rows += [_row(y, m, period, d) for d in data]
            if not data and not any(r["period"] > f"{y}-{m:02d}" for r in rows):
                empty_tail += 1  # still inside the publication lag
            print(f"{period}: {len(data)} rows", flush=True)
            # checkpoint so an interrupted run resumes where it stopped
            if rows:
                pd.DataFrame(rows).sort_values(["hs_code", "period"]).to_csv(path, index=False, encoding="utf-8")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)

    df = pd.DataFrame(rows).sort_values(["hs_code", "period"])
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"wrote {len(df)} rows -> {path}; "
          f"{empty_tail} most-recent months not yet published")



if __name__ == "__main__":
    main()
