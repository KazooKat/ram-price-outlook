"""Check the hand-entered tables in data/raw/perf_manual/ against their sources.

The CSVs in perf_manual/ are typed in by hand (one source_url per row) because the
facts live in press releases and spec pages, not in a downloadable dataset:
  msrp_crosscheck.csv       5+ launch MSRPs from Wikipedia vs manufacturer pages
  dram_generations.csv      JEDEC DRAM standards, speeds, module-capacity milestones
  pcie_ssd_generations.csv  PCIe spec releases, consumer NVMe SSD speed milestones
  announced_products.csv    officially announced next-gen products through 2027

This script never edits those files. It re-fetches every source_url and checks that
the row's verbatim_quote occurs in the page text, writing the result to
quote_check.csv. Pages that block scripted access are reported, not worked around.
"""
from __future__ import annotations

import io
import re
import time
import unicodedata

import pandas as pd
from lxml import html as lhtml

from fetch._common import get, raw_dir, write_source_note

SOURCE = "perf_manual"
TABLES = ["msrp_crosscheck.csv", "dram_generations.csv", "pcie_ssd_generations.csv",
          "announced_products.csv"]

# URLs that refuse scripted fetches but whose quotes were confirmed by reading the
# page with a separate fetch tool (date checked). Kept apart from quote_found.
MANUAL_CHECKS = {
    "https://www.sec.gov/Archives/edgar/data/0000723125/000072312526000013/a2026q3ex991-pressrelease.htm": "2026-10-06",
    "https://www.sec.gov/Archives/edgar/data/0000723125/000072312526000018/a2026q4ex991-pressrelease.htm": "2026-10-06",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.translate({ord(c): None for c in "®™©​‌­"})
    s = s.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"}))
    return re.sub(r"\s+", " ", s).strip().lower()


def page_text(url: str) -> tuple[str | None, str]:
    try:
        r = get(url, retries=2, backoff=5.0, timeout=45)
    except Exception as e:  # HTTP 4xx, timeouts, DNS: report, don't retry differently
        cause = e.__cause__ or e
        code = getattr(getattr(cause, "response", None), "status_code", None)
        return None, f"fetch_failed ({code or type(cause).__name__})"
    ctype = r.headers.get("content-type", "")
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        from pypdf import PdfReader
        text = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
    else:
        doc = lhtml.fromstring(r.content)
        for el in doc.xpath("//script|//style|//noscript"):
            el.drop_tree()
        text = doc.text_content()
    return norm(text), "ok"


def main() -> None:
    d = raw_dir(SOURCE)
    cache: dict[str, tuple[str | None, str]] = {}
    out = []
    for name in TABLES:
        df = pd.read_csv(d / name, dtype=str, keep_default_na=False)
        if (df["source_url"].str.strip() == "").any():
            raise RuntimeError(f"{name}: every row needs a source_url")
        for i, row in df.iterrows():
            url = row["source_url"].strip()
            if url not in cache:
                cache[url] = page_text(url)
                time.sleep(1.0)
            text, status = cache[url]
            quote = row.get("verbatim_quote", "")
            frags = [norm(f) for f in re.split(r"\.\.\.|…", quote) if norm(f)]
            if text is None:
                found = None
            else:
                found = all(f in text for f in frags) if frags else None
            label = next((row[c] for c in ("model", "product", "item") if c in row and row[c]), "")
            out.append(dict(table=name, row=i, label=label, source_url=url, fetch_status=status,
                            quote=quote, quote_found=found,
                            manual_check_date=MANUAL_CHECKS.get(url) if found is None else None))
    res = pd.DataFrame(out)
    res.to_csv(d / "quote_check.csv", index=False)
    summary = res.assign(q=res.quote_found.map({True: "found", False: "NOT_FOUND"}).fillna("unchecked"))
    print(summary.groupby(["table", "q"]).size().unstack(fill_value=0))

    write_source_note(
        SOURCE,
        title="Hand-entered spec, milestone and announcement tables (with source URL per row)",
        urls=sorted(res.source_url.unique()),
        notes="""
HAND-ENTERED. Rows were compiled from the linked pages (mostly manufacturer press
releases, JEDEC / PCI-SIG pages, investor releases). Each row has source_url and a
short verbatim_quote. quote_check.csv records whether a scripted fetch of the URL
found that quote (quote_found True / False / blank = page could not be fetched by
script: HTTP 403 or the server never answering a non-browser client). For unfetchable
rows, manual_check_date is set when the quote was confirmed with a separate fetch
tool; the rest (Samsung newsroom, amd.com blog/store) were read during compilation
but are NOT independently re-verified. The scripted fetch uses the project's own
User-Agent and does not impersonate a browser.

source_type flags secondary sources (secondary_news, news_report_of_official_keynote);
prefer the primary rows when they disagree.

announced_products.csv: official announcements only (company press release, keynote,
investor release, official blog). EXCLUDED as rumour/leak/unconfirmed (as of 2026-10-06):
- Nvidia RTX 50 Super / RTX 60 / consumer Rubin dates (no official consumer GPU announced)
- AMD RDNA 5 / UDNA Radeon timing (not officially dated)
- AMD Zen 6 desktop "Olympic Ridge" (Ryzen 10000) launch timing; Zen 6 mobile "Medusa" year
- EPYC Venice SP7 Q4-2026 / SP8 1H-2027 split and $700-$14,904 prices (press only)
- Intel Nova Lake core counts, LGA1954, DDR5-8000, "Q1 2027 retail" (leaks)
- Intel Razor Lake / Hammer Lake dates; Arc Celestial / Xe4 "Druid" claims
- Intel Diamond Rapids 192 cores / PCIe 6 (press reading of keynote)
- DDR6 timelines (no JEDEC or memory-maker date; JEDEC says only "in development")
- Samsung GDDR7 28/32/36 Gbps production bins (press only); SK hynix 48 Gbps GDDR7 (conference paper)
- TrendForce / analyst HBM ramp forecasts
""",
    )


if __name__ == "__main__":
    main()
