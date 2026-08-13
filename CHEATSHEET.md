# Polyamide Index — Cheatsheet

Run everything from the project root `C:\Users\aresi\Claude\code\polyamide-index`.
Reads the data produced by **Parser Zara** (`..\parser\russia\zara`); nothing is re-scraped.

---

## The whole thing
```powershell
python run_monthly.py --dry-run     # build index + dashboard, PRINT the email, send nothing (safe)
python run_monthly.py               # build + SEND the email to config recipients
python run_monthly.py --no-email    # build index + dashboard only
python run_monthly.py --offline     # reuse cached FX (no network) — for testing
```
Output lands in `output\<run_date>\` and `output\latest.json` / `output\dashboard.html`.

## Layer 1 — dataset
```powershell
python build_index.py                        # latest snapshot with the reference
python build_index.py --run-date 2026-08-10  # a specific snapshot date
python build_index.py --offline              # reuse config\fx_cache.json instead of fetching
```
Writes `output\<run_date>\data.json` (+ `output\latest.json`). Prints min / max / spread.

## Layer 2 — dashboard
```powershell
python build_dashboard.py                    # from output\latest.json
python build_dashboard.py --run-date 2026-08-10
```
Writes a self-contained `output\<run_date>\dashboard.html` (+ `output\dashboard.html`).
Double-click to open — no server, no internet.

## Layer 3 — email
```powershell
python email_report.py --dry-run             # print the email, send nothing (no creds needed)
python email_report.py                       # send to config\settings.json recipients
python email_report.py --to a@b.com,c@d.com  # override recipients
```
HTML summary in the body, `dashboard.html` attached. SMTP is **reused from Parser Zara's**
`config\email.ini` (or `PI_SMTP_*` / `ZARA_SMTP_*` env vars).

---

## Schedule — 20th of every month, 07:00
```powershell
# ELEVATED PowerShell (Run as administrator) → SYSTEM task, unattended:
powershell -ExecutionPolicy Bypass -File schedule\register_schedule.ps1
# ...or under your own account (prompts for your Windows password):
powershell -ExecutionPolicy Bypass -File schedule\register_schedule.ps1 -CurrentUser

powershell -ExecutionPolicy Bypass -File schedule\unregister_schedule.ps1   # remove
schtasks /Query /TN PolyamideIndexMonthly /V /FO LIST                       # inspect
schtasks /Run   /TN PolyamideIndexMonthly                                   # run now (BUILDS + SENDS)
```
Task name **`PolyamideIndexMonthly`**. Logs: `logs\task_*.log` and `logs\run_<YYYY-MM>.log`.

---

## Change what is tracked / who gets it — `config\settings.json`
| Key | Meaning |
|-----|---------|
| `reference` | Zara `style/colour` to track (e.g. `3905/532/800`). Swap to track any model. |
| `display_currency` | Currency every market is converted to at spot rates (`EUR`). |
| `base_country` | Anchor market = the 0% line in the "vs" views (`es` = Spain). |
| `ref_country` | Secondary comparison shown alongside (`us` = USA). |
| `recipients` | Email recipients (list). |
| `zara_db` | Path to Parser Zara's `master.sqlite` (relative to project root). |
| `zara_email_ini` | Path to Parser Zara's `email.ini` reused for SMTP. |

After changing `reference`, just re-run `python run_monthly.py --dry-run` to preview.

---

## Files
| Path | Purpose |
|------|---------|
| `common.py` | paths, config, country metadata (name/region/flag/symbol), live USD FX |
| `build_index.py` | DB → USD → `data.json` |
| `build_dashboard.py` + `dashboard_template.html` | `data.json` → `dashboard.html` |
| `email_report.py` | send summary + attach dashboard |
| `run_monthly.py` | orchestrator (1→2→3) |
| `schedule\` | `run_monthly.bat`, `register_schedule.ps1`, `unregister_schedule.ps1` |
| `config\settings.json` | what to track, who to email, where the parser lives |
| `config\fx_cache.json` | last good FX (auto-written; used by `--offline`) |
| `output\` , `logs\` | generated runs and logs |
