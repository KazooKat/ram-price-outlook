"""Monthly HS6 trade value and quantity for memory, processors, SSDs and computer parts
from the UN Comtrade keyless public preview API.

The US Census trade API now requires a key, so US imports come from Comtrade instead
(the US reports to Comtrade with Census-sourced value and item counts), split by the
main Asian origin partners. Korea, Japan and Malaysia exports (world partner) are
producer-side signals. Taiwan does not report to Comtrade; it appears only as a
partner ("Other Asia, nes", code 490).

The preview endpoint allows one period per call and rate-limits hard (HTTP 429, often
shared across users), so the script retries patiently, checkpoints to the CSV every
few periods, and is incremental: on a re-run it fetches only periods missing from the
CSV plus the most recent REFRESH_MONTHS periods (which get revised). Delete the CSV to
force a full pull (~650 calls). The preview also has a per-IP call-volume quota (403,
"replenished in HH:MM:SS"; observed: ~100 calls, then a wait of up to ~50 minutes); the
script sleeps through waits up to MAX_QUOTA_WAIT, so a full pull from scratch takes
~6-7 hours. USA and KOR are fetched first (newest period first), then JPN and MYS, so
an interrupted run still lands the most important series; re-running resumes. Recent
periods are re-fetched only when our copy is older than REFRESH_AFTER_DAYS.

Output (data/raw/official_comtrade/):
  comtrade_monthly.csv  date, reporter, flow, partner_code, partner, cmd_code, cmd_desc,
                        value_usd, qty, qty_unit, qty_estimated, net_weight_kg,
                        usd_per_unit, usd_per_kg
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
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "official_comtrade"
BASE = "https://comtradeapi.un.org/public/v1"
REF = "https://comtradeapi.un.org/files/v1/app/reference"
START = 201301
REFRESH_MONTHS = 12
REFRESH_AFTER_DAYS = 7     # re-fetch a recent period only if our copy is older than this
CHECKPOINT_EVERY = 10
MAX_QUOTA_WAIT = 65 * 60   # seconds; longer quota waits abort (progress is checkpointed)

# (reporter code, ISO3, flow, partner codes, priority); 0 = World. Lower priority value is
# fetched first (all its periods, newest first) because the call quota is tight.
US_PARTNERS = [0, 410, 490, 156, 458, 704, 392]   # World, KOR, TWN(490), CHN, MYS, VNM, JPN
REPORTERS = [
    (842, "USA", "M", US_PARTNERS, 1),
    (410, "KOR", "X", [0], 1),
    (392, "JPN", "X", [0], 2),
    (458, "MYS", "X", [0], 2),
]
CMD_CODES = ["854232", "854231", "852351", "847170", "847180", "847330"]

COLUMNS = ["date", "reporter", "flow", "partner_code", "partner", "cmd_code", "cmd_desc",
           "value_usd", "qty", "qty_unit", "qty_estimated", "net_weight_kg", "fetched_on"]


def _get_json(url: str, params: dict | None = None, tries: int = 20) -> dict:
    """Comtrade's preview 429s intermittently (short waits) and also enforces a per-IP
    call-volume quota (403 "Quota will be replenished in HH:MM:SS"). Wait out both."""
    for _ in range(tries):
        try:
            return get(url, params=params, retries=1, backoff=4.0).json()
        except RuntimeError:          # 429 / 5xx after get()'s own pause
            time.sleep(4)
        except requests.HTTPError as e:
            m = re.search(r"replenished in (\d+):(\d+):(\d+)", e.response.text)
            if e.response.status_code != 403 or not m:
                raise
            wait = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + 30
            if wait > MAX_QUOTA_WAIT:
                raise RuntimeError(f"Comtrade quota exhausted for {wait}s; re-run later") from e
            print(f"  quota exhausted, sleeping {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"Comtrade still rate-limited after {tries} tries: {url} {params}")


def _reference(name: str, key: str, val: str) -> dict:
    return {str(r[key]): r[val] for r in _get_json(f"{REF}/{name}.json")["results"]}


def _available_periods(reporter: int) -> list[int]:
    j = _get_json(f"{BASE}/getDA/C/M/HS", {"reporterCode": reporter})
    return sorted(int(d["period"]) for d in j.get("data") or [] if int(d["period"]) >= START)


def _fetch(reporter: int, flow: str, partners: list[int], period: int) -> list[dict]:
    j = _get_json(f"{BASE}/preview/C/M/HS", {
        "reporterCode": reporter, "period": period,
        "partnerCode": ",".join(map(str, partners)),
        "cmdCode": ",".join(CMD_CODES), "flowCode": flow})
    if j.get("error"):
        raise RuntimeError(f"Comtrade error {reporter} {period}: {j['error']}")
    if (j.get("count") or 0) >= 500:
        raise RuntimeError(f"Comtrade preview truncated at 500 rows: {reporter} {period}")
    # keep totals across all customs procedures, transport modes and second partners
    return [d for d in j.get("data") or []
            if d["partner2Code"] == 0 and d["customsCode"] == "C00" and d["motCode"] == 0]


def _period(date: pd.Series) -> pd.Series:
    return date.str.replace("-", "").str[:6].astype(int)


def _save(path, old: pd.DataFrame, rows: list[dict], done: set) -> pd.DataFrame:
    """Write old rows plus new rows; every (reporter, flow, period) re-fetched this run
    is replaced wholesale, so revised or withdrawn rows don't linger."""
    if not old.empty:
        key = zip(old["reporter"], old["flow"], _period(old["date"]))
        old = old[[k not in done for k in key]]
    new = pd.DataFrame(rows, columns=COLUMNS)
    df = pd.concat([f for f in (old, new) if not f.empty], ignore_index=True)
    valid_qty = (df["qty"] > 0) & (df["qty_unit"] == "u")
    df["usd_per_unit"] = (df["value_usd"] / df["qty"]).where(valid_qty)
    df["usd_per_kg"] = (df["value_usd"] / df["net_weight_kg"]).where(df["net_weight_kg"] > 0)
    df = df.sort_values(["reporter", "flow", "partner_code", "cmd_code", "date"]).reset_index(drop=True)
    df.to_csv(path, index=False)
    return df


def _write_note(hs: dict) -> None:
    write_source_note(
        SOURCE,
        title="UN Comtrade monthly HS6 trade: memory ICs, processors, SSD/storage, computer parts",
        urls=[f"{BASE}/preview/C/M/HS?reporterCode=<R>&period=<YYYYMM>&partnerCode=<P,...>"
              f"&cmdCode={','.join(CMD_CODES)}&flowCode=<M|X>",
              f"{BASE}/getDA/C/M/HS?reporterCode=<R>",
              f"{REF}/HS.json", f"{REF}/partnerAreas.json", f"{REF}/QuantityUnits.json"],
        notes=f"""
Keyless public preview API (one period per call, max 500 rows per call).
Reporters/flows: {'; '.join(f'{i} {"imports" if f == "M" else "exports"} (partners {p})' for _, i, f, p, _ in REPORTERS)}.
Partner 0 = World; 490 = "Other Asia, nes" (Taiwan in Comtrade).
HS6 codes: {'; '.join(hs.values())}.

Columns: value_usd = primaryValue (US imports: customs value; exports: FOB), qty in
qty_unit ('u' = number of items, 'kg', 'N/A'), net_weight_kg. usd_per_unit only where
qty_unit == 'u' and qty > 0; usd_per_kg where net weight > 0.

Caveats:
- Unit values are mix-sensitive proxies, not prices: one HS6 code spans cheap NOR flash
  to HBM stacks. Korea and Japan report weight, not item counts, so only $/kg exists there.
- qty = 0 with qty_unit 'N/A' means quantity not reported that month, not zero trade.
- Finished PC parts may sit outside 8542.32: memory modules can be classed as computer
  parts (8473.30) or as memories (the EU CN label for 8542.32.90 names "modules"), and
  graphics cards / SSDs as 8473.30 / 8471.70 / 8471.80 -- classification practice varies
  by country and was not verified here.
- US 854232 item counts have breaks (e.g. 2023-2024 counts several times higher than
  before/after, and qty missing in some months such as 2022 and 2026-07), so US memory
  usd_per_unit is not a consistent series; compare value_usd instead.
- Reporting lags differ (max date per reporter in the CSV); recent periods are revised,
  so the last {REFRESH_MONTHS} periods are re-fetched when older than {REFRESH_AFTER_DAYS} days.
- Coverage depends on how far a quota-limited run got: periods are filled newest-first,
  USA and KOR before JPN and MYS. Check min(date) per reporter; re-run to extend.
""",
    )



def main() -> None:
    out = raw_dir(SOURCE)
    path = out / "comtrade_monthly.csv"
    old = (pd.read_csv(path, dtype={"cmd_code": str})[COLUMNS] if path.exists()
           else pd.DataFrame(columns=COLUMNS))

    units = _reference("QuantityUnits", "qtyCode", "qtyAbbr")
    hs = {k: v for k, v in _reference("HS", "id", "text").items() if k in CMD_CODES}
    areas = _reference("partnerAreas", "id", "text")
    _write_note(hs)

    # Build the work list, newest periods first across all reporters, so an interrupted
    # (quota-limited) run still lands the recent window; older history fills in on re-runs.
    today = dt.date.today()
    stale_before = (today - dt.timedelta(days=REFRESH_AFTER_DAYS)).isoformat()
    tasks = []
    for code, iso, flow, partners, prio in REPORTERS:
        periods = _available_periods(code)
        mine = old[(old["reporter"] == iso) & (old["flow"] == flow)]
        fetched = mine.groupby(_period(mine["date"]))["fetched_on"].min().to_dict() if not mine.empty else {}
        missing = {p for p in periods if p not in fetched}
        stale = {p for p in periods[-REFRESH_MONTHS:] if p in fetched and fetched[p] < stale_before}
        todo = sorted(missing | stale)
        print(f"{iso} {flow}: {len(periods)} periods available "
              f"({periods[0] if periods else '-'}..{periods[-1] if periods else '-'}), "
              f"fetching {len(missing)} missing + {len(stale)} stale", flush=True)
        tasks += [(prio, p, code, iso, flow, partners) for p in todo]
        time.sleep(2)
    tasks.sort(key=lambda t: (t[0], -t[1]))

    rows, done = [], set()
    for i, (_, p, code, iso, flow, partners) in enumerate(tasks, 1):
        for d in _fetch(code, flow, partners, p):
            rows.append({
                "date": f"{p // 100}-{p % 100:02d}-01",
                "reporter": iso,
                "flow": flow,
                "partner_code": d["partnerCode"],
                "partner": areas.get(str(d["partnerCode"]), str(d["partnerCode"])),
                "cmd_code": d["cmdCode"],
                "cmd_desc": hs.get(d["cmdCode"], ""),
                "value_usd": d["primaryValue"],
                "qty": d["qty"],
                "qty_unit": units.get(str(d["qtyUnitCode"]), str(d["qtyUnitCode"])),
                "qty_estimated": d["isQtyEstimated"],
                "net_weight_kg": d["netWgt"],
                "fetched_on": today.isoformat(),
            })
        done.add((iso, flow, p))
        if i % CHECKPOINT_EVERY == 0:
            _save(path, old, rows, done)
            print(f"  {i}/{len(tasks)} done (last {iso} {p})", flush=True)
        time.sleep(2)

    df = _save(path, old, rows, done)
    print(f"wrote {len(df)} rows to {path}")


if __name__ == "__main__":
    main()
