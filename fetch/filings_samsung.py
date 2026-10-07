"""Samsung Electronics quarterly segment results (Memory / DS / total) from IR decks.

Source: Samsung Electronics IR "Earnings Release" page, which links one
English conference-call deck (PDF) per quarter. Each deck has a segment table
("Segment Sales & Operating Profit" / "Results by Business Segment") giving
sales by division for the current quarter, prior quarter and year-ago quarter.
DART is not used (needs an API key).

Outputs (data/raw/samsung_results/):
- segment_observations.csv  every (deck, column) value parsed - restatement audit
- quarterly_segments.csv    one value per (period, metric): taken from that
                            quarter's own deck (as first reported)
"""
from __future__ import annotations

import io
import re
import sys
import time
from pathlib import Path

import pandas as pd
import pypdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "samsung_results"
IR_PAGE = "https://www.samsung.com/global/ir/financial-information/earnings-release/"
UA = {"User-Agent": "Mozilla/5.0 (ram-price-outlook research)"}
MIN_YEAR = 2014

QLABEL = re.compile(r"(?:([1-4])Q|Q([1-4]))\s?[’'`]?\s?(\d{2})(?!\d)")
HEADER_TOKEN = re.compile(r"(?:[1-4]Q|Q[1-4])\s?[’'`]?\s?\d{2}(?!\d)|QoQ|YoY|\b20\d\d\b")
VALUE_TOKEN = re.compile(r"[△(]?-?\d[\d,]*\.?\d*\)?(?:%)?[↑↓]?")
ROWS = {  # metric label in the deck -> our metric stem
    "Memory": "memory",
    "DS": "ds",
    "Semiconductor": "semiconductor",
    "Total": "total",
}


def deck_urls() -> list[str]:
    page = get(IR_PAGE, headers=UA).text
    urls = sorted(set(re.findall(r'href="(//images\.samsung\.com[^"]+\.pdf)"', page)))
    return ["https:" + u for u in urls]


def deck_quarter(url: str) -> tuple[int, int] | None:
    name = url.rsplit("/", 1)[-1]
    m = re.match(r"(\d{4})_([1-4])Q_", name)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d{4})(\d{2})\d{2}_conference", name)  # dated by call date -> previous quarter
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        q = (mo - 1) // 3  # Jan-Mar call reports Q4 of prior year
        return (y - 1, 4) if q == 0 else (y, q)
    return None


def _num(tok: str) -> float | None:
    if "%" in tok or "↑" in tok or "↓" in tok:
        return None  # change columns
    neg = tok.startswith(("△", "(")) or tok.startswith("-")
    t = tok.strip("△()-").replace(",", "")
    try:
        return -float(t) if neg else float(t)
    except ValueError:
        return None


def parse_deck(text_pages: list[str]) -> list[dict]:
    """Find header lines with >=2 quarter labels; map following rows' tokens onto header columns."""
    obs = []
    for pno, text in enumerate(text_pages):
        lines = [ln.strip() for ln in text.split("\n")]
        header = None
        block_has_memory = False
        block_rows: list[tuple[str, list[str], str]] = []

        def flush():
            if header is None:
                return
            table = "sales" if block_has_memory else "operating_profit"
            for label, toks, raw in block_rows:
                if len(toks) != len(header):
                    continue
                for col, tok in zip(header, toks):
                    lab = QLABEL.fullmatch(col.replace(" ", "")) or QLABEL.fullmatch(col)
                    if not lab:
                        continue
                    v = _num(tok)
                    if v is None:
                        continue
                    q = int(lab.group(1) or lab.group(2))
                    obs.append({"period": f"20{lab.group(3)}Q{q}", "metric": f"{ROWS[label]}_{table}",
                                "value": v, "page": pno + 1, "row_text": raw})

        for ln in lines:
            toks = HEADER_TOKEN.findall(ln)
            if sum(1 for t in toks if QLABEL.search(t)) >= 2 and not VALUE_TOKEN.fullmatch(ln.split()[0] if ln.split() else ""):
                flush()
                header, block_has_memory, block_rows = toks, False, []
                continue
            if header is None:
                continue
            m = re.match(r"^[-–\s]*(Memory|DS|Semiconductor|Total)\s+(.*)$", ln)
            if m:
                vals = m.group(2).split()
                if vals and all(VALUE_TOKEN.fullmatch(v) for v in vals):
                    block_rows.append((m.group(1), vals, ln))
                    block_has_memory |= m.group(1) == "Memory"
                continue
            # 2016-2022 decks print the company total as an unlabeled numeric row right under the header
            vals = ln.split()
            if vals and all(VALUE_TOKEN.fullmatch(v) for v in vals) and not block_rows and len(vals) == len(header):
                block_rows.append(("Total", vals, ln))
        flush()
    # Keep only the segment table page: the first page with a parsed Memory sales row.
    seg_pages = sorted({o["page"] for o in obs if o["metric"] == "memory_sales"})
    if not seg_pages:
        return []
    return [o for o in obs if o["page"] == seg_pages[0]]


def main() -> None:
    out = raw_dir(SOURCE)
    all_obs = []
    for url in deck_urls():
        dq = deck_quarter(url)
        if dq is None or dq[0] < MIN_YEAR:
            continue
        pdf = pypdf.PdfReader(io.BytesIO(get(url, headers=UA).content))
        pages = [(p.extract_text() or "") for p in pdf.pages]
        obs = parse_deck(pages)
        for o in obs:
            o.update({"deck_quarter": f"{dq[0]}Q{dq[1]}", "source_url": url})
        all_obs += obs
        print(f"{dq[0]}Q{dq[1]}: {len(obs)} observations", flush=True)
        time.sleep(0.5)

    obs = pd.DataFrame(all_obs)
    obs["company"] = "Samsung Electronics"
    obs["unit"] = "KRW trillion"
    # The same (deck, period, metric) can appear twice when a deck repeats a table; keep the first.
    obs = obs.drop_duplicates(["deck_quarter", "period", "metric"], keep="first")
    obs.to_csv(out / "segment_observations.csv", index=False, encoding="utf-8")

    obs["deck_order"] = obs["deck_quarter"].map(lambda q: pd.Period(q).ordinal)
    obs["period_order"] = obs["period"].map(lambda q: pd.Period(q).ordinal)
    obs = obs[obs["deck_order"] >= obs["period_order"]]
    # As first reported: the quarter's own deck; if that deck's table could not be parsed
    # (e.g. Q4 decks whose row labels are detached from the numbers), the next deck that reprints it.
    best = (obs.sort_values(["period", "metric", "deck_order"])
            .drop_duplicates(["period", "metric"], keep="first").copy())
    best["as_first_reported"] = best["deck_quarter"] == best["period"]
    stats = (obs.merge(best[["period", "metric", "value"]], on=["period", "metric"], suffixes=("_other", ""))
             .assign(d=lambda x: (x["value_other"] - x["value"]).abs())
             .groupby(["period", "metric"])
             .agg(n_decks=("d", "size"), max_abs_diff_across_decks=("d", "max")))
    own = best.merge(stats, on=["period", "metric"], how="left")
    own["period_end"] = own["period"].map(lambda p: pd.Period(p).end_time.date().isoformat())
    own = own.rename(columns={"deck_quarter": "reported_in_deck"})
    cols = ["period", "period_end", "company", "metric", "value", "unit", "reported_in_deck",
            "as_first_reported", "n_decks", "max_abs_diff_across_decks", "row_text", "page", "source_url"]
    own = own[cols].sort_values(["metric", "period"])
    own.to_csv(out / "quarterly_segments.csv", index=False, encoding="utf-8")
    print(f"wrote {len(own)} rows -> {out / 'quarterly_segments.csv'} ({len(obs)} observations)")

    write_source_note(
        SOURCE,
        title="Samsung Electronics quarterly segment sales / operating profit (IR decks)",
        urls=[IR_PAGE, "https://images.samsung.com/is/content/samsung/assets/global/ir/docs/<YYYY>_<Q>Q_conference_eng.pdf"],
        notes="""
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
""",
    )


if __name__ == "__main__":
    main()
