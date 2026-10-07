"""Launch prices and specs for desktop CPUs and GPUs, from Wikipedia list tables.

Wikipedia is a secondary source: the tables cite manufacturer pages, but the
values are community-edited. Every row keeps the raw cell text next to the
parsed number, plus the page revision it came from, so a value can be traced
and re-checked. Launch MSRPs are cross-checked against manufacturer press
releases in perf_manual/msrp_crosscheck.csv.

Output (data/raw/perf_wikipedia/):
  cpu_desktop.csv  AMD Ryzen 3000-9000 (Zen 2-5), Intel Core 10th gen - Core Ultra 200S
  gpu_desktop.csv  Nvidia GeForce 10 - RTX 50, AMD Radeon RX 5000 - RX 9000
"""
from __future__ import annotations

import io
import re
import time

import pandas as pd
from lxml import html as lhtml

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from fetch._common import get, raw_dir, write_source_note  # noqa: E402

SOURCE = "perf_wikipedia"
API = "https://en.wikipedia.org/w/api.php"

# (page, section regex, family label, vendor, kind)
# Sections are matched against the "h2 > h3 > h4" heading path above each table.
SECTIONS = [
    ("List of AMD Ryzen processors", r"> Matisse \(3000 series", "Ryzen 3000 (Zen 2)", "AMD", "cpu"),
    ("List of AMD Ryzen processors", r"> Vermeer \(5000 series", "Ryzen 5000 (Zen 3)", "AMD", "cpu"),
    ("List of AMD Ryzen processors", r"> Raphael \(7000 series", "Ryzen 7000 (Zen 4)", "AMD", "cpu"),
    ("List of AMD Ryzen processors", r"> Granite Ridge \(9000 series", "Ryzen 9000 (Zen 5)", "AMD", "cpu"),
    ("Comet Lake", r"Comet Lake processors > Desktop > Comet Lake-S$", "Core 10th gen (Comet Lake)", "Intel", "cpu"),
    ("Rocket Lake", r"Rocket Lake-S \(Desktop", "Core 11th gen (Rocket Lake)", "Intel", "cpu"),
    ("Alder Lake", r"Desktop processors \(Alder Lake-S\)", "Core 12th gen (Alder Lake)", "Intel", "cpu"),
    ("Raptor Lake", r"13th-generation .* > Raptor Lake-S$", "Core 13th gen (Raptor Lake)", "Intel", "cpu"),
    ("Raptor Lake", r"14th-generation .* > Raptor Lake-S Refresh$", "Core 14th gen (Raptor Lake Refresh)", "Intel", "cpu"),
    ("Arrow Lake (microprocessor)", r"^List of Arrow Lake processors > Desktop > Arrow Lake-S$", "Core Ultra 200S (Arrow Lake)", "Intel", "cpu"),
    ("Arrow Lake (microprocessor)", r"^List of Arrow Lake Refresh processors > Desktop", "Core Ultra 200S Plus (Arrow Lake Refresh)", "Intel", "cpu"),
    ("List of Nvidia graphics processing units", r"^Desktop GPUs > GeForce 10 series$", "GeForce 10 (Pascal)", "Nvidia", "gpu"),
    ("List of Nvidia graphics processing units", r"^Desktop GPUs > GeForce GTX 16 series$", "GeForce 16 (Turing)", "Nvidia", "gpu"),
    ("List of Nvidia graphics processing units", r"^Desktop GPUs > GeForce RTX 20 series$", "GeForce RTX 20 (Turing)", "Nvidia", "gpu"),
    ("List of Nvidia graphics processing units", r"^Desktop GPUs > GeForce RTX 30 series$", "GeForce RTX 30 (Ampere)", "Nvidia", "gpu"),
    ("List of Nvidia graphics processing units", r"^Desktop GPUs > GeForce RTX 40 series$", "GeForce RTX 40 (Ada Lovelace)", "Nvidia", "gpu"),
    ("List of Nvidia graphics processing units", r"^Desktop GPUs > GeForce RTX 50 series$", "GeForce RTX 50 (Blackwell)", "Nvidia", "gpu"),
    ("List of AMD graphics processing units", r"^Desktop GPUs > Radeon RX 5000 series$", "Radeon RX 5000 (RDNA)", "AMD", "gpu"),
    ("List of AMD graphics processing units", r"^Desktop GPUs > Radeon RX 6000 series$", "Radeon RX 6000 (RDNA 2)", "AMD", "gpu"),
    ("List of AMD graphics processing units", r"^Desktop GPUs > Radeon RX 7000 series$", "Radeon RX 7000 (RDNA 3)", "AMD", "gpu"),
    ("List of AMD graphics processing units", r"^Desktop GPUs > Radeon RX 9000 series$", "Radeon RX 9000 (RDNA 4)", "AMD", "gpu"),
]

# Some Intel tables have no release-date column. For those, the desktop family's
# launch date is read from the page's own prose with these patterns, never typed in.
FAMILY_DATE_TEXT = {
    "Core 10th gen (Comet Lake)": r"desktop Comet Lake-S CPUs on ([A-Z][a-z]+ \d{1,2}, \d{4})",
    "Core 11th gen (Rocket Lake)": r"launched the Rocket Lake desktop family on ([A-Z][a-z]+ \d{1,2}, \d{4})",
    "Core 12th gen (Alder Lake)": r"It was launched on ([A-Z][a-z]+ \d{1,2}, \d{4})",
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
NA_RE = re.compile(r"^\s*(—\s*)?(n/?a|tba|tbd|\?|—|-|–|unknown)?\s*$", re.I)


# ---------- fetching and table extraction ----------

def fetch_page(title: str) -> tuple[str, int]:
    # Wikimedia rate-limits per User-Agent (Retry-After ~25 s); back off well past that.
    r = get(API, params=dict(action="parse", page=title, prop="text|revid", format="json",
                             formatversion=2, redirects=1), retries=6, backoff=15.0)
    p = r.json()["parse"]
    return p["text"], p["revid"]


def clean_doc(text: str):
    doc = lhtml.fromstring(text)
    # footnote markers, hidden sort keys and inline CSS would leak into cell text
    for el in doc.xpath('//sup[contains(@class,"reference")]|//*[contains(@style,"display:none")]|//style'):
        el.drop_tree()
    for br in doc.xpath("//br"):
        br.tail = " / " + (br.tail or "")
    return doc


def iter_tables(doc):
    """Yield (heading path, table element) for every wikitable."""
    path = ["", "", ""]
    for el in doc.iter():
        if el.tag in ("h2", "h3", "h4"):
            lvl = int(el.tag[1]) - 2
            path[lvl] = el.text_content().strip()
            path[lvl + 1:] = [""] * (2 - lvl)
        elif el.tag == "table" and "wikitable" in (el.get("class") or ""):
            yield " > ".join(p for p in path if p), el


def read_table(el) -> pd.DataFrame:
    t = pd.read_html(io.StringIO(lhtml.tostring(el, encoding="unicode")))[0]
    cols = []
    for c in t.columns:
        parts = c if isinstance(c, tuple) else (c,)
        parts = [str(p) for p in parts if not str(p).startswith("Unnamed:")]
        cols.append(norm_header(" | ".join(dict.fromkeys(parts))))
    t.columns = cols
    # repeated header rows inside the body (pandas keeps them as data)
    first = t.columns[0]
    t = t[t[first].astype(str).map(norm_header) != first]
    return t.astype(object).where(t.notna(), None)


def norm_header(s: str) -> str:
    s = str(s).replace("\xa0", " ")
    s = re.sub(r"(^|\s)/(?=\s|$)", " ", s)  # lone "/" from a <br> inside a header cell
    s = re.sub(r"\[[a-z0-9]+\]", "", s)  # leftover footnote letters like [a], [ii]
    s = re.sub(r"\s+", " ", s).strip(" |")
    return re.sub(r"\s*\|\s*$", "", s).lower()


# ---------- cell parsers ----------

def txt(v) -> str | None:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip()
    return None if NA_RE.match(s) or s.lower() == "nan" else s


def name(v) -> str | None:
    """Model/brand cell; a <br> inside a name is a line wrap, not a separator."""
    s = txt(v)
    return re.sub(r"\s+", " ", s.replace(" / ", " ")).strip(" /") if s else None


def nums(s: str | None) -> list[float]:
    if not s:
        return []
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", s)]


def first_num(s):
    n = nums(s)
    return n[0] if n else None


def max_num(s):
    n = nums(s)
    return max(n) if n else None


def price(s: str | None) -> float | None:
    if not s:
        return None
    if re.search(r"\bonly\b|exclusive", s, re.I):
        return None  # region-limited price (e.g. "$130-$150 (Europe Only)"), not a US launch MSRP
    m = re.search(r"\$\s?(\d[\d,]*(?:\.\d+)?)", s)
    if m:
        return float(m.group(1).replace(",", ""))
    m = re.fullmatch(r"(?:US)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:USD)?", s.strip())
    return float(m.group(1).replace(",", "")) if m else None


def parse_date(s: str | None) -> tuple[str | None, str | None]:
    """First date in the cell -> (ISO date, precision)."""
    if not s:
        return None, None
    s = s.replace(" / ", " ")  # "October<br>12, 2022"
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1)[:3].lower()]:02d}-{int(m.group(2)):02d}", "day"
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        return m.group(0), "day"
    m = re.search(r"\b([A-Za-z]{3,9})\.?,?\s+(\d{4})", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        return f"{m.group(2)}-{MONTHS[m.group(1)[:3].lower()]:02d}-01", "month"
    m = re.search(r"\b(?:Q([1-4])|([12])H)\s*(\d{4})", s)
    if m:
        month = (int(m.group(1)) - 1) * 3 + 1 if m.group(1) else (1 if m.group(2) == "1" else 7)
        return f"{m.group(3)}-{month:02d}-01", "quarter" if m.group(1) else "half"
    m = re.search(r"\b(20\d{2}|19\d{2})\b", s)
    if m:
        return f"{m.group(1)}-01-01", "year"
    return None, None


def cores_threads(s):
    """'8 (16)' -> (8, 16)."""
    n = nums(s)
    if not n:
        return None, None
    return n[0], (n[1] if len(n) > 1 else n[0])


def pick(cols, *include, exclude=()):
    """Columns whose header matches every include regex and no exclude regex."""
    return [c for c in cols if all(re.search(p, c) for p in include)
            and not any(re.search(p, c) for p in exclude)]


# ---------- per-kind row builders ----------

def cpu_rows(t: pd.DataFrame) -> list[dict]:
    cols = list(t.columns)
    model_c = (pick(cols, r"^(model|sku)$") or pick(cols, r"branding and model.*\.1$")
               or pick(cols, r"^model"))[0]
    brand_c = (pick(cols, r"^(processor )?branding( and model)?$") or [None])[0]
    total_c = pick(cols, r"cores.*threads", r"total") or pick(cols, r"cores.*threads", exclude=[r"\| e$", r"\| p$"])
    p_c, e_c = pick(cols, r"cores.*threads", r"\| p$"), pick(cols, r"cores.*threads", r"\| e$")
    base_c = pick(cols, r"base", r"clock|ghz", exclude=[r"\| e$", r"\| e \|", r"lp-e", r"gpu|graphics", r"power|tdp"])
    boost_c = pick(cols, r"boost|turbo", exclude=[r"\| e$", r"all-core", r"lp-e", r"gpu|graphics", r"power|tdp"])
    l3_c = pick(cols, r"l3|smart cache")
    tdp_c = pick(cols, r"tdp|power", exclude=[r"turbo", r"down", r"up$", r"pl2"])
    date_c = pick(cols, r"release|launch", exclude=[r"price|msrp"])
    price_c = pick(cols, r"price|msrp")
    out = []
    for _, r in t.iterrows():
        model = name(r[model_c])
        if not model:
            continue
        if p_c:
            pc, pt = cores_threads(txt(r[p_c[0]]))
            ec, et = cores_threads(txt(r[e_c[0]])) if e_c else (None, None)
            cores = (pc or 0) + (ec or 0) or None
            threads = (pt or 0) + (et or 0) or None
        else:
            cores, threads = cores_threads(txt(r[total_c[0]])) if total_c else (None, None)
            pc = ec = None
        date_raw = txt(r[date_c[0]]) if date_c else None
        price_raw = txt(r[price_c[0]]) if price_c else None
        d, prec = parse_date(date_raw)
        boosts = [max_num(txt(r[c])) for c in boost_c]
        boosts = [b for b in boosts if b is not None and b < 10]  # GHz sanity
        out.append(dict(
            brand=name(r[brand_c]) if brand_c else None,
            model=model,
            cores=cores, threads=threads, p_cores=pc, e_cores=ec,
            base_ghz=first_num(txt(r[base_c[0]])) if base_c else None,
            boost_ghz=max(boosts) if boosts else None,
            l3_mb=first_num(txt(r[l3_c[0]])) if l3_c else None,
            tdp_w=first_num(txt(r[tdp_c[0]])) if tdp_c else None,
            release_date=d, release_date_precision=prec, release_raw=date_raw,
            launch_price_usd=price(price_raw), price_raw=price_raw,
        ))
    return out


def gpu_rows(t: pd.DataFrame) -> list[dict]:
    cols = list(t.columns)
    model_c = pick(cols, r"^model")[0]
    date_c = pick(cols, r"launch|release")
    msrp_c = pick(cols, r"price", r"msrp")
    fe_c = pick(cols, r"price", r"founders")
    combined_price = not msrp_c and bool(pick(cols, r"release.*price"))
    fp32_c = pick(cols, r"single")
    clock_c = pick(cols, r"clock", r"boost|core", exclude=[r"memory"])
    size_c = pick(cols, r"^memory", r"size")
    type_c = pick(cols, r"^memory", r"dram type|bus type")
    width_c = pick(cols, r"^memory", r"(?<!band)width")
    bw_c = pick(cols, r"^memory", r"bandwidth")
    tdp_c = pick(cols, r"^(tdp|tbp)")
    out = []
    for _, r in t.iterrows():
        model = name(r[model_c])
        if not model:
            continue
        date_raw = txt(r[date_c[0]]) if date_c else None
        d, prec = parse_date(date_raw)
        if combined_price:
            price_raw = date_raw
            msrp = price(date_raw)
            fe = None
        else:
            price_raw = txt(r[msrp_c[0]]) if msrp_c else None
            msrp = price(price_raw)
            fe = price(txt(r[fe_c[0]])) if fe_c else None
        fp32 = max_num(txt(r[fp32_c[0]])) if fp32_c else None
        if fp32 is not None and "tflops" in fp32_c[0]:
            fp32 *= 1000.0
        mtype = txt(r[type_c[0]]) if type_c else None
        bw = first_num(txt(r[bw_c[0]])) if bw_c else None
        if d is None and fp32 is None and bw is None:
            continue  # spill-over row (e.g. a wrapped "architecture & fab" cell), not a model
        out.append(dict(
            model=re.sub(r"\s*\(([^)]*)\)\s*$", "", model).strip(),
            code_name=(re.search(r"\(([^)]*)\)\s*$", model) or [None, None])[1],
            release_date=d, release_date_precision=prec, release_raw=date_raw,
            launch_msrp_usd=msrp, founders_edition_usd=fe,
            launch_price_usd=msrp if msrp is not None else fe,
            price_raw=price_raw,
            fp32_gflops_boost=fp32,
            boost_clock_mhz=max_num(txt(r[clock_c[0]])) if clock_c else None,
            mem_size_gb=first_num(txt(r[size_c[0]])) if size_c else None,
            mem_type=(re.search(r"(G?DDR\d\w*|HBM\d?\w*)", mtype or "", re.I) or [None])[0],
            mem_bus_bits=(first_num(txt(r[width_c[0]])) if width_c and "type" not in width_c[0]
                          else first_num(re.sub(r"G?DDR\d\w*", "", mtype or "")) if mtype else None),
            mem_bandwidth_gbs=bw,
            board_power_w=first_num(txt(r[tdp_c[0]])) if tdp_c else None,
        ))
    return out


# ---------- main ----------

def main() -> None:
    out_dir = raw_dir(SOURCE)
    pages = list(dict.fromkeys(s[0] for s in SECTIONS))
    rows = {"cpu": [], "gpu": []}
    revs = {}
    for page in pages:
        text, rev = fetch_page(page)
        revs[page] = rev
        time.sleep(5.0)
        doc = clean_doc(text)
        specs = [s for s in SECTIONS if s[0] == page]
        hit = {s[1]: 0 for s in specs}
        prose = re.sub(r"\s+", " ", doc.text_content())
        for path, el in iter_tables(doc):
            for _, pat, family, vendor, kind in specs:
                if not re.search(pat, path):
                    continue
                hit[pat] += 1
                t = read_table(el)
                built = cpu_rows(t) if kind == "cpu" else gpu_rows(t)
                url = f"https://en.wikipedia.org/w/index.php?title={page.replace(' ', '_')}&oldid={rev}"
                fam_date = fam_raw = None
                if family in FAMILY_DATE_TEXT:
                    m = re.search(FAMILY_DATE_TEXT[family], prose)
                    if not m:
                        raise RuntimeError(f"{family}: launch-date sentence not found on {page}")
                    fam_raw, fam_date = m.group(0), parse_date(m.group(1))[0]
                for b in built:
                    b["release_date_basis"] = "table" if b["release_date"] else None
                    if b["release_date"] is None and fam_date:
                        b.update(release_date=fam_date, release_date_precision="day",
                                 release_raw=f"family launch, page text: '{fam_raw}'",
                                 release_date_basis="page_text_family")
                    rows[kind].append(dict(vendor=vendor, family=family, **b,
                                           wiki_page=page, wiki_section=path, wiki_revid=rev, source_url=url))
        missing = [p for p, n in hit.items() if n == 0]
        if missing:
            raise RuntimeError(f"{page}: no table under sections {missing} (page layout changed?)")
        print(f"{page}: rev {rev}, sections {hit}")

    for kind, name in (("cpu", "cpu_desktop.csv"), ("gpu", "gpu_desktop.csv")):
        df = pd.DataFrame(rows[kind]).drop_duplicates()
        df.to_csv(out_dir / name, index=False)
        print(f"{name}: {len(df)} rows, {df['launch_price_usd'].notna().sum()} with launch price")

    write_source_note(
        SOURCE,
        title="Desktop CPU and GPU launch prices and specs (Wikipedia)",
        urls=[f"https://en.wikipedia.org/w/index.php?title={p.replace(' ', '_')}&oldid={r}"
              for p, r in revs.items()],
        notes="""
Secondary source (community-edited tables that cite vendor pages). Pulled via the
MediaWiki parse API; each row records the page revision (wiki_revid) and section.

Parsing rules:
- Footnote markers and hidden sort keys are stripped; `<br>` becomes " / ".
- *_raw columns hold the original cell text; parsed numbers are blank when the cell
  is N/a, TBA, "?" or OEM-only (no $ amount).
- launch_price_usd: first "$" amount in the cell. For Nvidia it is the MSRP column,
  falling back to the Founders Edition price when MSRP is blank. Intel prices are
  Intel's recommended customer price (tray, 1k units), not a retail MSRP.
- GPU fp32_gflops_boost: theoretical FP32 throughput at boost clock (largest value in
  the cell). Not comparable across architectures one-to-one (e.g. Ampere dual-issue FP32).
- CPU cores/threads for Intel hybrid parts = P + E cores; boost_ghz = highest P-core
  turbo (incl. Turbo Boost Max 3.0 / TVB).
- release_date is the first date in the cell; release_date_precision says whether it
  is a day, month, quarter, half or year. Intel 10th-12th gen tables have no date
  column; there it is the desktop family launch date quoted from the same page's prose
  (release_date_basis = page_text_family; for Comet Lake-S that is the announcement date).
Prices are nominal USD, not inflation-adjusted.
""",
    )


if __name__ == "__main__":
    main()
