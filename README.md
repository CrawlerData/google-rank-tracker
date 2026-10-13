# Google Rank Tracker (Python)

A self-hosted Google keyword rank tracker. Put your keywords and domain in a CSV, run `rank_tracker.py track` daily for any mix of countries and desktop/mobile, and it stores each keyword's position, ranking URL and AI Overview presence in SQLite. `report` shows what moved since the previous run (up, down, lost, entered); `export` gives you the full history as CSV. Python with one dependency (`requests`).

> **Uses the CrawlerData API — you need an API key** (free trial credits available at https://app.crawlerdata.com/register). Each Google results page checked costs 1 credit.

## Features

- Keywords × countries × devices in one command (`--countries us,gb,de --devices desktop,mobile`)
- Position, ranking URL and title for your domain (subdomains count, `www.` is ignored)
- Depth from top ~10 (1 page) to 10 pages; paging stops as soon as your domain is found, so you only pay for pages you need
- AI Overview tracking: whether the keyword shows an AI Overview and whether it cites your domain
- Full top-N results saved per run (`serp` table), so you can see who outranks you
- `report`: latest vs previous run with `+N` / `-N` / `=` / `lost` / `entered` / `new`, optional CSV
- `export`: full history as CSV for Sheets, Looker Studio or Excel
- Different domains per keyword (track competitors side by side)

## Quickstart

```bash
git clone https://github.com/CrawlerData/google-rank-tracker.git
cd google-rank-tracker
pip install -r requirements.txt

export CRAWLERDATA_API_KEY="your_api_key"        # PowerShell: $env:CRAWLERDATA_API_KEY="your_api_key"

python rank_tracker.py track                                    # run daily
python rank_tracker.py track --countries us,gb --devices desktop,mobile --pages 3
python rank_tracker.py report
python rank_tracker.py export -o rankings.csv
```

## Input: `keywords.csv`

```csv
keyword,domain
best crm software,hubspot.com
crm for small business,hubspot.com
email marketing software,hubspot.com
```

The `domain` column is optional if you pass `--domain example.com`. Add rows with other domains to track competitors for the same keywords. Use plain keywords; advanced operators such as `site:` are not a reliable way to track rankings with this endpoint.

## Sample output

Real runs on 13 October 2026 (the example domain is just a well-known site, not a customer):

```text
$ python rank_tracker.py track --devices desktop,mobile --pages 2
'best crm software' [us/desktop] hubspot.com: #6  https://www.hubspot.com/comparisons/best-crm | AI Overview
'best crm software' [us/mobile] hubspot.com: #19  https://www.hubspot.com/comparisons/best-crm | AI Overview
'crm for small business' [us/desktop] hubspot.com: #1  https://www.hubspot.com/products/crm | AI Overview cites you
'crm for small business' [us/mobile] hubspot.com: #1  https://www.hubspot.com/products/crm | AI Overview cites you
'email marketing software' [us/desktop] hubspot.com: #8  https://www.hubspot.com/products/marketing/email | AI Overview cites you
'email marketing software' [us/mobile] hubspot.com: #8  https://www.hubspot.com/products/marketing/email | AI Overview cites you
Run 2026-10-13T05:26:06Z saved to ranks.db. Credits used: 7

$ python rank_tracker.py track
...
Run 2026-10-13T05:27:05Z saved to ranks.db. Credits used: 3

$ python rank_tracker.py report
Rank report for run 2026-10-13T05:27:05Z vs previous run
keyword                          cc  device  domain                  pos prev   change  url
best crm software                us  desktop hubspot.com               6    6        =  https://www.hubspot.com/comparisons/best-crm
crm for small business           us  desktop hubspot.com               1    1        =  https://www.hubspot.com/products/crm
email marketing software         us  desktop hubspot.com               8    8        =  https://www.hubspot.com/products/marketing/email
```

The first run cost 7 credits: 6 keyword/device combinations at 1 page each, plus a second page for the one keyword (mobile) not found on page 1. The two runs were a minute apart, hence no movement. When positions change, the report looks like this:

```text
keyword                          cc  device  domain                  pos prev   change  url
best crm software                us  desktop hubspot.com               4    6       +2  ...
crm for small business           us  desktop hubspot.com               -    1     lost
email marketing software         us  desktop hubspot.com              11    8       -3  ...
```

`export` ([sample](examples/sample-rankings.csv)):

```csv
run_at,keyword,domain,country,device,position,url,title,pages_checked,has_ai_overview,cited_in_ai_overview
2026-10-13T05:26:06Z,best crm software,hubspot.com,us,desktop,6,https://www.hubspot.com/comparisons/best-crm,Best CRM Software of 2026 | Compare Top CRMs,1,1,0
2026-10-13T05:26:06Z,crm for small business,hubspot.com,us,desktop,1,https://www.hubspot.com/products/crm,Streamline Your Entire Business With a Free CRM,1,1,1
```

## Cost per run

1 credit per Google results page. For each keyword × country × device the tracker checks page 1, and only checks further pages (up to `--pages`) while your domain hasn't been found.

| Setup | Credits per run | Per month (daily) |
| --- | --- | --- |
| 100 keywords, 1 country, desktop, top 10 | 100 | ~3,000 |
| 100 keywords, 1 country, desktop + mobile, top 10 | 200 | ~6,000 |
| 100 keywords, 3 countries, desktop, up to 3 pages | 300-900 | ~9,000-27,000 |

At $1.00 per 1,000 credits on the smallest pack (down to $0.30 on larger packs, see [pricing](https://crawlerdata.com/pricing)), 100 keywords daily on desktop is about $3 a month. Failed jobs are free.

## Options

| Command / option | Default | Description |
| --- | --- | --- |
| `--db FILE` | `ranks.db` | SQLite file (goes before the command) |
| `track -k FILE` | `keywords.csv` | Keywords, with an optional `domain` column |
| `track --domain` | | Domain for rows without one |
| `track --countries` | `us` | Comma-separated: us, gb, ca, au, de, fr, nl, it, es, pt, be, at, ch, se, no, dk, fi, ie, pl, cz, il, ae, in, jp, kr, sg, mx, br, nz, za, tr |
| `track --devices` | `desktop` | `desktop`, `mobile` or `desktop,mobile` |
| `track --pages N` | `1` | Max result pages to check (1-10) |
| `report -o FILE` | | Also write the report as CSV |
| `export -o FILE` | `rankings.csv` | Full history |

To see who outranks you on a keyword:

```sql
SELECT position, domain, url FROM serp
WHERE keyword = 'best crm software' AND device = 'desktop'
  AND run_at = (SELECT MAX(run_at) FROM serp)
ORDER BY position;
```

## Running it daily

```cron
# cron (Linux/macOS): every day at 06:00
0 6 * * * cd /path/to/google-rank-tracker && CRAWLERDATA_API_KEY=your_api_key python3 rank_tracker.py track >> ranks.log 2>&1
```

```powershell
# Windows Task Scheduler
setx CRAWLERDATA_API_KEY your_api_key
schtasks /Create /SC DAILY /ST 06:00 /TN "RankTracker" /TR "cmd /c cd /d C:\path\to\google-rank-tracker && python rank_tracker.py track >> ranks.log 2>&1"
```

## How positions are counted

- `position` is the organic rank across pages (1 = first organic result). Ads, AI Overviews, People Also Ask and other features are not counted.
- Google's later pages can repeat URLs from earlier pages; repeats are counted once.
- Organic results per page vary (roughly 7-12), so "page 1" isn't always exactly 10 results.
- Rankings depend on country, device and time. Results are not personalised and not tied to a city.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `HTTP 401` | The API key is missing or wrong. Check `echo $CRAWLERDATA_API_KEY` (or `$env:CRAWLERDATA_API_KEY` in PowerShell) and create a key under API Access in the [dashboard](https://app.crawlerdata.com). |
| `HTTP 402` | You are out of credits. Buy a credit pack in the dashboard (from $1.00 down to $0.30 per 1,000 credits, see [pricing](https://crawlerdata.com/pricing)). |
| `HTTP 429` | Rate limit: 100 requests per minute and 20 per second per key. The client waits until `X-RateLimit-Reset` and retries automatically; for big batches, spread requests out. |
| Timeouts | Live requests return when Google has been fetched: a few seconds for search, 30 to 120 seconds for Google Shopping sellers. The client uses a 200 second timeout. |
| `job ... failed` | The HTTP call worked but the job did not (for example Google blocked that attempt). Failed jobs cost 0 credits and the client retries them twice before giving up. |

## Links

- [CrawlerData](https://crawlerdata.com)
- [SEO rank tracking with CrawlerData](https://crawlerdata.com/solutions/seo-rank-tracking)
- [Google Search API](https://crawlerdata.com/apis/google-search-api)
- [API docs](https://app.crawlerdata.com/docs)
- [Cheapest SERP API](https://crawlerdata.com/blog/cheapest-serp-api)

## More CrawlerData examples

| Repo | What it does |
| --- | --- |
| [google-shopping-scraper](https://github.com/CrawlerData/google-shopping-scraper) | Search Google Shopping, export products to CSV/JSON (Python + Node.js) |
| [google-shopping-sellers-scraper](https://github.com/CrawlerData/google-shopping-sellers-scraper) | Every seller and price for one product, as a comparison table |
| [google-shopping-price-tracker](https://github.com/CrawlerData/google-shopping-price-tracker) | Scheduled price history in SQLite, CSV export and an HTML chart |
| [competitor-price-monitoring](https://github.com/CrawlerData/competitor-price-monitoring) | Your catalog vs Google Shopping sellers, with undercut alerts |
| [map-violation-monitor](https://github.com/CrawlerData/map-violation-monitor) | Flag sellers below MAP with timestamped evidence |
| [google-search-scraper](https://github.com/CrawlerData/google-search-scraper) | Google SERP to JSON/CSV: organic, ads, People Also Ask, AI Overview (Python + Node.js) |
| [google-rank-tracker](https://github.com/CrawlerData/google-rank-tracker) | Daily keyword positions by country and device, with a change report |
| [google-local-business-leads](https://github.com/CrawlerData/google-local-business-leads) | Google Local results to a lead list CSV |
| [google-news-scraper](https://github.com/CrawlerData/google-news-scraper) | Brand and keyword news monitoring to CSV and JSON Feed |
| [google-search-mcp-server](https://github.com/CrawlerData/google-search-mcp-server) | Connect Claude, Cursor or n8n to the CrawlerData MCP server |
| [crawlerdata-examples](https://github.com/CrawlerData/crawlerdata-examples) | Python, Node.js and curl snippets for every endpoint |

## License

MIT. See [LICENSE](LICENSE). Google and Google Shopping are trademarks of Google LLC; this project is not affiliated with Google.
