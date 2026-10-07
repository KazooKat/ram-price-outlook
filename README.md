# When will RAM prices return to normal?

An analysis of when RAM, SSD, GPU and CPU prices return to where they were before the AI-driven memory shortage, and what changes in price and performance a PC buyer should expect.

Data runs through September 2026 (some series through early October). Every number here is computed in this repo from free public data: government price indices, company filings, archived retail prices and public market data. Outside forecasts appear only in [one section](#outside-forecasts-and-whether-they-hold), where I check them against these results.

Numbers are marked **measured** (read from a source) or **modeled** (output of the forecast).

## The answer

"Normal" means the average price from January 2024 to June 2025, the 18 months before the spike. RAM didn't get more expensive because of AI until mid-2025. It hit a record low in 2023, months after ChatGPT launched.

| Component | Now vs normal (measured) | Back to normal, base case (modeled) | Range, fast to slow (modeled) |
|---|---|---|---|
| RAM, 32GB DDR5-6000 kit | $540 vs $111 (4.9x) | Dec 2030 | Aug 2029 to Jul 2031 |
| RAM, back to the late-2022 price ($239, Oct-Dec 2022 avg) | 2.3x | Jun 2029 | Aug 2028 to Jan 2030 |
| SSD, 2TB NVMe | 2.4x | Sep 2029 | Sep 2028 to Jun 2030 |
| GPU | +40% vs a normal card of the same age | follows RAM; see [GPUs](#gpus-and-cpus) | |
| CPU | +2% on average; Ryzen X3D chips +30% to +42% | close to normal now | |

The base case has retail RAM prices peaking around February 2027 at about $625 for a 32GB kit, staying near that level through most of 2027, then falling. It reaches twice the normal price around August 2029.

The fastest plausible case, a sudden demand drop such as cuts to AI spending, gets RAM back to normal around December 2028. Even at the fastest decline seen since 2003, prices can't get back to normal before mid-2028.

![RAM outlook](charts/ram-outlook-light.png#gh-light-mode-only)
![RAM outlook](charts/ram-outlook-dark.png#gh-dark-mode-only)

## Buy now or wait

- **RAM.** Prices will probably be higher in early 2027 than today, so waiting a few months doesn't help. If you need a PC now, buy the capacity you need (32GB rather than 64GB) and upgrade later. Prices are unlikely to fall below twice normal before 2029.
- **DDR4.** If you're building on an existing DDR4 platform, DDR4 kits went up less than DDR5 (about 4x) and cost less in absolute terms: $224 vs $540 for 32GB. Don't count on DDR4 fully recovering. DDR2 1Gb and DDR3 2Gb chips never got back to their pre-spike lows once manufacturers moved on to the next generation.
- **SSD.** The spike is smaller (2.4x), and wafer spot prices for NAND, the memory chips inside SSDs, peaked in March 2026. If you can wait, 2028 prices should be clearly lower. Buy the capacity you need now and add storage later.
- **GPU.** The premium is concentrated in high-VRAM cards. The RTX 5090 sells for 159% more than a normal card its age; the RTX 5070 and RX 9070 class is 22% to 33% above normal. The memory in a 16GB card costs about $150 more than in 2025.
- **CPU.** No reason to wait on price. Most CPUs are at or below where a chip their age normally sells. The exceptions: AMD's X3D gaming chips run 30% to 42% above normal, and Intel reportedly raised desktop CPU prices about 10% on October 5, too recent for this data.

## What happened

All measured. "Before" is the January 2024 to June 2025 average unless noted.

| Series | Before | Latest | Change |
|---|---|---|---|
| DDR5 16Gb chip, spot (DRAMeXchange) | $5.00 | $58.07 (Oct 2026) | 11.6x |
| DDR5 8GB SO-DIMM, contract (DRAMeXchange) | $24.67 | $133 (Aug 2026) | 5.4x |
| DDR4 8Gb chip, contract (DRAMeXchange) | $1.83 | $25.00 (Aug 2026) | 13.7x |
| 32GB DDR5-6000 kit, lowest US retail (PCPartPicker) | $111 | $540 (Sep 2026) | 4.9x |
| 32GB DDR4-3200 kit, Corsair LPX, lowest US retail | $58 | $224 (Aug 2026) | 3.9x |
| Japan import price index, memory chips (Bank of Japan) | 84.3 (Jan 2025) | 388.5 (Aug 2026) | 4.6x |
| 512Gb TLC NAND wafer, spot | $2.41 (Jan 2025) | $19.98 (Sep 2026); peak $22.49 in Mar 2026 | 8.3x |
| 2TB NVMe SSD, Samsung 990 Pro and WD SN850X, lowest US retail | $158 | $388 to $430 | 2.4x |
| Micron gross margin | 37% to 45% (FY2025) | 86.8% (quarter ended Sep 2026) | |
| Micron quarterly revenue | $11.3B (quarter ended Aug 2025) | $54.2B (quarter ended Sep 2026) | 4.8x |
| Capex of Microsoft, Alphabet, Amazon, Meta and Oracle, per quarter | $46B (Q1 2024) | $182B (Q2 2026) | 4.0x |

DDR4 chip prices started rising in April-May 2025, DDR5 chip prices in October 2025, and retail DDR5 kits in November 2025.

This spike is far larger than any in the record. Past DRAM spikes since 2003 peaked at 1.3x to 3.0x their pre-spike low.

![Cycles compared](charts/cycles-compared-light.png#gh-light-mode-only)
![Cycles compared](charts/cycles-compared-dark.png#gh-dark-mode-only)

Micron's gross margin, its share of revenue left after the cost of making the chips, shows how far prices are above cost. At 86.8%, Micron's price is 7.6x its cost of goods (1 ÷ (1 − 0.868)). In FY2025 the price was about 1.6x cost. That is a 4.6x gap, close to the 4.9x jump in retail kit prices.

![Margin and capex](charts/margin-capex-light.png#gh-light-mode-only)
![Margin and capex](charts/margin-capex-dark.png#gh-dark-mode-only)

## How past spikes ended

I identified 52 price spikes across 12 series:
- DRAM chip spot prices, 2000-2026
- Contract prices
- The Bank of Japan's memory import price index
- John McCallum's retail memory prices, 1984-2024
- NAND and SSD series

A spike is a rise of at least 30% from a low, followed by a 30% fall (25% for the smoother Bank of Japan index). Full table: [`data/processed/cycles.csv`](data/processed/cycles.csv).

Three findings drive the forecast:

1. **After a peak, prices fall at a fairly steady rate.** For mainstream DRAM since 2003 (18 spikes), the median fall is 4.5% a month (log terms). The middle half falls 4.2% to 6.3% a month, the full range 3.2% to 8.5%.
2. **That rate does not depend on how big the spike was.** Across 30 spikes there is no correlation between spike size and fall rate (Spearman rank correlation 0.09, p = 0.65). So the time back to the old price grows with the spike's size: months ≈ ln(peak ÷ pre-spike price) ÷ monthly fall rate. On past spikes this formula's median ratio of actual to predicted time is 1.0. Past spikes took a median of 17 months to get back. This one is 5x at retail, so the same arithmetic gives about 3 years.
3. **Older generations don't always come back.** DDR2 1Gb chips never returned to their 2008 low after the 2010 spike; they bottomed 74% higher. DDR3 2Gb chips bottomed 24% above their 2011 low after the 2014 spike. Both were being phased out. DDR4 is in the same position now.

## Forecast

**Peak timing.** In past upswings, the quarterly price increase peaked and then shrank quarter by quarter until prices stopped rising. DDR5 contract prices rose 105% in Q1 2026, 49% in Q2 and 17% in Q3. Past cycles shrank by a median ratio of 0.43 per quarter (25th to 75th percentile: 0.20 to 0.59). Applied here:

- Base case: the peak is around February 2027, about 10% above the July-September 2026 average.
- Fast case: November 2026.
- Slow case: May 2027.

Other indicators are slowing too. Nanya, a pure DRAM maker, grew revenue 1.9% in August and 0.9% in September, after monthly gains of 6% to 49% earlier in 2026. The Bank of Japan memory import index rose 25.6% in July and 1.4% in August. Retail kits have hovered between $480 and $590 since January. Retail's markup over the contract price fell from about 68% to 7%, so retail is now tracking contract prices.

![Momentum](charts/momentum-light.png#gh-light-mode-only)
![Momentum](charts/momentum-dark.png#gh-dark-mode-only)

**The fall.** From the peak, prices fall at the historical rates above: the median for the base case, the 75th percentile for fast and the 25th for slow.

**Backtest.** I ran the same method at the same stage of 9 past cycles, using only data available at the time:
- Peak calls were a median 2 months early (average miss 4 months).
- The return to normal was called a median of 7 months too early: prices historically stay near the peak longer than the steady-fall model assumes.
- All dates below include that 7-month correction.
- Details: [`data/processed/forecast_backtest.csv`](data/processed/forecast_backtest.csv).

All modeled; dates are when the 32GB DDR5 kit crosses each level.

| Scenario | Peak | Peak kit price | 2x normal ($222) | 1.5x ($167) | Normal ($111) | Late-2022 price ($239) |
|---|---|---|---|---|---|---|
| Fast | Nov 2026 | $584 | Sep 2028 | Feb 2029 | Aug 2029 | Aug 2028 |
| **Base** | **Feb 2027** | **$624** | **Aug 2029** | **Feb 2030** | **Dec 2030** | **Jun 2029** |
| Slow | May 2027 | $679 | Mar 2030 | Oct 2030 | Jul 2031 | Jan 2030 |
| Crash (sensitivity) | Oct 2026 | $566 | Apr 2028 | Jul 2028 | Dec 2028 | Mar 2028 |

The crash row assumes price increases stop now and prices fall at the fastest rate seen since 2003 (8.5% a month). A sudden demand drop, such as a cut in AI spending, would look like that.

"Normal" is also a moving target. Retail memory's long-run price per GB fell about 10% a year between the 2016 and 2023 lows (McCallum data). At that trend, a normal 32GB kit at the end of 2030 would cost about $60, not $111. These dates are for getting back to 2024-25 prices, which is the easier bar.

**SSD.** Same method, using NAND's own history, which falls more slowly: a median of 3.5% a month across 9 NAND and SSD spikes. NAND wafer spot prices peaked in March 2026, but contract prices for PC SSDs were still rising in August. So the peak scenarios are now (fast), January 2027 (base) and May 2027 (slow).

| Scenario | Peak | 1.5x normal | 1.2x | Normal |
|---|---|---|---|---|
| Fast | Oct 2026 | Jan 2028 | Jun 2028 | Sep 2028 |
| **Base** | **Jan 2027** | **Sep 2028** | **Apr 2029** | **Sep 2029** |
| Slow | May 2027 | Apr 2029 | Dec 2029 | Jun 2030 |

![SSD prices](charts/ssd-prices-light.png#gh-light-mode-only)
![SSD prices](charts/ssd-prices-dark.png#gh-dark-mode-only)

## GPUs and CPUs

**GPUs.** Graphics card prices compared to April-August 2025, from r/buildapcsales deal posts (measured):

- **RTX 5090:** up $1,900 (+79%).
- **RTX 5080:** up $170. **RTX 5070 Ti:** up $130.
- **RTX 5070:** flat.
- **RX 9070 XT:** down $79. **RX 9070:** down $20.

The extra memory cost per card comes from the GDDR6 spot price, which rose from $2.48 to $11.67 per GB. That's about $147 for a 16GB card and $294 for a 32GB card.
- **Memory cost explains the RTX 5080 and 5070 Ti increases almost exactly.**
- **It explains only 15% of the RTX 5090's.** The rest is scarcity pricing on the top card.
- **AMD's 16GB cards fell in price despite the memory cost.** Their April-August 2025 prices were still inflated from launch, so this comparison flatters them.

No public GDDR7 price series exists, so GDDR6 stands in for GDDR7 cards.

![GPU memory cost](charts/gpu-memory-light.png#gh-light-mode-only)
![GPU memory cost](charts/gpu-memory-dark.png#gh-dark-mode-only)

**Same-age comparison.** CPUs and GPUs get cheaper as they age, so "cheaper than last year" doesn't mean "back to normal". I built a normal aging curve from deal prices before July 2025: price as a share of launch price, by age in 6-month steps. The 2020-22 GPU shortage is excluded. Against that curve (measured):

- **GPUs:** 40% above normal on average across 8 models and 150 posts.
- **CPUs:** 2% above normal across 9 models and 55 posts. The Ryzen 7800X3D (+42%), 9800X3D (+30%) and Core i7-14700K (+38%) are high. The Ryzen 9600X (−22%) and the new Core Ultra Plus chips (−14% to −23%) are low.

GPU prices depend mostly on memory prices and Nvidia's supply. I expect the GPU premium to shrink roughly on the RAM timeline. CPUs contain no DRAM.

![Aging](charts/aging-light.png#gh-light-mode-only)
![Aging](charts/aging-dark.png#gh-dark-mode-only)

## Performance per dollar

From Blender's public benchmark database and launch prices (measured, nominal dollars):

- **CPUs:** the Blender score per launch dollar improved a median 22% per generation. That's 10% to 16% a year for the main AMD and Intel lines.
- **GPUs:** +37% per generation, excluding the jump to ray-tracing cores in RTX 20. That's 16% to 29% a year.
- **The latest generation was the weakest:** +8% to +31% for GPUs, +11% to +22% for CPUs. Flagship GPU launch prices kept rising: the RTX 5090 launched 25% above the 4090.

![Performance per dollar](charts/perf-per-dollar-light.png#gh-light-mode-only)
![Performance per dollar](charts/perf-per-dollar-dark.png#gh-dark-mode-only)

What waiting for normal prices gets you (modeled from the rates above):

- **CPU:** if the trend holds to late 2030, performance per launch dollar would be roughly 1.4x to 1.8x today's.
- **GPU:** 1.8x to 2.8x at the long-run rate, less if the last generation is the guide.
- **RAM:** larger chips are standard now. 24Gb and 32Gb chips allowed the first 48GB (2023) and 64GB (2024) desktop modules. No date has been announced for DDR6.

Officially announced products (company sources, [`data/raw/perf_manual/announced_products.csv`](data/raw/perf_manual/announced_products.csv)):

- **Intel:** Nova Lake desktop CPUs at "end of 2026".
- **AMD:** no Zen 6 desktop date yet. AM5 is supported through 2029.
- **Nvidia and AMD graphics:** no new consumer GPU announced.
- **Data center:** Nvidia's Vera Rubin arrives in the second half of 2026 and Rubin Ultra in the second half of 2027. Both use HBM.
- **Micron:** stopped shipping Crucial consumer memory in February 2026.

## Sentiment

Measured from public discussion, search and news data, not opinions:

- **Attention far beyond the last spike.** Hacker News comments mentioning "RAM prices" (per 100k comments and posts, so the count isn't inflated by the site growing) peaked at 17.1 in Q1 2026, 9x the 2018 peak of 1.9.
- **Buyers' attention peaked in December 2025 and has been falling since.**
  - US Google searches for "RAM prices" are down 79% from December to September.
  - RAM-price posts on r/buildapc, r/pcmasterrace and r/hardware went from 18 per 1,000 posts in December to 4 in September.
  - Hacker News fell from 17.1 in Q1 2026 to 9.5 so far in Q4.
- **Industry news peaked later.** News articles about the "memory shortage" (GDELT, as a share of all articles it monitors) peaked in July 2026 and were still 24% below that peak in September. News tone on "RAM prices" moved from −1.5 in December 2025 to about −0.1 to −0.4 since August.
- **Reddit tone is still negative.** Price-related RAM posts have had more complaints than good news every month since October 2025. The one exception is September 2026 (+0.07 on a −1 to +1 scale), and early October is back to −0.43, so one month isn't a turn.
- **In 2018, attention peaked with prices.** Hacker News attention peaked in Q1 2018, the same quarter the DDR4 spot price peaked (January 2018).
- **This time it peaked with retail, not chip prices.** Buyers' attention peaked in December 2025 to January 2026, the same time retail kit prices stopped climbing. Contract and spot chip prices kept rising, and industry news kept growing until July. My reading: falling attention here is people getting used to high prices, not a sign the market has turned.

![Sentiment](charts/sentiment-light.png#gh-light-mode-only)
![Sentiment](charts/sentiment-dark.png#gh-dark-mode-only)

## Outside forecasts, and whether they hold

These are the only outside opinions in this report. Sources and dates are in [`docs/external_views_notes.md`](docs/external_views_notes.md).

| Source | View | Verdict |
|---|---|---|
| TrendForce, Jul and Sep 2026 | DRAM undersupply widens in 2027; new capacity mostly in 2028; Q4 2026 contract prices +10% to +15% | Plausible. +10% to +15% is above the base case's next step (+7%) and matches the slow scenario. Our data agrees increases are shrinking. |
| Micron, Sep 2026 | Supply "much tighter in 2027 and 2028 than 2026"; no line of sight to balance | Partly valid. Its own guidance (revenue +13% next quarter) implies prices still rising, which fits the base and slow cases. A tight market can still see prices fall from an 87% margin. And memory makers have an obvious interest in saying shortages will last. |
| SK hynix CEO, Aug 2026 | Shortage could last until 2030 | Plausible for HBM. For PC RAM, even the slow scenario returns to normal by mid-2031, and no past spike lasted anywhere near this long. |
| Gartner, 2026 | 3.6% undersupply through 2027; prices fall in the second half of 2027 | Consistent with the base case: peak in early 2027, decline from late 2027. |
| Kye-hyun Kyung (former Samsung chip head), May 2026 | Significant price drop by the second half of 2027 from Chinese capacity | Plausible as the start of the decline. A big drop is not a return to normal: from a 5x peak, even a 50% fall leaves prices 2.5x normal. |
| Acer CEO Jason Chen, Sep 2026 (DigiTimes) | PC prices peak in the first half of 2027 and ease from late 2027; says 2030 shortage claims protect memory makers' margins | Matches the base case's timing. Again, prices starting to ease is not the same as being back to normal. |
| Intel, reported Sep 2026 (TweakTown, secondary) | About 10% increase on desktop CPU prices from Oct 5, 2026, after smaller increases earlier in the year | Not yet visible: deal data runs through September, and Intel chips sat at or below normal aging then. If it sticks, Intel CPUs move about 10% above normal, still far less than RAM or GPUs. |

Most outside forecasts agree with this data that prices stay high through 2027. They mostly answer when the shortage ends. This report answers when retail prices get back to 2024-25 levels, which comes 2 to 3 years after the decline starts.

## Method and limitations

Pipeline: `fetch/` downloads each source into `data/raw/<source>/`, each with a `SOURCE.md` recording URLs, the fetch date and caveats. `analysis/` builds the series, cycles, forecast, component analysis and charts. Outputs are in `data/processed/`.

| Source | Used for |
|---|---|
| DRAMeXchange/TrendForce public price tables, rebuilt from 1,110 Wayback Machine captures (2000-2026) | Chip spot and contract prices, NAND, GDDR6 |
| PCPartPicker product pages via the Wayback Machine (22 products, 2019-2026) | Retail prices |
| r/buildapcsales deal posts via the Arctic Shift archive (117,138 posts, 2019-2026) | Street prices for RAM, SSD, CPU, GPU |
| John C. McCallum's price history (via Wayback) | Retail memory and SSD prices, 1957-2024 |
| Bank of Japan corporate goods price index | Memory chip import and export prices, 2000-2026 |
| FRED (BLS, Census) | US producer, import and consumer price indices |
| Eurostat Comext, UN Comtrade | Trade unit values |
| SEC EDGAR XBRL and filings | Micron, Nvidia, hyperscaler financials; Micron's stated price changes |
| Taiwan MOPS monthly revenue | Nanya, Winbond, ADATA, TSMC and others |
| SK hynix and Samsung investor relations | Quarterly results |
| Blender Open Data, Wikipedia (pinned revisions) | Benchmarks and launch prices |
| Google Trends, Hacker News (Algolia), Reddit (Arctic Shift), GDELT, Wikipedia pageviews | Attention and sentiment |

Limitations:
- **Small history.** The forecast rests on 18 past declines and a 9-cycle backtest. This spike (5x at retail, 12x at spot) is larger than any of them (at most 3x since 2003), so the fall-rate pattern is being stretched.
- **Thin 2026 deal data.** RAM deal posts dropped to a handful a month (people post fewer deals when prices rise), so quarterly pooling is used. Archived retail captures are irregular.
- **Spot prices are noisy.** Spot is a thin market. Retail is anchored to contract prices, which is where most volume trades.
- **Nominal US prices.** No inflation adjustment; US retail only.
- **The forecast assumes the old pattern holds.** If AI demand keeps growing and new fabs slip past 2028, the decline starts later than the slow case.
- **Withheld raw data.** The WSTS billing workbook and the raw DRAMeXchange page captures are not redistributed (rights notices). The fetch scripts rebuild them, and the processed monthly series are included.
- **Incomplete UN Comtrade history.** The free API limits calls per hour. Re-running the fetch resumes it.
- **Partial sentiment sources.** Reddit tone covers January 2025 onward. GDELT returned 10 of 18 query series before it rate-limited; GPU and SSD news series are missing.

Reproduce:

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt    # .venv/bin/python on macOS/Linux
.venv/Scripts/python run.py            # analysis and charts from the included data
.venv/Scripts/python run.py --fetch    # re-download everything first (slow)
```

SEC asks for contact details in the User-Agent of EDGAR requests. Set `SEC_USER_AGENT="your-name you@example.com"` before `--fetch`.
