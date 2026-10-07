# Desktop CPU and GPU launch prices and specs (Wikipedia)

Fetched: 2026-10-06

Sources:
- https://en.wikipedia.org/w/index.php?title=List_of_AMD_Ryzen_processors&oldid=1376710910
- https://en.wikipedia.org/w/index.php?title=Comet_Lake&oldid=1370488598
- https://en.wikipedia.org/w/index.php?title=Rocket_Lake&oldid=1359904771
- https://en.wikipedia.org/w/index.php?title=Alder_Lake&oldid=1369487491
- https://en.wikipedia.org/w/index.php?title=Raptor_Lake&oldid=1376695055
- https://en.wikipedia.org/w/index.php?title=Arrow_Lake_(microprocessor)&oldid=1376121424
- https://en.wikipedia.org/w/index.php?title=List_of_Nvidia_graphics_processing_units&oldid=1377107724
- https://en.wikipedia.org/w/index.php?title=List_of_AMD_graphics_processing_units&oldid=1376670003

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
