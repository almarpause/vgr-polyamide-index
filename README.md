# Zara Polyamide Index

A **Big Mac Index for one identical Zara garment.** The Economist prices one identical
burger across countries to expose what local economies do to a fixed product. This does the
same with one physical item — Zara's **FINE STRAP POLYAMIDE T-SHIRT** (reference
`3905/532/800`, colour *Black*) — sold in ~65 countries.

Every market is priced in **one currency — euros — at live market (spot) rates**, and
**anchored to Spain** (Zara's home market, whose €7.95 is the 0% baseline). Because the product
is identical everywhere, the gap between the cheapest and dearest market is **not about the
product**. It is the sum of what it costs to land and sell that one t-shirt in each country:

> **local operating cost** + **global logistics** + **import duties & tariffs** + **VAT** + **local margin**

That is the story the dashboard and the monthly email tell.

---

## What it produces

- **`output/<run_date>/dashboard.html`** — a single, self-contained interactive dashboard in
  The Economist's chart grammar (Econ-Red accent, navy/blue data palette, Georgia + Arial).
  Opens by double-click, no server, no internet. Ranked bar chart of all markets in USD,
  sortable by *€ price / vs Spain / vs USA*, filterable by region; a "how many t-shirts does
  €100 buy?" infographic; regional averages; the product card.
- **`output/<run_date>/data.json`** (+ `output/latest.json`) — the computed dataset.
- **A monthly email** to the configured recipients with an Economist-styled HTML summary
  (dearest / cheapest tables, KPIs) and the full `dashboard.html` attached.

---

## How it works

It **reuses the data already produced by Parser Zara** (`../parser/russia/zara`). That weekly
scraper stores every country's price for every Zara reference in `master.sqlite`. The Polyamide
Index reads the **latest snapshot** of the tracked reference, converts each local price to **euros
at live market (spot) rates** (`open.er-api.com`, free, no key — *not* the parser's fixed
`fx_rates.csv`), and ranks the world against the Spanish anchor.

```
Parser Zara (weekly)            Polyamide Index (monthly, 20th)
  master.sqlite  ──────────►  build_index.py   → data.json     (DB + live USD FX)
                              build_dashboard.py → dashboard.html
                              email_report.py   → emails summary + attaches dashboard
                              run_monthly.py     = the three, chained, with logging
```

Nothing is re-scraped; the index is a **view** over the parser's database, so it is fast and
never hammers Zara.

---

## Pipeline

| Step | Script | Does |
|------|--------|------|
| 1 | `build_index.py` | Latest Zara snapshot for the reference → USD via live FX → `data.json` |
| 2 | `build_dashboard.py` | `data.json` → self-contained `dashboard.html` (Economist style) |
| 3 | `email_report.py` | Emails the HTML summary + attaches `dashboard.html` |
| — | `run_monthly.py` | Runs 1→2→3 with a shared run and a monthly log |

```bash
python run_monthly.py --dry-run     # build everything, print the email, send nothing
python run_monthly.py               # full run: build + send the email
python run_monthly.py --no-email    # build only
```

See **CHEATSHEET.md** for every command and flag.

---

## Configuration — `config/settings.json`

```json
{
  "reference": "3905/532/800",     // Zara style/colour to track (swap to track another model)
  "display_currency": "EUR",       // convert every market to this currency (spot rates)
  "base_country": "es",            // the anchor / 0% line in the "vs" views (Spain)
  "ref_country": "us",             // a secondary comparison shown alongside (USA)
  "recipients": ["pau.almar@verygoodretail.com"],
  "zara_db": "../parser/russia/zara/layer3_consolidator/database/master.sqlite",
  "zara_email_ini": "../parser/russia/zara/config/email.ini"
}
```

- **Track a different model:** change `reference` and re-run. The product name, image and
  category are pulled automatically from the parser's `products` table.
- **Email/SMTP:** credentials are **reused from Parser Zara's** `config/email.ini` (Gmail +
  app password) — nothing is duplicated or hard-coded here. Override with `PI_SMTP_*` or
  `ZARA_SMTP_*` environment variables for the unattended task.

---

## Scheduling — the 20th of every month

Windows Task Scheduler, mirroring the parser's approach.

```powershell
# from an ELEVATED (Run as administrator) PowerShell — creates a SYSTEM task
powershell -ExecutionPolicy Bypass -File schedule\register_schedule.ps1

# or run under your own account (prompts for your password)
powershell -ExecutionPolicy Bypass -File schedule\register_schedule.ps1 -CurrentUser

powershell -ExecutionPolicy Bypass -File schedule\unregister_schedule.ps1   # remove
schtasks /Run /TN PolyamideIndexMonthly                                      # trigger now (sends!)
```

The task **`PolyamideIndexMonthly`** fires on **day 20 at 07:00**, runs `run_monthly.py`, and
logs to `logs\task_*.log`. It reads whatever the newest Parser Zara run in the DB is (the
scraper runs weekly on Mondays), so the 20th always sees fresh data.

---

## Notes & caveats

- Prices are **recommended retail (RRP)**; on-sale prices are used when present. RRP is
  **VAT-inclusive where local law includes it** (e.g. EU), which is part of the story — VAT is
  one of the cost layers the index surfaces.
- Conversion uses **market spot** exchange rates pulled live on the run's FX date (shown in the
  footer), not PPP and not any fixed/stored rate. `--offline` reuses the last live pull.
- Change `display_currency` / `base_country` in `config/settings.json` to re-anchor (e.g. back to
  `USD` / `us`); every label, symbol and comparison follows automatically.
- A market is included only if it has an in-stock price for the reference on the snapshot date
  and a currency with a live FX rate (any skipped market is listed in the run log).
