"""Polyamide Index — Layer 1: build the dataset.

Reads the latest Zara snapshot for the tracked reference from the parser's
master.sqlite, converts every local price to the display currency at live market
(spot) rates, ranks the countries and computes each one's premium/discount versus
the benchmark market (Spain — its price is the anchor) and a secondary reference
(USA). Writes output/<run_date>/data.json (+ latest.json), the single input the
dashboard and the email consume.

    python build_index.py                 # latest run in the DB
    python build_index.py --run-date 2026-08-10
    python build_index.py --offline        # reuse last good FX (config/fx_cache.json)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from datetime import date
from pathlib import Path
from urllib.parse import quote

import common

FX_CACHE = common.CONFIG_DIR / "fx_cache.json"
SNAPSHOT = common.ROOT / "web" / "snapshot_local.json"
LANDED = common.CONFIG_DIR / "landed.json"


def attach_cost_stack(countries: list[dict]) -> dict | None:
    """Decompose each country's retail price into a cost waterfall:
    DC COGS -> outbound freight -> duties & tariffs -> other -> margin -> VAT.
    Assumptions live in config/landed.json (all editable). Adds c['stack'] with
    each segment in EUR; returns the global params for the legend, or None if the
    config is missing (the chart then just skips the inner strip)."""
    if not LANDED.exists():
        return None
    cfg = json.loads(LANDED.read_text(encoding="utf-8"))
    dc = float(cfg["dc_cogs_eur"]); other_pct = float(cfg["other_pct"]); ins = float(cfg["insurance_pct"])
    opex_pct = float(cfg.get("opex_pct", 0.0))
    per = cfg.get("countries", {})
    for c in countries:
        p = per.get(c["cc"])
        if not p:
            c["stack"] = None; continue
        vat, freight, duty = float(p["vat"]), float(p["freight"]), float(p["duty"])
        spec = float(p.get("duty_specific_eur", 0) or 0)      # per-unit specific duty
        rule = p.get("duty_rule", "add")                      # add | higher | advalorem
        value = c["value"]
        net = value / (1 + vat / 100)
        cif = dc + freight + ins * (dc + freight)
        duty_adv = duty / 100 * cif
        if spec > 0 and rule == "higher":
            duty_eur = max(duty_adv, spec)
        elif spec > 0 and rule == "add":
            duty_eur = duty_adv + spec
        else:
            duty_eur = duty_adv
        other = other_pct * net
        opex = opex_pct * net
        landed_cogs = dc + freight + duty_eur + other        # cost to get one unit onto the shelf
        gross_margin = net - landed_cogs
        margin = gross_margin - opex                          # operating contribution after local opex
        vat_eur = value - net
        c["stack"] = {
            "dc": round(dc, 3), "freight": round(freight, 3), "duty": round(duty_eur, 3),
            "other": round(other, 3), "opex": round(opex, 3), "margin": round(margin, 3),
            "vat": round(vat_eur, 3), "net": round(net, 3), "landed": round(landed_cogs, 3),
            "gross_margin": round(gross_margin, 3),
            "duty_pct": duty, "duty_specific_eur": spec, "vat_pct": vat, "mode": p.get("mode", ""),
            "below_cost": gross_margin < 0,                    # price under-covers landed COGS (pre-opex)
        }
    return {"dc_cogs_eur": dc, "other_pct": other_pct, "opex_pct": opex_pct, "insurance_pct": ins}


def load_from_snapshot(run_date_override: str | None) -> tuple[str, dict, list[dict]]:
    """Cloud path: read the committed web/snapshot_local.json instead of the
    parser's SQLite DB (which only exists on the scraping machine). Returns the
    same (run_date, product meta, price rows) shape as the DB path."""
    if not SNAPSHOT.exists():
        raise SystemExit(f"[index] no DB and no snapshot at {SNAPSHOT}; run export_snapshot.py locally first")
    s = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    meta = {"reference": s["reference"], "style": s["style"], **s.get("product", {})}
    snaps = [{"cc": r["cc"], "currency": r["currency"], "rrp_local": r["rrp"],
              "price_local": r["rrp"], "on_sale": False} for r in s["rows"]]
    return run_date_override or s["run_date"], meta, snaps


def latest_run_with_ref(cur: sqlite3.Cursor, ref: str) -> str | None:
    cur.execute("SELECT MAX(run_date) FROM price_snapshots WHERE reference=? AND in_stock=1", (ref,))
    return cur.fetchone()[0]


def product_meta(cur: sqlite3.Cursor, ref: str) -> dict:
    cols = ["reference", "style", "colour_code", "colour_name", "season",
            "gender", "prod_group", "family", "subfamily", "name", "image_url"]
    cur.execute(f"SELECT {','.join(cols)} FROM products WHERE reference=?", (ref,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"[index] reference {ref!r} not found in products table")
    return dict(zip(cols, row))


def snapshots(cur: sqlite3.Cursor, ref: str, run_date: str) -> list[dict]:
    cur.execute(
        "SELECT country, currency, rrp, discounted_price, in_stock "
        "FROM price_snapshots WHERE reference=? AND run_date=? AND in_stock=1",
        (ref, run_date))
    out = []
    for cc, ccy, rrp, disc, in_stock in cur.fetchall():
        # Always use the RRP (list price), even when the item is discounted right
        # now: the index measures a market's standing price, not a transient promo.
        price = rrp
        if price is None or price <= 0 or not ccy:
            continue
        out.append({"cc": cc, "currency": ccy, "rrp_local": rrp,
                    "price_local": price, "on_sale": bool(disc)})
    return out


def load_fx(base: str, offline: bool) -> tuple[dict, str]:
    if not offline:
        try:
            rates, asof = common.fetch_rates(base)
            FX_CACHE.write_text(json.dumps({"base": base, "rates": rates, "asof": asof}), encoding="utf-8")
            return rates, asof
        except Exception as e:  # noqa: BLE001 — fall back to cache, never crash the pipeline
            print(f"[index] live FX failed ({type(e).__name__}: {e}); trying cache")
    if FX_CACHE.exists():
        c = json.loads(FX_CACHE.read_text(encoding="utf-8"))
        if c.get("base", base) != base:
            raise SystemExit(f"[index] cached FX base {c.get('base')!r} != {base!r}; run once online")
        return {k: float(v) for k, v in c["rates"].items()}, c.get("asof", "") + " (cached)"
    raise SystemExit("[index] no live FX and no fx_cache.json — cannot convert prices")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_index")
    ap.add_argument("--run-date", default=None, help="snapshot date; default = latest with the reference")
    ap.add_argument("--offline", action="store_true", help="reuse cached FX instead of fetching")
    ap.add_argument("--from-snapshot", action="store_true",
                    help="build from web/snapshot_local.json instead of the SQLite DB (cloud mode)")
    a = ap.parse_args(argv)

    cfg = common.load_settings()
    ref = cfg["reference"]
    ccy_disp = cfg.get("display_currency", "EUR").upper()
    base_cc = cfg.get("base_country", "es")     # benchmark / 0% line (Spain)
    ref_cc = cfg.get("ref_country", "us")       # secondary comparison (USA)
    # Correct stale currency labels from the scraper (e.g. Bulgaria's price is now
    # quoted in EUR after euro adoption, but the feed still tags it BGN, which would
    # otherwise be double-converted). {cc: ISO currency}.
    ccy_override = {k.lower(): v.upper() for k, v in (cfg.get("currency_overrides") or {}).items()}
    symbol = common.currency_symbol(ccy_disp)

    db = Path(cfg["zara_db"])
    use_snapshot = a.from_snapshot or not db.exists()
    if use_snapshot:
        run_date, meta, snaps = load_from_snapshot(a.run_date)
        print(f"[index] source: web/snapshot_local.json (cloud mode)")
    else:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.cursor()
        run_date = a.run_date or latest_run_with_ref(cur, ref)
        if not run_date:
            raise SystemExit(f"[index] no in-stock snapshots for {ref!r} in {db}")
        meta = product_meta(cur, ref)
        snaps = snapshots(cur, ref, run_date)
        con.close()
    if not snaps:
        raise SystemExit(f"[index] no priced rows for {ref!r} on {run_date}")

    rates, fx_asof = load_fx(ccy_disp, a.offline)

    # Per-country deep link into that market's Zara store, searching the item's
    # style reference (e.g. 3905/532). Opens the localised storefront showing the
    # product and its local price. (Zara's direct PDP needs an internal product id
    # that isn't in the parser DB; the localised search is stable and id-free.)
    search_term = meta["style"] or ref
    def zara_url(cc: str) -> str:
        return f"https://www.zara.com/{cc}/en/search?searchTerm={quote(search_term, safe='')}"

    countries, skipped, corrected = [], [], []
    for s in snaps:
        ccy = ccy_override.get(s["cc"], s["currency"])
        if ccy != s["currency"]:
            corrected.append(f"{s['cc']}:{s['currency']}->{ccy}")
        r = rates.get(ccy)
        if not r:
            skipped.append(s["cc"]); continue
        value = s["price_local"] / r          # local -> display currency (spot)
        countries.append({
            "cc": s["cc"],
            "name": common.country_name(s["cc"]),
            "region": common.country_region(s["cc"]),
            "flag": common.flag_emoji(s["cc"]),
            "currency": ccy,
            "price_local": round(s["price_local"], 2),
            "price_local_label": common.money(s["price_local"], ccy),
            "value": round(value, 2),
            "on_sale": s["on_sale"],
            "zara_url": zara_url(s["cc"]),
        })

    countries.sort(key=lambda c: c["value"], reverse=True)
    val_of = {c["cc"]: c["value"] for c in countries}
    base_val = val_of.get(base_cc)              # Spain's price = the anchor
    ref_val = val_of.get(ref_cc)
    for i, c in enumerate(countries, 1):
        c["rank"] = i
        c["vs_base_pct"] = round((c["value"] / base_val - 1) * 100, 1) if base_val else None
        c["vs_ref_pct"] = round((c["value"] / ref_val - 1) * 100, 1) if ref_val else None

    stack_params = attach_cost_stack(countries)

    vals = [c["value"] for c in countries]
    cheapest, dearest = countries[-1], countries[0]
    summary = {
        "reference": ref,
        "style": meta["style"],
        "product_name": meta["name"],
        "colour_name": meta["colour_name"],
        "gender": meta["gender"],
        "family": meta["family"],
        "subfamily": meta["subfamily"],
        "season": meta["season"],
        "image_url": meta["image_url"],
        "run_date": run_date,
        "generated_on": date.today().isoformat(),
        "fx_asof": fx_asof,
        "fx_source": f"open.er-api.com — market (spot) rates, {ccy_disp} base",
        "zara_search_term": search_term,
        "currency": ccy_disp, "symbol": symbol,
        "base_country": base_cc, "base_name": common.country_name(base_cc), "base_value": base_val,
        "ref_country": ref_cc, "ref_name": common.country_name(ref_cc), "ref_value": ref_val,
        "n_countries": len(countries),
        "min": round(min(vals), 2), "max": round(max(vals), 2),
        "avg": round(statistics.mean(vals), 2),
        "median": round(statistics.median(vals), 2),
        "spread_pct": round((max(vals) / min(vals) - 1) * 100, 1),
        "cheapest": {"cc": cheapest["cc"], "name": cheapest["name"], "value": cheapest["value"]},
        "dearest": {"cc": dearest["cc"], "name": dearest["name"], "value": dearest["value"]},
        "skipped_no_fx": skipped,
        "currency_corrections": corrected,
        "price_basis": "RRP (list price; current discounts ignored)",
        "stack_params": stack_params,
    }

    data = {"meta": summary, "countries": countries}
    out_dir = common.OUTPUT_DIR / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (common.OUTPUT_DIR / "latest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[index] {meta['name']} ({ref}) — run_date {run_date} — priced in {ccy_disp}")
    print(f"[index] {len(countries)} countries  "
          f"(min {symbol}{summary['min']} {cheapest['name']} · max {symbol}{summary['max']} {dearest['name']} · "
          f"spread {summary['spread_pct']}% · {base_cc.upper()} anchor {symbol}{base_val})")
    if corrected:
        print(f"[index] currency corrections: {', '.join(corrected)}")
    if skipped:
        print(f"[index] skipped (no FX): {', '.join(skipped)}")
    print(f"[index] wrote {out_dir / 'data.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
