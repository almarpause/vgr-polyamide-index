"""Polyamide Index — export the tiny web snapshot.

The interactive web build runs in the cloud (GitHub Actions) where the parser's
1 GB master.sqlite does not exist. This script distils the one thing the cloud
needs — the latest per-country LOCAL prices for the tracked reference plus the
product's metadata — into a small, committable JSON file (web/snapshot_local.json,
~65 rows). The cloud reads that + fetches live FX daily.

Run this locally whenever the weekly Zara scrape refreshes prices (then commit +
push, see web_update.bat). The FX is NOT stored here — the cloud pulls spot rates
itself so the web index moves daily even though prices refresh weekly.

    python export_snapshot.py                 # latest run with the reference
    python export_snapshot.py --run-date 2026-08-10
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

import build_index
import common

WEB_DIR = common.ROOT / "web"
SNAPSHOT = WEB_DIR / "snapshot_local.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="export_snapshot")
    ap.add_argument("--run-date", default=None)
    a = ap.parse_args(argv)

    cfg = common.load_settings()
    ref = cfg["reference"]
    db = Path(cfg["zara_db"])
    if not db.exists():
        raise SystemExit(f"[export] Zara DB not found: {db} (run this on the machine with the parser)")

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cur = con.cursor()
    run_date = a.run_date or build_index.latest_run_with_ref(cur, ref)
    if not run_date:
        raise SystemExit(f"[export] no in-stock snapshots for {ref!r}")
    meta = build_index.product_meta(cur, ref)
    snaps = build_index.snapshots(cur, ref, run_date)   # already RRP-based
    con.close()

    payload = {
        "reference": ref,
        "style": meta["style"],
        "run_date": run_date,
        "exported_on": date.today().isoformat(),
        "product": {k: meta[k] for k in
                    ("colour_name", "gender", "family", "subfamily", "season", "name", "image_url")},
        "rows": [{"cc": s["cc"], "currency": s["currency"], "rrp": s["price_local"]} for s in snaps],
    }
    WEB_DIR.mkdir(exist_ok=True)
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[export] {meta['name']} ({ref}) run_date {run_date}: {len(payload['rows'])} markets -> {SNAPSHOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
